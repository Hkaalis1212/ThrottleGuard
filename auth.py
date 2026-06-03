"""
auth.py — ThrottleGuard authentication gate

Uses Streamlit's native OAuth (st.login / st.user / st.logout, added in
Streamlit 1.40) when Google credentials are present in secrets.toml.
Falls back to username/password login for local dev or admin accounts.

Usage (top of app.py):
    from auth import run_auth_gate, clear_auth_session
    run_auth_gate()
"""

import streamlit as st
from tg_auth import init_auth_db, login_page, get_or_create_google_user


def _ensure_db_ready() -> None:
    if "_auth_db_ready" not in st.session_state:
        init_auth_db()
        st.session_state["_auth_db_ready"] = True


def _google_configured() -> bool:
    """True when setup_secrets.py has written Google credentials to secrets.toml."""
    try:
        return bool(st.secrets.get("auth", {}).get("google"))
    except Exception:
        return False


def run_auth_gate() -> None:
    """
    Call once at the very top of app.py, before any other rendering.
    Returns only when the user is authenticated and tg_user is set in session state.
    """
    if _google_configured():
        if not st.user.is_logged_in:
            st.login("google")
            st.stop()

        # Map the verified Google identity to a ThrottleGuard user
        if not st.session_state.get("tg_user"):
            _ensure_db_ready()
            email = getattr(st.user, "email", "") or ""
            if email:
                st.session_state["tg_user"] = get_or_create_google_user(email)

        if not st.session_state.get("tg_user"):
            st.error("Could not read your Google account email. Please try again.")
            if st.button("Sign out and retry"):
                st.logout()
            st.stop()
    else:
        # Google not configured — use username/password (local dev / admin access)
        _ensure_db_ready()
        if not st.session_state.get("tg_user"):
            login_page()
            st.stop()


def clear_auth_session() -> None:
    """
    Clear auth state on sign-out. Call before st.rerun() in any sign-out handler.
    When Google OAuth is active, calls st.logout() which redirects immediately —
    the caller's st.rerun() will never be reached (which is fine).
    """
    for key in ["tg_user", "_auth_db_ready"]:
        st.session_state.pop(key, None)

    if _google_configured():
        st.logout()
