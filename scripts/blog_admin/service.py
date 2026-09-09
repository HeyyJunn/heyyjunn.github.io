from __future__ import annotations

import hashlib
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
from velog_sync.images import (
    SAFE_UPLOAD_MIME_EXTENSIONS,
    detect_image_content_type,
    override_source_file,
    remove_post_images,
)
from velog_sync.models import SyncOutcome, VelogSyncError
from velog_sync.state import load_state
from velog_sync.sync import SyncEngine, SyncResult, canonical_url, normalize_url, validate_post_path


ACTION_LABELS = {
    "IMPORT": "새로 등록 예정",
    "UPDATE": "수정 예정",
    "UNCHANGED": "최신 상태",
    "EXCLUDED": "가져오지 않음",
    "HIDDEN": "GitHub에서 숨김",
    "ERROR": "오류",
}

PUBLISH_PATHS = (
    ".velog-sync/config.yml",
    ".velog-sync/state.json",
    ".velog-sync/thumbnail-overrides",
    "_posts",
    "assets/img/velog",
)


def _is_publish_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return (
        normalized in {".velog-sync/config.yml", ".velog-sync/state.json"}
        or normalized.startswith(".velog-sync/thumbnail-overrides/")
        or normalized.startswith("_posts/")
        or normalized.startswith("assets/img/velog/")
    )


