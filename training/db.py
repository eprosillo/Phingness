"""
Training database — races, workouts, training plans, race results.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import get_conn, fetchall, fetchone, ph


def init_training_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                date        TEXT NOT NULL,
                distance_mi REAL NOT NULL,
                goal_pace   TEXT,
                notes       TEXT,
                created_at  TEXT DEFAULT CURRENT_DATE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workout_logs (
                id              SERIAL PRIMARY KEY,
                date            TEXT NOT NULL,
                type            TEXT NOT NULL DEFAULT 'run',
                distance_mi     REAL,
                duration_min    REAL,
                pace_per_mile   TEXT,
                effort          INTEGER,
                notes           TEXT,
                source          TEXT DEFAULT 'manual',
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS training_plans (
                id          SERIAL PRIMARY KEY,
                week_start  TEXT NOT NULL UNIQUE,
                race_id     INTEGER,
                plan_json   TEXT NOT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS race_results (
                id            SERIAL PRIMARY KEY,
                race_id       INTEGER,
                race_name     TEXT NOT NULL,
                date          TEXT NOT NULL,
                distance_mi   REAL NOT NULL,
                finish_time   TEXT NOT NULL,
                pace_per_mile TEXT,
                place         TEXT,
                notes         TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


# ── Settings ───────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = None) -> str | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT value FROM app_settings WHERE key = {ph()}", (key,))
        row = cur.fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO app_settings (key, value) VALUES ({ph()}, {ph()})
            ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value
        """, (key, value))


# ── Races ──────────────────────────────────────────────────────────────────────

def upsert_race(name: str, date: str, distance_mi: float, goal_pace: str = None, notes: str = None) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id FROM races WHERE name = {ph()} AND date = {ph()}", (name, date)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                f"UPDATE races SET distance_mi={ph()}, goal_pace={ph()}, notes={ph()} WHERE id={ph()}",
                (distance_mi, goal_pace, notes, row[0]),
            )
            return row[0]
        cur.execute(
            f"INSERT INTO races (name, date, distance_mi, goal_pace, notes) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()}) RETURNING id",
            (name, date, distance_mi, goal_pace, notes),
        )
        return cur.fetchone()[0]


def get_races() -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM races ORDER BY date ASC")
        return fetchall(cur)


def get_race(race_id: int) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM races WHERE id={ph()}", (race_id,))
        return fetchone(cur)


def delete_race(race_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM races WHERE id={ph()}", (race_id,))


# ── Workout logs ───────────────────────────────────────────────────────────────

def log_workout(
    date: str,
    workout_type: str,
    distance_mi: float = None,
    duration_min: float = None,
    pace_per_mile: str = None,
    effort: int = None,
    notes: str = None,
    source: str = "manual",
) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO workout_logs
                (date, type, distance_mi, duration_min, pace_per_mile, effort, notes, source)
            VALUES ({ph()},{ph()},{ph()},{ph()},{ph()},{ph()},{ph()},{ph()})
            RETURNING id
        """, (date, workout_type, distance_mi, duration_min, pace_per_mile, effort, notes, source))
        row = cur.fetchone()
        return row[0] if row else None


def get_workouts(days: int = 60) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM workout_logs
            ORDER BY date DESC
            LIMIT {ph()}
        """, (days,))
        return list(reversed(fetchall(cur)))


def get_strava_workouts(days: int = 60) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM workout_logs
            WHERE source = 'strava'
            ORDER BY date DESC
            LIMIT {ph()}
        """, (days,))
        return fetchall(cur)


def update_workout(
    workout_id: int,
    workout_type: str,
    distance_mi: float = None,
    duration_min: float = None,
    pace_per_mile: str = None,
    effort: int = None,
    notes: str = None,
):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE workout_logs
            SET type={ph()}, distance_mi={ph()}, duration_min={ph()},
                pace_per_mile={ph()}, effort={ph()}, notes={ph()}
            WHERE id={ph()}
        """, (workout_type, distance_mi, duration_min, pace_per_mile, effort, notes, workout_id))


def delete_workout(workout_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM workout_logs WHERE id={ph()}", (workout_id,))


# ── Training plans ─────────────────────────────────────────────────────────────

def save_training_plan(week_start: str, plan_json: str, race_id: int = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO training_plans (week_start, race_id, plan_json)
            VALUES ({ph()},{ph()},{ph()})
            ON CONFLICT(week_start) DO UPDATE SET
                plan_json  = EXCLUDED.plan_json,
                race_id    = EXCLUDED.race_id,
                created_at = CURRENT_TIMESTAMP
        """, (week_start, race_id, plan_json))


def get_training_plan(week_start: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM training_plans WHERE week_start={ph()}", (week_start,))
        return fetchone(cur)


# ── Race results ───────────────────────────────────────────────────────────────

def log_race_result(
    race_name: str,
    date: str,
    distance_mi: float,
    finish_time: str,
    pace_per_mile: str = None,
    place: str = None,
    notes: str = None,
    race_id: int = None,
) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO race_results
                (race_id, race_name, date, distance_mi, finish_time, pace_per_mile, place, notes)
            VALUES ({ph()},{ph()},{ph()},{ph()},{ph()},{ph()},{ph()},{ph()})
            RETURNING id
        """, (race_id, race_name, date, distance_mi, finish_time, pace_per_mile, place, notes))
        row = cur.fetchone()
        return row[0] if row else None


def get_race_results() -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM race_results ORDER BY date DESC")
        return fetchall(cur)


def delete_race_result(result_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM race_results WHERE id={ph()}", (result_id,))
