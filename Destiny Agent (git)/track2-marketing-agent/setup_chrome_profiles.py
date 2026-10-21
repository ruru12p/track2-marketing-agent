
"""유튜브1·2·3의 독립 Chrome 프로필 초기 설정."""

import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROFILES = BASE / "profiles"

CHROME = Path(
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)

if not CHROME.exists():
    CHROME = Path(
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )

if not CHROME.exists():
    raise FileNotFoundError(
        "Google Chrome을 찾지 못했습니다."
    )

ACCOUNTS = ("유튜브1", "유튜브2", "유튜브3")

for account in ACCOUNTS:
    profile_dir = PROFILES / account
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[{account}] 일반 Chrome 실행")
    print(f"프로필 위치: {profile_dir}")

    process = subprocess.Popen([
        str(CHROME),
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--new-window",
        "https://www.youtube.com/"
    ])

    input(
        f"\n{account} 계정으로 로그인하고 "
        "YouTube 채널을 확인하세요.\n"
        "확인 후 Chrome 창을 닫고 Enter를 누르세요..."
    )

    if process.poll() is None:
        print("Chrome이 아직 실행 중입니다.")
        print("창을 완전히 종료한 뒤 다음 계정으로 진행하세요.")
        process.wait()

print("\nChrome 프로필 3개 설정 완료")
