import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "oura_data.db"
DEFAULT_USER = "default"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                user_id             TEXT NOT NULL DEFAULT 'default',
                date                TEXT NOT NULL,
                readiness_score     INTEGER,
                hrv_balance         REAL,
                resting_heart_rate  INTEGER,
                sleep_score         INTEGER,
                total_sleep_hours   REAL,
                sleep_efficiency    REAL,
                activity_score      INTEGER,
                steps               INTEGER,
                calories_active     INTEGER,
                PRIMARY KEY (user_id, date)
            )
        """)
        # Migrate existing rows that pre-date the user_id column
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migration_done (id INTEGER PRIMARY KEY)
        """)
        already = conn.execute("SELECT id FROM _migration_done WHERE id=1").fetchone()
        if not already:
            try:
                conn.execute("ALTER TABLE daily_metrics ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass  # column already exists in new schema
            conn.execute("INSERT OR IGNORE INTO _migration_done VALUES (1)")


def upsert_metrics(rows: list[dict], user_id: str = DEFAULT_USER):
    if not rows:
        return
    for r in rows:
        r["user_id"] = user_id
    with _connect() as conn:
        conn.executemany("""
            INSERT INTO daily_metrics (
                user_id, date, readiness_score, hrv_balance, resting_heart_rate,
                sleep_score, total_sleep_hours, sleep_efficiency,
                activity_score, steps, calories_active
            ) VALUES (
                :user_id, :date, :readiness_score, :hrv_balance, :resting_heart_rate,
                :sleep_score, :total_sleep_hours, :sleep_efficiency,
                :activity_score, :steps, :calories_active
            )
            ON CONFLICT(user_id, date) DO UPDATE SET
                readiness_score    = excluded.readiness_score,
                hrv_balance        = excluded.hrv_balance,
                resting_heart_rate = excluded.resting_heart_rate,
                sleep_score        = excluded.sleep_score,
                total_sleep_hours  = excluded.total_sleep_hours,
                sleep_efficiency   = excluded.sleep_efficiency,
                activity_score     = excluded.activity_score,
                steps              = excluded.steps,
                calories_active    = excluded.calories_active
        """, rows)


def fetch_metrics(days: int = 60, user_id: str = DEFAULT_USER) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM daily_metrics
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT ?
        """, (user_id, days)).fetchall()
    return [dict(r) for r in reversed(rows)]


def fetch_all_metrics(user_id: str = DEFAULT_USER) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_metrics WHERE user_id = ? ORDER BY date ASC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_users() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM daily_metrics ORDER BY user_id"
        ).fetchall()
    return [r["user_id"] for r in rows]
