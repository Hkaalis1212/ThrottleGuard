"""
auth.py — ThrottleGuard Google OAuth gate

Wraps streamlit-google-auth so app.py stays clean.
Falls back to the existing username/password login (tg_auth.login_page)
when GOOGLE_CLIENT_ID is not set — safe for local dev.

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
    Run the Google OAuth flow.
    Sets st.session_state['tg_user'] on success, calls st.stop() if not yet authenticated.
    """
    from streamlit_google_auth import Authenticate

    authenticator = Authenticate(
        secret_credentials_path=None,
        cookie_name="throttleguard_auth",
        cookie_key=os.environ.get("SESSION_SECRET", "throttleguard"),
        redirect_uri=os.environ.get("REDIRECT_URI"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    )

    authenticator.check_authentification()

    if not st.session_state.get("connected"):
        authenticator.login()
        st.stop()

    # Authenticated — map Google identity to a ThrottleGuard user on first visit
    if not st.session_state.get("tg_user"):
        _ensure_db_ready()
        email = (st.session_state.get("user_info") or {}).get("email", "")
        if email:
            st.session_state["tg_user"] = get_or_create_google_user(email)


def run_auth_gate() -> None:
    """
    Call once at the very top of app.py, before any other rendering.

    - If GOOGLE_CLIENT_ID is set: Google OAuth is the primary login.
    - Otherwise: falls back to username/password (tg_auth.login_page).

    Either way, the function returns only when st.session_state['tg_user'] is set.
    """
    if os.environ.get("GOOGLE_CLIENT_ID"):
        _google_gate()

    # Always run the DB init and password-auth fallback so that:
    # - the tg_users table exists (needed even for Google users)
    # - local dev / admin accounts still work when GOOGLE_CLIENT_ID is absent
    _ensure_db_ready()

    if not st.session_state.get("tg_user"):
        login_page()
        st.stop()


def clear_auth_session() -> None:
    """
    Clear all auth-related session state on sign-out.
    Call this before st.rerun() in any sign-out handler.
    """
    auth_keys = ["tg_user", "_auth_db_ready", "connected", "user_info"]
    for key in auth_keys:
        st.session_state.pop(key, None)
