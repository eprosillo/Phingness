"""
Fetch Strava activities and save them to the workout_logs table.
"""
from __future__ import annotations
import os
import time
import requests
from dotenv import load_dotenv
from training.db import log_workout, get_workouts

load_dotenv()

API_BASE = "https://www.strava.com/api/v3"

ACTIVITY_TYPE_MAP = {
    "Run":          "easy run",
    "TrailRun":     "easy run",
    "VirtualRun":   "easy run",
    "Workout":      "cross-train",
    "Ride":         "cross-train",
    "VirtualRide":  "cross-train",
    "Swim":         "cross-train",
    "Walk":         "cross-train",
    "Hike":         "cross-train",
    "WeightTraining": "cross-train",
    "Yoga":         "cross-train",
}


def _meters_to_miles(m: float) -> float:
    return round(m / 1609.344, 2)


def _seconds_to_pace(distance_m: float, time_s: float) -> str | None:
    """Return pace as MM:SS per mile string."""
    if not distance_m or not time_s:
        return None
    pace_s = time_s / (distance_m / 1609.344)
    mins = int(pace_s // 60)
    secs = int(pace_s % 60)
    return f"{mins}:{secs:02d}"


def _existing_dates() -> set[str]:
    return {w["date"] for w in get_workouts(days=365) if w.get("source") == "strava"}


def fetch_and_sync(access_token: str, days: int = 60) -> int:
    """Pull recent Strava activities and upsert into workout_logs.

    Returns number of new activities saved.
    """
    after = int(time.time()) - days * 86400
    existing = _existing_dates()
    saved = 0
    page = 1

    while True:
        resp = requests.get(
            f"{API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after, "per_page": 50, "page": page},
        )
        resp.raise_for_status()
        activities = resp.json()
        if not activities:
            break

        for a in activities:
            act_date = a["start_date_local"][:10]
            if act_date in existing:
                continue

            workout_type = ACTIVITY_TYPE_MAP.get(a.get("type", ""), "cross-train")

            # Try to classify running workouts more specifically by name
            name_lower = a.get("name", "").lower()
            if workout_type == "easy run":
                if any(w in name_lower for w in ["tempo", "threshold"]):
                    workout_type = "tempo"
                elif any(w in name_lower for w in ["interval", "repeat", "track"]):
                    workout_type = "intervals"
                elif any(w in name_lower for w in ["long"]):
                    workout_type = "long run"

            dist_m  = a.get("distance", 0)
            time_s  = a.get("moving_time", 0)
            dist_mi = _meters_to_miles(dist_m) if dist_m else None
            pace    = _seconds_to_pace(dist_m, time_s) if dist_m and time_s else None
            dur_min = round(time_s / 60, 1) if time_s else None

            effort = a.get("perceived_exertion")
            if effort is None:
                hr_max = a.get("max_heartrate")
                effort = min(10, max(1, int(hr_max / 20))) if hr_max else 5

            notes = a.get("name", "")
            if a.get("suffer_score"):
                notes += f" (suffer score: {a['suffer_score']})"

            log_workout(
                date=act_date,
                workout_type=workout_type,
                distance_mi=dist_mi,
                duration_min=dur_min,
                pace_per_mile=pace,
                effort=effort,
                notes=notes,
                source="strava",
            )
            existing.add(act_date)
            saved += 1

        page += 1

    return saved
