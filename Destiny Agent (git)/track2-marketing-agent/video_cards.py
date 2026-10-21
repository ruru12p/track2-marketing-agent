"""Streamlit video cards for a pre-existing list of YouTube videos.

Usage inside an existing Streamlit app:
    from video_cards import enrich_videos, render_video_cards
    enriched = enrich_videos(st.session_state.videos)
    render_video_cards(enriched)

Requires yt-dlp and streamlit. Does not modify the supplied items.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import re

import streamlit as st
import yt_dlp

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _video_id(url: str) -> str | None:
    p = urlparse(url)
    if p.hostname in ("youtu.be", "www.youtu.be"):
        candidate = p.path.strip("/").split("/")[0]
    elif p.hostname in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        candidate = (parse_qs(p.query).get("v") or [""])[0]
        if not candidate and p.path.startswith("/shorts/"):
            candidate = p.path.split("/")[2]
    else:
        return None
    return candidate if _ID.fullmatch(candidate) else None


def _date_string(value) -> str | None:
    if value is None:
        return None
    raw = str(value)
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_video_metadata(video_id: str) -> dict:
    """Fetch a single video's real upload date/title/thumbnail; never invent metadata."""
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True, "socket_timeout": 12, "retries": 1,
        "extractor_args": {"youtube": {"lang": ["ko"]}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    info = info or {}
    thumb = info.get("thumbnail")
    if not thumb:
        thumbs = info.get("thumbnails") or []
        thumb = next((t.get("url") for t in reversed(thumbs) if t.get("url")), None)
    return {
        "title": info.get("title") or None,
        "channel": info.get("channel") or info.get("uploader") or None,
        "uploaded": _date_string(info.get("upload_date")) or _date_string(info.get("release_date")),
        "thumbnail": thumb,
    }


def enrich_videos(videos: list[dict], workers: int = 4) -> list[dict]:
    """Run metadata lookups concurrently, keeping each original video even on errors."""
    result = [dict(v) for v in videos]
    tasks = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 5))) as pool:
        for index, v in enumerate(result):
            vid = _video_id(v.get("url", ""))
            if vid:
                v["video_id"] = vid
                tasks[pool.submit(_fetch_video_metadata, vid)] = index
        for job in as_completed(tasks):
            i = tasks[job]
            try:
                details = job.result()
            except Exception:
                details = {}
            # Prefer actual original/Korean title from existing collection, which
            # already sets yt-dlp's preferred Korean language. Only fill blanks.
            if not result[i].get("title") and details.get("title"):
                result[i]["title"] = details["title"]
            if not result[i].get("channel") and details.get("channel"):
                result[i]["channel"] = details["channel"]
            result[i]["upload_date"] = details.get("uploaded") or _date_string(result[i].get("upload_date"))
            result[i]["thumbnail"] = details.get("thumbnail") or result[i].get("thumbnail")
    return result


def render_video_cards(videos: list[dict]):
    st.caption(f"수집된 영상 · {len(videos)}개")
    for index, video in enumerate(videos, 1):
        title = str(video.get("title") or "제목 정보 없음")
        channel = str(video.get("channel") or "채널 미확인")
        date = video.get("upload_date") or "게시일 확인 불가"
        url = video.get("url", "")
        video_id = video.get("video_id") or _video_id(url)
        thumb = video.get("thumbnail") or (
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None
        )
        with st.container(border=True):
            cols = st.columns([1, 2.3], gap="small", vertical_alignment="center")
            with cols[0]:
                if thumb:
                    st.image(thumb, use_container_width=True)
            with cols[1]:
                st.markdown(f"**{index}. {title}**")
                st.caption(f"{channel}  ·  {date}")
            with st.expander("영상 상세 / 링크", expanded=False):
                st.write(title)
                st.caption(f"채널: {channel} | 게시일: {date}")
                if url:
                    st.link_button("YouTube에서 보기", url, use_container_width=True)
