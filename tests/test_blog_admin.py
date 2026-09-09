from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from blog_admin import service as service_module  # noqa: E402
from blog_admin.service import BlogService, CommandResult, ConfigStore, UserInputError  # noqa: E402
from blog_admin.web import TaskRunner, create_app  # noqa: E402
from blog_manager import build_parser  # noqa: E402
from velog_sync.config import SyncConfig  # noqa: E402
from velog_sync.models import PostMetadata, Series, SyncOutcome  # noqa: E402
from velog_sync.sync import SyncResult  # noqa: E402


POSTS = (
    PostMetadata("11111111-1111-1111-1111-111111111111", "첫 번째 글", "first", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z", Series("s1", "Python", "python")),
    PostMetadata("22222222-2222-2222-2222-222222222222", "두 번째 글", "second", "2025-01-02T00:00:00Z", "2025-01-02T00:00:00Z", None),
    PostMetadata("33333333-3333-3333-3333-333333333333", "세 번째 글", "third", "2025-01-03T00:00:00Z", "2025-01-03T00:00:00Z", Series("s2", "Java", "java")),
)


class FakeEngine:
    def __init__(self, root: Path, cfg: SyncConfig):
        self.root, self.cfg = root, cfg

    def run(self, dry_run: bool = False) -> SyncResult:
        outcomes = []
        for item in POSTS:
            action = "HIDDEN" if item.id in self.cfg.hidden_post_ids else "EXCLUDED" if item.id in self.cfg.exclude_post_ids else "IMPORT"
            categories = (item.series.name,) if item.series else ()
            outcomes.append(SyncOutcome(action, item, f"_posts/2025-01-0{len(outcomes)+1}-{item.slug}.md", categories, image_count=len(outcomes)))
        return SyncResult(tuple(outcomes), (3, 0), True, 3, False, dry_run)


def write_config(root: Path) -> None:
    path = root / ".velog-sync"
    path.mkdir(parents=True)
    (path / "config.yml").write_text(
        "velog:\n  username: ilwha\nexclude_post_ids: []\nhidden_post_ids: []\nimport_after: null\nseries_category_map: {}\nthumbnail_overrides: {}\nimages:\n  enabled: false\n  max_bytes: 64\n",
        encoding="utf-8",
    )
    (path / "state.json").write_text('{"posts": {}, "schema_version": 1}\n', encoding="utf-8")
    (root / "_posts").mkdir()


class AdminFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write_config(self.root)
        self.service = BlogService(
            self.root, lambda root, cfg: FakeEngine(root, cfg), enforce_git_safety=False
        )

    def tearDown(self) -> None:
        self.temp.cleanup()


class CliAndConfigTests(AdminFixture):
    def test_cli_argument_parsing(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["dry-run"]).command, "dry-run")
        args = parser.parse_args(["exclude", "add", "1", "second"])
        self.assertEqual((args.exclude_command, args.posts), ("add", ["1", "second"]))

    def test_number_slug_and_uuid_resolution(self) -> None:
        selected = self.service.resolve_ids(
            ["1", "second", POSTS[2].id]
        )
        self.assertEqual([item.post.id for item in selected], [item.id for item in POSTS])

    def test_url_input_resolves_to_uuid_exclusion(self) -> None:
        self.service.exclude(["https://velog.io/@ilwha/second"], True)
        raw = yaml.safe_load((self.root / ".velog-sync/config.yml").read_text())
        self.assertEqual(raw["exclude_post_ids"], [POSTS[1].id])
        self.assertNotIn("exclude_slugs", raw)
        self.assertNotIn("exclude_urls", raw)

    def test_invalid_number_uuid_and_shell_text(self) -> None:
        marker = self.root / "injected"
        for value in ("0", "99", "not-a-post", "; touch injected"):
            with self.subTest(value=value), self.assertRaises(UserInputError):
                self.service.resolve_ids([value])
        self.assertFalse(marker.exists())

    def test_exclude_add_remove_and_multiple(self) -> None:
        self.service.exclude(["1", "3"], True)
        cfg = self.service.config()
        self.assertEqual(cfg.exclude_post_ids, frozenset({POSTS[0].id, POSTS[2].id}))
        self.assertEqual([item.action for item in self.service.preview(force=True).outcomes], ["EXCLUDED", "IMPORT", "EXCLUDED"])
        self.service.exclude([POSTS[0].id], False)
        self.assertEqual(self.service.config().exclude_post_ids, frozenset({POSTS[2].id}))

    def test_hide_removes_managed_post_but_keeps_state_and_unhide(self) -> None:
        managed = self.root / "_posts/2025-01-01-first.md"
        managed.write_text("managed", encoding="utf-8")
        image = self.root / "assets/img/velog" / POSTS[0].id / "image.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"image")
        state = {"schema_version": 1, "posts": {POSTS[0].id: {"post_path": "_posts/2025-01-01-first.md", "images": {"url": {"path": image.relative_to(self.root).as_posix()}}}}}
        (self.root / ".velog-sync/state.json").write_text(json.dumps(state), encoding="utf-8")
        self.service.hide(["1"])
        self.assertFalse(managed.exists())
        self.assertFalse(image.parent.exists())
        self.assertIn(POSTS[0].id, self.service.config().hidden_post_ids)
        self.assertIn(POSTS[0].id, json.loads((self.root / ".velog-sync/state.json").read_text())["posts"])
        self.service.unhide([POSTS[0].id])
        self.assertNotIn(POSTS[0].id, self.service.config().hidden_post_ids)

    def test_unmanaged_post_must_be_excluded_not_hidden(self) -> None:
        with self.assertRaisesRegex(UserInputError, "가져오지 않기"):
            self.service.hide(["1"])
        self.assertFalse(self.service.config().hidden_post_ids)

    def test_config_update_is_atomic_on_replace_failure(self) -> None:
        path = self.root / ".velog-sync/config.yml"
        before = path.read_bytes()
        store = ConfigStore(path)
        with patch("blog_admin.service.os.replace", side_effect=OSError("blocked")):
            with self.assertRaises(OSError):
                store.update(lambda raw: raw.update({"import_after": "2025-01-01"}))
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(list(path.parent.glob("*.part")))

    def test_settings_mapping_and_no_tags_state(self) -> None:
        self.service.save_settings("2025-01-01", {"NLP": ["AI", "NLP"]})
        raw = yaml.safe_load((self.root / ".velog-sync/config.yml").read_text())
        self.assertEqual(raw["series_category_map"]["NLP"], ["AI", "NLP"])
        self.assertNotIn("tags", raw)

    def test_thumbnail_override_config_rejects_path_traversal(self) -> None:
        config_path = self.root / ".velog-sync/config.yml"
        raw = yaml.safe_load(config_path.read_text())
        raw["thumbnail_overrides"] = {
            POSTS[0].id: {"source_path": "../../escape.png"}
        }
        config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "unsafe thumbnail override"):
            self.service.config()


