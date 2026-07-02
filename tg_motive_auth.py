"""
tg_motive_auth.py
=================
Persistent storage for Motive OAuth tokens — Supabase PostgreSQL backend.

Replaces the in-memory token_store in api.py. Railway redeploys/restarts wipe
process memory, which would otherwise force a fleet operator to redo the OAuth
authorization flow every time the service restarts.

Schema
------
tg_motive_tokens
    id              SERIAL PRIMARY KEY
    provider        TEXT        UNIQUE — "motive" (room for other telematics providers later)
    access_token    TEXT
    refresh_token   TEXT        NULL — Motive may not always issue one
    expires_at      TEXT        (ISO timestamp) — when access_token stops working
    updated_at      TEXT        (ISO timestamp) — last time this row was written
"""

import logging

import httpx
import psycopg2.extras
from datetime import datetime, timedelta, timezone

from tg_db import get_conn

log = logging.getLogger(__name__)


def _now() -> datetime:
    """Naive UTC datetime — drop-in for the deprecated _now()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tg_motive_tokens (
    id              SERIAL PRIMARY KEY,
    provider        TEXT NOT NULL UNIQUE,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT,
    expires_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

# Refresh this many seconds before expiry so a poller never gets caught
# mid-request with a token that just went stale.
EXPIRY_BUFFER_SECONDS = 300


def init_db() -> None:
    """Create the tg_motive_tokens table if it doesn't exist."""
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(CREATE_TABLE_SQL)
    finally:
        conn.close()


def save_token(provider: str, access_token: str, refresh_token: str, expires_in: int) -> None:
    """
    Store (or replace) the token for a provider.

    expires_in is the "seconds from now" value Motive returns — we convert it
    to an absolute expires_at timestamp so callers don't need to track when
    the token was issued.
    """
    init_db()
    now        = _now()
    expires_at = now + timedelta(seconds=expires_in or 0)

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tg_motive_tokens
                    (provider, access_token, refresh_token, expires_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider) DO UPDATE SET
                    access_token  = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expires_at    = EXCLUDED.expires_at,
                    updated_at    = EXCLUDED.updated_at
                """,
                (provider, access_token, refresh_token, expires_at.isoformat(), now.isoformat()),
            )
    finally:
        conn.close()


def get_token(provider: str) -> dict | None:
    """Return the stored token row for a provider, or None if not connected yet."""
    init_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT provider, access_token, refresh_token, expires_at, updated_at "
                "FROM tg_motive_tokens WHERE provider = %s",
                (provider,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def token_is_expired(provider: str) -> bool:
    """
    True if there's no stored token, or the stored token is expired
    (or about to expire within EXPIRY_BUFFER_SECONDS).
    """
    token = get_token(provider)
    if not token:
        return True

    expires_at = datetime.fromisoformat(token["expires_at"])
    return _now() >= expires_at - timedelta(seconds=EXPIRY_BUFFER_SECONDS)


def refresh_access_token(provider: str, client_id: str, client_secret: str, token_url: str) -> bool:
    """
    Use the stored refresh_token to get a new access_token from Motive.

    Motive access tokens expire (typically after 2 hours). This should be called
    proactively whenever token_is_expired() returns True — before making any
    API calls, not after getting a 401.

    Returns True if the refresh succeeded and the new token was saved.
    Returns False if there's no refresh_token stored, or the Motive request fails
    (caller should then re-run the full OAuth flow via /authorize).
    """
    stored = get_token(provider)
    if not stored or not stored.get("refresh_token"):
        log.warning(f"[{provider}] No refresh_token stored — full OAuth re-authorization needed")
        return False

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                token_url,
                data={
                    "grant_type":    "refresh_token",
                    "refresh_token": stored["refresh_token"],
                    "client_id":     client_id,
                    "client_secret": client_secret,
                },
            )

        if response.status_code != 200:
            log.error(f"[{provider}] Token refresh failed: {response.status_code} {response.text[:300]}")
            return False

        token_data = response.json()
        new_access  = token_data.get("access_token")
        new_refresh = token_data.get("refresh_token") or stored["refresh_token"]
        expires_in  = int(token_data.get("expires_in") or 3600)

        save_token(provider, new_access, new_refresh, expires_in)
        log.info(f"[{provider}] Access token refreshed — expires in {expires_in}s")
        return True

    except Exception as exc:
        log.error(f"[{provider}] Token refresh exception: {exc}")
        return False
