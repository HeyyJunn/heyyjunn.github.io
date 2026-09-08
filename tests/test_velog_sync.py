from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from velog_sync.client import GraphQLClient, JsonTransport  # noqa: E402
from velog_sync.config import ImageConfig, SyncConfig  # noqa: E402
from velog_sync.images import ImageMirror, ImagePlan, ImageProbe  # noqa: E402
from velog_sync.markdown import image_urls, unclosed_fence  # noqa: E402
from velog_sync.models import (  # noqa: E402
    DetailedPost,
    Inventory,
    PostMetadata,
    RssItem,
    Series,
    SourceError,
)
from velog_sync.state import serialize_state  # noqa: E402
from velog_sync.sync import SyncEngine, render_post  # noqa: E402


def post(
    ident: str = "11111111-1111-1111-1111-111111111111",
    *,
    title: str = "제목: [C++] #1 & 😊",
    slug: str = "테스트-글",
    body_date: str = "2025-01-02T03:04:05.000Z",
    updated: str = "2025-01-03T04:05:06.000Z",
    series: Series | None = Series("s1", "[Python] Notion📚", "python-notion"),
) -> PostMetadata:
    return PostMetadata(ident, title, slug, body_date, updated, series, False)


def raw_metadata(item: PostMetadata, tags: list[str] | None = None) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "url_slug": item.slug,
        "released_at": item.released_at,
        "updated_at": item.updated_at,
        "tags": tags or [],  # Extra source metadata is intentionally ignored.
        "is_private": item.is_private,
        "series": None
        if item.series is None
        else {"id": item.series.id, "name": item.series.name, "url_slug": item.series.slug},
    }


class FakeGraphQL:
    def __init__(self, posts: list[PostMetadata], bodies: dict[str, str], error: Exception | None = None):
        self.posts = posts
        self.bodies = bodies
        self.error = error

    def fetch_inventory(self) -> Inventory:
        return Inventory(tuple(self.posts), (len(self.posts), 0), True)

    def fetch_post(self, expected: PostMetadata) -> DetailedPost:
        if self.error:
            raise self.error
        return DetailedPost(expected, self.bodies[expected.id], True)


class BrokenInventory(FakeGraphQL):
    def fetch_inventory(self) -> Inventory:
        raise SourceError("inventory unavailable")


class FakeRss:
    def __init__(self, items: tuple[RssItem, ...] = (), error: Exception | None = None):
        self.items = items
        self.error = error

    def fetch_items(self) -> tuple[RssItem, ...]:
        if self.error:
            raise self.error
        return self.items


