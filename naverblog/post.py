"""글 파일(front matter + 마크다운) 읽기/쓰기."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import markdown
import yaml

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass
class Post:
    title: str
    body: str  # 마크다운
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    meta: dict = field(default_factory=dict)  # 그 밖의 front matter 값 (topic, url 등)

    def to_html(self) -> str:
        return markdown.markdown(self.body, extensions=["extra", "sane_lists"])

    def dumps(self) -> str:
        front = {"title": self.title, "tags": self.tags}
        if self.category:
            front["category"] = self.category
        front.update(self.meta)
        header = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{header}\n---\n\n{self.body.strip()}\n"

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
        return cls(title=str(title), body=m.group(2).strip(), tags=[str(t) for t in tags],
                   category=category, meta=front)

    @classmethod
    def load(cls, path: Path) -> Post:
        return cls.loads(path.read_text(encoding="utf-8"))


def slugify(text: str, max_len: int = 40) -> str:
    """파일명용 슬러그. 한글은 그대로 두고 공백/특수문자만 정리한다."""
    slug = re.sub(r"[^\w가-힣]+", "-", text).strip("-").lower()
    return slug[:max_len].rstrip("-") or "post"


def draft_filename(title: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{now:%Y%m%d-%H%M}-{slugify(title)}.md"
