from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class VelogSyncError(RuntimeError):
    """Base error for a safe, user-facing synchronization failure."""


class SourceError(VelogSyncError):
    """Raised when a remote source is incomplete or invalid."""


class ImageError(VelogSyncError):
    """Raised when an image cannot be safely mirrored."""


@dataclass(frozen=True)
class Series:
    id: str
    name: str
    slug: str


@dataclass(frozen=True)
class PostMetadata:
    id: str
    title: str
    slug: str
    released_at: str
    updated_at: str
    series: Series | None
    is_private: bool = False
    thumbnail: str | None = None
    preview_description: str | None = None


@dataclass(frozen=True)
class DetailedPost:
    metadata: PostMetadata
    body: str
    is_markdown: bool


@dataclass(frozen=True)
class Inventory:
    posts: tuple[PostMetadata, ...]
    page_sizes: tuple[int, ...]
    complete: bool


@dataclass(frozen=True)
class RssItem:
    title: str
    url: str
    guid: str
    published_at: str


@dataclass
class SyncOutcome:
    action: str
    post: PostMetadata
    post_path: str | None
    categories: tuple[str, ...]
    image_count: int = 0
    image_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    desired_text: str | None = None
    state_entry: dict[str, Any] | None = None
    image_plans: list[Any] = field(default_factory=list)
    body: str | None = None
    body_source: str = "graphql"
    thumbnail: dict[str, Any] | None = None
    thumbnail_plan: Any | None = None
    thumbnail_change: str = "none"
    preview_description_change: str = "none"