def _status_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.rsplit(" -> ", 1)[1]
        paths.append(value.strip('"'))
    return sorted(set(paths))


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
        enforce_git_safety: bool = True,
    ):
        self.root = root.resolve()
        self.config_path = self.root / ".velog-sync" / "config.yml"
        self.state_path = self.root / ".velog-sync" / "state.json"
        self.store = ConfigStore(self.config_path)
        self.engine_factory = engine_factory or (lambda root, cfg: SyncEngine(root, cfg))
        self.enforce_git_safety = enforce_git_safety
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
        self._ensure_write_safe()
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

    def post_view(
        self,
        outcome: SyncOutcome,
        number: int,
        cfg: SyncConfig,
        state_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        item = outcome.post
        source_url = canonical_url(cfg.username, item.slug)
        github_url = None
        if outcome.post_path and (self.root / outcome.post_path).is_file() and outcome.action != "HIDDEN":
            stem = Path(outcome.post_path).stem
            post_slug = stem[11:] if len(stem) > 11 else stem
            github_url = f"https://heyyjunn.github.io/posts/{quote(post_slug)}/"
        warnings = [self.warning_text(value) for value in outcome.warnings]
        override = cfg.thumbnail_overrides.get(item.id.lower())
        resolved = outcome.thumbnail
        if (
            resolved is None
            and outcome.thumbnail_change != "removed"
            and isinstance(state_entry, dict)
        ):
            resolved = state_entry.get("thumbnail")
        if item.thumbnail:
            thumbnail_source = "velog"
            preview_url = item.thumbnail
        elif override is not None:
            thumbnail_source = "override"
            preview_url = f"/api/posts/{item.id}/thumbnail-override"
        else:
            thumbnail_source = "none"
            preview_url = None
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
            "thumbnail_source": thumbnail_source,
            "thumbnail_preview_url": preview_url,
            "velog_thumbnail_url": item.thumbnail,
            "thumbnail_path": resolved.get("path") if isinstance(resolved, dict) else None,
            "thumbnail_override_exists": override is not None,
            "thumbnail_editable": item.thumbnail is None,
            "thumbnail_change": outcome.thumbnail_change,
        }

    def snapshot(self, force: bool = False) -> dict[str, Any]:
        result = self.preview(force=force)
        cfg = self.config()
        state = load_state(self.state_path)
        posts = [
            self.post_view(
                outcome,
                index,
                cfg,
                state["posts"].get(outcome.post.id),
            )
            for index, outcome in enumerate(result.outcomes, 1)
        ]
        counts = {ACTION_LABELS[key]: result.counts[key] for key in ACTION_LABELS}
        published = sum(
            1
            for ident, entry in state["posts"].items()
            if ident.lower() not in cfg.hidden_post_ids
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
            "thumbnail_changes": {
                key: sum(
                    1
                    for item in result.outcomes
                    if item.action not in {"HIDDEN", "EXCLUDED", "ERROR"}
                    and item.thumbnail_change == key
                )
                for key in ("added", "changed", "removed", "none", "unchanged")
            },
            "git": self.git_status(fetch=self.enforce_git_safety),
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
                    if not matches and value.startswith(("https://", "http://")):
                        wanted = normalize_url(value)
                        username = self.config().username
                        matches = [
                            item
                            for item in outcomes
                            if normalize_url(canonical_url(username, item.post.slug)) == wanted
                        ]
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
        self._ensure_write_safe()
        selected = self._resolve(values)
        self._update_id_list("exclude_post_ids", (item.post.id for item in selected), add)
        return selected

    def hide(self, values: Iterable[str]) -> list[SyncOutcome]:
        self._ensure_write_safe()
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
            remove_post_images(self.root, item.post.id)
        self.invalidate()
        return selected

    def unhide(self, values: Iterable[str]) -> list[SyncOutcome]:
        self._ensure_write_safe()
        selected = self._resolve(values)
        self._update_id_list("hidden_post_ids", (item.post.id for item in selected), False)
        return selected

    def save_settings(
        self,
        import_after: str | None,
        mapping: dict[str, list[str]],
    ) -> None:
        self._ensure_write_safe()
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
            raw["import_after"] = import_after or None
            raw["series_category_map"] = cleaned

        self.store.update(mutate)
        self.invalidate()

    def set_thumbnail_override(
        self, post_id: str, data: bytes, claimed_content_type: str | None
    ) -> str:
        self._ensure_write_safe()
        try:
            normalized = str(uuid.UUID(post_id))
        except ValueError as exc:
            raise UserInputError("올바른 게시물 UUID가 아닙니다.") from exc
        if normalized != post_id.lower():
            raise UserInputError("게시물 UUID는 표준 형식이어야 합니다.")
        selected = self._resolve([normalized])
        item = selected[0].post
        if item.thumbnail:
            raise UserInputError(
                "Velog에 미리보기 이미지가 설정되어 있어 해당 이미지가 우선 적용됩니다."
            )
        cfg = self.config()
        if not data or len(data) > cfg.images.max_bytes:
            raise UserInputError(
                f"이미지는 1바이트 이상 {cfg.images.max_bytes // (1024 * 1024)}MB 이하여야 합니다."
            )
        detected = detect_image_content_type(data)
        if detected not in SAFE_UPLOAD_MIME_EXTENSIONS:
            raise UserInputError("PNG, JPEG, GIF, WebP 또는 AVIF 이미지 파일만 사용할 수 있습니다.")
        claimed = (claimed_content_type or "").split(";", 1)[0].lower()
        if claimed not in {"", "application/octet-stream", detected}:
            raise UserInputError("파일 내용과 브라우저가 보낸 이미지 MIME 형식이 일치하지 않습니다.")

        digest = hashlib.sha256(data).hexdigest()
        extension = SAFE_UPLOAD_MIME_EXTENSIONS[detected]
        source_path = (
            Path(".velog-sync") / "thumbnail-overrides" / normalized / f"{digest}{extension}"
        ).as_posix()
        target = override_source_file(self.root, normalized, source_path)
        old = cfg.thumbnail_overrides.get(normalized)
        old_path = old.source_path if old else None
        existed = target.is_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".part", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)

            def mutate(raw: dict[str, Any]) -> None:
                overrides = raw.setdefault("thumbnail_overrides", {})
                if not isinstance(overrides, dict):
                    raise UserInputError("thumbnail_overrides 설정은 객체여야 합니다.")
                overrides[normalized] = {"source_path": source_path}

            self.store.update(mutate)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            if not existed:
                target.unlink(missing_ok=True)
            raise

        if old_path and old_path != source_path:
            old_file = override_source_file(self.root, normalized, old_path)
            old_file.unlink(missing_ok=True)
        self.invalidate()
        return source_path

    def remove_thumbnail_override(self, post_id: str) -> bool:
        self._ensure_write_safe()
        try:
            normalized = str(uuid.UUID(post_id))
        except ValueError as exc:
            raise UserInputError("올바른 게시물 UUID가 아닙니다.") from exc
        if normalized != post_id.lower():
            raise UserInputError("게시물 UUID는 표준 형식이어야 합니다.")
        self._resolve([normalized])
        cfg = self.config()
        override = cfg.thumbnail_overrides.get(normalized)
        if override is None:
            return False

        def mutate(raw: dict[str, Any]) -> None:
            overrides = raw.get("thumbnail_overrides", {})
            if isinstance(overrides, dict):
                overrides.pop(normalized, None)
                if not overrides:
                    raw.pop("thumbnail_overrides", None)

        self.store.update(mutate)
        source = override_source_file(self.root, normalized, override.source_path)
        source.unlink(missing_ok=True)
        try:
            source.parent.rmdir()
        except OSError:
            pass
        self.invalidate()
        return True

    def thumbnail_override_file(self, post_id: str) -> tuple[Path, str]:
        try:
            normalized = str(uuid.UUID(post_id))
        except ValueError as exc:
            raise UserInputError("올바른 게시물 UUID가 아닙니다.") from exc
        if normalized != post_id.lower():
            raise UserInputError("게시물 UUID는 표준 형식이어야 합니다.")
        override = self.config().thumbnail_overrides.get(normalized)
        if override is None:
            raise UserInputError("직접 지정한 미리보기 이미지가 없습니다.")
        source = override_source_file(self.root, normalized, override.source_path)
        if not source.is_file():
            raise UserInputError("직접 지정한 미리보기 이미지 파일을 찾을 수 없습니다.")
        if source.stat().st_size <= 0 or source.stat().st_size > self.config().images.max_bytes:
            raise UserInputError("저장된 미리보기 이미지의 크기가 허용 범위를 벗어났습니다.")
        content_type = detect_image_content_type(source.read_bytes())
        if content_type not in SAFE_UPLOAD_MIME_EXTENSIONS:
            raise UserInputError("저장된 미리보기 이미지 형식이 올바르지 않습니다.")
        return source, content_type

    def git_status(self, fetch: bool = False) -> dict[str, Any]:
        """Describe local/main versus origin/main without modifying user work."""

        inside = _run(["git", "rev-parse", "--is-inside-work-tree"], self.root)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return {
                "repository": False,
                "branch": "확인할 수 없음",
                "dirty": False,
                "changes": [],
                "managed_changes": [],
                "unrelated_changes": [],
                "ahead_paths": [],
                "unrelated_ahead_paths": [],
                "relation": "unavailable",
                "label": "Git 저장소가 아닙니다",
                "message": "현재 폴더는 Git 저장소가 아닙니다.",
                "fetch_ok": False,
                "can_pull": False,
                "can_publish": False,
                "ahead": 0,
                "behind": 0,
            }

        branch_result = _run(["git", "branch", "--show-current"], self.root)
        branch = branch_result.stdout.strip() or "확인할 수 없음"
        raw_status = _run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], self.root
        )
        changes = _status_paths(raw_status.stdout)
        managed = [path for path in changes if _is_publish_path(path)]
        unrelated = [path for path in changes if not _is_publish_path(path)]

        fetch_ok = not fetch
        fetch_error = ""
        if fetch:
            fetched = _run(["git", "fetch", "--prune", "origin", "main"], self.root)
            fetch_ok = fetched.returncode == 0
            if not fetch_ok:
                fetch_error = fetched.stdout.strip() or "origin/main을 가져오지 못했습니다."

        head = _run(["git", "rev-parse", "HEAD"], self.root)
        remote = _run(["git", "rev-parse", "--verify", "refs/remotes/origin/main"], self.root)
        relation = "unavailable"
        ahead = behind = 0
        ahead_paths: list[str] = []
        if head.returncode == 0 and remote.returncode == 0:
            counts = _run(
                ["git", "rev-list", "--left-right", "--count", "HEAD...refs/remotes/origin/main"],
                self.root,
            )
            if counts.returncode == 0:
                try:
                    ahead, behind = (int(value) for value in counts.stdout.split())
                except (TypeError, ValueError):
                    ahead = behind = 0
                if ahead == 0 and behind == 0:
                    relation = "current"
                elif ahead > 0 and behind == 0:
                    relation = "ahead"
                elif behind > 0 and ahead == 0:
                    relation = "behind"
                else:
                    relation = "diverged"
        if relation == "ahead":
            committed = _run(
                ["git", "diff", "--name-only", "refs/remotes/origin/main..HEAD"], self.root
            )
            if committed.returncode == 0:
                ahead_paths = sorted(set(committed.stdout.splitlines()))
        unrelated_ahead = [path for path in ahead_paths if not _is_publish_path(path)]

        labels = {
            "current": "GitHub와 최신 상태",
            "ahead": "로컬에만 변경 있음",
            "behind": "GitHub에 더 최신 변경 있음",
            "diverged": "로컬과 GitHub 이력이 갈라짐",
            "unavailable": "GitHub 상태를 확인할 수 없음",
        }
        messages = {
            "current": "로컬 커밋과 origin/main이 같습니다.",
            "ahead": f"로컬에 아직 push하지 않은 커밋이 {ahead}개 있습니다.",
            "behind": f"GitHub에 먼저 받아야 할 커밋이 {behind}개 있습니다.",
            "diverged": "자동으로 merge/reset하지 않습니다. 이력을 직접 검토해야 합니다.",
            "unavailable": "origin/main 비교 기준을 찾지 못했습니다.",
        }
        if branch != "main":
            messages[relation] = f"현재 브랜치는 {branch}입니다. 관리 작업은 main에서만 허용됩니다."
        if fetch and not fetch_ok:
            messages[relation] = "GitHub 최신 상태를 확인하지 못했습니다. 네트워크 연결 후 다시 시도해 주세요."

        safe_relation = relation in {"current", "ahead"}
        return {
            "repository": True,
            "branch": branch,
            "dirty": bool(changes),
            "changes": changes,
            "managed_changes": managed,
            "unrelated_changes": unrelated,
            "ahead_paths": ahead_paths,
            "unrelated_ahead_paths": unrelated_ahead,
            "relation": relation,
            "label": labels[relation],
            "message": messages[relation],
            "fetch_ok": fetch_ok,
            "fetch_error": fetch_error,
            "can_pull": fetch_ok and branch == "main" and relation == "behind" and not changes,
            "can_publish": (
                fetch_ok
                and branch == "main"
                and safe_relation
                and not unrelated
                and not unrelated_ahead
                and (bool(managed) or relation == "ahead")
            ),
            "ahead": ahead,
            "behind": behind,
        }

    def _ensure_write_safe(self) -> dict[str, Any] | None:
        if not self.enforce_git_safety:
            return None
        status = self.git_status(fetch=True)
        if not status["repository"]:
            raise UserInputError(status["message"])
        if not status["fetch_ok"]:
            raise UserInputError(
                "GitHub 최신 상태를 확인하지 못해 쓰기 작업을 중단했습니다. "
                "네트워크 연결을 확인해 주세요."
            )
        if status["branch"] != "main":
            raise UserInputError("블로그 관리 쓰기 작업은 main 브랜치에서만 실행할 수 있습니다.")
        if status["relation"] == "behind":
            raise UserInputError(
                "GitHub에 더 최신 변경 사항이 있습니다. 먼저 '최신 상태 가져오기'를 실행해 주세요."
            )
        if status["relation"] == "diverged":
            raise UserInputError(
                "로컬과 GitHub 이력이 갈라져 자동으로 처리할 수 없습니다. merge/reset 없이 이력을 직접 검토해 주세요."
            )
        if status["relation"] not in {"current", "ahead"}:
            raise UserInputError("origin/main과 안전하게 비교하지 못해 쓰기 작업을 중단했습니다.")
        return status

    def pull_ff_only(self) -> CommandResult:
        status = self.git_status(fetch=True)
        if not status["repository"] or not status["fetch_ok"]:
            return CommandResult(False, "최신 상태를 가져올 수 없습니다", status["message"])
        if status["branch"] != "main":
            return CommandResult(False, "최신 상태를 가져올 수 없습니다", "main 브랜치에서만 실행할 수 있습니다.")
        if status["dirty"]:
            return CommandResult(
                False,
                "최신 상태를 가져올 수 없습니다",
                "로컬 변경 사항을 먼저 검토해 주세요. 자동 stash나 reset은 실행하지 않습니다.",
                "\n".join(status["changes"]),
            )
        if status["relation"] == "current":
            return CommandResult(True, "이미 최신 상태입니다", "로컬과 origin/main이 같습니다.")
        if status["relation"] != "behind":
            return CommandResult(False, "자동으로 가져올 수 없습니다", status["message"])
        result = _run(["git", "pull", "--ff-only", "origin", "main"], self.root)
        return CommandResult(
            result.returncode == 0,
            "최신 상태를 가져왔습니다" if result.returncode == 0 else "최신 상태 가져오기 실패",
            "origin/main을 fast-forward 방식으로 반영했습니다."
            if result.returncode == 0
            else "자동 merge/reset 없이 중단했습니다.",
            result.stdout,
        )

    def publish(self, progress: Callable[[str], None] | None = None) -> CommandResult:
        status = self.git_status(fetch=True)
        if not status["repository"] or not status["fetch_ok"]:
            return CommandResult(False, "GitHub에 반영할 수 없습니다", status["message"])
        if status["branch"] != "main" or status["relation"] not in {"current", "ahead"}:
            return CommandResult(False, "GitHub에 반영할 수 없습니다", status["message"])
        if status["unrelated_changes"]:
            return CommandResult(
                False,
                "자동으로 반영할 수 없는 다른 변경 사항이 있습니다",
                "관리 대상이 아닌 파일은 자동 stage하지 않습니다. 별도로 검토해 주세요.",
                "\n".join(status["unrelated_changes"]),
            )
        if status["unrelated_ahead_paths"]:
            return CommandResult(
                False,
                "자동으로 push할 수 없는 로컬 commit이 있습니다",
                "origin/main 이후 commit에 블로그 관리 대상이 아닌 파일이 포함되어 있습니다.",
                "\n".join(status["unrelated_ahead_paths"]),
            )
        if not status["managed_changes"] and status["relation"] != "ahead":
            return CommandResult(True, "반영할 변경 사항이 없습니다", "로컬과 GitHub가 이미 같습니다.")

        if progress:
            progress("게시 전 테스트와 사이트 검사를 실행하고 있습니다")
        checked = self.check()
        if not checked.ok:
            return CommandResult(
                False,
                "검사 실패로 GitHub 반영을 중단했습니다",
                "commit과 push를 실행하지 않았습니다.",
                checked.output,
            )

        if progress:
            progress("GitHub 최신 상태를 다시 확인하고 있습니다")
        ready = self.git_status(fetch=True)
        if (
            not ready["fetch_ok"]
            or ready["branch"] != "main"
            or ready["relation"] not in {"current", "ahead"}
        ):
            return CommandResult(False, "GitHub 반영을 안전하게 중단했습니다", ready["message"])
        if ready["unrelated_changes"]:
            return CommandResult(
                False,
                "자동으로 반영할 수 없는 다른 변경 사항이 있습니다",
                "검사 중 생긴 관리 대상 외 변경을 자동 stage하지 않습니다.",
                "\n".join(ready["unrelated_changes"]),
            )
        if ready["unrelated_ahead_paths"]:
            return CommandResult(
                False,
                "자동으로 push할 수 없는 로컬 commit이 있습니다",
                "origin/main 이후 commit 내용을 직접 검토해 주세요.",
                "\n".join(ready["unrelated_ahead_paths"]),
            )

        output: list[str] = [checked.summary]
        if ready["managed_changes"]:
            name = _run(["git", "config", "user.name"], self.root)
            email = _run(["git", "config", "user.email"], self.root)
            if name.returncode != 0 or not name.stdout.strip() or email.returncode != 0 or not email.stdout.strip():
                return CommandResult(
                    False,
                    "Git 작성자 설정이 필요합니다",
                    "git user.name과 user.email을 설정한 뒤 다시 시도해 주세요.",
                )
            if progress:
                progress("허용된 블로그 관리 파일만 commit하고 있습니다")
            stage_paths = [
                path
                for path in PUBLISH_PATHS
                if (self.root / path).exists()
                or bool(_run(["git", "ls-files", "--", path], self.root).stdout.strip())
            ]
            staged = _run(["git", "add", "-A", "--", *stage_paths], self.root)
            output.append(staged.stdout)
            if staged.returncode != 0:
                return CommandResult(False, "파일 stage 실패", "commit하지 않았습니다.", "\n".join(output))
            staged_paths = _run(["git", "diff", "--cached", "--name-only"], self.root)
            unexpected = [path for path in staged_paths.stdout.splitlines() if not _is_publish_path(path)]
            if unexpected:
                return CommandResult(
                    False,
                    "허용되지 않은 stage를 발견했습니다",
                    "예상 밖 파일은 commit하지 않았습니다.",
                    "\n".join(unexpected),
                )
            committed = _run(
                ["git", "commit", "-m", "chore(blog): publish local manager changes"],
                self.root,
            )
            output.append(committed.stdout)
            if committed.returncode != 0:
                return CommandResult(False, "commit 실패", "push를 실행하지 않았습니다.", "\n".join(output))

        if progress:
            progress("origin/main에 일반 push를 실행하고 있습니다")
        pushed = _run(["git", "push", "origin", "HEAD:main"], self.root)
        output.append(pushed.stdout)
        if pushed.returncode != 0:
            return CommandResult(
                False,
                "GitHub push에 실패했습니다",
                "로컬 commit은 보존되어 있습니다. 네트워크와 원격 상태를 확인한 뒤 다시 반영하세요.",
                "\n".join(output),
            )
        return CommandResult(
            True,
            "GitHub에 반영했습니다",
            "허용된 블로그 관리 변경만 검증·commit·push했습니다.",
            "\n".join(output),
        )

    def github_status(self) -> dict[str, Any]:
        gh = shutil.which("gh")
        if not gh:
            return {
                "available": False,
                "automatic": True,
                "message": "GitHub CLI가 설치되어 있지 않습니다.",
            }
        auth = _run([gh, "auth", "status"], self.root)
        if auth.returncode != 0:
            return {
                "available": False,
                "automatic": True,
                "message": "GitHub CLI에 로그인되어 있지 않습니다.",
            }
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
            "automatic": True,
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
        changes = snapshot["thumbnail_changes"]
        lines.extend(
            (
                "",
                "미리보기 이미지",
                f"추가: {changes['added']}개",
                f"변경: {changes['changed']}개",
                f"제거: {changes['removed']}개",
                f"이미지 없음: {changes['none']}개",
            )
        )
        reasons = [
            f"{item['number']}. {item['title']}: 미리보기 이미지 { {'added': '추가', 'changed': '변경', 'removed': '제거'}[item['thumbnail_change']] }"
            for item in snapshot["posts"]
            if item["thumbnail_change"] in {"added", "changed", "removed"}
        ]
        if reasons:
            lines.extend(("", "미리보기 이미지 변경 이유", *reasons))
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
