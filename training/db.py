"""
Training database — races, workouts, training plans, race results.
Uses the same SQLite file as oura/db.py.
"""
from __future__ import annotations
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent.parent / "oura_data.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_training_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                date        TEXT NOT NULL,
                distance_mi REAL NOT NULL,
                goal_pace   TEXT,
                notes       TEXT,
                created_at  TEXT DEFAULT (date('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workout_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                type            TEXT NOT NULL DEFAULT 'run',
                distance_mi     REAL,
                duration_min    REAL,
                pace_per_mile   TEXT,
                effort          INTEGER,
                notes           TEXT,
                source          TEXT DEFAULT 'manual',
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_plans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start  TEXT NOT NULL UNIQUE,
                race_id     INTEGER,
                plan_json   TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS race_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id     INTEGER,
                race_name   TEXT NOT NULL,
                date        TEXT NOT NULL,
                distance_mi REAL NOT NULL,
                finish_time TEXT NOT NULL,
                pace_per_mile TEXT,
                place       TEXT,
                notes       TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)


# ── Races ──────────────────────────────────────────────────────────────────────

def upsert_race(name: str, date: str, distance_mi: float, goal_pace: str = None, notes: str = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id FROM races WHERE name = ? AND date = ?", (name, date)
        )
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE races SET distance_mi=?, goal_pace=?, notes=? WHERE id=?",
                (distance_mi, goal_pace, notes, row["id"]),
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO races (name, date, distance_mi, goal_pace, notes) VALUES (?,?,?,?,?)",
            (name, date, distance_mi, goal_pace, notes),
        )
        return cur.lastrowid


def get_races() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM races ORDER BY date ASC").fetchall()
    return [dict(r) for r in rows]


def get_race(race_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM races WHERE id=?", (race_id,)).fetchone()
    return dict(row) if row else None


def delete_race(race_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM races WHERE id=?", (race_id,))


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
    with _connect() as conn:
        cur = conn.execute("""
            INSERT INTO workout_logs
                (date, type, distance_mi, duration_min, pace_per_mile, effort, notes, source)
            VALUES (?,?,?,?,?,?,?,?)
        """, (date, workout_type, distance_mi, duration_min, pace_per_mile, effort, notes, source))
        return cur.lastrowid


def get_workouts(days: int = 60) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM workout_logs
            ORDER BY date DESC
            LIMIT ?
        """, (days,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def delete_workout(workout_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM workout_logs WHERE id=?", (workout_id,))


# ── Training plans ─────────────────────────────────────────────────────────────

def save_training_plan(week_start: str, plan_json: str, race_id: int = None):
    with _connect() as conn:
        conn.execute("""
            INSERT INTO training_plans (week_start, race_id, plan_json)
            VALUES (?,?,?)
            ON CONFLICT(week_start) DO UPDATE SET
                plan_json = excluded.plan_json,
                race_id   = excluded.race_id,
                created_at = datetime('now')
        """, (week_start, race_id, plan_json))


def get_training_plan(week_start: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM training_plans WHERE week_start=?", (week_start,)
        ).fetchone()
    return dict(row) if row else None


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
    with _connect() as conn:
        cur = conn.execute("""
            INSERT INTO race_results
                (race_id, race_name, date, distance_mi, finish_time, pace_per_mile, place, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (race_id, race_name, date, distance_mi, finish_time, pace_per_mile, place, notes))
        return cur.lastrowid


def get_race_results() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM race_results ORDER BY date DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_race_result(result_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM race_results WHERE id=?", (result_id,))
