#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from velog_sync.config import load_config  # noqa: E402
from velog_sync.models import VelogSyncError  # noqa: E402
from velog_sync.sync import SyncEngine  # noqa: E402


def format_values(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "(none)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize public Velog posts into Chirpy")
    parser.add_argument("--dry-run", action="store_true", help="inspect without changing repository files")
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT / ".velog-sync" / "config.yml",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        result = SyncEngine(REPOSITORY_ROOT, config).run(dry_run=args.dry_run)
    except VelogSyncError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    print(f"Velog user: {config.username}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print(f"GraphQL pages fetched: {' -> '.join(map(str, result.page_sizes))}")
    print(f"Inventory complete: {'yes' if result.inventory_complete else 'no'}")
    print(f"Total posts: {len(result.outcomes)}")
    print(f"RSS recent items: {result.rss_count if result.rss_count is not None else 'unavailable'}")
    print()
    for index, outcome in enumerate(result.outcomes, 1):
        post = outcome.post
        print(f"{index}. [{outcome.action}] {post.title.strip()}")
        print(f"   UUID: {post.id}")
        print(f"   Slug: {post.slug}")
        print(f"   Path: {outcome.post_path or '(none)'}")
        print(f"   Series: {post.series.name if post.series else '(none)'}")
        print(f"   Categories: {format_values(outcome.categories)}")
        print(f"   Images: {outcome.image_count}")
        source = outcome.thumbnail.get("kind") if outcome.thumbnail else "none"
        print(f"   Thumbnail: {source} ({outcome.thumbnail_change})")
        description = "present" if post.preview_description is not None else "none"
        print(
            f"   Preview description: {description} "
            f"({outcome.preview_description_change})"
        )
        if outcome.error:
            print(f"   ERROR: {outcome.error}")
        for warning in outcome.warnings:
            print(f"   WARNING: {warning}")
    counts = result.counts
    print("\nSUMMARY")
    for key in ("IMPORT", "UPDATE", "UNCHANGED", "EXCLUDED", "HIDDEN", "ERROR"):
        print(f"{key}: {counts[key]}")
    print(f"WARNINGS: {result.warning_count}")
    print(f"IMAGES: {result.image_count}")
    print(f"IMAGE_BYTES: {result.image_bytes}")
    for change in ("added", "changed", "removed", "none", "unchanged"):
        count = sum(
            1
            for outcome in result.outcomes
            if outcome.action not in {"HIDDEN", "EXCLUDED", "ERROR"}
            and outcome.thumbnail_change == change
        )
        print(f"THUMBNAIL_{change.upper()}: {count}")
    for change in ("added", "changed", "removed", "none", "unchanged"):
        count = sum(
            1
            for outcome in result.outcomes
            if outcome.action not in {"HIDDEN", "EXCLUDED", "ERROR"}
            and outcome.preview_description_change == change
        )
        print(f"PREVIEW_DESCRIPTION_{change.upper()}: {count}")
    return 2 if counts["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
