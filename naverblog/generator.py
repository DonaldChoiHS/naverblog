"""Claude API 로 블로그 글 초안 생성."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import anthropic
from PIL import Image, ImageOps

from .post import IMAGE_EXTS, Post, image_markdown

# API 로 보낼 때만 줄인다(업로드는 원본 사용). 긴 변 1568px 이 넘으면 모델이 어차피 줄여서 본다.
_MAX_EDGE = 1568

SYSTEM_PROMPT = """\
당신은 네이버 블로그에 글을 쓰는 한국어 블로거입니다.
독자가 검색으로 들어와 끝까지 읽고 싶어지는 글을 씁니다.

글쓰기 원칙:
- 자연스러운 구어체 존댓말(~요, ~습니다)을 쓰고, 번역투나 AI 같은 상투적 표현은 피합니다.
- 도입부에서 독자가 얻을 것을 바로 알려줍니다.
- 소제목(##)으로 3~6개 섹션을 나누고, 문단은 짧게(2~4문장) 씁니다.
- 필요하면 목록, 표, 굵은 글씨를 쓰되 남발하지 않습니다.
- 확실하지 않은 사실, 가격, 날짜는 단정하지 말고 확인이 필요하다고 표시합니다.
- 핵심 키워드는 제목과 본문 앞부분에 자연스럽게 넣고, 억지로 반복하지 않습니다.
- 마지막에 짧은 정리 문단을 둡니다.

body 는 마크다운으로 쓰고, 제목(#)은 body 에 다시 넣지 않습니다.
tags 는 # 없이 5~10개, 검색에 쓰일 만한 단어로 만듭니다.
"""

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "블로그 글 제목 (40자 이내 권장)"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "body": {"type": "string", "description": "마크다운 본문"},
    },
    "required": ["title", "tags", "body"],
    "additionalProperties": False,
}

IMAGE_INSTRUCTIONS = """\
첨부한 사진들을 보고 내용에 맞게 글에 배치해 주세요.
- 각 사진은 정확히 한 번, 어울리는 문단 사이에 단독 줄로 넣습니다.
- 사진마다 적힌 표기를 그대로 쓰고, `설명` 부분만 사진에 맞는 짧은 설명으로 바꿉니다. 괄호 안 경로는 한 글자도 바꾸지 않습니다.
- 사진에 보이는 내용을 본문에 자연스럽게 녹여 쓰되, 사진으로 확인할 수 없는 사실은 지어내지 않습니다.
"""


class GenerationError(RuntimeError):
    pass


def build_prompt(topic: str, keywords: list[str], tone: str | None, length: int,
                 notes: str | None) -> str:
    lines = [f"주제: {topic}"]
    if keywords:
        lines.append(f"핵심 키워드: {', '.join(keywords)}")
    if tone:
        lines.append(f"톤: {tone}")
    lines.append(f"분량: 본문 약 {length}자")
    if notes:
        lines.append(f"추가 지시/참고 자료:\n{notes}")
    return "\n".join(lines) + "\n\n위 조건으로 네이버 블로그 글을 작성해 주세요."


def encode_image(path: Path) -> dict:
    """사진을 API 입력용 base64 JPEG 블록으로 만든다(휴대폰 사진 회전 정보 반영)."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((_MAX_EDGE, _MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    data = base64.standard_b64encode(buf.getvalue()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def build_content(prompt: str, images: list[tuple[str, Path]]) -> str | list[dict]:
    """images: (글에 적을 경로, 실제 파일) 목록."""
    if not images:
        return prompt
    content: list[dict] = []
    for i, (label, path) in enumerate(images, 1):
        content.append({"type": "text", "text": f"사진 {i} — 글에 넣을 표기: {image_markdown('설명', label)}"})
        content.append(encode_image(path))
    content.append({"type": "text", "text": f"{prompt}\n\n{IMAGE_INSTRUCTIONS}"})
    return content


def ensure_images(body: str, labels: list[str]) -> str:
    """모델이 빠뜨린 사진은 본문 끝에 붙인다."""
    missing = [label for label in labels if label not in body]
    if missing:
        body = body.rstrip() + "\n\n" + "\n\n".join(image_markdown("", m) for m in missing)
    return body


def generate_post(topic: str, *, model: str, keywords: list[str] | None = None,
                  tone: str | None = None, length: int = 2000,
                  notes: str | None = None, images: list[tuple[str, Path]] | None = None,
                  client: anthropic.Anthropic | None = None) -> Post:
    client = client or anthropic.Anthropic()
    keywords = keywords or []
    images = images or []
    for _, path in images:
        if path.suffix.lower() not in IMAGE_EXTS:
            raise GenerationError(f"지원하지 않는 이미지 형식입니다: {path.name}")

    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": build_content(build_prompt(topic, keywords, tone, length, notes), images)}],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": POST_SCHEMA},
        },
        # 안전 분류기가 요청을 거절하면 서버가 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    if response.stop_reason == "refusal":
        raise GenerationError("모델이 이 주제의 글 작성을 거절했습니다. 주제나 지시를 바꿔 다시 시도해 주세요.")
    if response.stop_reason == "max_tokens":
        raise GenerationError("출력이 길이 제한에 걸려 잘렸습니다. --length 를 줄여 다시 시도해 주세요.")

    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GenerationError(f"응답을 JSON 으로 읽지 못했습니다: {e}") from e

    tags = [t.lstrip("#").strip() for t in data["tags"] if t.strip()]
    meta = {"topic": topic}
    if keywords:
        meta["keywords"] = keywords
    body = ensure_images(data["body"], [label for label, _ in images])
    return Post(title=data["title"].strip(), body=body, tags=tags, meta=meta)
