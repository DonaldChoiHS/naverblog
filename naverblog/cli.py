"""명령줄 진입점: naverblog login | generate | publish"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .config import ROOT, load_config
from .post import IMAGE_EXTS, Post, display_path, draft_filename, parse_schedule,
                   validate_schedule


def collect_images(files: list[str], image_dir: str | None) -> list[tuple[str, Path]]:
    """(글에 적을 경로, 실제 파일) 목록. 폴더는 파일 이름순."""
    paths = [Path(f).expanduser() for f in files]
    if image_dir:
        d = Path(image_dir).expanduser()
        if not d.is_dir():
            raise FileNotFoundError(f"사진 폴더가 없습니다: {d}")
        paths += sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f"사진 파일이 없습니다: {p}")
    return [(display_path(p, ROOT), p.resolve()) for p in paths]


def cmd_login(args, cfg) -> None:
    from .publisher import login
    login(cfg.profile_dir, timeout_sec=args.timeout)


def cmd_generate(args, cfg) -> None:
    from .generator import generate_post

    notes = Path(args.notes_file).read_text(encoding="utf-8") if args.notes_file else None
    images = collect_images(args.images, args.image_dir)
    schedule = parse_schedule(args.schedule) if args.schedule else None
    if schedule:
        validate_schedule(schedule)
    extra = f", 사진 {len(images)}장" if images else ""
    print(f"'{args.topic}' 초안 생성 중... ({cfg.model}{extra})")
    post = generate_post(
        args.topic, model=cfg.model, keywords=args.keywords, tone=args.tone,
        length=args.length, notes=notes, images=images,
    )
    if args.category:
        post.category = args.category
    post.schedule = schedule
    path = post.save(cfg.drafts_dir / draft_filename(post.title))
    print(f"저장: {path}")
    print(f"제목: {post.title}")
    print(f"태그: {', '.join(post.tags)}")
    if schedule:
        print(f"예약: {schedule:%Y-%m-%d %H:%M} (publish 할 때 이 시각으로 예약됩니다)")
    print("내용을 검토·수정한 뒤 `naverblog publish <파일>` 로 발행하세요.")


def cmd_publish(args, cfg) -> None:
    from .publisher import publish

    path = Path(args.file)
    post = Post.load(path)
    schedule = None if args.now else (parse_schedule(args.schedule) if args.schedule else post.schedule)
    when = f" ({schedule:%Y-%m-%d %H:%M} 예약)" if schedule else ""
    print(f"발행 준비: {post.title}{when}")
    url = publish(
        post, blog_id=cfg.blog_id, profile_dir=cfg.profile_dir,
        screenshots_dir=cfg.screenshots_dir, root=ROOT, post_dir=path.parent,
        schedule=schedule, headless=args.headless, dry_run=args.dry_run,
    )
    if url is None:
        return
    post.schedule = schedule
    post.meta["status"] = "scheduled" if schedule else "published"
    post.meta["url"] = url
    post.meta["published_at"] = datetime.now().isoformat(timespec="seconds")
    dest = cfg.published_dir / path.name
    post.save(dest)
    if path.resolve() != dest.resolve():
        path.unlink()
    print(f"예약 완료: {schedule:%Y-%m-%d %H:%M} 에 발행됩니다." if schedule else f"발행 완료: {url}")
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
    p.add_argument("-i", "--images", nargs="*", default=[], help="글에 넣을 사진 파일들 (Claude 가 보고 배치)")
    p.add_argument("--image-dir", help="이 폴더의 사진을 모두 사용 (파일 이름순)")
    p.add_argument("--schedule", help="예약 발행 시각, 예: '2026-10-15 09:30' (10분 단위)")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("publish", help="마크다운 글 파일을 블로그에 발행")
    p.add_argument("file", help="posts/drafts/ 의 글 파일")
    p.add_argument("--dry-run", action="store_true", help="최종 발행 버튼 직전에 멈춤")
    p.add_argument("--headless", action="store_true", help="브라우저 창 없이 실행")
    p.add_argument("--schedule", help="예약 발행 시각 (글 파일의 schedule 보다 우선), 예: '2026-10-15 09:30'")
    p.add_argument("--now", action="store_true", help="글 파일에 schedule 이 있어도 바로 발행")
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
