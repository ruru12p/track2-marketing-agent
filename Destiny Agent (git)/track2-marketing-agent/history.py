"""영구적인 영상+계정별 1회 예약 및 전체 계정 합산 일일 게시 상한 관리."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parent / "live_history.sqlite3"

CREATE_POSTS = """
CREATE TABLE posts (
    video_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    account TEXT NOT NULL,
    comment TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    day TEXT NOT NULL,
    message TEXT DEFAULT '',
    screenshot TEXT DEFAULT '',
    PRIMARY KEY (video_id, account)
)
"""


def _initialize(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='posts'"
        ).fetchone()
        if not exists:
            db.execute(CREATE_POSTS)
        else:
            columns = db.execute("PRAGMA table_info(posts)").fetchall()
            pk = [c[1] for c in sorted(columns, key=lambda c: c[5]) if c[5] > 0]
            if pk == ["video_id"]:
                # 기존 행을 보존하면서 복합 기본키로 전환
                db.execute(CREATE_POSTS.replace("CREATE TABLE posts", "CREATE TABLE posts_new"))
                db.execute("""
                    INSERT INTO posts_new
                        (video_id, channel_id, account, comment, status,
                         created_at, day, message, screenshot)
                    SELECT video_id, channel_id, account, comment, status,
                           created_at, day, message, screenshot FROM posts
                """)
                db.execute("DROP TABLE posts")
                db.execute("ALTER TABLE posts_new RENAME TO posts")
            elif pk != ["video_id", "account"]:
                raise RuntimeError(f"알 수 없는 posts 기본키 구조: {pk}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_posts_day ON posts(day, status)")
        db.commit()
    except Exception:
        db.rollback()
        raise


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    try:
        _initialize(db)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def stats(video_id, account, daily_limit):
    with connect() as db:
        found = db.execute(
            "SELECT status FROM posts WHERE video_id=? AND account=?",
            (video_id, account),
        ).fetchone()
        day = datetime.now().astimezone().date().isoformat()
        today = db.execute(
            """SELECT COUNT(*) FROM posts WHERE day=?
               AND status IN ('pending', 'confirmed', 'uncertain')""",
            (day,),
        ).fetchone()[0]
    return found[0] if found else None, today, today >= daily_limit


def reserve(video_id, channel_id, account, comment, daily_limit):
    now = datetime.now().astimezone()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        found = db.execute(
            "SELECT status FROM posts WHERE video_id=? AND account=?",
            (video_id, account),
        ).fetchone()
        if found:
            return False, f"{account}은(는) 이 영상에 이미 게시/시도 기록이 있습니다: {found[0]}"
        today = db.execute(
            """SELECT COUNT(*) FROM posts WHERE day=?
               AND status IN ('pending', 'confirmed', 'uncertain')""",
            (now.date().isoformat(),),
        ).fetchone()[0]
        if today >= daily_limit:
            return False, f"하루 최대 {daily_limit}개 상한에 도달했습니다."
        db.execute(
            """INSERT INTO posts
               (video_id, channel_id, account, comment, status, created_at, day)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (video_id, channel_id, account, comment, "pending",
             now.isoformat(timespec="seconds"), now.date().isoformat()),
        )
    return True, "예약 완료"


def finish(video_id, account, success, message, screenshot=None):
    # 결과가 불확실하면 해당 영상/계정의 예약을 그대로 잠근다.
    with connect() as db:
        cur = db.execute(
            """UPDATE posts SET status=?, message=?, screenshot=?
               WHERE video_id=? AND account=? AND status='pending'""",
            ("confirmed" if success else "uncertain", message,
             screenshot or "", video_id, account),
        )
        if cur.rowcount != 1:
            raise RuntimeError("완료 처리할 pending 예약을 찾지 못했습니다.")




def last_rows(limit=15):
    with connect() as db:
        return db.execute(
            """
            SELECT
                created_at,
                video_id,
                account,
                status,
                message,
                screenshot,
                comment
            FROM posts
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()




