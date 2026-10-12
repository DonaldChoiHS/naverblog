"""환경 변수와 경로 설정."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    blog_id: str
    model: str
    drafts_dir: Path
    published_dir: Path
    # 네이버 로그인 세션을 담아두는 브라우저 프로필 (git 에 올리지 않음)
    profile_dir: Path
    screenshots_dir: Path


def load_config() -> Config:
    return Config(
        blog_id=os.getenv("NAVER_BLOG_ID", "").strip(),
        model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        drafts_dir=ROOT / "posts" / "drafts",
        published_dir=ROOT / "posts" / "published",
        profile_dir=ROOT / ".auth" / "profile",
        screenshots_dir=ROOT / "screenshots",
    )
