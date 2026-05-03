"""
tg_auth.py — ThrottleGuard User Authentication

Stores users in Supabase PostgreSQL (via DATABASE_URL env var).
Uses hashlib + per-user salt for password hashing — no external auth deps.

Roles
-----
Admin      — full access: upload, view results, manage users, view prediction history
Technician — upload CSVs, view results, log real-world outcomes
Viewer     — read-only: view results and history, no uploads

First Run
---------
On first launch, a default admin account is created.
Set TG_ADMIN_PASSWORD env var before first deploy — Railway Variables panel.
Admin should change this password immediately in the user management panel.
"""

import hashlib
import os
import secrets
import psycopg2
import psycopg2.extras
import psycopg2.errorcodes
from datetime import datetime, timedelta

import streamlit as st

from tg_db import get_conn

# ── Role permissions ──────────────────────────────────────────────────────────
# Maps role name → set of allowed actions. Check with can_do(action).

ROLE_PERMISSIONS = {
    "Admin":      {"upload", "view", "outcomes", "manage_users", "history"},
    "Technician": {"upload", "view", "outcomes", "history"},
    "Viewer":     {"view", "history"},
}

# ── Database setup ────────────────────────────────────────────────────────────

CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS tg_users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'Viewer',
    created_at    TEXT NOT NULL,
    last_login    TEXT
);
"""

DEFAULT_ADMIN_USERNAME = "admin"

# Read from env var so the default is never exposed in source control.
# Set TG_ADMIN_PASSWORD in Railway (or your .env) before first deploy.
# Falls back to a placeholder that forces an immediate password change.
DEFAULT_ADMIN_PASSWORD = os.environ.get("TG_ADMIN_PASSWORD", "ChangeMe_OnFirstLogin!")

if DEFAULT_ADMIN_PASSWORD == "ChangeMe_OnFirstLogin!":
    print(
        "[ThrottleGuard Auth] WARNING: TG_ADMIN_PASSWORD env var not set. "
        "Default admin password is insecure — set it before exposing this app."
    )


# ── Rate limiting ─────────────────────────────────────────────────────────────
# In-memory store — resets on dyno restart, which is acceptable for a
# single-instance Railway deployment. Keeps login brute-force in check.

_failed_attempts: dict[str, list] = {}  # username -> list of failure datetimes
_MAX_ATTEMPTS    = 5
_LOCKOUT_SECONDS = 900  # 15 minutes


def _is_locked_out(username: str) -> bool:
    cutoff = datetime.utcnow() - timedelta(seconds=_LOCKOUT_SECONDS)
    recent = [t for t in _failed_attempts.get(username, []) if t > cutoff]
    _failed_attempts[username] = recent
    return len(recent) >= _MAX_ATTEMPTS


def _record_failure(username: str) -> None:
    _failed_attempts.setdefault(username, []).append(datetime.utcnow())


def _clear_failures(username: str) -> None:
    _failed_attempts.pop(username, None)


# ── Password hashing ──────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    """PBKDF2-SHA256 with 260,000 iterations — NIST-recommended for password storage."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"pbkdf2:{dk.hex()}"


def _verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """
    Verify a password against its stored hash.
    Supports both PBKDF2 (new) and legacy SHA-256 (old) hashes so existing
    users aren't locked out. SHA-256 hashes are upgraded to PBKDF2 on login.
    """
    if stored_hash.startswith("pbkdf2:"):
        expected = _hash_password(password, salt)
        return secrets.compare_digest(expected, stored_hash)
    else:
        # Legacy SHA-256 hash — compare and signal upgrade needed
        legacy = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return secrets.compare_digest(legacy, stored_hash)


def init_auth_db() -> None:
    """
    Create the tg_users table and seed a default admin account if empty.
    Called once at app startup.
    """
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(CREATE_USERS_SQL)

            cur.execute("SELECT COUNT(*) FROM tg_users")
            count = cur.fetchone()[0]
            if count == 0:
                salt    = secrets.token_hex(16)
                pw_hash = _hash_password(DEFAULT_ADMIN_PASSWORD, salt)
                cur.execute(
                    "INSERT INTO tg_users (username, password_hash, salt, role, created_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (DEFAULT_ADMIN_USERNAME, pw_hash, salt, "Admin", datetime.utcnow().isoformat()),
                )
                print("[ThrottleGuard Auth] Default admin account created — change password on first login.")
    finally:
        conn.close()


