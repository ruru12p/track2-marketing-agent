"""Visible local Playwright posting. Uses isolated Chrome profiles (not regular Chrome Default)."""
import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

async def post_comment_real(video_url: str, comment_text: str, profile_path: str, event=None):
    def report(msg):
        if event:
            event(msg)
    context = None
    page = None
    screenshots = Path(__file__).resolve().parent / "screenshots"
    screenshots.mkdir(exist_ok=True)
    try:
        async with async_playwright() as p:
            report("크롬 프로필 여는 중")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(Path(profile_path).resolve()),
                headless=False,
                channel="chrome",
                locale="ko-KR",
                viewport={"width": 1365, "height": 900},
            )
            page = context.pages[0] if context.pages else await context.new_page()
            report("동영상 접속 중")
            await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
            await page.locator("ytd-watch-flexy").wait_for(timeout=25000)
            await page.locator("#comments").scroll_into_view_if_needed(timeout=20000)
            await page.wait_for_timeout(2000)

            # YouTube local UI changes periodically; fail closed if missing.
            placeholder = page.locator("ytd-comment-simplebox-renderer #placeholder-area").first
            await placeholder.wait_for(state="visible", timeout=20000)
            await placeholder.click()
            editor = page.locator("ytd-comment-simplebox-renderer #contenteditable-root[contenteditable='true']").first
            await editor.wait_for(state="visible", timeout=10000)
            report("댓글 입력 중")
            await editor.press_sequentially(comment_text, delay=45)
            typed = (await editor.inner_text()).strip()
            if typed != comment_text.strip():
                raise RuntimeError("입력한 댓글이 원문과 일치하지 않습니다. 게시하지 않았습니다.")

            submit = page.locator("ytd-comment-simplebox-renderer #submit-button button").first
            await submit.wait_for(state="visible", timeout=10000)
            if not await submit.is_enabled():
                raise RuntimeError("게시 버튼이 비활성화되어 있습니다. 로그인 상태를 확인하세요.")
            report("댓글 게시 버튼 누르는 중")
            await submit.click()
            report("게시 후 댓글 표시 확인 중")
            # Check the newly added comment; do not claim success from a click alone.
            comment = page.locator("ytd-comment-thread-renderer #content-text").filter(has_text=comment_text.strip()).first
            try:
                await comment.wait_for(state="visible", timeout=18000)
            except Exception:
                raise RuntimeError("게시 클릭 후 댓글 표시를 확인하지 못했습니다. 재시도 전 영상에서 실제 게시 여부를 확인하세요.")
            report("댓글 표시 확인 완료")
            return True, "실제 게시 후 댓글 표시 확인", None
    except Exception as exc:
        shot = None
        if page:
            shot = screenshots / f"failure_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            try:
                await page.screenshot(path=str(shot), full_page=False, timeout=5000)
            except Exception:
                shot = None
        return False, str(exc), str(shot) if shot else None
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

def run_real_automation(video_url, comment_text, profile_path, event=None):
    return asyncio.run(post_comment_real(video_url, comment_text, profile_path, event))