class WebTests(AdminFixture):
    def setUp(self) -> None:
        super().setUp()
        self.runner = TaskRunner()
        self.app = create_app(self.service, self.runner)
        self.app.testing = True
        self.client = self.app.test_client()

    def test_ui_routes_and_korean_navigation(self) -> None:
        for route in ("/", "/posts", "/sync", "/checks", "/preview", "/settings", "/history"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertIn("블로그 관리".encode(), response.data)

    def test_post_list_status_is_korean(self) -> None:
        payload = self.client.get("/api/status").get_json()["data"]
        self.assertEqual(len(payload["posts"]), 3)
        self.assertEqual(payload["posts"][0]["status"], "새로 등록 예정")
        self.assertNotIn("tags", payload["posts"][0])

    def test_tags_column_and_menu_do_not_exist(self) -> None:
        html = self.client.get("/posts").get_data(as_text=True)
        self.assertNotIn("<th>태그</th>", html)
        self.assertNotIn("data-field=\"tags\"", html)

    def test_ui_exclude_and_unexclude(self) -> None:
        denied = self.client.post("/api/posts/exclude", json={"posts": [POSTS[0].id]})
        self.assertEqual(denied.status_code, 400)
        added = self.client.post("/api/posts/exclude", json={"posts": [POSTS[0].id], "confirmed": True})
        self.assertEqual(added.status_code, 200)
        self.assertIn(POSTS[0].id, self.service.config().exclude_post_ids)
        removed = self.client.post("/api/posts/unexclude", json={"posts": [POSTS[0].id]})
        self.assertEqual(removed.status_code, 200)
        self.assertNotIn(POSTS[0].id, self.service.config().exclude_post_ids)

    def test_ui_hide_and_unhide(self) -> None:
        managed = self.root / "_posts/2025-01-01-first.md"
        managed.write_text("managed", encoding="utf-8")
        state = {"schema_version": 1, "posts": {POSTS[0].id: {"post_path": "_posts/2025-01-01-first.md"}}}
        (self.root / ".velog-sync/state.json").write_text(json.dumps(state), encoding="utf-8")
        denied = self.client.post("/api/posts/hide", json={"posts": [POSTS[0].id]})
        self.assertEqual(denied.status_code, 400)
        hidden = self.client.post("/api/posts/hide", json={"posts": [POSTS[0].id], "confirmed": True})
        self.assertEqual(hidden.status_code, 200)
        self.assertIn(POSTS[0].id, self.service.config().hidden_post_ids)
        shown = self.client.post("/api/posts/unhide", json={"posts": [POSTS[0].id]})
        self.assertEqual(shown.status_code, 200)
        self.assertNotIn(POSTS[0].id, self.service.config().hidden_post_ids)

    def test_dangerous_sync_requires_backend_confirmation(self) -> None:
        response = self.client.post("/api/tasks/sync", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("확인이 필요한 작업", response.get_json()["message"])
        for kind in ("pull", "publish"):
            with self.subTest(kind=kind):
                denied = self.client.post(f"/api/tasks/{kind}", json={})
                self.assertEqual(denied.status_code, 400)

    def test_ui_dry_run_task_and_history(self) -> None:
        response = self.client.post("/api/tasks/dry-run", json={})
        self.assertEqual(response.status_code, 202)
        for _ in range(100):
            current = self.client.get("/api/tasks/current").get_json()
            if not current["busy"]:
                break
            time.sleep(0.01)
        self.assertFalse(current["busy"])
        self.assertTrue(current["data"]["ok"])
        history = self.client.get("/api/tasks/history").get_json()["data"]
        self.assertEqual(history[0]["title"], "동기화 미리보기 완료")

    def test_concurrent_operation_lock(self) -> None:
        release = threading.Event()
        self.assertTrue(self.runner.start("긴 작업", lambda _: (release.wait(1), CommandResult(True, "완료", "완료"))[1]))
        response = self.client.post("/api/tasks/dry-run", json={})
        self.assertEqual(response.status_code, 409)
        self.assertIn("진행 중", response.get_json()["message"])
        release.set()

    def test_ui_settings_update(self) -> None:
        response = self.client.post(
            "/api/settings",
            json={"username": "someone-else", "import_after": "2025-01-01", "series_category_map": {"NLP": ["AI", "NLP"]}},
        )
        self.assertEqual(response.status_code, 200)
        config = self.client.get("/api/config").get_json()["data"]
        self.assertEqual(config["username"], "ilwha")
        self.assertEqual(config["series_category_map"]["NLP"], ["AI", "NLP"])

    def test_username_is_read_only_and_advanced_navigation_exists(self) -> None:
        html = self.client.get("/settings").get_data(as_text=True)
        self.assertIn('<output id="username">', html)
        self.assertNotIn('<input id="username"', html)
        self.assertIn("고급 도구", html)

    def test_gh_absence_does_not_break_status(self) -> None:
        with patch("blog_admin.service.shutil.which", return_value=None):
            payload = self.client.get("/api/status").get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["github"]["available"])
        self.assertTrue(payload["data"]["github"]["automatic"])
        javascript = (ROOT / "scripts/blog_admin/static/admin.js").read_text(encoding="utf-8")
        self.assertIn("s.github||", javascript)
        self.assertIn("s.git||", javascript)

    def test_valid_thumbnail_upload_ignores_filename_and_remove_is_atomic(self) -> None:
        response = self.client.post(
            f"/api/posts/{POSTS[0].id}/thumbnail-override",
            data={
                "thumbnail": (
                    io.BytesIO(b"\x89PNG\r\n\x1a\nvalid"),
                    "../../malicious<script>.png",
                    "image/png",
                )
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        cfg = self.service.config()
        override = cfg.thumbnail_overrides[POSTS[0].id]
        self.assertNotIn("malicious", override.source_path)
        source = self.root / override.source_path
        self.assertTrue(source.is_file())
        preview = self.client.get(
            f"/api/posts/{POSTS[0].id}/thumbnail-override"
        )
        self.assertEqual((preview.status_code, preview.mimetype), (200, "image/png"))
        preview.close()
        denied = self.client.delete(
            f"/api/posts/{POSTS[0].id}/thumbnail-override", json={}
        )
        self.assertEqual(denied.status_code, 400)
        removed = self.client.delete(
            f"/api/posts/{POSTS[0].id}/thumbnail-override",
            json={"confirmed": True},
        )
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(source.exists())
        self.assertNotIn(POSTS[0].id, self.service.config().thumbnail_overrides)

    def test_thumbnail_upload_rejects_invalid_mime_oversize_and_uuid(self) -> None:
        invalid_mime = self.client.post(
            f"/api/posts/{POSTS[0].id}/thumbnail-override",
            data={"thumbnail": (io.BytesIO(b"\x89PNG\r\n\x1a\nvalid"), "x.png", "text/html")},
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid_mime.status_code, 400)
        oversize = self.client.post(
            f"/api/posts/{POSTS[0].id}/thumbnail-override",
            data={"thumbnail": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 65), "x.png", "image/png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(oversize.status_code, 400)
        traversal = self.client.post(
            "/api/posts/..%2F..%2Fescape/thumbnail-override",
            data={"thumbnail": (io.BytesIO(b"\x89PNG\r\n\x1a\nvalid"), "x.png", "image/png")},
            content_type="multipart/form-data",
        )
        self.assertIn(traversal.status_code, {400, 404})
        self.assertFalse((self.root / "escape").exists())

    def test_velog_thumbnail_disables_manual_upload_in_api_and_ui(self) -> None:
        item = PostMetadata(
            POSTS[0].id, POSTS[0].title, POSTS[0].slug,
            POSTS[0].released_at, POSTS[0].updated_at, POSTS[0].series,
            False, "https://velog.velcdn.com/preview.jpg",
        )
        outcome = SyncOutcome("IMPORT", item, "_posts/x.md", ("Python",))
        fake = SyncResult((outcome,), (1, 0), True, 1, False, True)
        with patch.object(self.service, "preview", return_value=fake):
            response = self.client.post(
                f"/api/posts/{item.id}/thumbnail-override",
                data={"thumbnail": (io.BytesIO(b"\x89PNG\r\n\x1a\nvalid"), "x.png", "image/png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        javascript = (ROOT / "scripts/blog_admin/static/admin.js").read_text(encoding="utf-8")
        self.assertIn("Velog 미리보기가 항상 우선 사용됩니다", javascript)
        self.assertIn("p.thumbnail_source==='velog'", javascript)

    def test_planned_thumbnail_removal_does_not_show_stale_deploy_path(self) -> None:
        outcome = SyncOutcome(
            "UPDATE",
            POSTS[0],
            "_posts/2025-01-01-first.md",
            ("Python",),
            thumbnail=None,
            thumbnail_change="removed",
        )
        state_entry = {
            "thumbnail": {
                "kind": "velog",
                "path": f"assets/img/velog/{POSTS[0].id}/old.png",
            }
        }

        view = self.service.post_view(
            outcome, 1, self.service.config(), state_entry
        )

        self.assertEqual(view["thumbnail_source"], "none")
        self.assertIsNone(view["thumbnail_path"])


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=True
    )


class GitSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.remote = base / "remote.git"
        self.root = base / "local"
        run_git(base, "init", "--bare", self.remote.as_posix())
        run_git(base, "init", "-b", "main", self.root.as_posix())
        run_git(self.root, "config", "user.name", "Test User")
        run_git(self.root, "config", "user.email", "test@example.com")
        write_config(self.root)
        run_git(self.root, "add", ".velog-sync", "_posts")
        run_git(self.root, "commit", "-m", "initial")
        run_git(self.root, "remote", "add", "origin", self.remote.as_posix())
        run_git(self.root, "push", "-u", "origin", "main")
        self.service = BlogService(self.root, lambda root, cfg: FakeEngine(root, cfg))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def remote_commit(self, name: str = "remote.txt") -> None:
        other = Path(self.temp.name) / f"other-{name}"
        run_git(Path(self.temp.name), "clone", "--branch", "main", self.remote.as_posix(), other.as_posix())
        run_git(other, "config", "user.name", "Remote User")
        run_git(other, "config", "user.email", "remote@example.com")
        (other / name).write_text(name, encoding="utf-8")
        run_git(other, "add", name)
        run_git(other, "commit", "-m", name)
        run_git(other, "push", "origin", "main")

    def test_git_relation_current(self) -> None:
        status = self.service.git_status(fetch=True)
        self.assertEqual((status["relation"], status["ahead"], status["behind"]), ("current", 0, 0))

    def test_git_relation_ahead(self) -> None:
        (self.root / "local.txt").write_text("local", encoding="utf-8")
        run_git(self.root, "add", "local.txt")
        run_git(self.root, "commit", "-m", "local")
        status = self.service.git_status(fetch=True)
        self.assertEqual((status["relation"], status["ahead"]), ("ahead", 1))
        self.assertIn("local.txt", status["unrelated_ahead_paths"])
        self.assertFalse(status["can_publish"])
        self.assertFalse(self.service.publish().ok)

    def test_git_relation_behind_and_pull_ff_only(self) -> None:
        self.remote_commit()
        status = self.service.git_status(fetch=True)
        self.assertEqual((status["relation"], status["behind"]), ("behind", 1))
        self.assertTrue(status["can_pull"])
        pulled = self.service.pull_ff_only()
        self.assertTrue(pulled.ok, pulled.output)
        self.assertEqual(self.service.git_status(fetch=True)["relation"], "current")

    def test_write_operation_is_blocked_while_local_is_behind(self) -> None:
        self.remote_commit()
        before = (self.root / ".velog-sync/config.yml").read_bytes()
        with self.assertRaisesRegex(UserInputError, "더 최신 변경"):
            self.service.exclude(["1"], True)
        self.assertEqual((self.root / ".velog-sync/config.yml").read_bytes(), before)

    def test_git_relation_diverged_is_never_auto_resolved(self) -> None:
        self.remote_commit()
        (self.root / "local.txt").write_text("local", encoding="utf-8")
        run_git(self.root, "add", "local.txt")
        run_git(self.root, "commit", "-m", "local")
        before = run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        status = self.service.git_status(fetch=True)
        self.assertEqual(status["relation"], "diverged")
        result = self.service.pull_ff_only()
        self.assertFalse(result.ok)
        self.assertEqual(run_git(self.root, "rev-parse", "HEAD").stdout.strip(), before)

    def test_dirty_paths_separate_manager_and_unrelated_changes(self) -> None:
        config_path = self.root / ".velog-sync/config.yml"
        config_path.write_text(config_path.read_text() + "# manager\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("user", encoding="utf-8")
        status = self.service.git_status(fetch=True)
        self.assertIn(".velog-sync/config.yml", status["managed_changes"])
        self.assertIn("notes.txt", status["unrelated_changes"])
        self.assertFalse(status["can_publish"])

    def test_publish_uses_allowlist_and_never_git_add_dot(self) -> None:
        config_path = self.root / ".velog-sync/config.yml"
        config_path.write_text(config_path.read_text() + "# publish\n", encoding="utf-8")
        commands: list[list[str]] = []
        real_run = service_module._run

        def recording(argv: list[str], root: Path, env=None):
            commands.append(list(argv))
            return real_run(argv, root, env)

        with patch("blog_admin.service._run", side_effect=recording), patch.object(
            self.service, "check", return_value=CommandResult(True, "ok", "검사 통과")
        ):
            result = self.service.publish()
        self.assertTrue(result.ok, result.output)
        add = next(command for command in commands if command[:2] == ["git", "add"])
        self.assertEqual(add[:4], ["git", "add", "-A", "--"])
        self.assertNotIn(".", add[4:])
        changed = run_git(self.root, "show", "--name-only", "--format=", "HEAD").stdout.splitlines()
        self.assertEqual(changed, [".velog-sync/config.yml"])

    def test_thumbnail_override_source_is_publish_managed(self) -> None:
        source = self.root / ".velog-sync/thumbnail-overrides" / POSTS[0].id / "cover.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"image")
        status = self.service.git_status(fetch=True)
        self.assertIn(source.relative_to(self.root).as_posix(), status["managed_changes"])
        self.assertFalse(status["unrelated_changes"])

    def test_unrelated_dirty_worktree_blocks_publish(self) -> None:
        (self.root / "notes.txt").write_text("user", encoding="utf-8")
        before = run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        result = self.service.publish()
        self.assertFalse(result.ok)
        self.assertIn("다른 변경", result.title)
        self.assertEqual(run_git(self.root, "rev-parse", "HEAD").stdout.strip(), before)

    def test_failed_check_creates_no_commit(self) -> None:
        config_path = self.root / ".velog-sync/config.yml"
        config_path.write_text(config_path.read_text() + "# pending\n", encoding="utf-8")
        before = run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        with patch.object(self.service, "check", return_value=CommandResult(False, "bad", "실패", "broken")):
            result = self.service.publish()
        self.assertFalse(result.ok)
        self.assertEqual(run_git(self.root, "rev-parse", "HEAD").stdout.strip(), before)

    def test_failed_push_preserves_and_reports_local_commit(self) -> None:
        config_path = self.root / ".velog-sync/config.yml"
        config_path.write_text(config_path.read_text() + "# pending\n", encoding="utf-8")
        before = run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        real_run = service_module._run

        def reject_push(argv: list[str], root: Path, env=None):
            if argv[:2] == ["git", "push"]:
                return subprocess.CompletedProcess(argv, 1, "rejected")
            return real_run(argv, root, env)

        with patch("blog_admin.service._run", side_effect=reject_push), patch.object(
            self.service, "check", return_value=CommandResult(True, "ok", "검사 통과")
        ):
            result = self.service.publish()
        self.assertFalse(result.ok)
        self.assertIn("로컬 commit은 보존", result.summary)
        self.assertNotEqual(run_git(self.root, "rev-parse", "HEAD").stdout.strip(), before)
        self.assertEqual(self.service.git_status(fetch=True)["relation"], "ahead")


class RepositoryPolicyTests(unittest.TestCase):
    def test_post_heading_bold_css_is_scoped_to_rendered_post_content(self) -> None:
        stylesheet = (ROOT / "assets/css/jekyll-theme-chirpy.scss").read_text(encoding="utf-8")
        self.assertIn("article[data-toc] > .content", stylesheet)
        for heading in range(1, 7):
            self.assertIn(f"h{heading},", stylesheet)
            self.assertIn(f"h{heading} a", stylesheet)
        self.assertIn("font-weight: 700", stylesheet)

    def test_tags_archive_is_removed(self) -> None:
        config = (ROOT / "_config.yml").read_text(encoding="utf-8")
        archive = config.split("jekyll-archives:", 1)[1]
        self.assertIn("enabled: [categories]", archive)
        self.assertNotIn("tag:", archive)

    def test_schedule_skips_unit_tests_but_push_keeps_them(self) -> None:
        workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "7,22,37,52 * * * *"', workflow)
        self.assertEqual(workflow.count("if: github.event_name != 'schedule'"), 1)
        self.assertNotIn("VELOG_SYNC_ENABLED", workflow)
        apply_step = workflow.split("- name: Apply Velog sync", 1)[1].split("- name:", 1)[0]
        self.assertIn("github.event_name == 'schedule'", apply_step)
        self.assertIn("steps.changes.outputs.has_changes", workflow)
        self.assertIn("steps.decision.outputs.should_deploy == 'true'", workflow)

    def test_scheduled_commit_identity_has_safe_bot_defaults(self) -> None:
        workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("${BLOG_GIT_NAME:-github-actions[bot]}", workflow)
        self.assertIn("users.noreply.github.com", workflow)

    def test_home_uses_custom_thumbnail_but_post_detail_does_not(self) -> None:
        home = (ROOT / "_layouts/home.html").read_text(encoding="utf-8")
        self.assertIn("{% if post.thumbnail %}", home)
        self.assertIn("post.thumbnail.path", home)
        self.assertNotIn("{% if post.image %}", home)
        self.assertFalse((ROOT / "_layouts/post.html").exists())

    def test_thumbnail_card_css_is_scoped_and_heading_bold_remains(self) -> None:
        stylesheet = (ROOT / "assets/css/jekyll-theme-chirpy.scss").read_text(encoding="utf-8")
        self.assertIn(".right-thumbnail", stylesheet)
        self.assertIn("aspect-ratio: 8 / 5", stylesheet)
        self.assertIn("object-fit: cover", stylesheet)
        self.assertIn("article[data-toc] > .content", stylesheet)
        self.assertIn("font-weight: 700", stylesheet)

    def test_setup_python_cache_dependency_file_exists(self) -> None:
        self.assertTrue((ROOT / "requirements-velog-sync.txt").is_file())
        self.assertFalse((ROOT / "requirements.txt").exists())

    def test_setup_python_uses_velog_requirements_for_pip_cache(self) -> None:
        workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")
        setup = workflow.split("- name: Setup Python", 1)[1].split("- name:", 1)[0]
        self.assertIn("cache: pip", setup)
        self.assertIn("cache-dependency-path: requirements-velog-sync.txt", setup)

    def test_push_workflow_reaches_python_test_build_and_deploy(self) -> None:
        workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")
        names = (
            "Setup Python",
            "Install sync dependencies",
            "Test Velog sync",
            "Decide whether to build and deploy",
            "Setup Ruby",
            "Build site",
            "Test site",
            "Upload site artifact",
            "Deploy to GitHub Pages",
        )
        positions = [workflow.index(f"name: {name}") for name in names]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('github.event_name == \'push\'', workflow)

    def test_home_thumbnail_is_after_text_in_compact_card(self) -> None:
        home = (ROOT / "_layouts/home.html").read_text(encoding="utf-8")
        self.assertIn('class="post-preview compact-preview d-flex"', home)
        self.assertLess(home.index("card-content-col"), home.index("right-thumbnail"))

    def test_home_has_no_full_width_thumbnail_markup(self) -> None:
        home = (ROOT / "_layouts/home.html").read_text(encoding="utf-8")
        for legacy in ("preview-img", "thumbnail-col", "col-md-5", "flex-md-row-reverse"):
            self.assertNotIn(legacy, home)

    def test_home_has_no_description_or_body_summary_fallback(self) -> None:
        home = (ROOT / "_layouts/home.html").read_text(encoding="utf-8")
        self.assertNotIn("preview_description", home)
        self.assertNotIn("include post-summary.html", home)

    def test_preview_description_is_absent_from_runtime_source(self) -> None:
        roots = (
            ROOT / "scripts/blog_admin",
            ROOT / "scripts/sync_velog.py",
            ROOT / "scripts/velog_sync/client.py",
            ROOT / "scripts/velog_sync/models.py",
            ROOT / "_layouts",
            ROOT / "assets/css",
        )
        users = [
            path
            for root in roots
            for path in (root.rglob("*") if root.is_dir() else (root,))
            if path.is_file()
            and path.suffix in {".py", ".js", ".html", ".scss"}
            and "preview_description" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(users, [])
        migration = (ROOT / "scripts/velog_sync/sync.py").read_text(encoding="utf-8")
        self.assertEqual(migration.count('entry.pop("preview_description", None)'), 1)

    def test_right_thumbnail_has_desktop_tablet_and_mobile_sizes(self) -> None:
        stylesheet = (ROOT / "assets/css/jekyll-theme-chirpy.scss").read_text(encoding="utf-8")
        for size in ("180px", "140px", "96px"):
            self.assertIn(f"width: {size}", stylesheet)
        self.assertIn("flex-wrap: nowrap", stylesheet)

    def test_text_only_card_has_no_placeholder_markup(self) -> None:
        home = (ROOT / "_layouts/home.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('<div class="right-thumbnail">'), 1)
        self.assertNotIn("placeholder", home.lower())
        self.assertNotIn("dummy", home.lower())

    def test_code_header_and_line_numbers_are_hidden_without_hiding_categories(self) -> None:
        stylesheet = (ROOT / "assets/css/jekyll-theme-chirpy.scss").read_text(encoding="utf-8")
        self.assertIn(".code-header {\n      display: none;", stylesheet)
        self.assertIn(".rouge-table td:first-child", stylesheet)
        self.assertIn(".rouge-table td.rouge-code", stylesheet)
        self.assertIn("padding: 1.25rem", stylesheet)
        self.assertIn("border-top-left-radius: inherit", stylesheet)
        self.assertNotIn("post-tail-wrapper", stylesheet)
        self.assertNotIn("> .d-flex > .post-meta", stylesheet)

    def test_no_first_body_image_thumbnail_fallback_or_tags(self) -> None:
        sync = (ROOT / "scripts/velog_sync/sync.py").read_text(encoding="utf-8")
        self.assertNotIn("body_urls[0]", sync)
        self.assertNotIn("first_image", sync)
        self.assertNotIn('"tags"', sync)

    def test_private_override_sources_are_excluded_from_jekyll(self) -> None:
        config = (ROOT / "_config.yml").read_text(encoding="utf-8")
        self.assertIn("  - .velog-sync", config)


if __name__ == "__main__":
    unittest.main()
