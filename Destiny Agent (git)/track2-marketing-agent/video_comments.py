"""YouTube Data API v3: 공개 영상의 인기 최상위 댓글을 가져옵니다.

사용: python video_comments.py "https://youtu.be/VIDEO_ID" [최대개수]
기존 프로젝트의 youtube_oauth.py/get_youtube_client()를 재사용합니다.
"""
import json
import re
import sys
from urllib.parse import parse_qs, urlparse

from googleapiclient.errors import HttpError
from youtube_oauth import get_youtube_client


def get_video_id(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
            video_id = parsed.path.strip("/").split("/")[1]
        else:
            video_id = ""
    else:
        video_id = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("유효한 YouTube 영상 ID 또는 URL이 아닙니다.")
    return video_id


def collect_popular_comments(video_url: str, account: str = "유튜브1", maximum: int = 20) -> dict:
    """공개 최상위 댓글을 관련성 순으로 조회. 작성자 개인정보는 저장하지 않습니다."""
    if not 1 <= maximum <= 100:
        raise ValueError("maximum은 1~100 사이여야 합니다.")
    video_id = get_video_id(video_url)
    youtube = get_youtube_client(account)
    try:
        response = youtube.commentThreads().list(
            part="snippet", videoId=video_id, order="relevance",
            textFormat="plainText", maxResults=maximum,
        ).execute()
    except HttpError as exc:
        reason = ""
        try:
            details = json.loads(exc.content.decode("utf-8"))
            reason = details.get("error", {}).get("errors", [{}])[0].get("reason", "")
        except (ValueError, IndexError, AttributeError, UnicodeDecodeError):
            pass
        if reason in {"commentsDisabled", "forbidden", "videoNotFound"}:
            raise RuntimeError(f"댓글 조회 불가: {reason}") from exc
        raise RuntimeError(f"YouTube API 오류 ({exc.resp.status}): {reason or exc.reason}") from exc
    comments = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        top = snippet.get("topLevelComment", {}).get("snippet", {})
        body = (top.get("textOriginal") or top.get("textDisplay") or "").strip()
        if not body:
            continue
        comments.append({
            "text": body,
            "likes": int(top.get("likeCount", 0)),
            "published_at": top.get("publishedAt", ""),
            "reply_count": int(snippet.get("totalReplyCount", 0)),
        })
    return {"video_id": video_id, "order": "relevance", "comments": comments}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('사용: python video_comments.py "https://youtu.be/VIDEO_ID" [개수]')
        sys.exit(2)
    try:
        maximum = int(sys.argv[2]) if len(sys.argv) >= 3 else 20
        result = collect_popular_comments(sys.argv[1], maximum=maximum)
        print(f"영상 {result['video_id']} · 인기 댓글 {len(result['comments'])}개")
        for i, item in enumerate(result["comments"], 1):
            preview = " ".join(item["text"].split())[:220]
            print(f"{i:02d}. 좋아요 {item['likes']} · 답글 {item['reply_count']} | {preview}")
    except (ValueError, RuntimeError, HttpError) as exc:
        print(f"댓글 수집 실패: {exc}", file=sys.stderr)
        sys.exit(1)
