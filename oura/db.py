from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import get_conn, fetchall, fetchone, ph

DEFAULT_USER = "default"


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
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


def upsert_metrics(rows: list[dict], user_id: str = DEFAULT_USER):
    if not rows:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        p = ph()
        for r in rows:
            cur.execute(f"""
                INSERT INTO daily_metrics (
                    user_id, date, readiness_score, hrv_balance, resting_heart_rate,
                    sleep_score, total_sleep_hours, sleep_efficiency,
                    activity_score, steps, calories_active
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                ON CONFLICT(user_id, date) DO UPDATE SET
                    readiness_score    = EXCLUDED.readiness_score,
                    hrv_balance        = EXCLUDED.hrv_balance,
                    resting_heart_rate = EXCLUDED.resting_heart_rate,
                    sleep_score        = EXCLUDED.sleep_score,
                    total_sleep_hours  = EXCLUDED.total_sleep_hours,
                    sleep_efficiency   = EXCLUDED.sleep_efficiency,
                    activity_score     = EXCLUDED.activity_score,
                    steps              = EXCLUDED.steps,
                    calories_active    = EXCLUDED.calories_active
            """, (
                user_id, r.get("date"), r.get("readiness_score"), r.get("hrv_balance"),
                r.get("resting_heart_rate"), r.get("sleep_score"), r.get("total_sleep_hours"),
                r.get("sleep_efficiency"), r.get("activity_score"), r.get("steps"),
                r.get("calories_active"),
            ))


def fetch_metrics(days: int = 60, user_id: str = DEFAULT_USER) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        p = ph()
        cur.execute(f"""
            SELECT * FROM daily_metrics
            WHERE user_id = {p}
            ORDER BY date DESC
            LIMIT {p}
        """, (user_id, days))
        rows = fetchall(cur)
    return list(reversed(rows))


def fetch_all_metrics(user_id: str = DEFAULT_USER) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM daily_metrics WHERE user_id = {ph()} ORDER BY date ASC",
            (user_id,),
        )
        return fetchall(cur)


def list_users() -> list[str]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT user_id FROM daily_metrics ORDER BY user_id")
        return [r[0] for r in cur.fetchall()]
