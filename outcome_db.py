"""
outcome_db.py
=============
SQLite logging for ThrottleGuard predictions.

Every prediction is written to predictions.db.
Fleet technicians fill in `actual_failure_occurred` and
`actual_outcome_date` after service — this becomes ground truth
for validating and improving the expert system over time.

Schema
------
predictions
    id                      INTEGER PRIMARY KEY
    vehicle_id              TEXT
    prediction_date         TEXT        (YYYY-MM-DD)
    predicted_priority      TEXT        (CRITICAL/HIGH/MEDIUM/LOW)
    predicted_failure_mode  TEXT        (CLOGGING/THERMAL_SHOCK/etc.)
    risk_score              INTEGER
    actual_outcome_date     TEXT        NULL — filled in by fleet
    actual_failure_occurred INTEGER     NULL — 1/0, filled in by fleet
    notes                   TEXT        NULL — technician notes
    created_at              TEXT
"""

import sqlite3
import pathlib
from datetime import date, datetime

DB_PATH = pathlib.Path(__file__).parent / "predictions.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
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

INSERT_SQL = """
INSERT INTO predictions
    (vehicle_id, prediction_date, predicted_priority,
     predicted_failure_mode, risk_score, created_at)
VALUES (?, ?, ?, ?, ?, ?);
"""


def init_db() -> None:
    """Create the predictions table if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()


def log_prediction(
    vehicle_id: str,
    predicted_priority: str,
    predicted_failure_mode: str,
    risk_score: int,
) -> int:
    """
    Insert a new prediction row.  Returns the row id.

    actual_outcome_date and actual_failure_occurred are left NULL —
    they are filled in by fleet staff after the vehicle is serviced.
    """
    init_db()
    now = datetime.utcnow().isoformat()
    today = date.today().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            INSERT_SQL,
            (vehicle_id, today, predicted_priority,
             predicted_failure_mode, int(risk_score), now),
        )
        conn.commit()
        return cur.lastrowid


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
    actual_failure_occurred : True if a DPF failure/service actually happened
    actual_outcome_date     : YYYY-MM-DD when failure/service occurred
    notes                   : technician free-text

    Returns number of rows updated.
    """
    init_db()
    outcome_date = actual_outcome_date or date.today().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            UPDATE predictions
            SET actual_failure_occurred = ?,
                actual_outcome_date     = ?,
                notes                   = ?
            WHERE vehicle_id      = ?
              AND prediction_date = ?
              AND id = (
                  SELECT MAX(id) FROM predictions
                  WHERE vehicle_id = ? AND prediction_date = ?
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
        conn.commit()
        return cur.rowcount


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
    clauses = []
    params: list = []

    if vehicle_id:
        clauses.append("vehicle_id = ?")
        params.append(vehicle_id)
    if priority:
        clauses.append("predicted_priority = ?")
        params.append(priority)
    if unvalidated_only:
        clauses.append("actual_failure_occurred IS NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM predictions {where} ORDER BY id DESC"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_validation_summary() -> dict:
    """
    Return a simple accuracy summary for validated predictions.
    Useful for checking expert-system performance over time.
    """
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT predicted_priority,
                   COUNT(*)                                        AS total,
                   SUM(CASE WHEN actual_failure_occurred = 1
                            THEN 1 ELSE 0 END)                    AS true_positives,
                   SUM(CASE WHEN actual_failure_occurred = 0
                            THEN 1 ELSE 0 END)                    AS false_positives,
                   SUM(CASE WHEN actual_failure_occurred IS NULL
                            THEN 1 ELSE 0 END)                    AS pending
            FROM predictions
            GROUP BY predicted_priority
            ORDER BY CASE predicted_priority
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH'     THEN 1
                WHEN 'MEDIUM'   THEN 2
                ELSE 3 END
            """
        ).fetchall()
        return [dict(r) for r in rows]
