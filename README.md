# naverblog

Claude 로 네이버 블로그 글 초안을 만들고, 브라우저 자동화(Playwright)로 발행하는 도구입니다.

```
주제 ──generate──▶ posts/drafts/*.md ──(사람이 검토·수정)──▶ publish ──▶ 블로그 글 + posts/published/*.md
```

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
playwright install chromium
cp .env.example .env               # ANTHROPIC_API_KEY, NAVER_BLOG_ID 입력
```

## 사용법

### 1. 네이버 로그인 (처음 한 번)

```bash
naverblog login
```

브라우저가 열리면 직접 로그인합니다. 세션은 `.auth/profile/` 에 저장되고 git 에는 올라가지 않습니다.
아이디·비밀번호를 코드에 저장하지 않으며, 캡차·2단계 인증도 사람이 처리합니다.
세션이 만료되면 다시 실행하면 됩니다.

### 2. 초안 생성

```bash
naverblog generate "제주도 3박 4일 가족여행 코스" -k 제주여행 가족여행 --tone "친근한 후기" --category 여행
```

`posts/drafts/` 에 마크다운 파일이 생깁니다. 참고 자료(직접 다녀온 메모, 가격표 등)가 있으면
`--notes-file memo.txt` 로 넘기면 더 정확한 글이 나옵니다.

### 3. 검토 후 발행

```bash
naverblog publish posts/drafts/20261012-0905-제주도-3박-4일.md --dry-run   # 발행 버튼 직전에 멈춤
naverblog publish posts/drafts/20261012-0905-제주도-3박-4일.md             # 실제 발행
```

발행되면 파일이 `posts/published/` 로 옮겨지고 글 주소(`url`)와 발행 시각이 기록됩니다.
실패하면 `screenshots/` 에 화면이 저장됩니다.

## 글 파일 형식

직접 쓴 글도 같은 형식이면 발행할 수 있습니다.

```markdown
---
title: 글 제목
tags: [태그1, 태그2]
category: 여행        # 선택, 블로그에 있는 카테고리 이름
---

## 소제목

본문은 **마크다운** 으로 씁니다.
```

## 구조

| 파일 | 역할 |
|---|---|
| `naverblog/generator.py` | Claude API 로 제목·태그·본문 생성 (구조화 출력) |
| `naverblog/publisher.py` | 스마트에디터 ONE 자동 입력·발행. 셀렉터는 상단 `SELECTORS` 에 모아 둠 |
| `naverblog/post.py` | front matter + 마크다운 파일 읽기/쓰기, HTML 변환 |
| `naverblog/cli.py` | `naverblog` 명령 |

## 알아둘 점

- **네이버에는 공개 글쓰기 API 가 없어서** 브라우저 화면을 조작합니다. 네이버가 에디터 화면을 바꾸면
  `publisher.py` 의 `SELECTORS` 를 고쳐야 할 수 있습니다. 처음엔 `--dry-run` 으로 확인하세요.
- 본문은 HTML 붙여넣기로 넣어 소제목·목록·굵게 서식을 살립니다. 붙여넣기가 안 먹히면 서식 없는 텍스트로 입력합니다.
- 이미지 첨부, 예약 발행은 아직 지원하지 않습니다.
- 짧은 시간에 많은 글을 자동 발행하거나 AI 글을 검토 없이 대량으로 올리면 네이버 운영정책상 저품질·스팸으로 판단될 수 있습니다.
  초안은 꼭 검토하고, 발행 간격을 충분히 두세요.

## 테스트

```bash
pytest
```