def config(**changes: object) -> SyncConfig:
    base = SyncConfig(username="ilwha", images=ImageConfig(enabled=False))
    return replace(base, **changes)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class GraphQLTests(unittest.TestCase):
    def test_cursor_pagination_20_20_0(self) -> None:
        pages = [[post(f"{n:08x}-1111-1111-1111-111111111111") for n in range(20)],
                 [post(f"{n:08x}-2222-2222-2222-222222222222") for n in range(20, 40)], []]
        calls = 0

        def transport(_: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            value = {"data": {"posts": [raw_metadata(x) for x in pages[calls]]}}
            calls += 1
            return value

        result = GraphQLClient("unused", "ilwha", transport=transport).fetch_inventory()
        self.assertEqual(result.page_sizes, (20, 20, 0))
        self.assertEqual(len(result.posts), 40)
        self.assertTrue(result.complete)

    def test_repeated_cursor_and_duplicate_uuid(self) -> None:
        one = post()
        responses = iter(({"data": {"posts": [raw_metadata(one)]}}, {"data": {"posts": [raw_metadata(one)]}}))
        with self.assertRaisesRegex(SourceError, "repeated GraphQL cursor"):
            GraphQLClient("unused", "ilwha", transport=lambda _: next(responses)).fetch_inventory()

        a, b = post(), post(slug="other")
        with self.assertRaisesRegex(SourceError, "duplicate post UUID"):
            GraphQLClient(
                "unused", "ilwha", transport=lambda _: {"data": {"posts": [raw_metadata(a), raw_metadata(b)]}}
            ).fetch_inventory()

    def test_partial_errors_and_missing_series_are_fatal(self) -> None:
        with self.assertRaisesRegex(SourceError, "errors"):
            GraphQLClient("unused", "ilwha", transport=lambda _: {"data": {"posts": []}, "errors": [{"message": "partial"}]}).fetch_inventory()
        invalid = raw_metadata(post())
        del invalid["series"]
        with self.assertRaisesRegex(SourceError, "authoritative series"):
            GraphQLClient("unused", "ilwha", transport=lambda _: {"data": {"posts": [invalid]}}).fetch_inventory()

    def test_list_detail_uuid_and_metadata_mismatch(self) -> None:
        listed = post()
        changed = replace(listed, id="22222222-2222-2222-2222-222222222222")
        client = GraphQLClient("unused", "ilwha", transport=lambda _: {"data": {"post": {**raw_metadata(changed), "body": "x", "is_markdown": True}}})
        with self.assertRaisesRegex(SourceError, "UUID mismatch"):
            client.fetch_post(listed)

    def test_tags_are_not_parsed_or_compared(self) -> None:
        item = post()
        first = GraphQLClient("unused", "ilwha", transport=lambda _: {})._parse_metadata(raw_metadata(item, ["python"]))
        second = GraphQLClient("unused", "ilwha", transport=lambda _: {})._parse_metadata(raw_metadata(item, ["python3"]))
        self.assertEqual(first, second)
        self.assertFalse(hasattr(first, "tags"))

    def test_malformed_json_and_timeout_are_source_errors(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return b"not-json"

        with patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaisesRegex(SourceError, "malformed JSON"):
                JsonTransport("https://example.invalid", retries=1)({})
        with patch("urllib.request.urlopen", side_effect=TimeoutError("slow")):
            with self.assertRaisesRegex(SourceError, "after 1 attempts"):
                JsonTransport("https://example.invalid", retries=1)({})


class RenderingTests(unittest.TestCase):
    def test_front_matter_unicode_yaml_and_no_tags(self) -> None:
        rendered = render_post(post(), "본문\n", ("[Python] Notion📚",), post().released_at, "Asia/Seoul")
        self.assertIn('title: "제목: [C++] #1 & 😊"', rendered)
        self.assertIn('  - "[Python] Notion📚"', rendered)
        self.assertNotIn("tags:", rendered)

    def test_no_series_omits_categories(self) -> None:
        item = post(series=None)
        rendered = render_post(item, "body", (), item.released_at, "Asia/Seoul")
        self.assertNotIn("categories:", rendered)

    def test_markdown_fences_liquid_table_and_unclosed_warning(self) -> None:
        body = "```c\n<string>\n```\n\n````cpp\n<T>\n````\n\n{{ safe }}\n\n|a|b|\n|-|-|\n|1|2|\n"
        rendered = render_post(post(), body, (), post().released_at, "Asia/Seoul")
        for fragment in ("```c", "````cpp", "{{ safe }}", "|a|b|"):
            self.assertIn(fragment, rendered)
        self.assertIn("render_with_liquid: false", rendered)
        self.assertIsNone(unclosed_fence(body))
        self.assertEqual(unclosed_fence("text\n```c\nint x;\n"), (2, "```"))

class ImageTests(unittest.TestCase):
    def mirror(self, probe=None, download=None, **settings: object) -> tuple[tempfile.TemporaryDirectory[str], ImageMirror]:
        temp = tempfile.TemporaryDirectory()
        cfg = ImageConfig(enabled=True, retries=1, **settings)
        return temp, ImageMirror(Path(temp.name), cfg, probe_func=probe, download_func=download)

    def test_png_jpeg_gif_paths_and_duplicate_url(self) -> None:
        for mime, extension in (("image/png", ".png"), ("image/jpeg", ".jpg"), ("image/gif", ".gif")):
            with self.subTest(mime=mime):
                temp, mirror = self.mirror(probe=lambda url, m=mime: ImageProbe(url, m, 12, url))
                try:
                    url = "https://velog.velcdn.com/images/a/image.png"
                    plans, warnings = mirror.plan(post().id, (url, url))
                    self.assertFalse(warnings)
                    self.assertEqual(len(plans), 1)
                    self.assertTrue(plans[url].path.endswith(extension))
                    self.assertEqual(len(Path(plans[url].path).stem), 64)
                finally:
                    temp.cleanup()

    def test_timeout_mime_oversize_and_path_traversal_are_rejected(self) -> None:
        url = "https://velog.velcdn.com/x"
        cases = (
            lambda _: (_ for _ in ()).throw(TimeoutError("timeout")),
            lambda x: ImageProbe(x, "text/html", 1, x),
            lambda x: ImageProbe(x, "image/png", 11, x),
        )
        for index, probe in enumerate(cases):
            temp, mirror = self.mirror(probe=probe, max_bytes=10)
            try:
                plans, warnings = mirror.plan(post().id, (url,))
                self.assertFalse(plans, index)
                self.assertTrue(warnings, index)
            finally:
                temp.cleanup()
        temp, mirror = self.mirror(probe=lambda x: ImageProbe(x, "image/png", 1, x))
        try:
            plans, warnings = mirror.plan("../../escape", (url,))
            self.assertFalse(plans)
            self.assertTrue(warnings)
        finally:
            temp.cleanup()

    def test_download_mime_mismatch_keeps_remote_and_no_part(self) -> None:
        url = "https://velog.velcdn.com/x"
        temp, mirror = self.mirror(download=lambda _: ("image/jpeg", b"x", url))
        try:
            plan = ImagePlan(url, "assets/img/velog/11111111-1111-1111-1111-111111111111/a.png", "image/png", 1)
            record, warning = mirror.materialize(plan)
            self.assertIsNone(record)
            self.assertIn("MIME mismatch", warning or "")
            self.assertFalse(list(Path(temp.name).rglob("*.part")))
        finally:
            temp.cleanup()

    def test_successful_download_is_atomic_and_reusable(self) -> None:
        url = "https://velog.velcdn.com/x"
        temp, mirror = self.mirror(
            probe=lambda x: ImageProbe(x, "image/png", 3, x),
            download=lambda _: ("image/png", b"png", url),
        )
        try:
            plans, _ = mirror.plan(post().id, (url,))
            record, warning = mirror.materialize(plans[url])
            self.assertIsNone(warning)
            self.assertIsNotNone(record)
            self.assertFalse(list(Path(temp.name).rglob("*.part")))
            reused, warnings = mirror.plan(post().id, (url,), {url: record})
            self.assertFalse(warnings)
            self.assertTrue(reused[url].reused)
        finally:
            temp.cleanup()

    def test_image_syntax_ignores_fenced_code(self) -> None:
        body = "![yes](https://velog.velcdn.com/a.png)\n```md\n![no](https://velog.velcdn.com/b.png)\n```\n"
        self.assertEqual(image_urls(body), ("https://velog.velcdn.com/a.png",))


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "_posts").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def engine(self, items: list[PostMetadata], bodies: dict[str, str], cfg: SyncConfig | None = None, **kwargs: object) -> SyncEngine:
        return SyncEngine(self.root, cfg or config(), FakeGraphQL(items, bodies, kwargs.get("error")), FakeRss(kwargs.get("rss", ())))

    def test_new_then_second_sync_is_unchanged_and_deterministic(self) -> None:
        item = post()
        first = self.engine([item], {item.id: "본문\n"}).run()
        self.assertEqual(first.counts["IMPORT"], 1)
        state_one = (self.root / ".velog-sync/state.json").read_bytes()
        file_one = (self.root / first.outcomes[0].post_path).read_bytes()
        second = self.engine([item], {item.id: "본문\n"}).run()
        self.assertEqual(second.counts["UNCHANGED"], 1)
        self.assertFalse(second.state_changed)
        self.assertEqual(state_one, (self.root / ".velog-sync/state.json").read_bytes())
        self.assertEqual(file_one, (self.root / second.outcomes[0].post_path).read_bytes())
        self.assertEqual(serialize_state(json.loads(state_one)), state_one.decode())

    def test_body_title_series_updates_keep_path(self) -> None:
        item = post()
        first = self.engine([item], {item.id: "one"}).run().outcomes[0]
        original_path = first.post_path
        body_changed = replace(item, updated_at="2025-01-04T00:00:00Z")
        second = self.engine([body_changed], {item.id: "two"}).run().outcomes[0]
        self.assertEqual((second.action, second.post_path), ("UPDATE", original_path))
        title_changed = replace(body_changed, title="새 제목", updated_at="2025-01-05T00:00:00Z")
        third = self.engine([title_changed], {item.id: "two"}).run().outcomes[0]
        self.assertEqual((third.action, third.post_path), ("UPDATE", original_path))
        series_changed = replace(title_changed, series=Series("s2", "Java Archive", "java"), updated_at="2025-01-06T00:00:00Z")
        fourth = self.engine([series_changed], {item.id: "two"}).run().outcomes[0]
        self.assertEqual((fourth.action, fourth.post_path), ("UPDATE", original_path))
        self.assertIn('  - "Java Archive"', (self.root / original_path).read_text())

    def test_authoritative_series_null_removes_category(self) -> None:
        item = post()
        path = self.engine([item], {item.id: "body"}).run().outcomes[0].post_path
        no_series = replace(item, series=None, updated_at="2025-02-01T00:00:00Z")
        result = self.engine([no_series], {item.id: "body"}).run()
        self.assertEqual(result.outcomes[0].action, "UPDATE")
        self.assertNotIn("categories:", (self.root / path).read_text())

    def test_same_title_different_uuid_gets_collision_suffix(self) -> None:
        one = post()
        two = replace(one, id="22222222-2222-2222-2222-222222222222")
        result = self.engine([one, two], {one.id: "a", two.id: "b"}).run(dry_run=True)
        self.assertNotEqual(result.outcomes[0].post_path, result.outcomes[1].post_path)
        self.assertIn(two.id[:8], result.outcomes[1].post_path or "")

    def test_exclude_uuid_import_after_and_imported_then_excluded(self) -> None:
        item = post()
        for cfg in (
            config(exclude_post_ids=frozenset({item.id})),
            config(import_after=date(2025, 1, 3)),
        ):
            result = self.engine([item], {item.id: "body"}, cfg).run(dry_run=True)
            self.assertEqual(result.outcomes[0].action, "EXCLUDED")
        imported = self.engine([item], {item.id: "body"}).run().outcomes[0]
        result = self.engine([item], {item.id: "body"}, config(exclude_post_ids=frozenset({item.id}))).run()
        self.assertEqual(result.outcomes[0].action, "EXCLUDED")
        self.assertTrue((self.root / (imported.post_path or "missing")).exists())
        self.assertIn(item.id, json.loads((self.root / ".velog-sync/state.json").read_text())["posts"])

    def test_deleted_source_is_preserved(self) -> None:
        one, two = post(), post("22222222-2222-2222-2222-222222222222", slug="two")
        first = self.engine([one, two], {one.id: "a", two.id: "b"}).run()
        path_two = first.outcomes[1].post_path
        self.engine([one], {one.id: "a"}).run()
        self.assertTrue((self.root / (path_two or "missing")).exists())
        self.assertIn(two.id, json.loads((self.root / ".velog-sync/state.json").read_text())["posts"])

    def test_detail_failure_preserves_existing_and_rss_never_supplies_body(self) -> None:
        item = post()
        imported = self.engine([item], {item.id: "old"}).run().outcomes[0]
        changed = replace(item, updated_at="2025-02-01T00:00:00Z")
        error_engine = SyncEngine(self.root, config(), FakeGraphQL([changed], {}, SourceError("raw failed")), FakeRss())
        result = error_engine.run()
        self.assertEqual(result.outcomes[0].action, "ERROR")
        self.assertIn("old", (self.root / (imported.post_path or "missing")).read_text())

        fresh_root = Path(tempfile.mkdtemp(dir=self.root))
        (fresh_root / "_posts").mkdir()
        rss = RssItem(item.title, f"https://velog.io/@ilwha/{item.slug}", "g", item.released_at)
        fallback = SyncEngine(fresh_root, config(), FakeGraphQL([item], {}, SourceError("raw failed")), FakeRss((rss,))).run(dry_run=True)
        self.assertEqual(fallback.outcomes[0].action, "ERROR")
        self.assertIsNone(fallback.outcomes[0].desired_text)

    def test_inventory_failure_never_treats_rss_as_full_inventory(self) -> None:
        item = post()
        rss = RssItem(item.title, "https://velog.io/@ilwha/x", "g", item.released_at)
        with self.assertRaisesRegex(SourceError, "inventory unavailable"):
            SyncEngine(self.root, config(), BrokenInventory([], {}), FakeRss((rss,))).run()

    def test_dry_run_has_zero_filesystem_mutation(self) -> None:
        marker = self.root / "marker"
        marker.write_text("keep")
        before = tree_digest(self.root)
        result = self.engine([post()], {post().id: "body"}).run(dry_run=True)
        self.assertEqual(result.outcomes[0].action, "IMPORT")
        self.assertEqual(before, tree_digest(self.root))
        self.assertFalse((self.root / ".velog-sync").exists())

    def test_tag_only_source_change_is_unchanged_bytes_and_state(self) -> None:
        item = post()
        raw_one, raw_two = raw_metadata(item, ["python"]), raw_metadata(item, ["python3"])
        parsed_one = GraphQLClient("unused", "ilwha", transport=lambda _: {})._parse_metadata(raw_one)
        parsed_two = GraphQLClient("unused", "ilwha", transport=lambda _: {})._parse_metadata(raw_two)
        initial = self.engine([parsed_one], {item.id: "body"}).run().outcomes[0]
        markdown_before = (self.root / (initial.post_path or "missing")).read_bytes()
        state_before = (self.root / ".velog-sync/state.json").read_bytes()
        result = self.engine([parsed_two], {item.id: "changed body must not be fetched"}).run()
        self.assertEqual(result.outcomes[0].action, "UNCHANGED")
        self.assertEqual(markdown_before, (self.root / (initial.post_path or "missing")).read_bytes())
        self.assertEqual(state_before, (self.root / ".velog-sync/state.json").read_bytes())

    def test_unclosed_fence_is_reported_not_repaired(self) -> None:
        item = post()
        body = "before\n```c\nint main() {}\n"
        outcome = self.engine([item], {item.id: body}).run(dry_run=True).outcomes[0]
        self.assertTrue(any("unclosed code fence" in warning for warning in outcome.warnings))
        self.assertIn(body, outcome.desired_text or "")

    def test_managed_markdown_drift_is_restored(self) -> None:
        item = post()
        imported = self.engine([item], {item.id: "authoritative"}).run().outcomes[0]
        managed = self.root / (imported.post_path or "missing")
        managed.write_text("manual drift", encoding="utf-8")
        result = self.engine([item], {item.id: "authoritative"}).run()
        self.assertEqual(result.outcomes[0].action, "UPDATE")
        self.assertIn("authoritative", managed.read_text(encoding="utf-8"))
        self.assertNotIn("manual drift", managed.read_text(encoding="utf-8"))

    def test_unsafe_state_post_path_is_rejected(self) -> None:
        item = post()
        self.engine([item], {item.id: "body"}).run()
        state_path = self.root / ".velog-sync/state.json"
        state = json.loads(state_path.read_text())
        state["posts"][item.id]["post_path"] = "../outside.md"
        state_path.write_text(serialize_state(state))
        with self.assertRaisesRegex(SourceError, "unsafe managed post path"):
            self.engine([item], {item.id: "body"}).run(dry_run=True)

    def test_hidden_post_is_skipped_and_never_recreated(self) -> None:
        item = post()
        result = self.engine(
            [item],
            {item.id: "body"},
            config(hidden_post_ids=frozenset({item.id})),
        ).run()
        self.assertEqual(result.outcomes[0].action, "HIDDEN")
        self.assertFalse(list(self.root.glob("_posts/*.md")))

    def test_slug_only_change_updates_source_state_without_rewriting_markdown(self) -> None:
        item = post()
        first = self.engine([item], {item.id: "body"}).run().outcomes[0]
        managed = self.root / (first.post_path or "missing")
        before_bytes = managed.read_bytes()
        before_stat = managed.stat().st_mtime_ns
        changed = replace(item, slug="새-slug")
        result = self.engine([changed], {item.id: "body"}).run()
        self.assertEqual(result.outcomes[0].action, "UNCHANGED")
        self.assertEqual(managed.read_bytes(), before_bytes)
        self.assertEqual(managed.stat().st_mtime_ns, before_stat)
        state = json.loads((self.root / ".velog-sync/state.json").read_text())
        self.assertEqual(state["posts"][item.id]["source_slug"], "새-slug")
        self.assertTrue(state["posts"][item.id]["source_url"].endswith("/%EC%83%88-slug"))

    def test_hidden_missing_image_is_not_an_update_loop(self) -> None:
        item = post()
        image_path = self.root / "assets/img/velog" / item.id / "image.png"
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"image")
        imported = self.engine([item], {item.id: "body"}).run().outcomes[0]
        state_path = self.root / ".velog-sync/state.json"
        state = json.loads(state_path.read_text())
        state["posts"][item.id]["images"] = {
            "https://velog.velcdn.com/x.png": {
                "content_type": "image/png",
                "path": image_path.relative_to(self.root).as_posix(),
                "sha256": "sha256:missing",
                "size": 5,
            }
        }
        state_path.write_text(serialize_state(state))
        image_path.unlink()
        result = self.engine(
            [item], {item.id: "must not be fetched"},
            config(hidden_post_ids=frozenset({item.id})),
        ).run(dry_run=True)
        self.assertEqual(result.outcomes[0].action, "HIDDEN")
        self.assertEqual(result.outcomes[0].post_path, imported.post_path)

    def test_hidden_images_are_pruned_and_unhide_restores_them(self) -> None:
        item = post()
        url = "https://velog.velcdn.com/images/test.png"
        body = f"![image]({url})\n"
        cfg = SyncConfig(username="ilwha", images=ImageConfig(enabled=True, retries=1))
        mirror = ImageMirror(
            self.root,
            cfg.images,
            probe_func=lambda value: ImageProbe(value, "image/png", 3, value),
            download_func=lambda value: ("image/png", b"png", value),
        )
        SyncEngine(self.root, cfg, FakeGraphQL([item], {item.id: body}), FakeRss(), mirror).run()
        state = json.loads((self.root / ".velog-sync/state.json").read_text())
        image = self.root / state["posts"][item.id]["images"][url]["path"]
        self.assertTrue(image.is_file())

        hidden_cfg = replace(cfg, hidden_post_ids=frozenset({item.id}))
        hidden = SyncEngine(
            self.root, hidden_cfg, FakeGraphQL([item], {item.id: body}), FakeRss(), mirror
        ).run()
        self.assertEqual(hidden.outcomes[0].action, "HIDDEN")
        self.assertFalse(image.parent.exists())
        self.assertIn(item.id, json.loads((self.root / ".velog-sync/state.json").read_text())["posts"])

        restored = SyncEngine(
            self.root, cfg, FakeGraphQL([item], {item.id: body}), FakeRss(), mirror
        ).run()
        self.assertEqual(restored.outcomes[0].action, "UNCHANGED")
        self.assertTrue(image.is_file())

    def test_pruning_hidden_images_does_not_touch_visible_post_images(self) -> None:
        visible = post()
        hidden = post("22222222-2222-2222-2222-222222222222", slug="hidden")
        visible_dir = self.root / "assets/img/velog" / visible.id
        hidden_dir = self.root / "assets/img/velog" / hidden.id
        visible_dir.mkdir(parents=True)
        hidden_dir.mkdir(parents=True)
        (visible_dir / "keep.png").write_bytes(b"keep")
        (hidden_dir / "remove.png").write_bytes(b"remove")
        result = self.engine(
            [visible, hidden],
            {visible.id: "visible", hidden.id: "hidden"},
            config(hidden_post_ids=frozenset({hidden.id})),
        ).run()
        self.assertEqual([item.action for item in result.outcomes], ["IMPORT", "HIDDEN"])
        self.assertTrue((visible_dir / "keep.png").is_file())
        self.assertFalse(hidden_dir.exists())


if __name__ == "__main__":
    unittest.main()
