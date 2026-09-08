from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .client import GraphQLClient, RssClient
from .config import SyncConfig
from .images import ImageMirror, ImagePlan
from .markdown import has_math, image_urls, normalize_markdown, rss_html_to_markdown, transform_images, unclosed_fence
from .models import PostMetadata, SourceError, SyncOutcome
from .state import atomic_write_text, load_state, serialize_state, sha256_bytes, sha256_file


TRANSFORMATION_SCHEMA = 1


@dataclass(frozen=True)
class SyncResult:
    outcomes: tuple[SyncOutcome, ...]
    page_sizes: tuple[int, ...]
    inventory_complete: bool
    rss_count: int | None
    state_changed: bool
    dry_run: bool

    @property
    def counts(self) -> dict[str, int]:
        result = {key: 0 for key in ("IMPORT", "UPDATE", "UNCHANGED", "EXCLUDED", "ERROR")}
        for outcome in self.outcomes:
            result[outcome.action] += 1
        return result

    @property
    def warning_count(self) -> int:
        return sum(len(outcome.warnings) for outcome in self.outcomes)

    @property
    def image_count(self) -> int:
        return sum(outcome.image_count for outcome in self.outcomes if outcome.action != "EXCLUDED")

    @property
    def image_bytes(self) -> int:
        return sum(outcome.image_bytes for outcome in self.outcomes if outcome.action != "EXCLUDED")


def canonical_url(username: str, slug: str) -> str:
    return f"https://velog.io/@{username}/{urllib.parse.quote(slug, safe='-._~')}"


def normalize_slug(value: str) -> str:
    return unicodedata.normalize("NFC", urllib.parse.unquote(value)).strip().strip("/")


def normalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/@-._~")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path.rstrip("/"), "", ""))


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceError(f"invalid Velog timestamp: {value}") from exc


def format_timestamp(value: str, timezone: str) -> str:
    return parse_timestamp(value).astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S %z")


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def resolved_categories(post: PostMetadata, config: SyncConfig) -> tuple[str, ...]:
    if post.series is None:
        return ()
    return config.series_category_map.get(post.series.name, (post.series.name,))


