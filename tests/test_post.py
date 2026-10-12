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


def test_segments_and_image_paths():
    post = Post(title="t", body="첫 문단\n\n![바다](posts/images/a.jpg)\n\n둘째\n\n![](<my photo.png>)")
    assert post.segments() == [("text", "첫 문단"), ("image", "posts/images/a.jpg"),
                               ("text", "둘째"), ("image", "my photo.png")]
    assert post.image_paths() == ["posts/images/a.jpg", "my photo.png"]


def test_resolve_image(tmp_path):
    from naverblog.post import resolve_image
    (tmp_path / "drafts").mkdir()
    (tmp_path / "img.jpg").write_bytes(b"x")
    assert resolve_image("img.jpg", tmp_path / "drafts", tmp_path) == (tmp_path / "img.jpg").resolve()
    with pytest.raises(FileNotFoundError):
        resolve_image("none.jpg", tmp_path / "drafts", tmp_path)


def test_schedule_roundtrip_and_validation():
    from naverblog.post import parse_schedule, validate_schedule
    post = Post.loads("---\ntitle: t\nschedule: 2026-10-15 09:30\n---\n본문")
    assert post.schedule == datetime(2026, 10, 15, 9, 30)
    assert Post.loads(post.dumps()).schedule == post.schedule
    assert parse_schedule("2026.10.15 09:30") == datetime(2026, 10, 15, 9, 30)
    now = datetime(2026, 10, 12, 9, 0)
    validate_schedule(datetime(2026, 10, 12, 10, 0), now)
    with pytest.raises(ValueError):
        validate_schedule(datetime(2026, 10, 12, 10, 5), now)   # 10분 단위 아님
    with pytest.raises(ValueError):
        validate_schedule(datetime(2026, 10, 12, 9, 0), now)    # 과거


def test_generate_post_with_images(tmp_path):
    from PIL import Image
    img = tmp_path / "a.jpg"
    Image.new("RGB", (3000, 2000), "blue").save(img)
    client, calls = _fake_client('{"title": "t", "tags": [], "body": "본문 ![바다](a.jpg)"}')
    post = generate_post("주제", model="m", images=[("a.jpg", img), ("b c.jpg", img)], client=client)
    content = calls["messages"][0]["content"]
    assert [b["type"] for b in content] == ["text", "image", "text", "image", "text"]
    assert "![설명](<b c.jpg>)" in content[2]["text"]
    assert post.body.endswith("![](<b c.jpg>)")  # 빠진 사진은 끝에 붙음
