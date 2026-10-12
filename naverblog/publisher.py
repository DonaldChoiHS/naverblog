"""Playwright 로 네이버 블로그(스마트에디터 ONE)에 글을 발행."""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from playwright.sync_api import BrowserContext, Frame, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .post import Post

# 네이버가 에디터 마크업을 바꾸면 여기만 고치면 되도록 셀렉터를 모아 둔다.
# 클래스명 뒤에 해시가 붙는 요소는 [class*=...] 로 접두어만 맞춘다.
SELECTORS = {
    "editor_root": ".se-content",
    "popup_cancel": ".se-popup-button-cancel",  # "작성 중인 글이 있습니다" → 새로 쓰기
    "help_close": ".se-help-panel-close-button",
    "title": ".se-documentTitle .se-text-paragraph",
    "body": ".se-component.se-text .se-text-paragraph",
    "body_text": ".se-main-container",
    "publish_open": "button[class*='publish_btn']",
    "category_button": "button[class*='selectbox_button']",
    "tag_input": "input#tag-input, input[class*='tag_input']",
    "publish_confirm": "button[data-testid='seOnePublishBtn'], button[class*='confirm_btn']",
}

LOGIN_URL = "https://nid.naver.com/nidlogin.login"
POST_URL_RE = re.compile(r"blog\.naver\.com/(?:PostView\.naver\?.*logNo=\d+|[\w-]+/\d+)")


class PublishError(RuntimeError):
    pass


@contextmanager
def browser_context(profile_dir: Path, headless: bool):
    """로그인 세션이 유지되는 영구 브라우저 프로필을 연다."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            locale="ko-KR",
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield context
        finally:
            context.close()


def is_logged_in(context: BrowserContext) -> bool:
    return any(c["name"] == "NID_AUT" for c in context.cookies("https://www.naver.com"))


def login(profile_dir: Path, timeout_sec: int = 300) -> None:
    """브라우저를 띄워 사용자가 직접 로그인하게 하고, 세션을 프로필에 저장한다.

    아이디/비밀번호를 코드에 넣지 않고 캡차·2단계 인증도 사람이 처리한다.
    """
    with browser_context(profile_dir, headless=False) as context:
        if is_logged_in(context):
            print("이미 로그인되어 있습니다.")
            return
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL)
        print(f"열린 브라우저에서 네이버에 로그인해 주세요. ({timeout_sec}초 대기)")
        print("'로그인 상태 유지'를 체크하면 세션이 더 오래 유지됩니다.")
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if is_logged_in(context):
                page.wait_for_timeout(2000)  # 쿠키가 프로필에 기록될 시간
                print("로그인 확인. 세션을 저장했습니다.")
                return
            page.wait_for_timeout(1000)
        raise PublishError("로그인 대기 시간이 지났습니다.")


def _find_editor_frame(page: Page, timeout_sec: int = 30) -> Frame:
    """에디터는 페이지 본문이나 mainFrame iframe 안에 있을 수 있어 둘 다 찾아본다."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if frame.locator(SELECTORS["editor_root"]).count() > 0:
                    return frame
            except Exception:
                continue  # 로딩 중 분리된 프레임
        page.wait_for_timeout(500)
    raise PublishError("글쓰기 에디터를 찾지 못했습니다. 로그인 상태와 NAVER_BLOG_ID 를 확인해 주세요.")


def _click_if_visible(frame: Frame, selector: str, timeout_ms: int = 1500) -> bool:
    loc = frame.locator(selector).first
    try:
        loc.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeout:
        return False
    loc.click()
    return True


def _paste_html(page: Page, frame: Frame, html: str, text: str) -> None:
    """클립보드 붙여넣기 이벤트로 HTML 을 넣는다. 에디터가 서식(소제목·목록·굵게)을 변환해 준다."""
    frame.evaluate(
        """([html, text]) => {
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            dt.setData('text/plain', text);
            const target = document.activeElement || document.body;
            target.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true,
            }));
        }""",
        [html, text],
    )
    page.wait_for_timeout(1500)


