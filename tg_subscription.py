"""
tg_subscription.py — ThrottleGuard Subscription Management
===========================================================
Subscription is per-fleet (per Railway deployment).
Each fleet has one subscription row tied to their admin account.

Pricing (per truck / month)
---------------------------
  trial      — 14 days free, full access, no card
  starter    — $39/truck/mo  (1–10 trucks)
  growth     — $29/truck/mo  (11–50 trucks)
  fleet      — $19/truck/mo  (51–250 trucks)
  enterprise — 250+ trucks, custom quote

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

TRIAL_DAYS = 14

# Per-truck / month tiers. Amount = fleet_size × per_truck rate.
# Enterprise (250+) is custom — no automated checkout.
PRICING_TIERS = [
    {"key": "starter",    "label": "Starter",    "min": 1,   "max": 10,  "per_truck": 39.00},
    {"key": "growth",     "label": "Growth",     "min": 11,  "max": 50,  "per_truck": 29.00},
    {"key": "fleet",      "label": "Fleet",      "min": 51,  "max": 250, "per_truck": 19.00},
]


def get_tier_for_fleet(fleet_size: int) -> dict | None:
    """Return the pricing tier dict for fleet_size, or None for enterprise (250+)."""
    for tier in PRICING_TIERS:
        if tier["min"] <= fleet_size <= tier["max"]:
            return tier
    return None


def monthly_price(fleet_size: int) -> float | None:
    """Return total monthly price for a fleet, or None if enterprise (250+)."""
    tier = get_tier_for_fleet(fleet_size)
    if tier is None:
        return None
    return fleet_size * tier["per_truck"]

# ── Schema ────────────────────────────────────────────────────────────────────

CREATE_SUBSCRIPTIONS_SQL = """
CREATE TABLE IF NOT EXISTS tg_subscriptions (
    id           SERIAL PRIMARY KEY,
    fleet_id     TEXT NOT NULL UNIQUE,   -- admin username = fleet identifier
    plan_type    TEXT NOT NULL,          -- trial / starter / growth / fleet
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
    end     = now + timedelta(days=TRIAL_DAYS)
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
        return {"success": True, "days": TRIAL_DAYS, "end_date": end}
    except Exception as e:
        logger.error(f"[TG Sub] start_trial error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def create_payment_intent(fleet_id: str, fleet_size: int) -> dict:
    """
    Create a Stripe PaymentIntent for fleet_size trucks.
    Amount = fleet_size × per_truck rate for their tier.
    Returns {success, client_secret, amount, tier} or {success, error}.
    """
    if not stripe.api_key:
        return {"success": False, "error": "Stripe is not configured — set STRIPE_SECRET_KEY."}

    tier = get_tier_for_fleet(fleet_size)
    if tier is None:
        return {"success": False, "error": "Enterprise fleets (250+ trucks) require a custom quote. Contact us."}

    price = monthly_price(fleet_size)
    amount_cents = int(round(price * 100))

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            metadata={
                "fleet_id":      fleet_id,
                "fleet_size":    fleet_size,
                "tier_key":      tier["key"],
                "per_truck_rate": tier["per_truck"],
            },
        )
        return {"success": True, "client_secret": intent.client_secret, "amount": price, "tier": tier}
    except stripe.error.StripeError as e:
        logger.error(f"[TG Sub] Stripe error: {e}")
        return {"success": False, "error": str(e)}


def confirm_payment(fleet_id: str, fleet_size: int, payment_intent_id: str) -> dict:
    """
    Verify payment succeeded with Stripe, then create/upgrade the subscription.
    fleet_size is used to re-derive the expected amount — prevents a tampered
    PaymentIntent from granting access at a lower price.
    Returns {success, error?}.
    """
    if not stripe.api_key:
        return {"success": False, "error": "Stripe is not configured."}

    tier = get_tier_for_fleet(fleet_size)
    if tier is None:
        return {"success": False, "error": "Enterprise fleets (250+) require a custom contract."}

    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError as e:
        return {"success": False, "error": f"Stripe error: {e}"}

    if intent.status != "succeeded":
        return {"success": False, "error": f"Payment not completed (status: {intent.status})."}

    expected_cents = round(monthly_price(fleet_size) * 100)
    if intent.amount != expected_cents:
        logger.error(
            f"[TG Sub] Amount mismatch for fleet_size={fleet_size}: "
            f"expected {expected_cents} cents, got {intent.amount}"
        )
        return {"success": False, "error": "Payment amount does not match the expected price for your fleet size."}

    amount    = monthly_price(fleet_size)
    plan_type = tier["key"]
    now       = datetime.utcnow()
    end       = now + timedelta(days=30)

    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tg_subscriptions SET status = 'cancelled' WHERE fleet_id = %s AND status = 'active'",
                (fleet_id,),
            )
            cur.execute(
                """
                INSERT INTO tg_subscriptions
                    (fleet_id, plan_type, status, start_date, end_date, amount_paid, created_at)
                VALUES (%s, %s, 'active', %s, %s, %s, %s)
                """,
                (fleet_id, plan_type, now.isoformat(), end.isoformat(), amount, now.isoformat()),
            )
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
