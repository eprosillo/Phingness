import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.ouraring.com/v2/usercollection"


def _headers():
    token = os.getenv("OURA_TOKEN")
    if not token:
        raise EnvironmentError("OURA_TOKEN not set in environment / .env file")
    return {"Authorization": f"Bearer {token}"}


def _get(endpoint: str, params: dict) -> list:
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def fetch_range(start: date, end: date) -> dict:
    params = {"start_date": str(start), "end_date": str(end)}
    return {
        "readiness":   _get("daily_readiness", params),
        "daily_sleep": _get("daily_sleep", params),
        "sleep":       _get("sleep", params),
        "activity":    _get("daily_activity", params),
    }


def fetch_last_n_days(n: int = 30) -> dict:
    end = date.today()
    start = end - timedelta(days=n - 1)
    return fetch_range(start, end)
