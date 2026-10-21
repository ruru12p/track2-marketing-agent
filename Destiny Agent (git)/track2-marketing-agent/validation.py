"""Validate actual channel owner before any live post, never trust the search label."""
import re
from urllib.parse import urlparse, parse_qs

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

def get_video_id(url):
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    if p.scheme != "https":
        return ""
    if host in ("youtu.be", "www.youtu.be"):
        vid = p.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        parts = p.path.strip("/").split("/")
        if p.path == "/watch":
            vid = parse_qs(p.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in ("shorts", "live", "embed"):
            vid = parts[1]
        else:
            return ""
    else:
        return ""
    return vid if VIDEO_ID.fullmatch(vid) else ""

def get_video_details(url):
    import yt_dlp
    vid = get_video_id(url)
    if not vid:
        raise ValueError("지원하지 않는 유튜브 주소입니다")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    return {"video_id": vid, "channel_id": info.get("channel_id") or "", "title": info.get("title") or "", "channel": info.get("channel") or "", "description": info.get("description") or ""}

def verify_video(url, allowed_channel_ids):
    info = get_video_details(url)
    if not info["channel_id"]:
        raise ValueError("실제 영상의 채널 ID를 확인하지 못해 게시를 차단했습니다")
    if info["channel_id"] not in set(allowed_channel_ids):
        raise ValueError(f"허용되지 않은 채널입니다: {info['channel']} ({info['channel_id']})")
    return info
