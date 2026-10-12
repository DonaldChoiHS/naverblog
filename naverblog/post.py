"""글 파일(front matter + 마크다운) 읽기/쓰기."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import markdown
import yaml

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
# ![설명](경로) 또는 공백이 있는 경로용 ![설명](<경로>)
_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^)\s]+))\s*\)")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@dataclass
class Post:
    title: str
    body: str  # 마크다운
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    schedule: datetime | None = None  # 예약 발행 시각
    meta: dict = field(default_factory=dict)  # 그 밖의 front matter 값 (topic, url 등)

    def to_html(self) -> str:
        return markdown.markdown(self.body, extensions=["extra", "sane_lists"])

    def dumps(self) -> str:
        front = {"title": self.title, "tags": self.tags}
        if self.category:
            front["category"] = self.category
        if self.schedule:
            front["schedule"] = self.schedule.strftime("%Y-%m-%d %H:%M")
        front.update(self.meta)
        header = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{header}\n---\n\n{self.body.strip()}\n"

    def segments(self) -> list[tuple[str, str]]:
        """본문을 ("text", 마크다운) / ("image", 경로) 조각으로 나눈다."""
        out: list[tuple[str, str]] = []
        pos = 0
        for m in _IMAGE.finditer(self.body):
            text = self.body[pos:m.start()].strip()
            if text:
                out.append(("text", text))
            out.append(("image", m.group(2) or m.group(3)))
            pos = m.end()
        tail = self.body[pos:].strip()
        if tail:
            out.append(("text", tail))
        return out

    def image_paths(self) -> list[str]:
        return [m.group(2) or m.group(3) for m in _IMAGE.finditer(self.body)]

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(), encoding="utf-8")
        return path

    @classmethod
    def loads(cls, text: str) -> Post:
        m = _FRONT_MATTER.match(text)
        if not m:
            raise ValueError("front matter(---) 가 없습니다. title 이 들어있는 front matter 가 필요합니다.")
        front = yaml.safe_load(m.group(1)) or {}
        title = front.pop("title", None)
        if not title:
            raise ValueError("front matter 에 title 이 없습니다.")
        tags = front.pop("tags", None) or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        category = front.pop("category", None)
        schedule = front.pop("schedule", None)
        return cls(title=str(title), body=m.group(2).strip(), tags=[str(t) for t in tags],
                   category=category, schedule=parse_schedule(schedule) if schedule else None,
                   meta=front)

    @classmethod
    def load(cls, path: Path) -> Post:
        return cls.loads(path.read_text(encoding="utf-8"))


def parse_schedule(value) -> datetime:
    """'2026-10-15 09:30' 같은 문자열(또는 YAML 이 읽은 datetime)을 datetime 으로."""
    if isinstance(value, datetime):
        return value.replace(second=0, microsecond=0)
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"예약 시각 형식을 알 수 없습니다: {value!r} (예: 2026-10-15 09:30)")


def validate_schedule(when: datetime, now: datetime | None = None) -> None:
    now = now or datetime.now()
    if when.minute % 10:
        raise ValueError("네이버 예약 발행은 10분 단위만 됩니다. 분을 00, 10, 20 ... 50 중 하나로 정해 주세요.")
    if when <= now + timedelta(minutes=10):
        raise ValueError(f"예약 시각은 지금보다 10분 이상 뒤여야 합니다: {when:%Y-%m-%d %H:%M}")


def resolve_image(src: str, post_dir: Path | None, root: Path) -> Path:
    """이미지 경로를 실제 파일로 찾는다: 절대경로 → 글 파일 기준 → 프로젝트 루트 기준."""
    p = Path(src).expanduser()
    candidates = [p] if p.is_absolute() else [d / p for d in (post_dir, root) if d]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {src}")


def image_markdown(alt: str, path: str) -> str:
    return f"![{alt}](<{path}>)" if " " in path else f"![{alt}]({path})"


def display_path(path: Path, root: Path) -> str:
    """글 파일에 적을 경로: 프로젝트 안이면 루트 기준 상대경로(드래프트→발행 이동 후에도 유지)."""
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def slugify(text: str, max_len: int = 40) -> str:
    """파일명용 슬러그. 한글은 그대로 두고 공백/특수문자만 정리한다."""
    slug = re.sub(r"[^\w가-힣]+", "-", text).strip("-").lower()
    return slug[:max_len].rstrip("-") or "post"


def draft_filename(title: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{now:%Y%m%d-%H%M}-{slugify(title)}.md"
