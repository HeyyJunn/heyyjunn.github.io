from __future__ import annotations

import json
import os
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
        "velog:\n  username: ilwha\nexclude_post_ids: []\nhidden_post_ids: []\nexclude_slugs: []\nexclude_urls: []\nimport_after: null\nseries_category_map: {}\nimages:\n  enabled: false\n",
        encoding="utf-8",
    )
    (path / "state.json").write_text('{"posts": {}, "schema_version": 1}\n', encoding="utf-8")
    (root / "_posts").mkdir()


class AdminFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write_config(self.root)
        self.service = BlogService(self.root, lambda root, cfg: FakeEngine(root, cfg))

    def tearDown(self) -> None:
        self.temp.cleanup()


class CliAndConfigTests(AdminFixture):
    def test_cli_argument_parsing(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["dry-run"]).command, "dry-run")
        args = parser.parse_args(["exclude", "add", "1", "second"])
        self.assertEqual((args.exclude_command, args.posts), ("add", ["1", "second"]))

    def test_number_slug_and_uuid_resolution(self) -> None:
        selected = self.service.resolve_ids(["1", "second", POSTS[2].id])
        self.assertEqual([item.post.id for item in selected], [item.id for item in POSTS])

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
        state = {"schema_version": 1, "posts": {POSTS[0].id: {"post_path": "_posts/2025-01-01-first.md"}}}
        (self.root / ".velog-sync/state.json").write_text(json.dumps(state), encoding="utf-8")
        self.service.hide(["1"])
        self.assertFalse(managed.exists())
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
        self.service.save_settings("ilwha", "2025-01-01", {"NLP": ["AI", "NLP"]})
        raw = yaml.safe_load((self.root / ".velog-sync/config.yml").read_text())
        self.assertEqual(raw["series_category_map"]["NLP"], ["AI", "NLP"])
        self.assertNotIn("tags", raw)


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
            json={"username": "ilwha", "import_after": "2025-01-01", "series_category_map": {"NLP": ["AI", "NLP"]}},
        )
        self.assertEqual(response.status_code, 200)
        config = self.client.get("/api/config").get_json()["data"]
        self.assertEqual(config["series_category_map"]["NLP"], ["AI", "NLP"])


if __name__ == "__main__":
    unittest.main()
