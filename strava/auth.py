"""
Strava OAuth2 helpers.
"""
from __future__ import annotations
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://www.strava.com/oauth/token"
AUTH_URL  = "https://www.strava.com/oauth/authorize"
SCOPE     = "activity:read_all"


def _get(key: str) -> str:
    try:
        import streamlit as st
        return str(st.secrets.get(key) or os.getenv(key, ""))
    except Exception:
        return os.getenv(key, "")


def get_auth_url(redirect_uri: str) -> str:
    client_id = _get("STRAVA_CLIENT_ID")
    return (
        f"{AUTH_URL}?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={SCOPE}"
        f"&approval_prompt=auto"
    )


def exchange_code(code: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id":     _get("STRAVA_CLIENT_ID"),
        "client_secret": _get("STRAVA_CLIENT_SECRET"),
        "code":          code,
        "grant_type":    "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id":     _get("STRAVA_CLIENT_ID"),
        "client_secret": _get("STRAVA_CLIENT_SECRET"),
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()


def get_valid_token(access_token: str, expires_at: int, refresh_token: str) -> tuple[str, dict | None]:
    if time.time() < expires_at - 60:
        return access_token, None
    new = refresh_access_token(refresh_token)
    return new["access_token"], new