def _body_text_length(frame: Frame) -> int:
    loc = frame.locator(SELECTORS["body_text"]).first
    try:
        return len(loc.inner_text(timeout=3000).strip())
    except PlaywrightTimeout:
        return 0


def _fill_body(page: Page, frame: Frame, post: Post) -> None:
    frame.locator(SELECTORS["body"]).first.click()
    before = _body_text_length(frame)
    _paste_html(page, frame, post.to_html(), post.body)
    if _body_text_length(frame) - before > len(post.title):
        return
    # 붙여넣기가 막힌 경우: 서식 없이 한 줄씩 직접 입력
    print("  HTML 붙여넣기가 적용되지 않아 일반 텍스트로 입력합니다(서식 없음).")
    for line in post.body.splitlines():
        if line.strip():
            page.keyboard.type(re.sub(r"^#+\s*", "", line), delay=5)
        page.keyboard.press("Enter")


def _select_category(frame: Frame, category: str) -> None:
    if not _click_if_visible(frame, SELECTORS["category_button"]):
        print(f"  카테고리 선택 버튼을 찾지 못해 '{category}' 지정을 건너뜁니다.")
        return
    option = frame.get_by_text(category, exact=True).last
    try:
        option.click(timeout=3000)
    except PlaywrightTimeout:
        print(f"  카테고리 '{category}' 를 찾지 못해 기본 카테고리로 발행합니다.")


def _add_tags(page: Page, frame: Frame, tags: list[str]) -> None:
    loc = frame.locator(SELECTORS["tag_input"]).first
    try:
        loc.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeout:
        print("  태그 입력칸을 찾지 못해 태그 없이 진행합니다.")
        return
    for tag in tags[:30]:  # 네이버 태그는 최대 30개
        loc.click()
        page.keyboard.type(tag, delay=20)
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)


def _screenshot(page: Page, screenshots_dir: Path, label: str) -> Path:
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    path = screenshots_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{label}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def publish(post: Post, *, blog_id: str, profile_dir: Path, screenshots_dir: Path,
            headless: bool = False, dry_run: bool = False) -> str | None:
    """글을 발행하고 글 주소를 돌려준다. dry_run 이면 최종 '발행' 직전에 멈춘다."""
    if not blog_id:
        raise PublishError("NAVER_BLOG_ID 가 비어 있습니다. .env 를 확인해 주세요.")

    with browser_context(profile_dir, headless=headless) as context:
        if not is_logged_in(context):
            raise PublishError("로그인 세션이 없습니다. 먼저 `naverblog login` 을 실행해 주세요.")
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(f"https://blog.naver.com/{blog_id}/postwrite", wait_until="domcontentloaded")
            frame = _find_editor_frame(page)
            page.wait_for_timeout(1500)
            _click_if_visible(frame, SELECTORS["popup_cancel"])
            _click_if_visible(frame, SELECTORS["help_close"])

            print("  제목 입력")
            frame.locator(SELECTORS["title"]).first.click()
            page.keyboard.type(post.title, delay=30)

            print("  본문 입력")
            _fill_body(page, frame, post)

            print("  발행 설정 열기")
            frame.locator(SELECTORS["publish_open"]).first.click()
            page.wait_for_timeout(1000)
            if post.category:
                _select_category(frame, post.category)
            if post.tags:
                _add_tags(page, frame, post.tags)

            if dry_run:
                shot = _screenshot(page, screenshots_dir, "dry-run")
                print(f"  [dry-run] 발행 직전에 멈췄습니다. 화면: {shot}")
                if not headless:
                    input("  브라우저를 확인한 뒤 Enter 를 누르면 닫습니다(발행되지 않음)...")
                return None

            print("  발행")
            frame.locator(SELECTORS["publish_confirm"]).first.click()
            try:
                page.wait_for_url(POST_URL_RE, timeout=30000)
            except PlaywrightTimeout:
                raise PublishError("발행 후 글 페이지로 이동하지 않았습니다. 블로그에서 결과를 확인해 주세요.")
            return page.url
        except Exception:
            shot = _screenshot(page, screenshots_dir, "error")
            print(f"  오류 화면 저장: {shot}")
            raise
