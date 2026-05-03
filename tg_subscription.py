"""
tg_subscription.py — ThrottleGuard Subscription Management
===========================================================
Subscription is per-fleet (per Railway deployment).
Each fleet has one subscription row tied to their admin account.

Plans
-----
  trial     — 14 days free, full access
  monthly   — $59.99 / month
  quarterly — $161.97 / quarter  (10% off)
  bi_annual — $305.95 / 6 months (15% off)

Tables (Supabase PostgreSQL)
----------------------------
  tg_subscriptions    — one row per fleet (keyed on fleet_id = admin username)
  tg_payment_history  — one row per completed payment

Environment variables
---------------------
  STRIPE_SECRET_KEY      — Stripe secret key (sk_live_... or sk_test_...)
  STRIPE_PUBLISHABLE_KEY — Stripe publishable key (pk_live_... or pk_test_...)
"""

import os
import logging
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
import stripe

from tg_db import get_conn

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# ── Pricing ───────────────────────────────────────────────────────────────────

PRICING = {
    "monthly":    59.99,
    "quarterly":  161.97,  # $59.99 * 3 * 0.90 — 10% off
    "bi_annual":  305.95,  # $59.99 * 6 * 0.85 — 15% off
    "trial_days": 14,
}

PLAN_DAYS = {
    "monthly":   30,
    "quarterly": 90,
    "bi_annual": 180,
}

# Stripe Price IDs (live mode) — prod_UGko1NRAaPqguV
STRIPE_PRICE_IDS = {
    "monthly":   "price_1TIDJvALl8vDltuMscHbk9a9",
    "quarterly": "price_1TIDKDALl8vDltuMwsWIuQ08",
    "bi_annual": "price_1TIDKUALl8vDltuMp8BnWMBs",
}

# ── Schema ────────────────────────────────────────────────────────────────────

CREATE_SUBSCRIPTIONS_SQL = """
CREATE TABLE IF NOT EXISTS tg_subscriptions (
    id           SERIAL PRIMARY KEY,
    fleet_id     TEXT NOT NULL UNIQUE,   -- admin username = fleet identifier
    plan_type    TEXT NOT NULL,          -- trial / monthly / quarterly / bi_annual
    status       TEXT NOT NULL DEFAULT 'active',  -- active / expired / cancelled
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    amount_paid  REAL NOT NULL DEFAULT 0.0,
    created_at   TEXT NOT NULL
);
"""

CREATE_PAYMENT_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS tg_payment_history (
    id               SERIAL PRIMARY KEY,
    fleet_id         TEXT    NOT NULL,
    amount           REAL    NOT NULL,
    plan_type        TEXT    NOT NULL,
    payment_date     TEXT    NOT NULL,
    transaction_id   TEXT,
    status           TEXT    NOT NULL DEFAULT 'completed'
);
"""


def init_subscription_db() -> None:
    """Create subscription tables if they don't exist."""
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(CREATE_SUBSCRIPTIONS_SQL)
            cur.execute(CREATE_PAYMENT_HISTORY_SQL)
    finally:
        conn.close()


# ── Core subscription functions ───────────────────────────────────────────────

