"""
auth.py — ThrottleGuard authentication gate

Manual OAuth 2.0 + PKCE flow using requests.
The PKCE verifier is encoded into the state parameter (HMAC-signed) so it
survives the full-page redirect to Google and back — Streamlit session state
does not persist across page redirects, so we cannot store state there.

Redirect URI must be the app root (e.g. https://your-app.railway.app).
Google appends ?code=...&state=... to it; we detect that in st.query_params.

Usage (top of app.py):
    from auth import run_auth_gate, clear_auth_session
    run_auth_gate()
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import urlencode

import requests
import streamlit as st

from tg_auth import init_auth_db, login_page, get_or_create_google_user

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_INFO_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"


def _ensure_db_ready() -> None:
    if "_auth_db_ready" not in st.session_state:
        init_auth_db()
        st.session_state["_auth_db_ready"] = True


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier  = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ── Signed state token — stateless CSRF protection ───────────────────────────
# We encode the PKCE verifier into the OAuth state parameter and sign it with
# SESSION_SECRET. Google returns the state unchanged, so we can decode the
# verifier from it on the callback without any server-side session storage.

def _secret() -> bytes:
    return os.environ.get("SESSION_SECRET", "throttleguard-default").encode()


def _encode_state(verifier: str) -> str:
    payload = json.dumps({"v": verifier}).encode()
    sig     = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()
    raw     = json.dumps({"p": payload.decode(), "s": sig})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_state(state: str) -> str | None:
    """Return the PKCE verifier from a signed state token, or None if invalid."""
    try:
        padded  = state + "=" * (-len(state) % 4)
        raw     = json.loads(base64.urlsafe_b64decode(padded).decode())
        payload = raw["p"].encode()
        expected = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, raw["s"]):
            return None
        return json.loads(payload)["v"]
    except Exception:
        return None


# ── OAuth flow ────────────────────────────────────────────────────────────────

def _build_auth_url(client_id: str, redirect_uri: str,
                    state: str, challenge: str) -> str:
    params = {
        "client_id":             client_id,
        "redirect_uri":          redirect_uri,
        "response_type":         "code",
        "scope":                 "openid email profile",
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "prompt":                "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _exchange_code(code: str, verifier: str, client_id: str,
                   client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
        "grant_type":    "authorization_code",
        "code_verifier": verifier,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _google_gate() -> None:
    client_id     = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
    redirect_uri  = (os.environ.get("REDIRECT_URI") or "").strip()

    if not all([client_id, client_secret, redirect_uri]):
        return  # Google not configured — fall through to password login

    params = st.query_params

    # ── Callback: Google returned ?code=... ───────────────────────────────────
    if "code" in params:
        code     = params["code"]
        state    = params.get("state", "")
        verifier = _decode_state(state)

        if verifier is None:
            st.error("Invalid OAuth state. Please sign in again.")
            st.query_params.clear()
            st.stop()

        try:
            token = _exchange_code(code, verifier, client_id, client_secret, redirect_uri)
        except Exception as exc:
            st.error(f"Token exchange failed: {exc}")
            st.stop()

        userinfo = requests.get(
            GOOGLE_INFO_URL,
            headers={"Authorization": f"Bearer {token['access_token']}"},
            timeout=10,
        ).json()

        email = userinfo.get("email", "")
        print(f"[auth] Google sign-in: {email}")

        if email:
            _ensure_db_ready()
            st.session_state["tg_user"] = get_or_create_google_user(email)
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Could not retrieve your Google email. Please try again.")
            st.stop()

    # ── No code: start the OAuth flow ─────────────────────────────────────────
    else:
        # Force https — Google rejects http redirect_uris for non-localhost
        if redirect_uri.startswith("http://") and "localhost" not in redirect_uri:
            redirect_uri = redirect_uri.replace("http://", "https://", 1)

        verifier, challenge = _pkce_pair()
        state = _encode_state(verifier)
        url   = _build_auth_url(client_id, redirect_uri, state, challenge)

        print(f"[auth] redirect_uri = {redirect_uri}")
        print(f"[auth] full auth_url = {url}")

        st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">',
                    unsafe_allow_html=True)
        st.stop()


def run_auth_gate() -> None:
    """
    Call once at the very top of app.py.
    Returns only when st.session_state['tg_user'] is set.
    """
    if not st.session_state.get("tg_user"):
        _google_gate()

    _ensure_db_ready()

    if not st.session_state.get("tg_user"):
        login_page()
        st.stop()


def clear_auth_session() -> None:
    """Clear auth state on sign-out. Caller should call st.rerun() after."""
    for key in ["tg_user", "_auth_db_ready"]:
        st.session_state.pop(key, None)
