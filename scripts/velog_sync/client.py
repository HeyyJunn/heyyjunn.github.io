from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from .models import DetailedPost, Inventory, PostMetadata, RssItem, Series, SourceError


POSTS_QUERY = """
query velogPosts($input: GetPostsInput!) {
  posts(input: $input) {
    id title url_slug released_at updated_at is_private thumbnail
    series { id name url_slug }
  }
}
"""

READ_POST_QUERY = """
query readPost($input: ReadPostInput!) {
  post(input: $input) {
    id title url_slug released_at updated_at is_private thumbnail
    body is_markdown
    series { id name url_slug }
  }
}
"""


class JsonTransport:
    def __init__(self, endpoint: str, timeout: float = 20.0, retries: int = 3):
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = max(1, retries)

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "heyyjunn-velog-sync/1"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    if response.status != 200:
                        raise SourceError(f"GraphQL HTTP {response.status}")
                try:
                    decoded = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise SourceError(f"GraphQL returned malformed JSON: {exc}") from exc
                if not isinstance(decoded, dict):
                    raise SourceError("GraphQL response root is not an object")
                return decoded
            except (urllib.error.URLError, TimeoutError, OSError, SourceError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(0.4 * (2**attempt))
        raise SourceError(f"GraphQL request failed after {self.retries} attempts: {last_error}")


class GraphQLClient:
    def __init__(
        self,
        endpoint: str,
        username: str,
        page_size: int = 20,
        max_pages: int = 1000,
        timeout: float = 20.0,
        retries: int = 3,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.username = username
        self.page_size = page_size
        self.max_pages = max_pages
        self.transport = transport or JsonTransport(endpoint, timeout, retries)

    def _execute(self, operation: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = self.transport(
            {"operationName": operation, "query": query, "variables": variables}
        )
        if response.get("errors"):
            raise SourceError(f"GraphQL {operation} errors: {response['errors']}")
        data = response.get("data")
        if not isinstance(data, dict):
            raise SourceError(f"GraphQL {operation} response is missing data")
        return data

    @staticmethod
    def _required(obj: dict[str, Any], key: str, expected: type) -> Any:
        if key not in obj or not isinstance(obj[key], expected):
            raise SourceError(f"post field {key!r} is missing or invalid")
        return obj[key]

    def _parse_metadata(self, raw: Any) -> PostMetadata:
        if not isinstance(raw, dict):
            raise SourceError("post entry is not an object")
        post_id = self._required(raw, "id", str)
        title = self._required(raw, "title", str)
        slug = self._required(raw, "url_slug", str)
        released_at = self._required(raw, "released_at", str)
        updated_at = self._required(raw, "updated_at", str)
        is_private = self._required(raw, "is_private", bool)
        thumbnail = raw.get("thumbnail")
        if thumbnail is not None and not isinstance(thumbnail, str):
            raise SourceError(f"post {post_id} has invalid thumbnail metadata")
        if "series" not in raw:
            raise SourceError(f"post {post_id} is missing authoritative series metadata")
        series_raw = raw["series"]
        series = None
        if series_raw is not None:
            if not isinstance(series_raw, dict):
                raise SourceError(f"post {post_id} has invalid series metadata")
            series = Series(
                id=self._required(series_raw, "id", str),
                name=self._required(series_raw, "name", str),
                slug=self._required(series_raw, "url_slug", str),
            )
        return PostMetadata(
            id=post_id,
            title=title,
            slug=slug,
            released_at=released_at,
            updated_at=updated_at,
            series=series,
            is_private=is_private,
            thumbnail=thumbnail,
        )

    def fetch_inventory(self) -> Inventory:
        posts: list[PostMetadata] = []
        page_sizes: list[int] = []
        seen_ids: set[str] = set()
        seen_cursors: set[str] = set()
        cursor: str | None = None

        for _ in range(self.max_pages):
            input_data: dict[str, Any] = {
                "username": self.username,
                "limit": self.page_size,
            }
            if cursor is not None:
                input_data["cursor"] = cursor
            data = self._execute("velogPosts", POSTS_QUERY, {"input": input_data})
            raw_page = data.get("posts")
            if not isinstance(raw_page, list):
                raise SourceError("GraphQL inventory is missing data.posts")
            page_sizes.append(len(raw_page))
            if not raw_page:
                return Inventory(tuple(posts), tuple(page_sizes), True)
            page = [self._parse_metadata(item) for item in raw_page]
            next_cursor = page[-1].id
            if next_cursor in seen_cursors:
                raise SourceError(f"repeated GraphQL cursor: {next_cursor}")
            for post in page:
                if post.id in seen_ids:
                    raise SourceError(f"duplicate post UUID in inventory: {post.id}")
                seen_ids.add(post.id)
                posts.append(post)
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise SourceError(f"inventory exceeded maximum safety page limit ({self.max_pages})")

    def fetch_post(self, expected: PostMetadata) -> DetailedPost:
        data = self._execute(
            "readPost",
            READ_POST_QUERY,
            {"input": {"username": self.username, "url_slug": expected.slug}},
        )
        raw = data.get("post")
        if not isinstance(raw, dict):
            raise SourceError(f"readPost returned no post for {expected.slug}")
        metadata = self._parse_metadata(raw)
        if metadata.id != expected.id:
            raise SourceError(
                f"list/readPost UUID mismatch for {expected.slug}: "
                f"{expected.id} != {metadata.id}"
            )
        if (
            metadata.title != expected.title
            or metadata.slug != expected.slug
            or metadata.released_at != expected.released_at
            or metadata.updated_at != expected.updated_at
            or metadata.series != expected.series
            or metadata.is_private != expected.is_private
            or metadata.thumbnail != expected.thumbnail
        ):
            raise SourceError(f"list/readPost metadata mismatch for UUID {expected.id}")
        body = raw.get("body")
        is_markdown = raw.get("is_markdown")
        if not isinstance(body, str) or not isinstance(is_markdown, bool):
            raise SourceError(f"readPost body metadata is incomplete for UUID {expected.id}")
        return DetailedPost(metadata, body, is_markdown)


class RssClient:
    def __init__(
        self,
        url: str,
        timeout: float = 20.0,
        fetcher: Callable[[], bytes] | None = None,
    ):
        self.url = url
        self.timeout = timeout
        self.fetcher = fetcher or self._fetch

    def _fetch(self) -> bytes:
        request = urllib.request.Request(
            self.url, headers={"User-Agent": "heyyjunn-velog-sync/1"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def fetch_items(self) -> tuple[RssItem, ...]:
        try:
            root = ET.fromstring(self.fetcher())
        except (OSError, ET.ParseError, urllib.error.URLError) as exc:
            raise SourceError(f"RSS request failed: {exc}") from exc
        items: list[RssItem] = []
        for item in root.findall("./channel/item"):
            values = {name: item.findtext(name) for name in ("title", "link", "guid", "pubDate")}
            if any(value is None for value in values.values()):
                raise SourceError("RSS item is missing a required field")
            try:
                parsedate_to_datetime(values["pubDate"] or "")
            except (TypeError, ValueError) as exc:
                raise SourceError("RSS item contains an invalid pubDate") from exc
            items.append(
                RssItem(
                    title=values["title"] or "",
                    url=values["link"] or "",
                    guid=values["guid"] or "",
                    published_at=values["pubDate"] or "",
                )
            )
        return tuple(items)
