"""
tg_auth.py — ThrottleGuard User Authentication

Simple, practical auth for a diesel technician audience.
Stores users in the same SQLite DB as predictions (predictions.db).
No external dependencies — uses hashlib (built-in) with salt for password hashing.

Roles
-----
Admin      — full access: upload, view results, manage users, view prediction history
Technician — upload CSVs, view results, log real-world outcomes
Viewer     — read-only: view results and history, no uploads

First Run
---------
On first launch, a default admin account is created:
  Username: admin
  Password: throttleguard2024
Admin should change this password immediately in the user management panel.
"""

import hashlib
import os
import secrets
import sqlite3
import pathlib
from datetime import datetime

import streamlit as st

DB_PATH = pathlib.Path(__file__).parent / "predictions.db"

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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT    NOT NULL UNIQUE,
    password_hash TEXT   NOT NULL,
    salt         TEXT    NOT NULL,
    role         TEXT    NOT NULL DEFAULT 'Viewer',
    created_at   TEXT    NOT NULL,
    last_login   TEXT
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


def _hash_password(password: str, salt: str) -> str:
    """SHA-256 hash with per-user salt. Simple and dependency-free."""
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    """
    Create the users table and seed a default admin account if no users exist.
    Called once at app startup.
    """
    with _get_conn() as conn:
        conn.execute(CREATE_USERS_SQL)
        conn.commit()

        # Only create the default admin if the table is completely empty
        count = conn.execute("SELECT COUNT(*) FROM tg_users").fetchone()[0]
        if count == 0:
            salt = secrets.token_hex(16)
            pw_hash = _hash_password(DEFAULT_ADMIN_PASSWORD, salt)
            conn.execute(
                "INSERT INTO tg_users (username, password_hash, salt, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (DEFAULT_ADMIN_USERNAME, pw_hash, salt, "Admin", datetime.utcnow().isoformat()),
            )
            conn.commit()
            print("[ThrottleGuard Auth] Default admin account created — change password on first login.")


def verify_login(username: str, password: str) -> dict | None:
    """
    Check credentials. Returns user dict if valid, None if not.
    Also updates last_login timestamp on success.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tg_users WHERE username = ?", (username.strip(),)
        ).fetchone()

        if not row:
            return None

        expected = _hash_password(password, row["salt"])
        if not secrets.compare_digest(expected, row["password_hash"]):
            return None

        # Update last login time
        conn.execute(
            "UPDATE tg_users SET last_login = ? WHERE username = ?",
            (datetime.utcnow().isoformat(), username),
        )
        conn.commit()

        return {"username": row["username"], "role": row["role"]}


def create_user(username: str, password: str, role: str) -> bool:
    """
    Create a new user. Returns False if username already exists.
    Admin-only operation — enforce this in the UI, not here.
    """
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Invalid role: {role}. Must be one of {list(ROLE_PERMISSIONS)}")

    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)

    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO tg_users (username, password_hash, salt, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username.strip(), pw_hash, salt, role, datetime.utcnow().isoformat()),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Username already exists


def change_password(username: str, new_password: str) -> None:
    """Update password for an existing user."""
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(new_password, salt)
    with _get_conn() as conn:
        conn.execute(
            "UPDATE tg_users SET password_hash = ?, salt = ? WHERE username = ?",
            (pw_hash, salt, username),
        )
        conn.commit()


def delete_user(username: str) -> bool:
    """Remove a user. Cannot delete the last admin."""
    with _get_conn() as conn:
        # Prevent deleting the last admin account — would lock everyone out
        admin_count = conn.execute(
            "SELECT COUNT(*) FROM tg_users WHERE role = 'Admin'"
        ).fetchone()[0]
        target_role = conn.execute(
            "SELECT role FROM tg_users WHERE username = ?", (username,)
        ).fetchone()

        if target_role and target_role["role"] == "Admin" and admin_count <= 1:
            return False  # Can't delete the last admin

        conn.execute("DELETE FROM tg_users WHERE username = ?", (username,))
        conn.commit()
        return True


def get_all_users() -> list[dict]:
    """Return all users (without password hashes). Admin-only use."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT username, role, created_at, last_login FROM tg_users ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]


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

    # Two-column layout: value props on the left, login form on the right
    col_left, col_right = st.columns([1.2, 1])

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
        st.markdown(
            """
            <div style="text-align:center; padding: 2rem 0 0.5rem;">
                <p style="color:#aaa; font-size:0.9rem;">Sign in to your fleet dashboard</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

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

        st.markdown(
            "<p style='text-align:center; color:#555; font-size:0.8rem; margin-top:2rem;'>"
            "AHC Developers · ThrottleGuard v2</p>",
            unsafe_allow_html=True,
        )


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
