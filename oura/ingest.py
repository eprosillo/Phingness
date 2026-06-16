"""
Pull data from Oura API and store in SQLite.
Merges readiness, daily_sleep, sleep (detailed), and activity by date.
"""
from __future__ import annotations
from .api import fetch_last_n_days, fetch_range
from .db import init_db, upsert_metrics, DEFAULT_USER
from datetime import date


def _parse(raw: dict) -> list[dict]:
    by_date: dict[str, dict] = {}

    # Readiness: score + hrv_balance contributor score + rhr contributor score
    for r in raw.get("readiness", []):
        d = r["day"]
        by_date.setdefault(d, {"date": d})
        by_date[d]["readiness_score"] = r.get("score")
        contrib = r.get("contributors", {})
        # hrv_balance here is a 0-100 contributor score, useful for trend tracking
        by_date[d]["hrv_balance"] = contrib.get("hrv_balance")

    # Daily sleep: score + efficiency contributor score
    for s in raw.get("daily_sleep", []):
        d = s["day"]
        by_date.setdefault(d, {"date": d})
        by_date[d]["sleep_score"] = s.get("score")
        by_date[d]["sleep_efficiency"] = s.get("contributors", {}).get("efficiency")

    # Sleep (detailed sessions): raw duration, actual RHR bpm, raw HRV ms
    # Multiple sessions per day possible — aggregate by summing duration, taking min HR
    for s in raw.get("sleep", []):
        d = s["day"]
        by_date.setdefault(d, {"date": d})
        dur_sec = s.get("total_sleep_duration") or 0
        existing_dur = by_date[d].get("_total_sleep_sec", 0) or 0
        by_date[d]["_total_sleep_sec"] = existing_dur + dur_sec

        rhr = s.get("lowest_heart_rate")
        existing_rhr = by_date[d].get("resting_heart_rate")
        if rhr is not None:
            by_date[d]["resting_heart_rate"] = (
                min(existing_rhr, rhr) if existing_rhr is not None else rhr
            )

        hrv_ms = s.get("average_hrv")
        existing_hrv_ms = by_date[d].get("_hrv_ms")
        # Keep highest HRV reading across sessions
        if hrv_ms is not None:
            by_date[d]["_hrv_ms"] = (
                max(existing_hrv_ms, hrv_ms) if existing_hrv_ms is not None else hrv_ms
            )

    # Convert accumulated sleep seconds → hours
    for row in by_date.values():
        sec = row.pop("_total_sleep_sec", None)
        if sec:
            row["total_sleep_hours"] = round(sec / 3600, 2)
        # If we have raw HRV ms and no contributor score, use raw ms for trend
        hrv_ms = row.pop("_hrv_ms", None)
        if hrv_ms is not None and row.get("hrv_balance") is None:
            row["hrv_balance"] = hrv_ms

    # Activity: score + steps + active calories
    for a in raw.get("activity", []):
        d = a["day"]
        by_date.setdefault(d, {"date": d})
        by_date[d]["activity_score"] = a.get("score")
        by_date[d]["steps"] = a.get("steps")
        by_date[d]["calories_active"] = a.get("active_calories")

    # Fill missing keys with None
    keys = [
        "readiness_score", "hrv_balance", "resting_heart_rate",
        "sleep_score", "total_sleep_hours", "sleep_efficiency",
        "activity_score", "steps", "calories_active",
    ]
    for row in by_date.values():
        for k in keys:
            row.setdefault(k, None)

    return list(by_date.values())


def sync(days: int = 60, user_id: str = DEFAULT_USER):
    init_db()
    raw = fetch_last_n_days(days)
    rows = _parse(raw)
    upsert_metrics(rows, user_id=user_id)
    return len(rows)


def sync_range(start: date, end: date, user_id: str = DEFAULT_USER):
    init_db()
    raw = fetch_range(start, end)
    rows = _parse(raw)
    upsert_metrics(rows, user_id=user_id)
    return len(rows)
