from __future__ import annotations

import hashlib
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import ImageConfig
from .models import ImageError
from .state import sha256_bytes, sha256_file


MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}

SAFE_UPLOAD_MIME_EXTENSIONS = {
    key: value for key, value in MIME_EXTENSIONS.items() if key != "image/svg+xml"
}


def detect_image_content_type(data: bytes) -> str | None:
    """Identify safe raster formats from bytes; filenames and client MIME are untrusted."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        box_size = int.from_bytes(data[:4], "big")
        if box_size < 12 or box_size > len(data):
            return None
        brands = data[8:box_size]
        if b"avif" in brands or b"avis" in brands:
            return "image/avif"
    return None


def post_image_directory(repository_root: Path, post_id: str) -> Path:
    """Return a validated, UUID-scoped image directory inside the repository."""

    try:
        valid_id = str(uuid.UUID(post_id))
    except (ValueError, AttributeError) as exc:
        raise ImageError(f"unsafe post UUID for image path: {post_id}") from exc
    if valid_id != post_id.lower():
        raise ImageError(f"unsafe post UUID for image path: {post_id}")
    root = (repository_root.resolve() / "assets" / "img" / "velog").resolve()
    target = root / valid_id
    if target.parent != root:
        raise ImageError(f"unsafe image directory: {target}")
    return target


def remove_post_images(repository_root: Path, post_id: str) -> bool:
    """Remove deployable image files for a hidden post, preserving its state metadata."""

    target = post_image_directory(repository_root, post_id)
    if not target.exists():
        return False
    if target.is_symlink() or not target.is_dir():
        raise ImageError(f"unsafe image directory: {target}")
    shutil.rmtree(target)
    return True


def prune_post_images(
    repository_root: Path,
    post_id: str,
    keep_paths: set[str],
    managed_paths: set[str],
) -> None:
    """Remove stale managed files without touching unknown files in the UUID directory."""

    target = post_image_directory(repository_root, post_id)
    if not target.exists():
        return
    if target.is_symlink() or not target.is_dir():
        raise ImageError(f"unsafe image directory: {target}")
    keep = {(repository_root.resolve() / path).resolve() for path in keep_paths}
    managed = {(repository_root.resolve() / path).resolve() for path in managed_paths}
    for child in target.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ImageError(f"unsafe file in managed image directory: {child}")
        if child.resolve() in managed and child.resolve() not in keep:
            child.unlink()
    if not any(target.iterdir()):
        target.rmdir()


def override_source_file(repository_root: Path, post_id: str, source_path: str) -> Path:
    try:
        valid_id = str(uuid.UUID(post_id))
    except (ValueError, AttributeError) as exc:
        raise ImageError(f"unsafe post UUID for thumbnail override: {post_id}") from exc
    if valid_id != post_id.lower() or "\\" in source_path:
        raise ImageError(f"unsafe thumbnail override source: {source_path}")
    root = (repository_root.resolve() / ".velog-sync" / "thumbnail-overrides" / valid_id).resolve()
    candidate = (repository_root.resolve() / source_path).resolve()
    if candidate.parent != root or candidate.name in {"", ".", ".."}:
        raise ImageError(f"unsafe thumbnail override source: {source_path}")
    if candidate.is_symlink():
        raise ImageError(f"thumbnail override may not be a symlink: {source_path}")
    return candidate


@dataclass(frozen=True)
class ImageProbe:
    url: str
    content_type: str
    size: int
    final_url: str


@dataclass(frozen=True)
class ImagePlan:
    url: str
    path: str
    content_type: str
    size: int
    reused: bool = False
    content_hash: str | None = None
    source_path: str | None = None

    def state_record(self, content_hash: str | None = None, size: int | None = None) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "path": self.path,
            "sha256": content_hash if content_hash is not None else self.content_hash,
            "size": self.size if size is None else size,
        }


class ImageMirror:
    def __init__(
        self,
        repository_root: Path,
        config: ImageConfig,
        probe_func: Callable[[str], ImageProbe] | None = None,
        download_func: Callable[[str], tuple[str, bytes, str]] | None = None,
    ):
        self.root = repository_root.resolve()
        self.config = config
        self.probe_func = probe_func or self._probe
        self.download_func = download_func or self._download

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ImageError(f"image URL must use HTTPS: {url}")
        if parsed.hostname not in self.config.allowed_hosts:
            raise ImageError(f"image host is not allowed: {parsed.hostname}")

    def _validate_probe(self, probe: ImageProbe) -> None:
        self._validate_url(probe.url)
        self._validate_url(probe.final_url)
        if probe.content_type not in MIME_EXTENSIONS:
            raise ImageError(f"unsupported image MIME {probe.content_type}: {probe.url}")
        if probe.size < 0 or probe.size > self.config.max_bytes:
            raise ImageError(f"image exceeds maximum size: {probe.url}")

    def _request(self, request: urllib.request.Request):
        last_error: Exception | None = None
        for attempt in range(max(1, self.config.retries)):
            try:
                return urllib.request.urlopen(request, timeout=self.config.timeout_seconds)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 < self.config.retries:
                    time.sleep(0.4 * (2**attempt))
        raise ImageError(f"image request failed: {request.full_url}: {last_error}")

    def _probe(self, url: str) -> ImageProbe:
        self._validate_url(url)
        request = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "heyyjunn-velog-sync/1"}
        )
        with self._request(request) as response:
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            if content_type == "application/octet-stream" and urllib.parse.urlparse(url).path.lower().endswith(".avif"):
                content_type = "image/avif"
            try:
                size = int(response.headers.get("Content-Length") or 0)
            except ValueError:
                size = 0
            probe = ImageProbe(url, content_type, size, response.geturl())
            self._validate_probe(probe)
            return probe

    def _download(self, url: str) -> tuple[str, bytes, str]:
        self._validate_url(url)
        request = urllib.request.Request(
            url, method="GET", headers={"User-Agent": "heyyjunn-velog-sync/1"}
        )
        with self._request(request) as response:
            final_url = response.geturl()
            self._validate_url(final_url)
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > self.config.max_bytes:
                raise ImageError(f"downloaded image exceeds maximum size: {url}")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.config.max_bytes:
                    raise ImageError(f"downloaded image exceeds maximum size: {url}")
                chunks.append(chunk)
            data = b"".join(chunks)
            if content_type == "application/octet-stream" and urllib.parse.urlparse(url).path.lower().endswith(".avif"):
                content_type = detect_image_content_type(data) or content_type
            if content_type not in MIME_EXTENSIONS:
                raise ImageError(f"unsupported downloaded image MIME {content_type}: {url}")
            return content_type, data, final_url

    def _safe_target(self, post_id: str, url: str, extension: str) -> tuple[str, Path]:
        image_dir = post_image_directory(self.root, post_id)
        valid_id = image_dir.name
        name = hashlib.sha256(url.encode("utf-8")).hexdigest() + extension
        relative = image_dir.relative_to(self.root) / name
        target = (self.root / relative).resolve()
        image_root = (self.root / "assets" / "img" / "velog").resolve()
        if target != image_root and image_root not in target.parents:
            raise ImageError(f"unsafe image destination: {target}")
        return relative.as_posix(), target

    def _safe_content_target(
        self, post_id: str, digest: str, extension: str
    ) -> tuple[str, Path]:
        image_dir = post_image_directory(self.root, post_id)
        name = digest.removeprefix("sha256:") + extension
        relative = image_dir.relative_to(self.root) / name
        return relative.as_posix(), self.root / relative

    def _reusable(self, record: Any) -> ImagePlan | None:
        if not isinstance(record, dict):
            return None
        path = record.get("path")
        expected_hash = record.get("sha256")
        content_type = record.get("content_type")
        size = record.get("size")
        if (
            not isinstance(path, str)
            or not isinstance(expected_hash, str)
            or content_type not in MIME_EXTENSIONS
            or not isinstance(size, int)
        ):
            return None
        target = (self.root / path).resolve()
        allowed = (self.root / "assets" / "img" / "velog").resolve()
        if allowed not in target.parents or sha256_file(target) != expected_hash:
            return None
        return ImagePlan("", path, content_type, size, True, expected_hash)

    def plan(
        self, post_id: str, urls: tuple[str, ...], existing: dict[str, Any] | None = None
    ) -> tuple[dict[str, ImagePlan], list[str]]:
        existing = existing or {}
        unique = tuple(dict.fromkeys(urls))
        if not self.config.enabled:
            return {}, []
        plans: dict[str, ImagePlan] = {}
        warnings: list[str] = []
        to_probe: list[str] = []
        for url in unique:
            reusable = self._reusable(existing.get(url))
            if reusable:
                plans[url] = ImagePlan(
                    url, reusable.path, reusable.content_type, reusable.size, True, reusable.content_hash
                )
            else:
                to_probe.append(url)

        def probe_safely(url: str) -> tuple[str, ImageProbe | None, str | None]:
            try:
                return url, self.probe_func(url), None
            except Exception as exc:
                return url, None, str(exc)

        if to_probe:
            with ThreadPoolExecutor(max_workers=max(1, self.config.workers)) as executor:
                results = executor.map(probe_safely, to_probe)
                for url, probe, error in results:
                    if error or probe is None:
                        warnings.append(f"image mirror probe failed; keeping remote URL: {url}: {error}")
                        continue
                    try:
                        self._validate_probe(probe)
                        relative, _ = self._safe_target(
                            post_id, url, MIME_EXTENSIONS[probe.content_type]
                        )
                        plans[url] = ImagePlan(url, relative, probe.content_type, probe.size)
                    except ImageError as exc:
                        warnings.append(f"image mirror rejected; keeping remote URL: {exc}")
        return plans, warnings

    def plan_local(
        self, post_id: str, source_path: str, existing: dict[str, Any] | None = None
    ) -> ImagePlan:
        source = override_source_file(self.root, post_id, source_path)
        if not source.is_file():
            raise ImageError(f"thumbnail override file is missing: {source_path}")
        size = source.stat().st_size
        if size <= 0 or size > self.config.max_bytes:
            raise ImageError(f"thumbnail override exceeds maximum size: {source_path}")
        data = source.read_bytes()
        content_type = detect_image_content_type(data)
        if content_type not in SAFE_UPLOAD_MIME_EXTENSIONS:
            raise ImageError(f"thumbnail override is not a supported raster image: {source_path}")
        digest = sha256_bytes(data)
        relative, _ = self._safe_content_target(
            post_id, digest, SAFE_UPLOAD_MIME_EXTENSIONS[content_type]
        )
        reusable = self._reusable(existing)
        if reusable and reusable.path == relative and reusable.content_hash == digest:
            return ImagePlan(
                "", relative, content_type, size, True, digest, source_path
            )
        return ImagePlan("", relative, content_type, size, False, digest, source_path)

    def materialize(self, plan: ImagePlan) -> tuple[dict[str, Any] | None, str | None]:
        if plan.reused:
            return plan.state_record(), None
        try:
            if plan.source_path:
                source = override_source_file(self.root, Path(plan.path).parent.name, plan.source_path)
                data = source.read_bytes()
                content_type = detect_image_content_type(data) or ""
                if sha256_bytes(data) != plan.content_hash:
                    raise ImageError(f"thumbnail override changed while syncing: {plan.source_path}")
            else:
                content_type, data, final_url = self.download_func(plan.url)
                self._validate_url(final_url)
            if content_type not in MIME_EXTENSIONS or content_type != plan.content_type:
                raise ImageError(
                    f"download MIME mismatch for {plan.url or plan.source_path}: "
                    f"{plan.content_type} != {content_type}"
                )
            if len(data) > self.config.max_bytes:
                raise ImageError(f"downloaded image exceeds maximum size: {plan.url}")
            expected_extension = MIME_EXTENSIONS[content_type]
            if not plan.path.endswith(expected_extension):
                raise ImageError(f"unsafe image extension mismatch: {plan.path}")
            target = (self.root / plan.path).resolve()
            allowed = (self.root / "assets" / "img" / "velog").resolve()
            if allowed not in target.parents:
                raise ImageError(f"unsafe image destination: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            part = Path(str(target) + ".part")
            try:
                with part.open("wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(part, target)
            finally:
                if part.exists():
                    part.unlink()
            digest = sha256_bytes(data)
            return plan.state_record(digest, len(data)), None
        except Exception as exc:
            source = plan.url or plan.source_path or "unknown"
            return None, f"image download failed: {source}: {exc}"