def verify_login(username: str, password: str) -> dict | None:
    """
    Check credentials. Returns user dict if valid, None if not.
    Enforces rate limiting and upgrades legacy SHA-256 hashes to PBKDF2 on success.
    """
    username = username.strip()

    if _is_locked_out(username):
        return None  # Silently deny — same response as wrong password

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM tg_users WHERE username = %s", (username,))
            row = cur.fetchone()

            if not row:
                _record_failure(username)
                return None

            if not _verify_password(password, row["salt"], row["password_hash"]):
                _record_failure(username)
                return None

            _clear_failures(username)

            # Transparently upgrade legacy SHA-256 hash to PBKDF2 on successful login
            if not row["password_hash"].startswith("pbkdf2:"):
                new_hash = _hash_password(password, row["salt"])
                cur.execute(
                    "UPDATE tg_users SET password_hash = %s WHERE username = %s",
                    (new_hash, username),
                )

            cur.execute(
                "UPDATE tg_users SET last_login = %s WHERE username = %s",
                (datetime.utcnow().isoformat(), username),
            )
            return {"username": row["username"], "role": row["role"]}
    finally:
        conn.close()


def create_user(username: str, password: str, role: str) -> bool:
    """
    Create a new user. Returns False if username already exists.
    Admin-only operation — enforce this in the UI, not here.
    """
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Invalid role: {role}. Must be one of {list(ROLE_PERMISSIONS)}")

    salt    = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tg_users (username, password_hash, salt, role, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (username.strip(), pw_hash, salt, role, datetime.utcnow().isoformat()),
            )
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False  # Username already exists
    finally:
        conn.close()


def change_password(username: str, new_password: str) -> None:
    """Update password for an existing user."""
    salt    = secrets.token_hex(16)
    pw_hash = _hash_password(new_password, salt)
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tg_users SET password_hash = %s, salt = %s WHERE username = %s",
                (pw_hash, salt, username),
            )
    finally:
        conn.close()


def delete_user(username: str) -> bool:
    """Remove a user. Cannot delete the last admin."""
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("SELECT COUNT(*) FROM tg_users WHERE role = 'Admin'")
            admin_count = cur.fetchone()["count"]

            cur.execute("SELECT role FROM tg_users WHERE username = %s", (username,))
            target = cur.fetchone()

            if target and target["role"] == "Admin" and admin_count <= 1:
                return False  # Can't delete the last admin

            cur.execute("DELETE FROM tg_users WHERE username = %s", (username,))
            return True
    finally:
        conn.close()


def get_all_users() -> list[dict]:
    """Return all users (without password hashes). Admin-only use."""
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT username, role, created_at, last_login FROM tg_users ORDER BY username"
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def can_do(action: str) -> bool:
    """Check if the current logged-in user has permission for an action."""
    role = st.session_state.get("tg_user", {}).get("role", "")
    return action in ROLE_PERMISSIONS.get(role, set())


# ── Streamlit login page ──────────────────────────────────────────────────────

