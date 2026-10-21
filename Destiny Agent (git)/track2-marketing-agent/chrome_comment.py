"""Visible YouTube commenting with an isolated, persistent Chrome profile.

Only use on accounts you control and for appropriately disclosed brand participation.
The caller must enforce per-account/per-video dedupe and daily caps before invoking.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def post_comment_visible(
    video_url: str,
    comment: str,
    account: str,
    base_dir: str | Path,
    update: Callable[[str], None] | None = None,
) -> dict:
    """Open Chrome, type each character, submit, then check visible confirmation.

    Returns {success: bool, message: str, screenshot: str|None}.
    An uncertain outcome is never marked successful.
    """
    report = update or (lambda _: None)
    base = Path(base_dir).resolve()
    if account not in {"유튜브1", "유튜브2", "유튜브3"}:
        raise ValueError("등록되지 않은 계정입니다.")
    profile_dir = base / "profiles" / account
    profile_dir.mkdir(parents=True, exist_ok=True)
    shots_dir = base / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    shot = str(shots_dir / f"post_{account}_{stamp}.png")
    posted = False
    clicked = False
    error = ""

    with sync_playwright() as p:
        report(f"{account}: Chrome 프로필 여는 중")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            viewport={"width": 1250, "height": 880},
            locale="ko-KR",
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        try:
            page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
            page.locator("ytd-comments, #comments").first.wait_for(timeout=30000)
            page.locator("#comments").first.scroll_into_view_if_needed(timeout=20000)
            report("영상 및 댓글 입력창 찾는 중")

            # YouTube requires clicking the placeholder before the contenteditable appears.
            placeholder = page.locator(
                "ytd-comment-simplebox-renderer #placeholder-area, "
                "#simplebox-placeholder, #placeholder-area"
            ).first
            placeholder.wait_for(state="visible", timeout=20000)
            placeholder.click()

            editor = page.locator(
                "ytd-comment-simplebox-renderer #contenteditable-root[contenteditable='true'], "
                "ytd-comment-simplebox-renderer div[contenteditable='true']"
            ).first
            editor.wait_for(state="visible", timeout=10000)
            editor.click()
            report(f"댓글 한 글자씩 타이핑 중 ({len(comment)}자)")
            # Avoid fill(): each character is typed visibly.
            for ch in comment:
                page.keyboard.insert_text(ch)
                page.wait_for_timeout(55)
            typed = editor.inner_text().strip()
            if typed != comment.strip():
                raise RuntimeError("입력된 댓글이 초안과 다릅니다. 게시하지 않았습니다.")

            submit = page.locator(
                "ytd-comment-simplebox-renderer #submit-button button, "
                "ytd-comment-simplebox-renderer #submit-button yt-button-shape button"
            ).first
            submit.wait_for(state="visible", timeout=10000)
            if not submit.is_enabled():
                raise RuntimeError("게시 버튼이 비활성화되어 있습니다. 계정 로그인 상태를 확인하세요.")
            report("YouTube 게시 버튼 클릭")
            submit.click()
            clicked = True
            report("게시한 댓글 화면에 나타나는지 확인 중")

            # A submit click is not proof of posting. Look for the posted text in comment elements.
            target = page.locator(
                "ytd-comment-view-model #content-text, "
                "ytd-comment-renderer #content-text"
            ).filter(has_text=comment.strip())
            try:
                target.first.wait_for(state="visible", timeout=20000)
                posted = any(e.inner_text().strip() == comment.strip() for e in target.all()[:8])
            except PlaywrightTimeoutError:
                posted = False

            if posted:
                report("게시한 댓글을 화면에서 확인했습니다")
                return {"success": True, "message": "Chrome 댓글 게시 및 화면 확인 완료", "screenshot": None}
            error = "게시 버튼은 눌렸으나 화면에서 댓글을 찾지 못했습니다. 중복 방지를 위해 수동 확인이 필요합니다."
            report(error)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            report(error)
        finally:
            if not posted:
                try:
                    page.screenshot(path=shot, full_page=False, timeout=7000)
                except Exception:
                    shot = None
                    
            # browser.close()

    if clicked and not posted:
        return {"success": False, "message": error, "screenshot": shot}
    return {"success": False, "message": "게시하지 않았습니다: " + error, "screenshot": shot}
