#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from blog_admin.service import ACTION_LABELS, BlogService, CommandResult, UserInputError  # noqa: E402
from velog_sync.models import VelogSyncError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="./blog",
        description="Velog와 GitHub Pages 블로그를 관리합니다.",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("help", help="사용할 수 있는 명령을 확인합니다.")
    commands.add_parser("ui", help="한국어 로컬 관리 화면을 엽니다.").add_argument(
        "--no-browser", action="store_true", help=argparse.SUPPRESS
    )
    commands.add_parser("list", help="Velog 게시물과 동기화 상태를 표시합니다.")
    commands.add_parser("dry-run", help="파일을 바꾸지 않고 변경 사항을 확인합니다.")
    sync = commands.add_parser("sync", help="Velog 변경 사항을 로컬에 반영합니다.")
    sync.add_argument("--yes", action="store_true", help="확인 질문 없이 실행합니다.")
    commands.add_parser("test", help="Python 테스트를 실행합니다.")
    commands.add_parser("build", help="GitHub Pages 사이트를 빌드합니다.")
    commands.add_parser("check", help="테스트, 미리보기, 빌드, HTML 검사를 모두 실행합니다.")
    commands.add_parser("serve", help="로컬 블로그를 127.0.0.1:4000에서 실행합니다.")
    commands.add_parser("status", help="블로그, Git, 연결 상태를 요약합니다.")

    exclude = commands.add_parser("exclude", help="가져오지 않을 게시물을 관리합니다.")
    exclude_commands = exclude.add_subparsers(dest="exclude_command", required=True)
    exclude_commands.add_parser("list", help="가져오지 않는 게시물을 표시합니다.")
    for name in ("add", "remove"):
        child = exclude_commands.add_parser(name)
        child.add_argument("posts", nargs="+")

    hide = commands.add_parser("hide", help="게시물을 GitHub에서만 숨깁니다.")
    hide.add_argument("posts", nargs="+")
    hide.add_argument("--yes", action="store_true")
    unhide = commands.add_parser("unhide", help="GitHub 숨김을 해제합니다.")
    unhide.add_argument("posts", nargs="+")
    commands.add_parser("hidden", help="숨긴 게시물을 표시합니다.")
    commands.add_parser("remote-dry-run", help="GitHub Actions 미리보기를 요청합니다.")
    remote = commands.add_parser("remote-sync", help="GitHub Actions 동기화를 요청합니다.")
    remote.add_argument("--yes", action="store_true")
    return parser


def confirm(message: str, expected: str = "계속") -> bool:
    if not sys.stdin.isatty():
        print(f"안전을 위해 확인이 필요합니다. 실행하려면 --yes 옵션을 사용하세요.", file=sys.stderr)
        return False
    print(message)
    answer = input(f"계속하려면 '{expected}'을 입력하세요: ").strip()
    return answer == expected


def print_result(result: CommandResult) -> int:
    print(result.title)
    print(result.summary)
    if result.output:
        print("\n자세한 결과")
        print(result.output.rstrip())
    return 0 if result.ok else 1


def print_posts(service: BlogService, only: str | None = None) -> None:
    snapshot = service.snapshot(force=True)
    for item in snapshot["posts"]:
        if only and item["action"] != only:
            continue
        category = " / ".join(item["categories"]) or "없음"
        attention = " · 확인 필요" if item["attention"] else ""
        print(f"{item['number']:>2}. [{item['status']}{attention}] {item['title']}")
        print(f"    UUID: {item['id']}")
        print(f"    slug: {item['slug']} · 카테고리: {category} · 이미지: {item['image_count']}개")


def print_summary(service: BlogService) -> None:
    snapshot = service.snapshot(force=True)
    print("블로그 동기화 상태\n")
    print("Velog")
    print(f"  전체 글: {snapshot['total']}개")
    print(f"  연결 상태: {'정상' if snapshot['inventory_complete'] else '불완전'}")
    print(f"  GraphQL 전체 목록: {'정상' if snapshot['inventory_complete'] else '불완전'}")
    print(f"  최근 RSS: {'정상' if snapshot['rss_count'] is not None else '오류'}")
    print("\nGitHub.io")
    print(f"  게시됨: {snapshot['published']}개")
    for label in ACTION_LABELS.values():
        print(f"  {label}: {snapshot['counts'][label]}개")
    print(f"  확인 필요: {snapshot['warnings']}개")
    print("\nGit")
    print(f"  브랜치: {snapshot['git']['branch']}")
    print(f"  작업 폴더: {snapshot['git']['label']}")
    github = snapshot["github"]
    automatic = github.get("automatic")
    auto_label = "활성" if automatic is True else "비활성" if automatic is False else "확인할 수 없음"
    print(f"  GitHub Actions 자동 동기화: {auto_label}")


