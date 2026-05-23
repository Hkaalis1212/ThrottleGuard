"""
outcome_db.py
=============
Prediction logging for ThrottleGuard — Supabase PostgreSQL backend.

Every prediction is written to tg_predictions.
Fleet technicians fill in actual_failure_occurred and actual_outcome_date
after service — this becomes ground truth for validating the expert system.

Schema
------
tg_predictions
    id                      SERIAL PRIMARY KEY
    vehicle_id              TEXT
    prediction_date         TEXT        (YYYY-MM-DD)
    predicted_priority      TEXT        (CRITICAL/HIGH/MEDIUM/LOW)
    predicted_failure_mode  TEXT        (CLOGGING/THERMAL_SHOCK/etc.)
    risk_score              INTEGER
    actual_outcome_date     TEXT        NULL — filled in after service
    actual_failure_occurred INTEGER     NULL — 1=failure confirmed, 0=false alarm
    notes                   TEXT        NULL — technician notes
    created_at              TEXT
"""

import psycopg2.extras
from datetime import date, datetime

from tg_db import get_conn

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tg_predictions (
    id                      SERIAL PRIMARY KEY,
    vehicle_id              TEXT    NOT NULL,
    prediction_date         TEXT    NOT NULL,
    predicted_priority      TEXT    NOT NULL,
    predicted_failure_mode  TEXT    NOT NULL,
    risk_score              INTEGER NOT NULL,
    actual_outcome_date     TEXT,
    actual_failure_occurred INTEGER,
    notes                   TEXT,
    created_at              TEXT    NOT NULL
);
"""


def init_db() -> None:
    """Create the tg_predictions table if it doesn't exist."""
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(CREATE_TABLE_SQL)
    finally:
        conn.close()


def log_prediction(
    vehicle_id: str,
    predicted_priority: str,
    predicted_failure_mode: str,
    risk_score: int,
) -> int:
    """
    Insert a new prediction row. Returns the row id.

    actual_outcome_date and actual_failure_occurred are left NULL —
    filled in by fleet staff after the vehicle is serviced.
    """
    init_db()
    now   = datetime.utcnow().isoformat()
    today = date.today().isoformat()

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tg_predictions
                    (vehicle_id, prediction_date, predicted_priority,
                     predicted_failure_mode, risk_score, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (vehicle_id, today, predicted_priority,
                 predicted_failure_mode, int(risk_score), now),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def log_predictions_batch(rows: list[dict]) -> None:
    """
    Insert multiple prediction rows in a single round-trip.

    Each dict in rows must have:
        vehicle_id, predicted_priority, predicted_failure_mode, risk_score

    Replaces calling log_prediction() in a loop, which opens a new connection
    and runs CREATE TABLE IF NOT EXISTS for every single truck — very slow on
    large fleets.
    """
    if not rows:
        return
    init_db()
    now   = datetime.utcnow().isoformat()
    today = date.today().isoformat()

    params = [
        (
            r["vehicle_id"],
            today,
            r["predicted_priority"],
            r["predicted_failure_mode"],
            int(r["risk_score"]),
            now,
        )
        for r in rows
    ]

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT INTO tg_predictions
                    (vehicle_id, prediction_date, predicted_priority,
                     predicted_failure_mode, risk_score, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                params,
            )
    finally:
        conn.close()


def record_outcome(
    vehicle_id: str,
    prediction_date: str,
    actual_failure_occurred: bool,
    actual_outcome_date: str | None = None,
    notes: str | None = None,
) -> int:
    """
    Update the most recent prediction for a vehicle with the real outcome.

    Parameters
    ----------
    vehicle_id              : unit identifier
    prediction_date         : YYYY-MM-DD of the original prediction
    actual_failure_occurred : True if a DPF/SCR failure actually happened
    actual_outcome_date     : YYYY-MM-DD when failure/service occurred
    notes                   : technician free-text

    Returns number of rows updated.
    """
    init_db()
    outcome_date = actual_outcome_date or date.today().isoformat()

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE tg_predictions
                SET actual_failure_occurred = %s,
                    actual_outcome_date     = %s,
                    notes                   = %s
                WHERE vehicle_id      = %s
                  AND prediction_date = %s
                  AND id = (
                      SELECT MAX(id) FROM tg_predictions
                      WHERE vehicle_id = %s AND prediction_date = %s
                  )
                """,
                (
                    1 if actual_failure_occurred else 0,
                    outcome_date,
                    notes,
                    vehicle_id, prediction_date,
                    vehicle_id, prediction_date,
                ),
            )
            return cur.rowcount
    finally:
        conn.close()


def get_predictions(
    vehicle_id: str | None = None,
    priority: str | None = None,
    unvalidated_only: bool = False,
) -> list[dict]:
    """
    Fetch prediction rows with optional filters.

    Parameters
    ----------
    vehicle_id       : filter to a single vehicle
    priority         : filter by predicted priority (CRITICAL/HIGH/etc.)
    unvalidated_only : only return rows where actual_failure_occurred is NULL
    """
    init_db()
    clauses: list[str] = []
    params:  list      = []

    if vehicle_id:
        clauses.append("vehicle_id = %s")
        params.append(vehicle_id)
    if priority:
        clauses.append("predicted_priority = %s")
        params.append(priority)
    if unvalidated_only:
        clauses.append("actual_failure_occurred IS NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql   = f"SELECT * FROM tg_predictions {where} ORDER BY id DESC"

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_calibration_data() -> list[dict]:
    """
    Return all validated predictions with risk_score and actual_failure_occurred.
    Used to plot score distributions and evaluate whether thresholds are well-calibrated.
    Only returns rows where actual_failure_occurred is NOT NULL.
    """
    init_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT risk_score,
                       predicted_priority,
                       actual_failure_occurred
                FROM tg_predictions
                WHERE actual_failure_occurred IS NOT NULL
                ORDER BY risk_score
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_validation_summary() -> list[dict]:
    """
    Return a simple accuracy summary for validated predictions.
    Useful for checking expert-system performance over time.
    """
    init_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT predicted_priority,
                       COUNT(*)                                          AS total,
                       SUM(CASE WHEN actual_failure_occurred = 1
                                THEN 1 ELSE 0 END)                      AS true_positives,
                       SUM(CASE WHEN actual_failure_occurred = 0
                                THEN 1 ELSE 0 END)                      AS false_positives,
                       SUM(CASE WHEN actual_failure_occurred IS NULL
                                THEN 1 ELSE 0 END)                      AS pending
                FROM tg_predictions
                GROUP BY predicted_priority
                ORDER BY CASE predicted_priority
                    WHEN 'CRITICAL' THEN 0
                    WHEN 'HIGH'     THEN 1
                    WHEN 'MEDIUM'   THEN 2
                    ELSE 3 END
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
