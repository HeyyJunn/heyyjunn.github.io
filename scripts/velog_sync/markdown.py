from __future__ import annotations

import html
import re
from html.parser import HTMLParser
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


class _HtmlToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.in_pre = False
        self.in_code = False
        self.link_stack: list[str | None] = []
        self.lists: list[str] = []

    def _newline(self, count: int = 1) -> None:
        self.parts.append("\n" * count)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        tag = tag.lower()
        if tag in {"p", "div", "section", "article"}:
            self._newline(2)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._newline(2)
            self.parts.append("#" * int(tag[1]) + " ")
        elif tag == "br":
            self._newline()
        elif tag == "blockquote":
            self._newline(2)
            self.parts.append("> ")
        elif tag in {"ul", "ol"}:
            self.lists.append(tag)
            self._newline()
        elif tag == "li":
            self._newline()
            self.parts.append("  " * max(0, len(self.lists) - 1))
            self.parts.append("1. " if self.lists and self.lists[-1] == "ol" else "- ")
        elif tag == "pre":
            self.in_pre = True
            self._newline(2)
            self.parts.append("```")
        elif tag == "code":
            classes = values.get("class") or ""
            if self.in_pre:
                language = next(
                    (part.removeprefix("language-") for part in classes.split() if part.startswith("language-")),
                    "",
                )
                self.parts.append(language + "\n")
            else:
                self.in_code = True
                self.parts.append("`")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "a":
            self.parts.append("[")
            self.link_stack.append(values.get("href"))
        elif tag == "img":
            src = values.get("src") or ""
            alt = values.get("alt") or ""
            self.parts.append(f"![{alt}]({src})")
        elif tag == "hr":
            self._newline(2)
            self.parts.append("---")
            self._newline(2)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}:
            self._newline(2)
        elif tag in {"ul", "ol"}:
            if self.lists:
                self.lists.pop()
            self._newline()
        elif tag == "pre":
            self.parts.append("\n```")
            self._newline(2)
            self.in_pre = False
        elif tag == "code" and not self.in_pre:
            self.parts.append("`")
            self.in_code = False
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "a":
            href = self.link_stack.pop() if self.link_stack else None
            self.parts.append(f"]({href})" if href else "]")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def result(self) -> str:
        text = html.unescape("".join(self.parts))
        text = re.sub(r"\n[ \t]+\n", "\n\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return normalize_markdown(text.strip())


def rss_html_to_markdown(value: str) -> str:
    parser = _HtmlToMarkdown()
    parser.feed(value)
    parser.close()
    return parser.result()
