from __future__ import annotations

import re
from typing import Callable


_OPEN_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_MARKDOWN_IMAGE = re.compile(
    r"!\[([^\]]*)\]\((<?)(https://[^\s)>]+)(>?)([^)]*)\)"
)
_HTML_IMAGE = re.compile(
    r"(<img\b[^>]*?\bsrc\s*=\s*[\"'])(https://[^\"']+)([\"'][^>]*>)",
    re.IGNORECASE,
)


def normalize_markdown(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip("\n") + "\n"


def _opening_fence(line: str) -> tuple[str, int] | None:
    match = _OPEN_FENCE.match(line)
    if not match:
        return None
    markers, info = match.groups()
    if markers[0] == "`" and "`" in info:
        return None
    return markers[0], len(markers)


def _closing_fence(line: str, char: str, length: int) -> bool:
    return bool(re.match(rf"^ {{0,3}}{re.escape(char)}{{{length},}}\s*$", line))


def unclosed_fence(body: str) -> tuple[int, str] | None:
    active: tuple[str, int, int] | None = None
    for number, line in enumerate(body.splitlines(), 1):
        if active is None:
            opened = _opening_fence(line)
            if opened:
                active = (opened[0], opened[1], number)
        elif _closing_fence(line, active[0], active[1]):
            active = None
    if active:
        return active[2], active[0] * active[1]
    return None


def has_math(body: str) -> bool:
    outside: list[str] = []
    active: tuple[str, int] | None = None
    for line in body.splitlines():
        if active is None:
            opened = _opening_fence(line)
            if opened:
                active = opened
            else:
                outside.append(line)
        elif _closing_fence(line, active[0], active[1]):
            active = None
    text = "\n".join(outside)
    if re.search(r"^\s*\$\$.*?\$\$\s*$", text, re.MULTILINE | re.DOTALL):
        return True
    return bool(
        re.search(r"(?<!\$)\$(?!\$)(?!\s)(?:\\.|[^$\n])+?(?<!\s)\$(?!\$)", text)
    )


def transform_images(
    body: str, resolver: Callable[[str], str]
) -> tuple[str, tuple[str, ...]]:
    """Rewrite image destinations outside fenced code while preserving other bytes."""

    active: tuple[str, int] | None = None
    found: list[str] = []
    cache: dict[str, str] = {}

    def resolve(url: str) -> str:
        found.append(url)
        if url not in cache:
            cache[url] = resolver(url)
        return cache[url]

    def markdown_replacement(match: re.Match[str]) -> str:
        alt, left, url, right, suffix = match.groups()
        return f"![{alt}]({left}{resolve(url)}{right}{suffix})"

    def html_replacement(match: re.Match[str]) -> str:
        return f"{match.group(1)}{resolve(match.group(2))}{match.group(3)}"

    output: list[str] = []
    for line in body.splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        if active is None:
            opened = _opening_fence(plain)
            if opened:
                active = opened
                output.append(line)
                continue
            line = _MARKDOWN_IMAGE.sub(markdown_replacement, line)
            line = _HTML_IMAGE.sub(html_replacement, line)
            output.append(line)
        else:
            output.append(line)
            if _closing_fence(plain, active[0], active[1]):
                active = None
    return "".join(output), tuple(found)


def image_urls(body: str) -> tuple[str, ...]:
    _, urls = transform_images(body, lambda url: url)
    return urls
