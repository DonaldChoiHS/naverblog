"""명령줄 진입점: naverblog login | generate | publish"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .config import load_config
from .post import Post, draft_filename


def cmd_login(args, cfg) -> None:
    from .publisher import login
    login(cfg.profile_dir, timeout_sec=args.timeout)


def cmd_generate(args, cfg) -> None:
    from .generator import generate_post

    notes = Path(args.notes_file).read_text(encoding="utf-8") if args.notes_file else None
    print(f"'{args.topic}' 초안 생성 중... ({cfg.model})")
    post = generate_post(
        args.topic, model=cfg.model, keywords=args.keywords, tone=args.tone,
        length=args.length, notes=notes,
    )
    if args.category:
        post.category = args.category
    path = post.save(cfg.drafts_dir / draft_filename(post.title))
    print(f"저장: {path}")
    print(f"제목: {post.title}")
    print(f"태그: {', '.join(post.tags)}")
    print("내용을 검토·수정한 뒤 `naverblog publish <파일>` 로 발행하세요.")


def cmd_publish(args, cfg) -> None:
    from .publisher import publish

    path = Path(args.file)
    post = Post.load(path)
    print(f"발행 준비: {post.title}")
    url = publish(
        post, blog_id=cfg.blog_id, profile_dir=cfg.profile_dir,
        screenshots_dir=cfg.screenshots_dir, headless=args.headless, dry_run=args.dry_run,
    )
    if url is None:
        return
    post.meta["url"] = url
    post.meta["published_at"] = datetime.now().isoformat(timespec="seconds")
    dest = cfg.published_dir / path.name
    post.save(dest)
    if path.resolve() != dest.resolve():
        path.unlink()
    print(f"발행 완료: {url}")
    print(f"기록: {dest}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="naverblog", description="네이버 블로그 초안 생성 + 자동 발행")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="브라우저를 띄워 네이버에 로그인하고 세션 저장")
    p.add_argument("--timeout", type=int, default=300, help="로그인 대기 시간(초)")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("generate", help="Claude 로 글 초안 생성 → posts/drafts/")
    p.add_argument("topic", help="글 주제")
    p.add_argument("-k", "--keywords", nargs="*", default=[], help="핵심 키워드")
    p.add_argument("--tone", help="톤 (예: 친근한 리뷰, 전문적인 정보글)")
    p.add_argument("--length", type=int, default=2000, help="본문 목표 글자 수")
    p.add_argument("--category", help="발행할 블로그 카테고리 이름")
    p.add_argument("--notes-file", help="참고 자료/추가 지시가 담긴 텍스트 파일")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("publish", help="마크다운 글 파일을 블로그에 발행")
    p.add_argument("file", help="posts/drafts/ 의 글 파일")
    p.add_argument("--dry-run", action="store_true", help="최종 발행 버튼 직전에 멈춤")
    p.add_argument("--headless", action="store_true", help="브라우저 창 없이 실행")
    p.set_defaults(func=cmd_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args, load_config())
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
