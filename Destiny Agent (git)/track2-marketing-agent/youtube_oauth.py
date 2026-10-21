
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE = Path(__file__).resolve().parent

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl"
]


def get_youtube_client(account="유튜브1", login=False):
    token_dir = BASE / "oauth_tokens"
    token_dir.mkdir(exist_ok=True)

    token_file = token_dir / f"{account}.json"
    client_file = BASE / "client_secret.json"

    if not client_file.exists():
        raise FileNotFoundError(
            "client_secret.json 파일이 없습니다."
        )

    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_file), SCOPES
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not login:
            raise RuntimeError(
                f"{account}의 OAuth 인증이 필요합니다."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_file), SCOPES
        )

        creds = flow.run_local_server(port=0)

    token_file.write_text(
        creds.to_json(),
        encoding="utf-8"
    )

    return build(
        "youtube",
        "v3",
        credentials=creds,
        cache_discovery=False
    )


def get_my_channel(account="유튜브1", login=False):
    youtube = get_youtube_client(account, login=login)

    response = youtube.channels().list(
        part="snippet",
        mine=True
    ).execute()

    items = response.get("items", [])

    if not items:
        raise RuntimeError(
            "인증된 YouTube 채널을 찾지 못했습니다."
        )

    channel = items[0]

    return {
        "id": channel["id"],
        "title": channel["snippet"]["title"]
    }


def post_youtube_comment(
    video_id,
    channel_id,
    comment_text,
    account="유튜브1"
):
    youtube = get_youtube_client(account)

    response = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "channelId": channel_id,
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": comment_text
                    }
                }
            }
        }
    ).execute()

    comment = response["snippet"]["topLevelComment"]

    return {
        "thread_id": response["id"],
        "comment_id": comment["id"],
        "text": comment["snippet"].get(
            "textDisplay", ""
        )
    }