def get_subscription(fleet_id: str) -> dict | None:
    """
    Return the current subscription for a fleet, or None if none exists.
    Automatically marks expired active subscriptions as expired.
    """
    init_subscription_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM tg_subscriptions WHERE fleet_id = %s ORDER BY id DESC LIMIT 1",
                (fleet_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            sub = dict(row)
            end_date = datetime.fromisoformat(sub["end_date"])
            now = datetime.utcnow()

            # Auto-expire
            if sub["status"] == "active" and end_date < now:
                cur.execute(
                    "UPDATE tg_subscriptions SET status = 'expired' WHERE id = %s",
                    (sub["id"],),
                )
                sub["status"] = "expired"

            sub["days_remaining"] = max(0, (end_date - now).days)
            return sub
    finally:
        conn.close()


def is_active(fleet_id: str) -> bool:
    """True if the fleet has an active (non-expired) subscription."""
    sub = get_subscription(fleet_id)
    return sub is not None and sub["status"] == "active"


def start_trial(fleet_id: str) -> dict:
    """
    Start a 14-day free trial. Returns {success, error?}.
    No-ops if a subscription already exists.
    """
    init_subscription_db()
    existing = get_subscription(fleet_id)
    if existing:
        return {"success": False, "error": "Subscription already exists."}

    now     = datetime.utcnow()
    end     = now + timedelta(days=PRICING["trial_days"])
    conn    = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tg_subscriptions
                    (fleet_id, plan_type, status, start_date, end_date, amount_paid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (fleet_id, "trial", "active", now.isoformat(), end.isoformat(), 0.0, now.isoformat()),
            )
        return {"success": True, "days": PRICING["trial_days"], "end_date": end}
    except Exception as e:
        logger.error(f"[TG Sub] start_trial error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def create_payment_intent(fleet_id: str, plan_type: str) -> dict:
    """
    Create a Stripe PaymentIntent. Returns {success, client_secret, amount} or {success, error}.
    """
    if not stripe.api_key:
        return {"success": False, "error": "Stripe is not configured — set STRIPE_SECRET_KEY."}
    if plan_type not in PRICING:
        return {"success": False, "error": f"Unknown plan: {plan_type}"}

    amount_cents = int(PRICING[plan_type] * 100)
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            metadata={
                "fleet_id": fleet_id,
                "plan_type": plan_type,
                "stripe_price_id": STRIPE_PRICE_IDS.get(plan_type, ""),
            },
        )
        return {"success": True, "client_secret": intent.client_secret, "amount": PRICING[plan_type]}
    except stripe.error.StripeError as e:
        logger.error(f"[TG Sub] Stripe error: {e}")
        return {"success": False, "error": str(e)}


def confirm_payment(fleet_id: str, plan_type: str, payment_intent_id: str) -> dict:
    """
    Verify payment succeeded with Stripe, then create/upgrade the subscription.
    Returns {success, error?}.
    """
    if not stripe.api_key:
        return {"success": False, "error": "Stripe is not configured."}

    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError as e:
        return {"success": False, "error": f"Stripe error: {e}"}

    if intent.status != "succeeded":
        return {"success": False, "error": f"Payment not completed (status: {intent.status})."}

    # Verify the amount matches the plan price — prevents a tampered intent
    # from activating a more expensive plan at a lower price
    expected_cents = round(PRICING[plan_type] * 100)
    if intent.amount != expected_cents:
        logger.error(
            f"[TG Sub] Amount mismatch for plan {plan_type}: "
            f"expected {expected_cents} cents, got {intent.amount}"
        )
        return {"success": False, "error": "Payment amount does not match plan price."}

    amount  = PRICING[plan_type]
    now     = datetime.utcnow()
    end     = now + timedelta(days=PLAN_DAYS[plan_type])

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            # Cancel any existing subscription
            cur.execute(
                "UPDATE tg_subscriptions SET status = 'cancelled' WHERE fleet_id = %s AND status = 'active'",
                (fleet_id,),
            )
            # Create new subscription
            cur.execute(
                """
                INSERT INTO tg_subscriptions
                    (fleet_id, plan_type, status, start_date, end_date, amount_paid, created_at)
                VALUES (%s, %s, 'active', %s, %s, %s, %s)
                """,
                (fleet_id, plan_type, now.isoformat(), end.isoformat(), amount, now.isoformat()),
            )
            # Log payment
            cur.execute(
                """
                INSERT INTO tg_payment_history
                    (fleet_id, amount, plan_type, payment_date, transaction_id, status)
                VALUES (%s, %s, %s, %s, %s, 'completed')
                """,
                (fleet_id, amount, plan_type, now.isoformat(), payment_intent_id),
            )
        return {"success": True, "plan_type": plan_type, "end_date": end, "amount": amount}
    except Exception as e:
        logger.error(f"[TG Sub] confirm_payment DB error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_payment_history(fleet_id: str) -> list[dict]:
    """Return payment history for a fleet, most recent first."""
    init_subscription_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM tg_payment_history WHERE fleet_id = %s ORDER BY id DESC",
                (fleet_id,),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def cancel_subscription(fleet_id: str) -> dict:
    """Cancel the active subscription. Access continues until the end_date."""
    init_subscription_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tg_subscriptions SET status = 'cancelled' WHERE fleet_id = %s AND status = 'active'",
                (fleet_id,),
            )
            if cur.rowcount == 0:
                return {"success": False, "error": "No active subscription found."}
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
