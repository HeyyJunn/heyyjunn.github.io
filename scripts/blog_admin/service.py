from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote

import yaml

from velog_sync.config import SyncConfig, load_config
from velog_sync.models import SourceError, SyncOutcome, VelogSyncError
from velog_sync.state import load_state
from velog_sync.sync import SyncEngine, SyncResult, canonical_url, validate_post_path


ACTION_LABELS = {
    "IMPORT": "새로 등록 예정",
    "UPDATE": "수정 예정",
    "UNCHANGED": "최신 상태",
    "EXCLUDED": "가져오지 않음",
    "HIDDEN": "GitHub에서 숨김",
    "ERROR": "오류",
}


class UserInputError(VelogSyncError):
    """An invalid selection or setting supplied by the local user."""


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    title: str
    summary: str
    output: str = ""


def _run(argv: list[str], root: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def read_raw(self) -> dict[str, Any]:
        try:
            value = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise UserInputError(f"설정 파일을 읽을 수 없습니다: {exc}") from exc
        if not isinstance(value, dict):
            raise UserInputError("설정 파일의 최상위 값은 객체여야 합니다.")
        return value

    def update(self, mutator: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            value = self.read_raw()
            mutator(value)
            rendered = yaml.safe_dump(
                value,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=self.path.name + ".", suffix=".part", dir=self.path.parent
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(rendered)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Validate the complete temporary file before replacing the original.
                load_config(Path(temporary))
                os.replace(temporary, self.path)
            except Exception:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                raise


class BlogService:
    def __init__(
        self,
        root: Path,
        engine_factory: Callable[[Path, SyncConfig], SyncEngine] | None = None,
    ):
        self.root = root.resolve()
        self.config_path = self.root / ".velog-sync" / "config.yml"
        self.state_path = self.root / ".velog-sync" / "state.json"
        self.store = ConfigStore(self.config_path)
        self.engine_factory = engine_factory or (lambda root, cfg: SyncEngine(root, cfg))
        self._preview_cache: SyncResult | None = None
        self._cache_lock = threading.Lock()
        self._serve_process: subprocess.Popen[str] | None = None

    def config(self) -> SyncConfig:
        return load_config(self.config_path)

    def invalidate(self) -> None:
        with self._cache_lock:
            self._preview_cache = None

    def preview(self, force: bool = False) -> SyncResult:
        with self._cache_lock:
            if self._preview_cache is not None and not force:
                return self._preview_cache
        cfg = self.config()
        result = self.engine_factory(self.root, cfg).run(dry_run=True)
        with self._cache_lock:
            self._preview_cache = result
        return result

    def apply(self) -> SyncResult:
        result = self.engine_factory(self.root, self.config()).run(dry_run=False)
        self.invalidate()
        return result

    @staticmethod
    def warning_text(warning: str) -> str:
        if "unclosed code fence" in warning:
            return (
                "원본 Markdown에서 닫히지 않은 코드 블록이 발견되었습니다. "
                "자동으로 수정하지 않았습니다. 현재 Jekyll 빌드는 성공하지만 "
                "이후 내용이 코드 블록으로 표시될 수 있습니다."
            )
        if "image" in warning.lower():
            return "일부 이미지를 로컬에 저장하지 못해 원격 주소를 유지합니다."
        if "RSS" in warning:
            return "최근 글 확인용 RSS 연결을 확인해 주세요."
        return "원문 호환성을 확인해야 하는 항목이 있습니다."

    def post_view(self, outcome: SyncOutcome, number: int) -> dict[str, Any]:
        item = outcome.post
        source_url = canonical_url(self.config().username, item.slug)
        github_url = None
        if outcome.post_path and (self.root / outcome.post_path).is_file() and outcome.action != "HIDDEN":
            stem = Path(outcome.post_path).stem
            post_slug = stem[11:] if len(stem) > 11 else stem
            github_url = f"https://heyyjunn.github.io/posts/{quote(post_slug)}/"
        warnings = [self.warning_text(value) for value in outcome.warnings]
        return {
            "number": number,
            "id": item.id,
            "title": item.title.strip(),
            "slug": item.slug,
            "source_url": source_url,
            "github_url": github_url,
            "series": item.series.name if item.series else None,
            "categories": list(outcome.categories),
            "published_at": item.released_at,
            "updated_at": item.updated_at,
            "post_path": outcome.post_path,
            "image_count": outcome.image_count,
            "action": outcome.action,
            "status": ACTION_LABELS[outcome.action],
            "attention": bool(warnings),
            "warnings": warnings,
            "error": outcome.error,
        }

    def snapshot(self, force: bool = False) -> dict[str, Any]:
        result = self.preview(force=force)
        posts = [self.post_view(outcome, index) for index, outcome in enumerate(result.outcomes, 1)]
        counts = {ACTION_LABELS[key]: result.counts[key] for key in ACTION_LABELS}
        state = load_state(self.state_path)
        published = sum(
            1
            for ident, entry in state["posts"].items()
            if ident.lower() not in self.config().hidden_post_ids
            and isinstance(entry, dict)
            and isinstance(entry.get("post_path"), str)
            and (self.root / entry["post_path"]).is_file()
        )
        return {
            "posts": posts,
            "counts": counts,
            "total": len(posts),
            "published": published,
            "warnings": result.warning_count,
            "images": result.image_count,
            "image_bytes": result.image_bytes,
            "page_sizes": list(result.page_sizes),
            "inventory_complete": result.inventory_complete,
            "rss_count": result.rss_count,
            "initial_import": not bool(state["posts"]),
            "git": self.git_status(),
            "github": self.github_status(),
        }

    def _resolve(self, values: Iterable[str], result: SyncResult | None = None) -> list[SyncOutcome]:
        outcomes = list((result or self.preview()).outcomes)
        selected: list[SyncOutcome] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw).strip()
            matches: list[SyncOutcome] = []
            if value.isdigit():
                number = int(value)
                if 1 <= number <= len(outcomes):
                    matches = [outcomes[number - 1]]
            else:
                try:
                    normalized = str(uuid.UUID(value))
                except ValueError:
                    normalized = ""
                if normalized:
                    matches = [item for item in outcomes if item.post.id.lower() == normalized]
                else:
                    matches = [item for item in outcomes if item.post.slug == value]
            if len(matches) != 1:
                raise UserInputError(f"게시물을 찾을 수 없습니다: {value}")
            item = matches[0]
            if item.post.id not in seen:
                selected.append(item)
                seen.add(item.post.id)
        if not selected:
            raise UserInputError("선택한 게시물이 없습니다.")
        return selected

    def resolve_ids(self, values: Iterable[str]) -> list[SyncOutcome]:
        return self._resolve(values)

    def _update_id_list(self, key: str, ids: Iterable[str], add: bool) -> None:
        normalized = {str(uuid.UUID(value)).lower() for value in ids}

        def mutate(raw: dict[str, Any]) -> None:
            current_raw = raw.get(key, [])
            if not isinstance(current_raw, list):
                raise UserInputError(f"{key} 설정은 목록이어야 합니다.")
            current = {str(uuid.UUID(str(value))).lower() for value in current_raw}
            current = current | normalized if add else current - normalized
            raw[key] = sorted(current)

        self.store.update(mutate)
        self.invalidate()

    def exclude(self, values: Iterable[str], add: bool) -> list[SyncOutcome]:
        selected = self._resolve(values)
        self._update_id_list("exclude_post_ids", (item.post.id for item in selected), add)
        return selected

    def hide(self, values: Iterable[str]) -> list[SyncOutcome]:
        selected = self._resolve(values)
        state = load_state(self.state_path)
        unmanaged = [item.post.title.strip() for item in selected if item.post.id not in state["posts"]]
        if unmanaged:
            raise UserInputError(
                "아직 GitHub에 게시하지 않은 글은 '가져오지 않기'를 사용해 주세요: "
                + ", ".join(unmanaged)
            )
        self._update_id_list("hidden_post_ids", (item.post.id for item in selected), True)
        for item in selected:
            entry = state["posts"].get(item.post.id)
            if isinstance(entry, dict) and isinstance(entry.get("post_path"), str):
                path = validate_post_path(self.root, entry["post_path"])
                if path.is_file():
                    path.unlink()
        self.invalidate()
        return selected

    def unhide(self, values: Iterable[str]) -> list[SyncOutcome]:
        selected = self._resolve(values)
        self._update_id_list("hidden_post_ids", (item.post.id for item in selected), False)
        return selected

    def save_settings(
        self,
        username: str,
        import_after: str | None,
        mapping: dict[str, list[str]],
    ) -> None:
        username = username.strip().lstrip("@")
        if not username or any(char.isspace() for char in username):
            raise UserInputError("Velog 사용자명을 확인해 주세요.")
        if import_after:
            try:
                datetime.strptime(import_after, "%Y-%m-%d")
            except ValueError as exc:
                raise UserInputError("자동 가져오기 기준일은 YYYY-MM-DD 형식이어야 합니다.") from exc
        cleaned: dict[str, list[str]] = {}
        for series, categories in mapping.items():
            series = series.strip()
            values = [str(value).strip() for value in categories if str(value).strip()]
            if not series or not 1 <= len(values) <= 2:
                raise UserInputError("시리즈 매핑에는 한 개 또는 두 개의 카테고리가 필요합니다.")
            cleaned[series] = values

        def mutate(raw: dict[str, Any]) -> None:
            velog = raw.setdefault("velog", {})
            if not isinstance(velog, dict):
                raise UserInputError("velog 설정이 올바르지 않습니다.")
            velog["username"] = username
            velog["rss_url"] = f"https://v2.velog.io/rss/@{username}"
            raw["import_after"] = import_after or None
            raw["series_category_map"] = cleaned

        self.store.update(mutate)
        self.invalidate()

    def git_status(self) -> dict[str, Any]:
        branch = _run(["git", "branch", "--show-current"], self.root)
        status = _run(["git", "status", "--porcelain"], self.root)
        return {
            "branch": branch.stdout.strip() or "확인할 수 없음",
            "dirty": bool(status.stdout.strip()),
            "label": "변경 있음" if status.stdout.strip() else "변경 없음",
        }

    def github_status(self) -> dict[str, Any]:
        gh = shutil.which("gh")
        if not gh:
            return {"available": False, "message": "GitHub CLI가 설치되어 있지 않습니다."}
        auth = _run([gh, "auth", "status"], self.root)
        if auth.returncode != 0:
            return {"available": False, "message": "GitHub CLI에 로그인되어 있지 않습니다."}
        variable = _run([gh, "variable", "get", "VELOG_SYNC_ENABLED"], self.root)
        recent = _run(
            [gh, "run", "list", "--workflow", "pages-deploy.yml", "--limit", "1", "--json", "status,conclusion,name,createdAt,url"],
            self.root,
        )
        run = None
        if recent.returncode == 0:
            try:
                values = json.loads(recent.stdout)
                run = values[0] if values else None
            except json.JSONDecodeError:
                pass
        return {
            "available": True,
            "message": "GitHub Actions를 사용할 수 있습니다.",
            "automatic": variable.stdout.strip() == "true" if variable.returncode == 0 else None,
            "recent": run,
        }

    def remote_workflow(self, mode: str) -> CommandResult:
        if mode not in {"dry-run", "apply"}:
            raise UserInputError("지원하지 않는 원격 작업입니다.")
        status = self.github_status()
        if not status["available"]:
            return CommandResult(False, "원격 작업을 시작할 수 없습니다", status["message"])
        result = _run(
            ["gh", "workflow", "run", "pages-deploy.yml", "--ref", "main", "-f", f"mode={mode}"],
            self.root,
        )
        title = "GitHub Actions 작업을 요청했습니다" if result.returncode == 0 else "GitHub Actions 요청 실패"
        summary = "Actions 화면에서 진행 상황을 확인할 수 있습니다." if result.returncode == 0 else "자세한 로그를 확인해 주세요."
        return CommandResult(result.returncode == 0, title, summary, result.stdout)

    def _ruby_environment(self) -> tuple[list[str], dict[str, str]]:
        candidates = [
            Path("/opt/homebrew/opt/ruby@3.4/bin/bundle"),
            Path("/usr/local/opt/ruby@3.4/bin/bundle"),
        ]
        bundle = next((str(value) for value in candidates if value.is_file()), shutil.which("bundle"))
        if not bundle:
            raise UserInputError("Bundler를 찾을 수 없습니다. Ruby 3.4 설치를 확인해 주세요.")
        env = os.environ.copy()
        env.pop("DEBUG", None)
        bundle_dir = str(Path(bundle).parent)
        env["PATH"] = bundle_dir + os.pathsep + env.get("PATH", "")
        env["BUNDLE_PATH"] = str(self.root / ".bundle-blog")
        return [bundle], env

    def _ensure_bundle(self) -> tuple[list[str], dict[str, str], str]:
        bundle, env = self._ruby_environment()
        checked = _run(bundle + ["check"], self.root, env)
        output = checked.stdout
        if checked.returncode != 0:
            installed = _run(bundle + ["install"], self.root, env)
            output += installed.stdout
            if installed.returncode != 0:
                raise UserInputError("Ruby 패키지 설치에 실패했습니다.\n" + output)
        return bundle, env, output

    def run_tests(self) -> CommandResult:
        result = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], self.root)
        return CommandResult(result.returncode == 0, "Python 테스트 완료" if result.returncode == 0 else "Python 테스트 실패", "모든 테스트를 통과했습니다." if result.returncode == 0 else "실패한 테스트를 확인해 주세요.", result.stdout)

    def build(self) -> CommandResult:
        bundle, env, setup = self._ensure_bundle()
        result = _run(bundle + ["exec", "jekyll", "build", "-d", "_site"], self.root, env)
        return CommandResult(result.returncode == 0, "GitHub Pages 빌드 완료" if result.returncode == 0 else "GitHub Pages 빌드 실패", "사이트 파일을 정상적으로 생성했습니다." if result.returncode == 0 else "빌드 로그를 확인해 주세요.", setup + result.stdout)

    def html_check(self) -> CommandResult:
        bundle, env, setup = self._ensure_bundle()
        result = _run(
            bundle
            + [
                "exec",
                "htmlproofer",
                "_site",
                "--disable-external",
                "--ignore-urls",
                "/^http://127.0.0.1/,/^http://0.0.0.0/,/^http://localhost/",
            ],
            self.root,
            env,
        )
        return CommandResult(result.returncode == 0, "HTML 검사 완료" if result.returncode == 0 else "HTML 검사 실패", "생성된 페이지에 문제가 없습니다." if result.returncode == 0 else "검사 로그를 확인해 주세요.", setup + result.stdout)

    def check(self, progress: Callable[[str], None] | None = None) -> CommandResult:
        logs: list[str] = []
        stages = (
            ("[1/4] Python 테스트 실행 중", self.run_tests),
            ("[2/4] Velog 변경 사항 확인 중", lambda: self.dry_run_result()),
            ("[3/4] GitHub Pages 빌드 중", self.build),
            ("[4/4] 생성된 HTML 검사 중", self.html_check),
        )
        for label, operation in stages:
            if progress:
                progress(label)
            result = operation()
            logs.append(f"{label}\n{result.output}")
            if not result.ok:
                return CommandResult(False, "검사 실패", f"{label.replace(' 중', '')} 단계에서 문제가 발생했습니다.", "\n".join(logs))
        return CommandResult(True, "전체 검사 완료", "모든 검사를 통과했습니다.", "\n".join(logs))

    def dry_run_result(self) -> CommandResult:
        try:
            snapshot = self.snapshot(force=True)
        except VelogSyncError as exc:
            return CommandResult(False, "변경 사항 확인 실패", "Velog 게시물 목록을 가져오는 데 실패했습니다. 기존 GitHub 게시물은 변경하지 않았습니다.", str(exc))
        counts = snapshot["counts"]
        lines = [f"{label}: {counts[label]}개" for label in ACTION_LABELS.values()]
        lines.append(f"확인 필요: {snapshot['warnings']}개")
        errors = [
            f"{item['number']}. {item['title']}: {item['error']}"
            for item in snapshot["posts"]
            if item["error"]
        ]
        if errors:
            lines.extend(("", "자세한 오류", *errors))
            return CommandResult(
                False,
                "변경 사항 확인 실패",
                "일부 Velog 원문을 가져오지 못했습니다. 실제 파일은 변경되지 않았습니다.",
                "\n".join(lines),
            )
        return CommandResult(
            True,
            "동기화 미리보기 완료",
            "실제 파일은 변경되지 않았습니다.",
            "\n".join(lines),
        )

    def start_serve(self) -> CommandResult:
        if self._serve_process is not None and self._serve_process.poll() is None:
            return CommandResult(True, "로컬 블로그가 이미 실행 중입니다", "http://127.0.0.1:4000")
        bundle, env, setup = self._ensure_bundle()
        self._serve_process = subprocess.Popen(
            bundle + ["exec", "jekyll", "serve", "--host", "127.0.0.1", "--port", "4000"],
            cwd=self.root,
            env=env,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return CommandResult(True, "로컬 블로그를 실행했습니다", "http://127.0.0.1:4000", setup)
