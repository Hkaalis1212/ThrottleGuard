"""
auth.py — ThrottleGuard authentication gate

Manual OAuth 2.0 + PKCE flow using requests + authlib.
No st.login() — avoids Streamlit's /oauth2/callback path routing which
breaks static asset resolution behind Railway's proxy.

Redirect URI must be the app root (e.g. https://your-app.railway.app).
Google appends ?code=...&state=... to it; we detect that in st.query_params.

Usage (top of app.py):
    from auth import run_auth_gate, clear_auth_session
    run_auth_gate()
"""

import hashlib
import base64
import os
import secrets

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


def _pkce_pair() -> tuple[str, str]:
    verifier  = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    from urllib.parse import urlencode
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
    """
    Run the Google OAuth flow.
    - If ?code= is in the URL: finish the exchange and set tg_user.
    - Otherwise: start the flow by redirecting to Google.
    Returns without setting tg_user only if Google env vars are not set.
    """
    client_id     = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri  = os.environ.get("REDIRECT_URI", "")

    if not all([client_id, client_secret, redirect_uri]):
        return  # Google not configured — fall through to password login

    params = st.query_params

    # ── Callback: Google redirected back with ?code= ──────────────────────────
    if "code" in params:
        code  = params["code"]
        state = params.get("state", "")

        if state != st.session_state.get("_oauth_state"):
            st.error("OAuth state mismatch — possible CSRF. Please sign in again.")
            for k in ("_oauth_state", "_oauth_verifier"):
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.stop()

        verifier = st.session_state.get("_oauth_verifier", "")

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
        print(f"[auth] Google callback — email={email}")

        if email:
            _ensure_db_ready()
            st.session_state["tg_user"] = get_or_create_google_user(email)
            for k in ("_oauth_state", "_oauth_verifier"):
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Could not retrieve your Google email. Please try again.")
            st.stop()

    # ── No code yet: start the OAuth flow ────────────────────────────────────
    else:
        state    = secrets.token_urlsafe(16)
        verifier, challenge = _pkce_pair()
        st.session_state["_oauth_state"]    = state
        st.session_state["_oauth_verifier"] = verifier

        url = _auth_url(client_id, redirect_uri, state, challenge)
        # Redirect the browser to Google
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
    for key in ["tg_user", "_auth_db_ready", "_oauth_state", "_oauth_verifier"]:
        st.session_state.pop(key, None)
