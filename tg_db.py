"""
tg_db.py
--------
Shared database connection for ThrottleGuard.
Reads DATABASE_URL from environment — points to Supabase PostgreSQL
on Railway, or a local Postgres for development.

Both tg_auth.py and outcome_db.py import from here.
Changing the connection string in one place updates both.
"""

import os
import psycopg2
import psycopg2.extras


def get_conn() -> psycopg2.extensions.connection:
    """
    Return a psycopg2 connection to the ThrottleGuard database.

    Usage pattern:
        conn = get_conn()
        try:
            with conn:           # commits on success, rolls back on exception
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(sql, params)
        finally:
            conn.close()
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Add it to your .env file (local) or Railway Variables (production). "
            "Format: postgresql://user:password@host:5432/dbname"
        )
    return psycopg2.connect(url)
