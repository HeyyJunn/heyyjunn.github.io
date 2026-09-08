from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .models import VelogSyncError


@dataclass(frozen=True)
class ImageConfig:
    enabled: bool = True
    allowed_hosts: tuple[str, ...] = ("velog.velcdn.com",)
    max_bytes: int = 25 * 1024 * 1024
    timeout_seconds: float = 20.0
    retries: int = 3
    workers: int = 8


@dataclass(frozen=True)
class SyncConfig:
    username: str
    graphql_url: str = "https://v3.velog.io/graphql"
    rss_url: str = "https://v2.velog.io/rss/@ilwha"
    page_size: int = 20
    max_pages: int = 1000
    timezone: str = "Asia/Seoul"
    exclude_post_ids: frozenset[str] = frozenset()
    hidden_post_ids: frozenset[str] = frozenset()
    exclude_slugs: frozenset[str] = frozenset()
    exclude_urls: frozenset[str] = frozenset()
    import_after: date | None = None
    series_category_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    images: ImageConfig = ImageConfig()


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise VelogSyncError(f"{label} must be a mapping")
    return value


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise VelogSyncError(f"{label} must be a list of strings")
    return tuple(value)


def load_config(path: Path) -> SyncConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise VelogSyncError(f"Unable to read config {path}: {exc}") from exc
    root = _mapping(raw, "config")
    velog = _mapping(root.get("velog"), "velog")
    username = velog.get("username")
    if not isinstance(username, str) or not username.strip():
        raise VelogSyncError("velog.username is required")

    import_after = root.get("import_after")
    if import_after is not None:
        if isinstance(import_after, date):
            parsed_after = import_after
        elif isinstance(import_after, str):
            try:
                parsed_after = date.fromisoformat(import_after)
            except ValueError as exc:
                raise VelogSyncError("import_after must use YYYY-MM-DD") from exc
        else:
            raise VelogSyncError("import_after must be null or YYYY-MM-DD")
    else:
        parsed_after = None

    raw_map = _mapping(root.get("series_category_map"), "series_category_map")
    category_map: dict[str, tuple[str, ...]] = {}
    for series_name, categories in raw_map.items():
        if not isinstance(series_name, str):
            raise VelogSyncError("series_category_map keys must be strings")
        parsed = _string_list(categories, f"series_category_map.{series_name}")
        if not 1 <= len(parsed) <= 2:
            raise VelogSyncError("each series mapping must contain one or two categories")
        category_map[series_name] = parsed

    image_raw = _mapping(root.get("images"), "images")
    enabled = image_raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise VelogSyncError("images.enabled must be true or false")
    images = ImageConfig(
        enabled=enabled,
        allowed_hosts=_string_list(
            image_raw.get("allowed_hosts", ["velog.velcdn.com"]), "images.allowed_hosts"
        ),
        max_bytes=int(image_raw.get("max_bytes", 25 * 1024 * 1024)),
        timeout_seconds=float(image_raw.get("timeout_seconds", 20)),
        retries=int(image_raw.get("retries", 3)),
        workers=int(image_raw.get("workers", 8)),
    )
    if images.max_bytes <= 0 or images.timeout_seconds <= 0:
        raise VelogSyncError("image size and timeout limits must be positive")
    if images.retries <= 0 or images.workers <= 0:
        raise VelogSyncError("image retries and workers must be positive")

    page_size = int(velog.get("page_size", 20))
    max_pages = int(velog.get("max_pages", 1000))
    if page_size <= 0 or max_pages <= 0:
        raise VelogSyncError("velog.page_size and velog.max_pages must be positive")

    return SyncConfig(
        username=username.strip().lstrip("@"),
        graphql_url=str(velog.get("graphql_url", "https://v3.velog.io/graphql")),
        rss_url=str(velog.get("rss_url", f"https://v2.velog.io/rss/@{username.strip().lstrip('@')}")),
        page_size=page_size,
        max_pages=max_pages,
        timezone=str(root.get("timezone", "Asia/Seoul")),
        exclude_post_ids=frozenset(x.lower() for x in _string_list(root.get("exclude_post_ids"), "exclude_post_ids")),
        hidden_post_ids=frozenset(x.lower() for x in _string_list(root.get("hidden_post_ids"), "hidden_post_ids")),
        exclude_slugs=frozenset(_string_list(root.get("exclude_slugs"), "exclude_slugs")),
        exclude_urls=frozenset(_string_list(root.get("exclude_urls"), "exclude_urls")),
        import_after=parsed_after,
        series_category_map=category_map,
        images=images,
    )
