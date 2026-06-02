"""
auth.py — ThrottleGuard Google OAuth gate

Uses streamlit-oauth which supports PKCE natively.
Falls back to username/password login when Google env vars are not set.

Usage (top of app.py):
    from auth import run_auth_gate
    run_auth_gate()
"""

import os
import streamlit as st

from tg_auth import init_auth_db, login_page, get_or_create_google_user


def _ensure_db_ready() -> None:
    if "_auth_db_ready" not in st.session_state:
        init_auth_db()
        st.session_state["_auth_db_ready"] = True


def _google_gate() -> None:
    """
    Render the Google sign-in button via streamlit-oauth (PKCE-compliant).
    On success: fetches email from Google userinfo, sets st.session_state['tg_user'].
    If not yet authenticated: renders the button and calls st.stop().
    """
    client_id     = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri  = os.environ.get("REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        return  # Google not configured — fall through to password login

    from streamlit_oauth import OAuth2Component
    import requests

    oauth2 = OAuth2Component(
        client_id=client_id,
        client_secret=client_secret,
        authorize_endpoint="https://accounts.google.com/o/oauth2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
    )

    result = oauth2.authorize_button(
        name="Sign in with Google",
        redirect_uri=redirect_uri,
        scope="openid email profile",
        key="google_oauth",
        use_pkce=True,
        extras_params={"prompt": "select_account"},
    )

    if result and result.get("token"):
        token = result["token"]
        userinfo = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        ).json()
        email = userinfo.get("email", "")
        if email:
            _ensure_db_ready()
            st.session_state["tg_user"] = get_or_create_google_user(email)
            st.session_state["connected"] = True
            st.rerun()
    else:
        st.stop()


def run_auth_gate() -> None:
    """
    Call once at the very top of app.py, before any other rendering.

    - If Google env vars are set: Google OAuth is the primary login.
    - Otherwise: falls back to username/password (tg_auth.login_page).

    Returns only when st.session_state['tg_user'] is set.
    """
    if not st.session_state.get("tg_user"):
        _google_gate()

    _ensure_db_ready()

    if not st.session_state.get("tg_user"):
        login_page()
        st.stop()


def clear_auth_session() -> None:
    """
    Clear all auth-related session state on sign-out.
    Call this before st.rerun() in any sign-out handler.
    """
    for key in ["tg_user", "_auth_db_ready", "connected"]:
        st.session_state.pop(key, None)
