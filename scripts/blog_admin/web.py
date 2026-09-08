from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Any, Callable

from flask import Flask, jsonify, render_template, request, send_file

from .service import BlogService, CommandResult, UserInputError
from velog_sync.models import VelogSyncError


class TaskRunner:
    def __init__(self):
        self._operation_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._current: dict[str, Any] | None = None
        self._history: deque[dict[str, Any]] = deque(maxlen=20)

    @property
    def busy(self) -> bool:
        return self._operation_lock.locked()

    def current(self) -> dict[str, Any] | None:
        with self._state_lock:
            return dict(self._current) if self._current else None

    def history(self) -> list[dict[str, Any]]:
        with self._state_lock:
            return [dict(item) for item in self._history]

    def start(self, name: str, operation: Callable[[Callable[[str], None]], CommandResult]) -> bool:
        if not self._operation_lock.acquire(blocking=False):
            return False
        started = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._state_lock:
            self._current = {
                "name": name,
                "state": "진행 중",
                "stage": "작업을 준비하고 있습니다",
                "started_at": started,
                "finished_at": None,
                "title": name,
                "summary": "",
                "output": "",
                "ok": None,
            }

        def progress(stage: str) -> None:
            with self._state_lock:
                if self._current:
                    self._current["stage"] = stage

        def execute() -> None:
            try:
                result = operation(progress)
            except Exception as exc:  # Converted to a user-safe task result below.
                result = CommandResult(
                    False,
                    "작업 실패",
                    "작업을 완료하지 못했습니다. 기존 GitHub 게시물은 안전하게 유지됩니다.",
                    str(exc),
                )
            finished = datetime.now().astimezone().isoformat(timespec="seconds")
            with self._state_lock:
                assert self._current is not None
                self._current.update(
                    {
                        "state": "완료" if result.ok else "실패",
                        "stage": "완료" if result.ok else "문제가 발생했습니다",
                        "finished_at": finished,
                        "title": result.title,
                        "summary": result.summary,
                        "output": result.output,
                        "ok": result.ok,
                    }
                )
                self._history.appendleft(dict(self._current))
            self._operation_lock.release()

        threading.Thread(target=execute, daemon=True, name=f"blog-{name}").start()
        return True