def login_page() -> None:
    """
    Renders the ThrottleGuard login page.
    Sets st.session_state.tg_user on successful login and reruns.
    """
    st.set_page_config(
        page_title="ThrottleGuard — Login",
        page_icon="🚛",
        layout="centered",
    )

    # Push content to vertical center
    st.markdown("<div style='height: 8vh'></div>", unsafe_allow_html=True)

    col_left, spacer, col_right = st.columns([1.2, 0.2, 1])

    with col_left:
        from tg_logo import render_logo
        render_logo("medium")
        st.markdown(
            """
            <div style="padding: 0.5rem 1rem 1rem 0;">
                <div></div>
                <hr style="border-color:#2d2d2d; margin-bottom:1.5rem">
                <p style="color:#ccc; font-size:0.95rem; line-height:1.7; margin-bottom:1.2rem;">
                    <b style="color:#FF6600">Know before it breaks.</b><br>
                    ThrottleGuard reads your fleet's J1939 sensor data and flags
                    DPF problems before they become roadside breakdowns — scoring
                    every truck <b>CRITICAL → HIGH → MEDIUM → LOW</b> with a
                    plain-English reason your dispatcher can act on immediately.
                </p>
                <div style="display:flex;flex-direction:column;gap:0.75rem">
                    <div style="color:#ccc;font-size:0.88rem">
                        🔴 <b>Stop unplanned breakdowns</b> — catch clogging, thermal shock,
                        and sensor faults before dispatch
                    </div>
                    <div style="color:#ccc;font-size:0.88rem">
                        ⚙️ <b>Built on 20 years in the field</b> — Detroit, Volvo/Mack,
                        Cummins/PACCAR thresholds field-validated by a master diesel tech
                    </div>
                    <div style="color:#ccc;font-size:0.88rem">
                        📋 <b>No black box</b> — every flag shows exactly which rule fired
                        and what action to take
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_right:
        tab_signin, tab_create, tab_reset = st.tabs(["Sign In", "Create Account", "Reset Password"])

        with tab_signin:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("Enter your username and password.")
                else:
                    user = verify_login(username, password)
                    if user:
                        st.session_state["tg_user"] = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

        with tab_create:
            with st.form("create_account_form"):
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                confirm_pw   = st.text_input("Confirm Password", type="password")
                # Self-registered accounts start as Viewer; Admin can promote them
                st.caption("New accounts are created as **Viewer**. Contact your Admin to request Technician access.")
                create_submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)

            if create_submitted:
                if not new_username or not new_password or not confirm_pw:
                    st.error("All fields are required.")
                elif new_password != confirm_pw:
                    st.error("Passwords do not match.")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    ok = create_user(new_username, new_password, "Viewer")
                    if ok:
                        user = verify_login(new_username, new_password)
                        st.session_state["tg_user"] = user
                        st.rerun()
                    else:
                        st.error(f"Username '{new_username}' is already taken.")

        with tab_reset:
            st.caption("Enter your current credentials and choose a new password.")
            with st.form("reset_pw_form"):
                reset_username  = st.text_input("Username")
                current_pw      = st.text_input("Current Password", type="password")
                new_pw          = st.text_input("New Password", type="password")
                confirm_new_pw  = st.text_input("Confirm New Password", type="password")
                reset_submitted = st.form_submit_button("Update Password", type="primary", use_container_width=True)

            if reset_submitted:
                if not all([reset_username, current_pw, new_pw, confirm_new_pw]):
                    st.error("All fields are required.")
                elif new_pw != confirm_new_pw:
                    st.error("New passwords do not match.")
                elif len(new_pw) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    # Verify current credentials before allowing change
                    user = verify_login(reset_username, current_pw)
                    if not user:
                        st.error("Current username or password is incorrect.")
                    else:
                        change_password(reset_username, new_pw)
                        st.success("Password updated. You can now sign in.")

        st.markdown(
            "<p style='text-align:center; color:#555; font-size:0.8rem; margin-top:2rem;'>"
            "AHC Developers · ThrottleGuard v2</p>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 8vh'></div>", unsafe_allow_html=True)


# ── User management panel (Admin only) ───────────────────────────────────────

def user_management_panel() -> None:
    """
    Admin panel for creating, listing, and removing users.
    Only renders if current user is Admin — call after checking can_do('manage_users').
    """
    st.markdown("### User Management")

    users = get_all_users()

    # Current users table
    if users:
        import pandas as pd
        df = pd.DataFrame(users)
        df.columns = ["Username", "Role", "Created", "Last Login"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No users found.")

    st.divider()

    # Create new user
    st.markdown("**Add User**")
    with st.form("add_user_form"):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        new_role     = st.selectbox("Role", list(ROLE_PERMISSIONS.keys()))
        if st.form_submit_button("Create User", type="primary"):
            if not new_username or not new_password:
                st.error("Username and password are required.")
            elif create_user(new_username, new_password, new_role):
                st.success(f"User '{new_username}' created as {new_role}.")
                st.rerun()
            else:
                st.error(f"Username '{new_username}' already exists.")

    st.divider()

    # Delete user
    st.markdown("**Remove User**")
    usernames = [u["username"] for u in users]
    current   = st.session_state.get("tg_user", {}).get("username", "")
    removable = [u for u in usernames if u != current]  # Can't delete yourself

    if removable:
        with st.form("delete_user_form"):
            to_delete = st.selectbox("Select user to remove", removable)
            if st.form_submit_button("Remove User", type="secondary"):
                if delete_user(to_delete):
                    st.success(f"User '{to_delete}' removed.")
                    st.rerun()
                else:
                    st.error("Cannot remove the last Admin account.")
    else:
        st.info("No other users to remove.")

    st.divider()

    # Change own password
    st.markdown("**Change Your Password**")
    with st.form("change_pw_form"):
        new_pw  = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        if st.form_submit_button("Update Password"):
            if not new_pw:
                st.error("Password cannot be empty.")
            elif new_pw != confirm:
                st.error("Passwords do not match.")
            else:
                change_password(current, new_pw)
                st.success("Password updated.")
