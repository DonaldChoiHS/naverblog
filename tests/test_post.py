from datetime import datetime
from types import SimpleNamespace

import pytest

from naverblog.generator import generate_post
from naverblog.post import Post, draft_filename, slugify


def test_roundtrip():
    post = Post(title="제주 3박4일 여행", body="## 첫째 날\n\n- 공항\n- **협재**",
                tags=["제주", "여행"], category="여행", meta={"topic": "제주"})
    loaded = Post.loads(post.dumps())
    assert loaded.title == post.title
    assert loaded.tags == post.tags
    assert loaded.category == "여행"
    assert loaded.meta == {"topic": "제주"}
    assert loaded.body == post.body


def test_tags_as_comma_string():
    post = Post.loads("---\ntitle: 테스트\ntags: 가, 나 ,다\n---\n본문")
    assert post.tags == ["가", "나", "다"]


def test_missing_front_matter():
    with pytest.raises(ValueError):
        Post.loads("그냥 본문")


def test_to_html():
    html = Post(title="t", body="## 소제목\n\n- a\n- **b**").to_html()
    assert "<h2>소제목</h2>" in html
    assert "<li><strong>b</strong></li>" in html


def test_filenames():
    assert slugify("갤럭시 S26 울트라, 한 달 사용 후기!") == "갤럭시-s26-울트라-한-달-사용-후기"
    assert draft_filename("제목", datetime(2026, 10, 12, 9, 5)) == "20261012-0905-제목.md"


def _fake_client(text, stop_reason="end_turn"):
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(stop_reason=stop_reason,
                               content=[SimpleNamespace(type="text", text=text)])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return client, calls


def test_generate_post_parses_json():
    client, calls = _fake_client('{"title": " 제목 ", "tags": ["#가", "나"], "body": "본문"}')
    post = generate_post("주제", model="claude-opus-5-5", keywords=["키"], client=client)
    assert post.title == "제목"
    assert post.tags == ["가", "나"]
    assert post.meta == {"topic": "주제", "keywords": ["키"]}
    assert calls["output_config"]["format"]["type"] == "json_schema"
    assert "핵심 키워드: 키" in calls["messages"][0]["content"]


def test_generate_post_refusal():
    client, _ = _fake_client("", stop_reason="refusal")
    with pytest.raises(RuntimeError):
        generate_post("주제", model="claude-opus-5-5", client=client)
