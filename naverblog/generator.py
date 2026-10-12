"""Claude API 로 블로그 글 초안 생성."""

from __future__ import annotations

import json

import anthropic

from .post import Post

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


def generate_post(topic: str, *, model: str, keywords: list[str] | None = None,
                  tone: str | None = None, length: int = 2000,
                  notes: str | None = None,
                  client: anthropic.Anthropic | None = None) -> Post:
    client = client or anthropic.Anthropic()
    keywords = keywords or []

    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(topic, keywords, tone, length, notes)}],
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
    return Post(title=data["title"].strip(), body=data["body"], tags=tags, meta=meta)
