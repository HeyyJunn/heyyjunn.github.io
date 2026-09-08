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
from .images import ImageMirror, ImagePlan, prune_post_images, remove_post_images
from .markdown import has_math, image_urls, normalize_markdown, transform_images, unclosed_fence
from .models import ImageError, PostMetadata, SourceError, SyncOutcome
from .state import atomic_write_text, load_state, serialize_state, sha256_bytes, sha256_file


TRANSFORMATION_SCHEMA = 4


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
        result = {key: 0 for key in ("IMPORT", "UPDATE", "UNCHANGED", "EXCLUDED", "HIDDEN", "ERROR")}
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


def metadata_hash(
    post: PostMetadata,
    categories: tuple[str, ...],
    source_url: str,
    thumbnail_input: dict[str, Any] | None,
) -> str:
    payload = {
        "categories": categories,
        "id": post.id,
        "preview_description": post.preview_description,
        "released_at": post.released_at,
        "schema": TRANSFORMATION_SCHEMA,
        "slug": post.slug,
        "source_url": source_url,
        "thumbnail": thumbnail_input,
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
    thumbnail: dict[str, Any] | None = None,
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
    if thumbnail:
        lines.extend(
            (
                "thumbnail:",
                f"  path: {yaml_quote('/' + str(thumbnail['path']).lstrip('/'))}",
                f"  alt: {yaml_quote(post.title.strip())}",
            )
        )
    if post.preview_description is not None:
        lines.append(
            f"preview_description: {yaml_quote(post.preview_description)}"
        )
    if has_math(body):
        lines.append("math: true")
    lines.extend(("render_with_liquid: false", "---", ""))
    return "\n".join(lines) + normalize_markdown(body)


def content_hash(
    post: PostMetadata,
    body: str,
    categories: tuple[str, ...],
    published_at: str,
    images: dict[str, Any],
    thumbnail: dict[str, Any] | None,
) -> str:
    payload = {
        "body": normalize_markdown(body),
        "categories": categories,
        "id": post.id,
        "images": images,
        "published_at": published_at,
        "preview_description": post.preview_description,
        "released_at": post.released_at,
        "schema": TRANSFORMATION_SCHEMA,
        "source_slug": post.slug,
        "thumbnail": thumbnail,
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

    def _excluded(self, post: PostMetadata) -> bool:
        return post.id.lower() in self.config.exclude_post_ids

    @staticmethod
    def _thumbnail_identity(value: Any) -> tuple[str, str] | None:
        if not isinstance(value, dict):
            return None
        kind = value.get("kind")
        source = value.get("source_url") if kind == "velog" else value.get("source_path")
        if isinstance(kind, str) and isinstance(source, str):
            return kind, source
        return None

    @classmethod
    def _thumbnail_change(cls, old: Any, new: Any) -> str:
        old_identity = cls._thumbnail_identity(old)
        new_identity = cls._thumbnail_identity(new)
        if old_identity is None and new_identity is None:
            return "none"
        if old_identity is None:
            return "added"
        if new_identity is None:
            return "removed"
        return "unchanged" if old_identity == new_identity else "changed"

    @staticmethod
    def _preview_description_change(old: Any, new: str | None) -> str:
        old_value = old if isinstance(old, str) and old.strip() else None
        if old_value is None and new is None:
            return "none"
        if old_value is None:
            return "added"
        if new is None:
            return "removed"
        return "unchanged" if old_value == new else "changed"

    def _state_entry(
        self,
        post: PostMetadata,
        path: str,
        body: str,
        categories: tuple[str, ...],
        published_at: str,
        source_url: str,
        image_records: dict[str, Any],
        thumbnail: dict[str, Any] | None,
        rendered: str,
        body_source: str,
    ) -> dict[str, Any]:
        return {
            "body_source": body_source,
            "categories": list(categories),
            "content_hash": content_hash(
                post, body, categories, published_at, image_records, thumbnail
            ),
            "images": image_records,
            "metadata_hash": metadata_hash(
                post,
                categories,
                source_url,
                self._thumbnail_hash_input(post, thumbnail),
            ),
            "post_path": path,
            "preview_description": post.preview_description,
            "published_at": published_at,
            "rendered_sha256": sha256_bytes(rendered.encode("utf-8")),
            "source_slug": post.slug,
            "source_updated_at": post.updated_at,
            "source_url": source_url,
            "thumbnail": thumbnail,
            "title": post.title.strip(),
        }

    @staticmethod
    def _thumbnail_hash_input(
        post: PostMetadata, thumbnail: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if post.thumbnail:
            return {"kind": "velog", "source_url": post.thumbnail}
        if isinstance(thumbnail, dict) and thumbnail.get("kind") == "override":
            return {
                "kind": "override",
                "source_path": thumbnail.get("source_path"),
                "sha256": thumbnail.get("sha256"),
            }
        return None

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
            existing_thumbnail = existing.get("thumbnail") if isinstance(existing, dict) else None
            existing_preview_description = (
                existing.get("preview_description") if isinstance(existing, dict) else None
            )
            if post.id.lower() in self.config.hidden_post_ids:
                outcomes.append(
                    SyncOutcome(
                        "HIDDEN",
                        post,
                        existing.get("post_path") if isinstance(existing, dict) else None,
                        categories,
                        thumbnail_change="none",
                        preview_description_change="none",
                    )
                )
                continue
            if self._excluded(post):
                outcomes.append(SyncOutcome("EXCLUDED", post, existing.get("post_path") if isinstance(existing, dict) else None, categories))
                continue
            if existing is None and self.config.import_after is not None:
                local_date = parse_timestamp(post.released_at).astimezone(ZoneInfo(self.config.timezone)).date()
                if local_date < self.config.import_after:
                    outcomes.append(SyncOutcome("EXCLUDED", post, None, categories))
                    continue

            override_plan: ImagePlan | None = None
            planned_override: dict[str, Any] | None = None
            override = self.config.thumbnail_overrides.get(post.id.lower())
            if not post.thumbnail and override is not None:
                try:
                    override_plan = self.images.plan_local(
                        post.id, override.source_path, existing_thumbnail
                    )
                    planned_override = {
                        "kind": "override",
                        "source_path": override.source_path,
                        **override_plan.state_record(),
                    }
                except ImageError as exc:
                    outcomes.append(
                        SyncOutcome(
                            "ERROR",
                            post,
                            existing.get("post_path") if isinstance(existing, dict) else None,
                            categories,
                            error=str(exc),
                        )
                    )
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
            thumbnail_hash_input = (
                {"kind": "velog", "source_url": post.thumbnail}
                if post.thumbnail
                else self._thumbnail_hash_input(post, planned_override)
            )
            meta_hash = metadata_hash(post, categories, source_url, thumbnail_hash_input)
            local_path = validate_post_path(self.root, path)
            drifted = not isinstance(existing, dict) or sha256_file(local_path) != existing.get("rendered_sha256")
            image_drift = False
            if isinstance(existing, dict):
                for record in (existing.get("images") or {}).values():
                    if not isinstance(record, dict) or sha256_file(self.root / str(record.get("path", ""))) != record.get("sha256"):
                        image_drift = True
                        break
                if not image_drift and isinstance(existing_thumbnail, dict):
                    image_drift = (
                        sha256_file(self.root / str(existing_thumbnail.get("path", "")))
                        != existing_thumbnail.get("sha256")
                    )
            needs_detail = (
                not isinstance(existing, dict)
                or existing.get("metadata_hash") != meta_hash
                or drifted
                or image_drift
                or existing.get("body_source") != "graphql"
            )
            if not needs_detail:
                warnings = [rss_warning] if rss_warning else []
                existing_paths = {
                    record.get("path")
                    for record in (existing.get("images") or {}).values()
                    if isinstance(record, dict) and isinstance(record.get("path"), str)
                }
                if isinstance(existing_thumbnail, dict) and isinstance(existing_thumbnail.get("path"), str):
                    existing_paths.add(existing_thumbnail["path"])
                outcomes.append(
                    SyncOutcome(
                        "UNCHANGED", post, path, categories,
                        image_count=len(existing_paths), warnings=warnings,
                        thumbnail=existing_thumbnail,
                        thumbnail_change=self._thumbnail_change(existing_thumbnail, existing_thumbnail),
                        preview_description_change=self._preview_description_change(
                            existing_preview_description, post.preview_description
                        ),
                    )
                )
                continue

            try:
                detail = self.graphql.fetch_post(post)
                if not detail.is_markdown:
                    raise SourceError(f"post {post.id} is not raw Markdown")
                body = normalize_markdown(detail.body)
            except SourceError as exc:
                outcomes.append(SyncOutcome("ERROR", post, path, categories, error=str(exc)))
                continue

            body_urls = image_urls(body)
            urls = body_urls + ((post.thumbnail,) if post.thumbnail else ())
            existing_images = existing.get("images", {}) if isinstance(existing, dict) else {}
            reusable_images = dict(existing_images)
            if (
                post.thumbnail
                and isinstance(existing_thumbnail, dict)
                and existing_thumbnail.get("kind") == "velog"
                and existing_thumbnail.get("source_url") == post.thumbnail
            ):
                reusable_images[post.thumbnail] = existing_thumbnail
            plans, warnings = self.images.plan(post.id, urls, reusable_images)
            if rss_warning:
                warnings.append(rss_warning)
            if rss_unknown:
                warnings.append(f"RSS contains {len(rss_unknown)} URL(s) absent from GraphQL inventory")
            fence = unclosed_fence(body)
            if fence:
                warnings.append(f"unclosed code fence at source line {fence[0]} ({fence[1]})")
            if post.thumbnail and post.thumbnail not in plans:
                outcomes.append(
                    SyncOutcome(
                        "ERROR", post, path, categories, warnings=warnings,
                        error=f"Velog thumbnail could not be mirrored safely: {post.thumbnail}",
                    )
                )
                continue
            planned_records = {
                url: plans[url].state_record() for url in body_urls if url in plans
            }
            thumbnail_plan = plans.get(post.thumbnail) if post.thumbnail else override_plan
            if post.thumbnail and thumbnail_plan:
                planned_thumbnail = {
                    "kind": "velog",
                    "source_url": post.thumbnail,
                    **thumbnail_plan.state_record(),
                }
            else:
                planned_thumbnail = planned_override
            rewritten, _ = transform_images(
                body, lambda url: "/" + plans[url].path if url in plans else url
            )
            rendered = render_post(
                post, rewritten, categories, published_at, self.config.timezone,
                planned_thumbnail,
            )
            entry = self._state_entry(
                post,
                path,
                rewritten,
                categories,
                published_at,
                source_url,
                planned_records,
                planned_thumbnail,
                rendered,
                "graphql",
            )
            rendered_same = (
                isinstance(existing, dict)
                and sha256_file(local_path) == entry["rendered_sha256"]
            )
            action = "UNCHANGED" if rendered_same else ("IMPORT" if existing is None else "UPDATE")
            outcomes.append(
                SyncOutcome(
                    action,
                    post,
                    path,
                    categories,
                    image_count=len({plan.path for plan in (*plans.values(),)})
                    + (1 if override_plan and override_plan.path not in {p.path for p in plans.values()} else 0),
                    image_bytes=sum(plan.size for plan in plans.values() if not plan.reused)
                    + (override_plan.size if override_plan and not override_plan.reused else 0),
                    warnings=warnings,
                    desired_text=rendered,
                    state_entry=entry,
                    image_plans=list(plans.values()),
                    body=body,
                    body_source="graphql",
                    thumbnail=planned_thumbnail,
                    thumbnail_plan=thumbnail_plan,
                    thumbnail_change=self._thumbnail_change(existing_thumbnail, planned_thumbnail),
                    preview_description_change=self._preview_description_change(
                        existing_preview_description, post.preview_description
                    ),
                )
            )

        result = SyncResult(
            tuple(outcomes), inventory.page_sizes, True, None if rss_items is None else len(rss_items), False, dry_run
        )
        if dry_run or result.counts["ERROR"]:
            return result

        # Hidden content is absent from the site, so its deployable image directory
        # must also be absent. State records remain intact for a future unhide.
        for post_id in self.config.hidden_post_ids:
            remove_post_images(self.root, post_id)
            hidden_entry = old_posts.get(post_id)
            if isinstance(hidden_entry, dict) and isinstance(hidden_entry.get("post_path"), str):
                hidden_post = validate_post_path(self.root, hidden_entry["post_path"])
                hidden_post.unlink(missing_ok=True)

        for outcome in outcomes:
            if outcome.state_entry is None or outcome.action not in {"IMPORT", "UPDATE", "UNCHANGED"}:
                continue
            records: dict[str, Any] = {}
            local_urls: dict[str, str] = {}
            materialized: dict[str, dict[str, Any] | None] = {}
            all_plans = list(outcome.image_plans)
            if isinstance(outcome.thumbnail_plan, ImagePlan) and all(
                plan.path != outcome.thumbnail_plan.path for plan in all_plans
            ):
                all_plans.append(outcome.thumbnail_plan)
            for plan in all_plans:
                assert isinstance(plan, ImagePlan)
                record, warning = self.images.materialize(plan)
                materialized[plan.path] = record
                if warning:
                    outcome.warnings.append(warning)
                if record:
                    if plan.url in image_urls(outcome.body or ""):
                        records[plan.url] = record
                        local_urls[plan.url] = "/" + plan.path
            thumbnail_record: dict[str, Any] | None = None
            if isinstance(outcome.thumbnail_plan, ImagePlan):
                base_record = materialized.get(outcome.thumbnail_plan.path)
                if base_record is None:
                    outcome.action = "ERROR"
                    outcome.error = "Thumbnail download failed; existing post was preserved."
                    old_entry = old_posts.get(outcome.post.id)
                    old_keep = set()
                    if isinstance(old_entry, dict):
                        old_keep.update(
                            record.get("path")
                            for record in (old_entry.get("images") or {}).values()
                            if isinstance(record, dict) and isinstance(record.get("path"), str)
                        )
                        old_thumbnail = old_entry.get("thumbnail")
                        if isinstance(old_thumbnail, dict) and isinstance(old_thumbnail.get("path"), str):
                            old_keep.add(old_thumbnail["path"])
                    created_paths = {
                        record["path"]
                        for record in materialized.values()
                        if isinstance(record, dict) and isinstance(record.get("path"), str)
                    }
                    prune_post_images(
                        self.root, outcome.post.id, old_keep, created_paths
                    )
                    continue
                thumbnail_record = dict(base_record)
                if outcome.post.thumbnail:
                    thumbnail_record.update(
                        {"kind": "velog", "source_url": outcome.post.thumbnail}
                    )
                else:
                    override = self.config.thumbnail_overrides.get(outcome.post.id.lower())
                    assert override is not None
                    thumbnail_record.update(
                        {"kind": "override", "source_path": override.source_path}
                    )
            assert outcome.body is not None and outcome.post_path is not None
            rewritten, _ = transform_images(outcome.body, lambda url: local_urls.get(url, url))
            published_at = (
                old_posts.get(outcome.post.id, {}).get("published_at", outcome.post.released_at)
                if isinstance(old_posts.get(outcome.post.id), dict)
                else outcome.post.released_at
            )
            rendered = render_post(
                outcome.post, rewritten, outcome.categories, published_at,
                self.config.timezone, thumbnail_record,
            )
            entry = self._state_entry(
                outcome.post,
                outcome.post_path,
                rewritten,
                outcome.categories,
                published_at,
                canonical_url(self.config.username, outcome.post.slug),
                records,
                thumbnail_record,
                rendered,
                outcome.body_source,
            )
            if sha256_file(self.root / outcome.post_path) != entry["rendered_sha256"]:
                atomic_write_text(self.root / outcome.post_path, rendered)
            new_state["posts"][outcome.post.id] = entry
            outcome.thumbnail = thumbnail_record
            keep_paths = {
                record["path"] for record in records.values() if isinstance(record, dict)
            }
            if thumbnail_record:
                keep_paths.add(str(thumbnail_record["path"]))
            old_entry = old_posts.get(outcome.post.id)
            previously_managed: set[str] = set()
            if isinstance(old_entry, dict):
                previously_managed.update(
                    record.get("path")
                    for record in (old_entry.get("images") or {}).values()
                    if isinstance(record, dict) and isinstance(record.get("path"), str)
                )
                old_thumbnail = old_entry.get("thumbnail")
                if isinstance(old_thumbnail, dict) and isinstance(old_thumbnail.get("path"), str):
                    previously_managed.add(old_thumbnail["path"])
            prune_post_images(
                self.root, outcome.post.id, keep_paths, previously_managed
            )

        old_serialized = serialize_state(state)
        new_serialized = serialize_state(new_state)
        changed = old_serialized != new_serialized
        if changed:
            atomic_write_text(self.state_path, new_serialized)
        return SyncResult(
            tuple(outcomes), inventory.page_sizes, True, None if rss_items is None else len(rss_items), changed, dry_run
        )