def run_check(service: BlogService) -> int:
    stages: list[str] = []

    def progress(label: str) -> None:
        stages.append(label)
        print(label + "...")

    result = service.check(progress)
    return print_result(result)


def main(argv: list[str] | None = None, service: BlogService | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {None, "help"}:
        parser.print_help()
        return 0
    service = service or BlogService(ROOT)
    try:
        if args.command == "ui":
            from blog_admin.web import create_app

            url = "http://127.0.0.1:8765"
            print("블로그 관리 페이지를 실행했습니다.")
            print(url)
            print("종료하려면 Ctrl+C를 누르세요.")
            if not args.no_browser:
                def open_browser() -> None:
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass

                threading.Timer(0.8, open_browser).start()
            create_app(service).run(host="127.0.0.1", port=8765, debug=False, threaded=True)
            return 0
        if args.command == "list":
            print("Velog 게시물 확인 중...")
            print_posts(service)
            return 0
        if args.command == "status":
            print_summary(service)
            return 0
        if args.command == "dry-run":
            print("Velog 변경 사항을 확인합니다...")
            return print_result(service.dry_run_result())
        if args.command == "sync":
            preview = service.snapshot(force=True)
            new_count = preview["counts"]["새로 등록 예정"]
            if new_count and not args.yes and not confirm(
                f"{new_count}개의 새 게시물이 생성되며 이미지도 함께 저장될 수 있습니다.\n계속하시겠습니까?",
                "동기화",
            ):
                return 1
            result = service.apply()
            lines = [f"{ACTION_LABELS[key]}: {result.counts[key]}개" for key in ACTION_LABELS]
            return print_result(CommandResult(not result.counts["ERROR"], "동기화가 완료되었습니다", "Velog 원문을 로컬 블로그에 반영했습니다.", "\n".join(lines)))
        if args.command == "test":
            return print_result(service.run_tests())
        if args.command == "build":
            return print_result(service.build())
        if args.command == "check":
            return run_check(service)
        if args.command == "serve":
            result = service.start_serve()
            print_result(result)
            print("종료하려면 Ctrl+C를 누르세요.")
            if service._serve_process:
                return service._serve_process.wait()
            return 0
        if args.command == "exclude":
            if args.exclude_command == "list":
                print_posts(service, "EXCLUDED")
                return 0
            selected = service.exclude(args.posts, args.exclude_command == "add")
            verb = "가져오기 대상에서 제외했습니다" if args.exclude_command == "add" else "다시 가져올 수 있도록 설정했습니다"
            print(f"다음 게시물을 {verb}.")
            for item in selected:
                print(f"- {item.post.title.strip()} ({item.post.id})")
            return 0
        if args.command == "hide":
            if not args.yes and not confirm(
                "선택한 글을 GitHub.io에서 숨깁니다. Velog 원문과 이미지는 삭제되지 않습니다.",
                "숨기기",
            ):
                return 1
            selected = service.hide(args.posts)
            for item in selected:
                print(f"'{item.post.title.strip()}' 글을 GitHub.io에서 숨김 처리했습니다.")
            print("Velog 원문은 삭제되지 않으며 다음 자동 동기화에서도 다시 게시되지 않습니다.")
            return 0
        if args.command == "unhide":
            selected = service.unhide(args.posts)
            for item in selected:
                print(f"'{item.post.title.strip()}' 글의 숨김을 해제했습니다.")
            print("다음 동기화에서 Velog 원문을 기준으로 다시 게시할 수 있습니다.")
            return 0
        if args.command == "hidden":
            print_posts(service, "HIDDEN")
            return 0
        if args.command == "remote-dry-run":
            return print_result(service.remote_workflow("dry-run"))
        if args.command == "remote-sync":
            if not args.yes and not confirm("GitHub Actions에서 실제 동기화를 시작하시겠습니까?", "원격 동기화"):
                return 1
            return print_result(service.remote_workflow("apply"))
    except UserInputError as exc:
        print(f"요청을 처리할 수 없습니다: {exc}", file=sys.stderr)
        return 2
    except (VelogSyncError, OSError) as exc:
        print("작업 중 문제가 발생했습니다.", file=sys.stderr)
        print("기존 GitHub 게시물은 안전하게 유지됩니다.", file=sys.stderr)
        print(f"자세한 오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