def create_app(service: BlogService, runner: TaskRunner | None = None) -> Flask:
    app = Flask(__name__)
    tasks = runner or TaskRunner()
    app.config.update(JSON_AS_ASCII=False, BLOG_SERVICE=service, TASK_RUNNER=tasks)
    app.config["MAX_CONTENT_LENGTH"] = service.config().images.max_bytes + 1024 * 1024

    @app.get("/")
    @app.get("/posts")
    @app.get("/sync")
    @app.get("/checks")
    @app.get("/preview")
    @app.get("/settings")
    @app.get("/history")
    def index():
        return render_template("index.html")

    def error_response(message: str, detail: str, status: int = 400):
        return jsonify({"ok": False, "message": message, "detail": detail}), status

    @app.errorhandler(413)
    def upload_too_large(_: Exception):
        return error_response(
            "이미지를 지정하지 못했습니다.",
            "업로드 파일이 허용된 최대 크기를 초과했습니다.",
            413,
        )

    @app.get("/api/status")
    def api_status():
        try:
            return jsonify({"ok": True, "data": service.snapshot(force=request.args.get("refresh") == "1")})
        except VelogSyncError as exc:
            return error_response(
                "Velog에서 게시물 목록을 가져오는 데 실패했습니다. 잠시 후 다시 시도해 주세요. 기존 GitHub 게시물은 변경하지 않았습니다.",
                str(exc),
                502,
            )

    @app.get("/api/config")
    def api_config():
        cfg = service.config()
        return jsonify(
            {
                "ok": True,
                "data": {
                    "username": cfg.username,
                    "import_after": cfg.import_after.isoformat() if cfg.import_after else "",
                    "exclude_post_ids": sorted(cfg.exclude_post_ids),
                    "hidden_post_ids": sorted(cfg.hidden_post_ids),
                    "series_category_map": {key: list(value) for key, value in cfg.series_category_map.items()},
                },
            }
        )

    def values_from_request() -> list[str]:
        payload = request.get_json(silent=True) or {}
        values = payload.get("posts")
        if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values):
            raise UserInputError("하나 이상의 게시물을 선택해 주세요.")
        return values

    def mutation_guard(require_confirmation: bool = False):
        if tasks.busy:
            return error_response("현재 다른 관리 작업이 진행 중입니다.", "작업이 끝난 뒤 다시 시도해 주세요.", 409)
        payload = request.get_json(silent=True) or {}
        if require_confirmation and payload.get("confirmed") is not True:
            return error_response("확인이 필요한 작업입니다.", "확인창을 거쳐 다시 요청해 주세요.", 400)
        return None

    @app.post("/api/posts/exclude")
    def api_exclude():
        guard = mutation_guard(require_confirmation=True)
        if guard:
            return guard
        try:
            selected = service.exclude(values_from_request(), True)
            return jsonify({"ok": True, "message": f"선택한 {len(selected)}개 글을 가져오지 않도록 설정했습니다."})
        except (UserInputError, ValueError) as exc:
            return error_response("게시물 제외 설정을 저장하지 못했습니다.", str(exc))

    @app.post("/api/posts/unexclude")
    def api_unexclude():
        guard = mutation_guard()
        if guard:
            return guard
        try:
            selected = service.exclude(values_from_request(), False)
            return jsonify({"ok": True, "message": f"선택한 {len(selected)}개 글을 다시 가져올 수 있습니다."})
        except (UserInputError, ValueError) as exc:
            return error_response("제외 해제 설정을 저장하지 못했습니다.", str(exc))

    @app.post("/api/posts/hide")
    def api_hide():
        guard = mutation_guard(require_confirmation=True)
        if guard:
            return guard
        try:
            selected = service.hide(values_from_request())
            return jsonify({"ok": True, "message": f"선택한 {len(selected)}개 글과 공개 이미지 artifact를 사이트에서 숨겼습니다. Velog 원문과 Git history는 삭제되지 않았습니다."})
        except (VelogSyncError, ValueError, OSError) as exc:
            return error_response("게시물을 숨기지 못했습니다.", str(exc))

    @app.post("/api/posts/unhide")
    def api_unhide():
        guard = mutation_guard()
        if guard:
            return guard
        try:
            selected = service.unhide(values_from_request())
            return jsonify({"ok": True, "message": f"선택한 {len(selected)}개 글의 숨김을 해제했습니다."})
        except (UserInputError, ValueError) as exc:
            return error_response("숨김 해제 설정을 저장하지 못했습니다.", str(exc))

    @app.post("/api/settings")
    def api_settings():
        guard = mutation_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True) or {}
        mapping = payload.get("series_category_map", {})
        if not isinstance(mapping, dict) or not all(isinstance(value, list) for value in mapping.values()):
            return error_response("설정을 저장하지 못했습니다.", "시리즈 매핑 형식을 확인해 주세요.")
        try:
            service.save_settings(payload.get("import_after") or None, mapping)
            return jsonify({"ok": True, "message": "설정을 안전하게 저장했습니다."})
        except (UserInputError, ValueError, OSError) as exc:
            return error_response("설정을 저장하지 못했습니다.", str(exc))

    @app.get("/api/posts/<post_id>/thumbnail-override")
    def api_thumbnail_override(post_id: str):
        try:
            path, content_type = service.thumbnail_override_file(post_id)
            return send_file(path, mimetype=content_type, conditional=True, max_age=0)
        except (UserInputError, ValueError, OSError) as exc:
            return error_response("미리보기 이미지를 열 수 없습니다.", str(exc), 404)

    @app.post("/api/posts/<post_id>/thumbnail-override")
    def api_set_thumbnail_override(post_id: str):
        guard = mutation_guard()
        if guard:
            return guard
        uploaded = request.files.get("thumbnail")
        if uploaded is None:
            return error_response("이미지를 지정하지 못했습니다.", "이미지 파일을 선택해 주세요.")
        limit = service.config().images.max_bytes
        data = uploaded.stream.read(limit + 1)
        try:
            service.set_thumbnail_override(post_id, data, uploaded.mimetype)
            return jsonify(
                {
                    "ok": True,
                    "message": "GitHub 블로그 전용 미리보기 이미지를 저장했습니다. 동기화 후 목록 카드에 반영됩니다.",
                }
            )
        except (UserInputError, ValueError, OSError) as exc:
            return error_response("이미지를 지정하지 못했습니다.", str(exc))

    @app.delete("/api/posts/<post_id>/thumbnail-override")
    def api_remove_thumbnail_override(post_id: str):
        guard = mutation_guard(require_confirmation=True)
        if guard:
            return guard
        try:
            removed = service.remove_thumbnail_override(post_id)
            message = (
                "직접 지정한 미리보기 이미지를 제거했습니다."
                if removed
                else "직접 지정한 미리보기 이미지가 없습니다."
            )
            return jsonify({"ok": True, "message": message})
        except (UserInputError, ValueError, OSError) as exc:
            return error_response("미리보기 이미지를 제거하지 못했습니다.", str(exc))

    def task_operation(kind: str) -> tuple[str, Callable[[Callable[[str], None]], CommandResult], bool]:
        operations: dict[str, tuple[str, Callable[[Callable[[str], None]], CommandResult], bool]] = {
            "dry-run": ("변경 사항 미리 확인", lambda progress: (progress("Velog 게시물과 변경 사항을 확인하고 있습니다"), service.dry_run_result())[1], False),
            "sync": (
                "지금 동기화하기",
                lambda progress: (
                    progress("Velog 게시물, 이미지, Markdown을 순서대로 동기화하고 있습니다"),
                    _sync_result(service),
                )[1],
                True,
            ),
            "test": ("Python 테스트", lambda progress: (progress("Python 테스트를 실행하고 있습니다"), service.run_tests())[1], False),
            "build": ("사이트 빌드", lambda progress: (progress("GitHub Pages 사이트를 빌드하고 있습니다"), service.build())[1], False),
            "html": ("HTML 검사", lambda progress: (progress("생성된 HTML을 검사하고 있습니다"), service.html_check())[1], False),
            "check": ("전체 검사", lambda progress: service.check(progress), False),
            "serve": ("로컬 미리보기", lambda progress: (progress("로컬 블로그를 실행하고 있습니다"), service.start_serve())[1], False),
            "pull": ("최신 상태 가져오기", lambda progress: (progress("origin/main을 안전하게 확인하고 있습니다"), service.pull_ff_only())[1], True),
            "publish": ("GitHub에 반영하기", lambda progress: service.publish(progress), True),
            "remote-dry-run": ("GitHub Actions 미리보기", lambda progress: (progress("GitHub Actions에 작업을 요청하고 있습니다"), service.remote_workflow("dry-run"))[1], False),
            "remote-sync": ("GitHub Actions 동기화", lambda progress: (progress("GitHub Actions에 동기화를 요청하고 있습니다"), service.remote_workflow("apply"))[1], True),
        }
        if kind not in operations:
            raise UserInputError("지원하지 않는 작업입니다.")
        return operations[kind]

    @app.post("/api/tasks/<kind>")
    def api_task(kind: str):
        try:
            name, operation, dangerous = task_operation(kind)
        except UserInputError as exc:
            return error_response("작업을 시작할 수 없습니다.", str(exc), 404)
        payload = request.get_json(silent=True) or {}
        if dangerous and payload.get("confirmed") is not True:
            return error_response("확인이 필요한 작업입니다.", "확인창을 거쳐 다시 요청해 주세요.")
        if not tasks.start(name, operation):
            return error_response("현재 다른 관리 작업이 진행 중입니다.", "작업이 끝난 뒤 다시 시도해 주세요.", 409)
        return jsonify({"ok": True, "message": f"{name} 작업을 시작했습니다."}), 202

    @app.get("/api/tasks/current")
    def api_task_current():
        return jsonify({"ok": True, "data": tasks.current(), "busy": tasks.busy})

    @app.get("/api/tasks/history")
    def api_task_history():
        return jsonify({"ok": True, "data": tasks.history()})

    return app


def _sync_result(service: BlogService) -> CommandResult:
    try:
        result = service.apply()
    except (VelogSyncError, OSError) as exc:
        return CommandResult(False, "동기화 실패", "기존 GitHub 게시물은 변경하지 않았습니다.", str(exc))
    counts = result.counts
    summary = (
        f"새로 등록 {counts['IMPORT']}개, 수정 {counts['UPDATE']}개, "
        f"변경 없음 {counts['UNCHANGED']}개, 가져오지 않음 {counts['EXCLUDED']}개, "
        f"GitHub에서 숨김 {counts['HIDDEN']}개, 오류 {counts['ERROR']}개"
    )
    return CommandResult(counts["ERROR"] == 0, "동기화가 완료되었습니다", summary)
