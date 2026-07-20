"""
Strava OAuth2 helpers.
"""
from __future__ import annotations
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("STRAVA_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
TOKEN_URL     = "https://www.strava.com/oauth/token"
AUTH_URL      = "https://www.strava.com/oauth/authorize"
SCOPE         = "activity:read_all"


def get_auth_url(redirect_uri: str) -> str:
    return (
        f"{AUTH_URL}?client_id={CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={SCOPE}"
        f"&approval_prompt=auto"
    )


def exchange_code(code: str) -> dict:
    """Exchange an auth code for tokens. Returns token dict."""
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "grant_type":    "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token. Returns updated token dict."""
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()


def get_valid_token(access_token: str, expires_at: int, refresh_token: str) -> tuple[str, dict | None]:
    """Return a valid access token, refreshing if needed.

    Returns (access_token, new_token_dict_or_None).
    new_token_dict is non-None only when a refresh happened — caller should persist it.
    """
    if time.time() < expires_at - 60:
        return access_token, None
    new = refresh_access_token(refresh_token)
    return new["access_token"], new
