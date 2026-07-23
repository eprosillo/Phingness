"""
Unified database layer.
Uses PostgreSQL (Supabase) when DATABASE_URL is set, SQLite otherwise.
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = Path(__file__).parent / "oura_data.db"


def _get_db_url() -> str | None:
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    except Exception:
        return os.getenv("DATABASE_URL")


def _is_postgres() -> bool:
    url = _get_db_url()
    return bool(url and url.startswith("postgresql"))


@contextmanager
def get_conn():
    if _is_postgres():
        import psycopg2
        import psycopg2.extras
        url = _get_db_url().split("?")[0]  # strip query params psycopg2 can't handle
        conn = psycopg2.connect(url)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def fetchall(cursor) -> list[dict]:
    """Normalize rows from either psycopg2 or sqlite3 cursor to list of dicts."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetchone(cursor) -> dict | None:
    cols = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    return dict(zip(cols, row)) if row else None


def placeholder(n: int = 1) -> str:
    """Return %s for postgres or ? for sqlite."""
    if _is_postgres():
        return ", ".join(["%s"] * n)
    return ", ".join(["?"] * n)


def ph() -> str:
    """Single placeholder."""
    return "%s" if _is_postgres() else "?"