def metadata_hash(post: PostMetadata, categories: tuple[str, ...], source_url: str) -> str:
    payload = {
        "categories": categories,
        "id": post.id,
        "slug": post.slug,
        "source_url": source_url,
        "title": post.title.strip(),
        "updated_at": post.updated_at,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(raw)


def safe_filename_slug(slug: str, post_id: str) -> str:
    value = unicodedata.normalize("NFKC", slug)
    value = re.sub(r"[\\/\x00-\x1f\x7f]+", "-", value)
    value = re.sub(r"\s+", "-", value.strip())
    value = re.sub(r"[^\w.+-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-. ")
    value = value[:100].rstrip("-. ")
    return value or f"velog-{post_id[:8]}"


def choose_post_path(
    post: PostMetadata,
    published_at: str,
    used_paths: set[str],
    timezone: str,
) -> str:
    date_prefix = parse_timestamp(published_at).astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d")
    slug = safe_filename_slug(post.slug, post.id)
    candidate = f"_posts/{date_prefix}-{slug}.md"
    if candidate in used_paths:
        candidate = f"_posts/{date_prefix}-{slug}-{post.id[:8].lower()}.md"
    return candidate


def validate_post_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    post_root = (root / "_posts").resolve()
    if post_root not in path.parents or path.suffix.lower() != ".md":
        raise SourceError(f"unsafe managed post path in state: {value}")
    return path


def render_post(
    post: PostMetadata,
    body: str,
    categories: tuple[str, ...],
    published_at: str,
    timezone: str,
) -> str:
    lines = [
        "---",
        f"title: {yaml_quote(post.title.strip())}",
        f"date: {format_timestamp(published_at, timezone)}",
        f"last_modified_at: {format_timestamp(post.updated_at, timezone)}",
    ]
    if categories:
        lines.append("categories:")
        lines.extend(f"  - {yaml_quote(category)}" for category in categories)
    if has_math(body):
        lines.append("math: true")
    lines.extend(("render_with_liquid: false", "---", ""))
    return "\n".join(lines) + normalize_markdown(body)


def content_hash(
    post: PostMetadata,
    body: str,
    categories: tuple[str, ...],
    published_at: str,
    source_url: str,
    images: dict[str, Any],
) -> str:
    payload = {
        "body": normalize_markdown(body),
        "categories": categories,
        "id": post.id,
        "images": images,
        "published_at": published_at,
        "schema": TRANSFORMATION_SCHEMA,
        "slug": post.slug,
        "source_url": source_url,
        "title": post.title.strip(),
        "updated_at": post.updated_at,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(raw)


class SyncEngine:
    def __init__(
        self,
        root: Path,
        config: SyncConfig,
        graphql: GraphQLClient | None = None,
        rss: RssClient | None = None,
        images: ImageMirror | None = None,
    ):
        self.root = root.resolve()
        self.config = config
        self.graphql = graphql or GraphQLClient(
            config.graphql_url,
            config.username,
            config.page_size,
            config.max_pages,
            timeout=config.images.timeout_seconds,
            retries=config.images.retries,
        )
        self.rss = rss or RssClient(config.rss_url, config.images.timeout_seconds)
        self.images = images or ImageMirror(self.root, config.images)
        self.state_path = self.root / ".velog-sync" / "state.json"

    def _excluded(self, post: PostMetadata, source_url: str) -> bool:
        return (
            post.id.lower() in self.config.exclude_post_ids
            or normalize_slug(post.slug) in {normalize_slug(x) for x in self.config.exclude_slugs}
            or normalize_url(source_url) in {normalize_url(x) for x in self.config.exclude_urls}
        )

    def _state_entry(
        self,
        post: PostMetadata,
        path: str,
        body: str,
        categories: tuple[str, ...],
        published_at: str,
        source_url: str,
        image_records: dict[str, Any],
        rendered: str,
        body_source: str,
    ) -> dict[str, Any]:
        return {
            "body_source": body_source,
            "categories": list(categories),
            "content_hash": content_hash(post, body, categories, published_at, source_url, image_records),
            "images": image_records,
            "metadata_hash": metadata_hash(post, categories, source_url),
            "post_path": path,
            "published_at": published_at,
            "rendered_sha256": sha256_bytes(rendered.encode("utf-8")),
            "source_slug": post.slug,
            "source_updated_at": post.updated_at,
            "source_url": source_url,
            "title": post.title.strip(),
        }

    def run(self, dry_run: bool = False) -> SyncResult:
        state = load_state(self.state_path)
        inventory = self.graphql.fetch_inventory()
        if not inventory.complete:
            raise SourceError("GraphQL inventory is incomplete")

        rss_items = None
        rss_warning = None
        try:
            rss_items = self.rss.fetch_items()
        except SourceError as exc:
            rss_warning = str(exc)
        rss_by_url = {normalize_url(item.url): item for item in (rss_items or ())}
        inventory_urls = {normalize_url(canonical_url(self.config.username, post.slug)) for post in inventory.posts}
        rss_unknown = [item.url for item in (rss_items or ()) if normalize_url(item.url) not in inventory_urls]

        old_posts: dict[str, Any] = state["posts"]
        new_state = copy.deepcopy(state)
        used_paths = {
            entry.get("post_path")
            for entry in old_posts.values()
            if isinstance(entry, dict) and isinstance(entry.get("post_path"), str)
        }
        used_paths.update(
            path.relative_to(self.root).as_posix()
            for path in (self.root / "_posts").glob("*")
            if path.is_file()
        )
        outcomes: list[SyncOutcome] = []

        for post in inventory.posts:
            if post.is_private:
                continue
            source_url = canonical_url(self.config.username, post.slug)
            categories = resolved_categories(post, self.config)
            existing = old_posts.get(post.id)
            if self._excluded(post, source_url):
                outcomes.append(SyncOutcome("EXCLUDED", post, existing.get("post_path") if isinstance(existing, dict) else None, categories))
                continue
            if existing is None and self.config.import_after is not None:
                local_date = parse_timestamp(post.released_at).astimezone(ZoneInfo(self.config.timezone)).date()
                if local_date < self.config.import_after:
                    outcomes.append(SyncOutcome("EXCLUDED", post, None, categories))
                    continue

            published_at = (
                existing.get("published_at", post.released_at)
                if isinstance(existing, dict)
                else post.released_at
            )
            path = (
                existing.get("post_path")
                if isinstance(existing, dict) and isinstance(existing.get("post_path"), str)
                else choose_post_path(post, published_at, used_paths, self.config.timezone)
            )
            used_paths.add(path)
            meta_hash = metadata_hash(post, categories, source_url)
            local_path = validate_post_path(self.root, path)
            drifted = not isinstance(existing, dict) or sha256_file(local_path) != existing.get("rendered_sha256")
            image_drift = False
            if isinstance(existing, dict):
                for record in (existing.get("images") or {}).values():
                    if not isinstance(record, dict) or sha256_file(self.root / str(record.get("path", ""))) != record.get("sha256"):
                        image_drift = True
                        break
            needs_detail = (
                not isinstance(existing, dict)
                or existing.get("metadata_hash") != meta_hash
                or drifted
                or image_drift
            )
            if not needs_detail:
                warnings = [rss_warning] if rss_warning else []
                outcomes.append(SyncOutcome("UNCHANGED", post, path, categories, warnings=warnings))
                continue

            body_source = "graphql"
            try:
                detail = self.graphql.fetch_post(post)
                if not detail.is_markdown:
                    raise SourceError(f"post {post.id} is not raw Markdown")
                body = normalize_markdown(detail.body)
            except SourceError as exc:
                rss_item = rss_by_url.get(normalize_url(source_url))
                can_fallback = rss_item is not None and (
                    existing is None
                    or (isinstance(existing, dict) and existing.get("body_source") == "rss")
                )
                if not can_fallback:
                    outcomes.append(SyncOutcome("ERROR", post, path, categories, error=str(exc)))
                    continue
                body = rss_html_to_markdown(rss_item.html)
                body_source = "rss"

            urls = image_urls(body)
            existing_images = existing.get("images", {}) if isinstance(existing, dict) else {}
            plans, warnings = self.images.plan(post.id, urls, existing_images)
            if rss_warning:
                warnings.append(rss_warning)
            if rss_unknown:
                warnings.append(f"RSS contains {len(rss_unknown)} URL(s) absent from GraphQL inventory")
            fence = unclosed_fence(body)
            if fence:
                warnings.append(f"unclosed code fence at source line {fence[0]} ({fence[1]})")
            planned_records = {url: plan.state_record() for url, plan in plans.items()}
            rewritten, _ = transform_images(
                body, lambda url: "/" + plans[url].path if url in plans else url
            )
            rendered = render_post(post, rewritten, categories, published_at, self.config.timezone)
            entry = self._state_entry(
                post,
                path,
                rewritten,
                categories,
                published_at,
                source_url,
                planned_records,
                rendered,
                body_source,
            )
            same = isinstance(existing, dict) and existing == entry and sha256_file(local_path) == entry["rendered_sha256"]
            action = "UNCHANGED" if same else ("IMPORT" if existing is None else "UPDATE")
            outcomes.append(
                SyncOutcome(
                    action,
                    post,
                    path,
                    categories,
                    image_count=len(plans),
                    image_bytes=sum(plan.size for plan in plans.values() if not plan.reused),
                    warnings=warnings,
                    desired_text=rendered,
                    state_entry=entry,
                    image_plans=list(plans.values()),
                    body=body,
                    body_source=body_source,
                )
            )

        result = SyncResult(
            tuple(outcomes), inventory.page_sizes, True, None if rss_items is None else len(rss_items), False, dry_run
        )
        if dry_run or result.counts["ERROR"]:
            return result

        for outcome in outcomes:
            if outcome.action not in {"IMPORT", "UPDATE"}:
                continue
            records: dict[str, Any] = {}
            local_urls: dict[str, str] = {}
            for plan in outcome.image_plans:
                assert isinstance(plan, ImagePlan)
                record, warning = self.images.materialize(plan)
                if warning:
                    outcome.warnings.append(warning)
                if record:
                    records[plan.url] = record
                    local_urls[plan.url] = "/" + plan.path
            assert outcome.body is not None and outcome.post_path is not None
            rewritten, _ = transform_images(outcome.body, lambda url: local_urls.get(url, url))
            published_at = (
                old_posts.get(outcome.post.id, {}).get("published_at", outcome.post.released_at)
                if isinstance(old_posts.get(outcome.post.id), dict)
                else outcome.post.released_at
            )
            rendered = render_post(
                outcome.post, rewritten, outcome.categories, published_at, self.config.timezone
            )
            entry = self._state_entry(
                outcome.post,
                outcome.post_path,
                rewritten,
                outcome.categories,
                published_at,
                canonical_url(self.config.username, outcome.post.slug),
                records,
                rendered,
                outcome.body_source,
            )
            if sha256_file(self.root / outcome.post_path) != entry["rendered_sha256"]:
                atomic_write_text(self.root / outcome.post_path, rendered)
            new_state["posts"][outcome.post.id] = entry

        old_serialized = serialize_state(state)
        new_serialized = serialize_state(new_state)
        changed = old_serialized != new_serialized
        if changed:
            atomic_write_text(self.state_path, new_serialized)
        return SyncResult(
            tuple(outcomes), inventory.page_sizes, True, None if rss_items is None else len(rss_items), changed, dry_run
        )
