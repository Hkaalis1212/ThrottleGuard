"""
throttleguard_billing.py
========================
Stripe per-truck billing for ThrottleGuard.

Pricing tiers:
  Pilot      — $35/truck/month  (90-day intro rate, auto-upgrades to Standard)
  Standard   — $49/truck/month  (full rate after pilot)
  Enterprise — custom pricing   (manual invoice, not automated here)

Billing model: Stripe licensed subscriptions (quantity = truck_count).
  Tim has 200 trucks → quantity=200, billed at rate × 200 each month.
  If he adds trucks: call update_truck_count() → Stripe prorates the difference.

Pilot → Standard auto-upgrade:
  Uses Stripe Subscription Schedules with two phases.
  Phase 1: pilot price × 3 billing months.
  Phase 2: standard price, perpetual.
  Stripe handles the transition automatically — no cron job needed.

DB table: tg_billing (created on first run — see CREATE_BILLING_TABLE_SQL below)

Environment variables (Railway → Variables):
  STRIPE_SECRET_KEY      — sk_test_... (test) or sk_live_... (live mode)
  STRIPE_PRICE_PILOT     — price_... ID after running create_stripe_products()
  STRIPE_PRICE_STANDARD  — price_... ID after running create_stripe_products()
  DATABASE_URL           — Supabase PostgreSQL connection string (already set)

Flip test → live:
  1. Change STRIPE_SECRET_KEY to sk_live_...
  2. Run create_stripe_products() again against the live Stripe account
  3. Update STRIPE_PRICE_PILOT and STRIPE_PRICE_STANDARD with the live price IDs
  (Live and test Stripe environments are fully separate — products/prices don't transfer)
"""

import os
import logging
from datetime import datetime, timedelta

import psycopg2.extras
import stripe

from tg_db import get_conn

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

PILOT_DAYS     = 90
PILOT_MONTHS   = 3      # Stripe schedules count billing cycles, not calendar days
PILOT_RATE     = 35.00  # dollars per truck per month
STANDARD_RATE  = 49.00  # dollars per truck per month


# ── DB schema ─────────────────────────────────────────────────────────────────

CREATE_BILLING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tg_billing (
    id                      SERIAL PRIMARY KEY,
    fleet_id                TEXT NOT NULL UNIQUE,       -- matches admin username / fleet identifier
    email                   TEXT,                       -- billing contact
    stripe_customer_id      TEXT NOT NULL,              -- cus_...
    stripe_subscription_id  TEXT,                       -- sub_...
    stripe_schedule_id      TEXT,                       -- sch_... (only for pilot fleets)
    tier                    TEXT NOT NULL DEFAULT 'standard',
    truck_count             INTEGER NOT NULL DEFAULT 1,
    pilot_start_date        TEXT,
    pilot_end_date          TEXT,
    subscription_status     TEXT NOT NULL DEFAULT 'active',
    monthly_amount          REAL,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);
"""


def init_billing_db() -> None:
    """Create tg_billing if it doesn't exist. Called at the top of every write."""
    conn = get_conn()
    try:
        with conn:
            conn.cursor().execute(CREATE_BILLING_TABLE_SQL)
    finally:
        conn.close()


# ── Price ID helpers ──────────────────────────────────────────────────────────

def _get_price_id(tier: str) -> str:
    """
    Read the Stripe price ID for a tier from environment variables.
    These are set after running create_stripe_products() once.
    """
    env_map = {"pilot": "STRIPE_PRICE_PILOT", "standard": "STRIPE_PRICE_STANDARD"}
    key = env_map.get(tier)
    if not key:
        raise ValueError(f"Unknown tier '{tier}'. Use 'pilot' or 'standard'.")
    price_id = os.environ.get(key, "").strip()
    if not price_id:
        raise RuntimeError(
            f"{key} is not set. Run create_stripe_products() first, "
            "then add the returned price IDs to Railway Variables."
        )
    return price_id


def _price_id_from_item(item: dict) -> str:
    """
    Extract a price ID string from a Stripe subscription phase item.
    Handles both unexpanded (price = "price_xxx") and expanded (price = {id: "..."}).
    """
    price = item.get("price", "")
    return price if isinstance(price, str) else price.get("id", "")


# ── Stripe: product and price setup ───────────────────────────────────────────

def create_stripe_products() -> dict:
    """
    Create the ThrottleGuard Stripe product and both price tiers.

    Run this ONCE to set up Stripe, then save the returned price IDs
    as STRIPE_PRICE_PILOT and STRIPE_PRICE_STANDARD in Railway Variables.
    Safe to run in test mode first — test and live Stripe environments are separate.

    Returns {"product_id", "pilot_price_id", "standard_price_id"}.
    """
    product = stripe.Product.create(
        name="ThrottleGuard",
        description="DPF + SCR predictive maintenance for commercial diesel fleets",
        metadata={"platform": "throttleguard"},
    )

    pilot_price = stripe.Price.create(
        product=product.id,
        nickname="ThrottleGuard Pilot — $35/truck/mo (90 days)",
        currency="usd",
        unit_amount=3500,       # Stripe amounts are always in cents
        recurring={"interval": "month", "usage_type": "licensed"},
        metadata={"tier": "pilot"},
    )

    standard_price = stripe.Price.create(
        product=product.id,
        nickname="ThrottleGuard Standard — $49/truck/mo",
        currency="usd",
        unit_amount=4900,
        recurring={"interval": "month", "usage_type": "licensed"},
        metadata={"tier": "standard"},
    )

    logger.info(f"Stripe setup complete. Product: {product.id}")
    logger.info(f"  Pilot price:    {pilot_price.id}")
    logger.info(f"  Standard price: {standard_price.id}")

    return {
        "product_id":        product.id,
        "pilot_price_id":    pilot_price.id,
        "standard_price_id": standard_price.id,
    }


# ── Stripe: customer ──────────────────────────────────────────────────────────

def create_stripe_customer(fleet_id: str, email: str, truck_count: int) -> str:
    """
    Create a Stripe Customer for a new fleet. Returns the customer ID (cus_...).
    The customer ID links all future payments, invoices, and subscriptions.
    """
    customer = stripe.Customer.create(
        email=email,
        name=f"Fleet: {fleet_id}",
        metadata={
            "fleet_id":    fleet_id,
            "truck_count": str(truck_count),
            "platform":    "throttleguard",
        },
    )
    logger.info(f"[{fleet_id}] Stripe customer created: {customer.id}")
    return customer.id


# ── Stripe: subscriptions ─────────────────────────────────────────────────────

def create_pilot_subscription(customer_id: str, truck_count: int, fleet_id: str) -> dict:
    """
    Create a Stripe Subscription Schedule with two billing phases:
      Phase 1 — pilot price ($35/truck) for PILOT_MONTHS billing cycles
      Phase 2 — standard price ($49/truck) indefinitely after pilot ends

    Stripe transitions phases automatically — no cron job or manual upgrade needed.
    Returns {"subscription_id", "schedule_id", "monthly_amount"}.
    """
    schedule = stripe.SubscriptionSchedule.create(
        customer=customer_id,
        start_behavior="now",
        phases=[
            {
                # Phase 1: pilot pricing for 3 months
                "items": [{"price": _get_price_id("pilot"), "quantity": truck_count}],
                "iterations": PILOT_MONTHS,   # billing cycles, not calendar months
                "metadata": {"phase": "pilot", "fleet_id": fleet_id},
            },
            {
                # Phase 2: standard pricing — no iterations = perpetual
                "items": [{"price": _get_price_id("standard"), "quantity": truck_count}],
                "metadata": {"phase": "standard", "fleet_id": fleet_id},
            },
        ],
    )

    logger.info(
        f"[{fleet_id}] Pilot schedule created: schedule={schedule.id}, "
        f"sub={schedule.subscription}, ${truck_count * PILOT_RATE:.2f}/mo"
    )
    return {
        "subscription_id": schedule.subscription,
        "schedule_id":     schedule.id,
        "monthly_amount":  truck_count * PILOT_RATE,
    }


def create_standard_subscription(customer_id: str, truck_count: int, fleet_id: str) -> dict:
    """
    Create a direct Standard-tier subscription (no pilot period, no schedule).
    Used when a fleet onboards straight to full pricing.
    Returns {"subscription_id", "monthly_amount"}.
    """
    sub = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": _get_price_id("standard"), "quantity": truck_count}],
        metadata={"fleet_id": fleet_id, "tier": "standard"},
    )
    logger.info(f"[{fleet_id}] Standard subscription created: {sub.id}")
    return {"subscription_id": sub.id, "monthly_amount": truck_count * STANDARD_RATE}


# ── DB write ──────────────────────────────────────────────────────────────────

def _save_billing_record(fleet_id: str, email: str, customer_id: str,
                          sub_result: dict, tier: str, truck_count: int) -> None:
    """
    Insert (or upsert) the tg_billing row after Stripe objects are created.
    ON CONFLICT DO UPDATE means calling onboard_fleet() twice is safe.
    """
    init_billing_db()
    now         = datetime.utcnow().isoformat()
    pilot_start = now if tier == "pilot" else None
    pilot_end   = (datetime.utcnow() + timedelta(days=PILOT_DAYS)).isoformat() if tier == "pilot" else None

    conn = get_conn()
    try:
        with conn:
            conn.cursor().execute(
                """
                INSERT INTO tg_billing
                    (fleet_id, email, stripe_customer_id, stripe_subscription_id,
                     stripe_schedule_id, tier, truck_count, pilot_start_date, pilot_end_date,
                     subscription_status, monthly_amount, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s,%s)
                ON CONFLICT (fleet_id) DO UPDATE SET
                    stripe_customer_id     = EXCLUDED.stripe_customer_id,
                    stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                    stripe_schedule_id     = EXCLUDED.stripe_schedule_id,
                    tier                   = EXCLUDED.tier,
                    truck_count            = EXCLUDED.truck_count,
                    subscription_status    = 'active',
                    monthly_amount         = EXCLUDED.monthly_amount,
                    updated_at             = EXCLUDED.updated_at
                """,
                (
                    fleet_id, email, customer_id,
                    sub_result.get("subscription_id"),
                    sub_result.get("schedule_id"),
                    tier, truck_count, pilot_start, pilot_end,
                    sub_result["monthly_amount"], now, now,
                ),
            )
    finally:
        conn.close()


# ── Main onboarding entry point ───────────────────────────────────────────────

def onboard_fleet(fleet_id: str, email: str, truck_count: int,
                  tier: str = "standard") -> dict:
    """
    Full onboarding for a new fleet in three steps:
      1. Create Stripe customer
      2. Create subscription (pilot schedule or standard)
      3. Write customer ID, subscription ID, and billing record to Supabase

    Parameters:
      fleet_id    — unique identifier ("tim_freight_co")
      email       — billing contact email
      truck_count — number of trucks (monthly charge = truck_count × rate)
      tier        — "pilot" or "standard"

    Returns a summary dict with fleet_id, tier, truck_count, monthly_amount, IDs.
    """
    if not stripe.api_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set.")

    customer_id = create_stripe_customer(fleet_id, email, truck_count)

    if tier == "pilot":
        sub_result = create_pilot_subscription(customer_id, truck_count, fleet_id)
    else:
        sub_result = create_standard_subscription(customer_id, truck_count, fleet_id)

    _save_billing_record(fleet_id, email, customer_id, sub_result, tier, truck_count)

    logger.info(
        f"[{fleet_id}] Onboarding complete — tier={tier}, trucks={truck_count}, "
        f"${sub_result['monthly_amount']:.2f}/mo"
    )
    return {
        "fleet_id":        fleet_id,
        "tier":            tier,
        "truck_count":     truck_count,
        "monthly_amount":  sub_result["monthly_amount"],
        "customer_id":     customer_id,
        "subscription_id": sub_result.get("subscription_id"),
        "schedule_id":     sub_result.get("schedule_id"),
    }


# ── Truck count scaling ───────────────────────────────────────────────────────

def _update_schedule_quantities(schedule_id: str, new_count: int) -> None:
    """
    Update truck quantity in all phases of an existing Subscription Schedule.
    Called when truck count changes on a pilot fleet — keeps phase 2 in sync.
    """
    schedule = stripe.SubscriptionSchedule.retrieve(schedule_id)

    # Rebuild phase definitions with the new quantity, keeping the same prices
    new_phases = []
    for i, phase in enumerate(schedule["phases"]):
        phase_def: dict = {
            "items": [
                {"price": _price_id_from_item(item), "quantity": new_count}
                for item in phase["items"]
            ],
        }
        # Phase 1 keeps its iteration count; phase 2 (no iterations) is perpetual
        if "iterations" in phase:
            phase_def["iterations"] = phase["iterations"]
        new_phases.append(phase_def)

    stripe.SubscriptionSchedule.modify(schedule_id, phases=new_phases)


def update_truck_count(fleet_id: str, new_count: int) -> dict:
    """
    Scale a fleet's billing to a new truck count.
    Stripe prorates the difference within the current billing period.

    For pilot fleets (Subscription Schedule): updates all schedule phases so
    the quantity is correct when phase 2 (Standard) kicks in automatically.

    Returns {"success": bool, "monthly_amount": float}.
    """
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT stripe_subscription_id, stripe_schedule_id, tier "
                "FROM tg_billing WHERE fleet_id = %s",
                (fleet_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return {"success": False, "error": f"No billing record found for fleet '{fleet_id}'"}

    if row["stripe_schedule_id"]:
        # Pilot fleet — update the schedule so phase 2 also gets the new quantity
        _update_schedule_quantities(row["stripe_schedule_id"], new_count)
    else:
        # Standard fleet — update the active subscription item directly
        sub  = stripe.Subscription.retrieve(row["stripe_subscription_id"])
        item = sub["items"]["data"][0]
        stripe.SubscriptionItem.modify(item["id"], quantity=new_count)

    rate       = PILOT_RATE if row["tier"] == "pilot" else STANDARD_RATE
    new_amount = new_count * rate
    now        = datetime.utcnow().isoformat()

    conn = get_conn()
    try:
        with conn:
            conn.cursor().execute(
                "UPDATE tg_billing SET truck_count=%s, monthly_amount=%s, updated_at=%s "
                "WHERE fleet_id=%s",
                (new_count, new_amount, now, fleet_id),
            )
    finally:
        conn.close()

    logger.info(f"[{fleet_id}] Truck count → {new_count}, ${new_amount:.2f}/mo")
    return {"success": True, "monthly_amount": new_amount}


# ── Pilot extension ───────────────────────────────────────────────────────────

def extend_pilot(fleet_id: str, additional_months: int = 1) -> dict:
    """
    Manually extend a fleet's pilot period.
    Adds billing cycles to phase 1 of the Stripe Subscription Schedule,
    which also pushes the Standard phase start date forward.

    Use case: Tim needs more time, or you want to reward early feedback.
    Returns {"success": bool, "new_pilot_end_date": str}.
    """
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT stripe_schedule_id, pilot_end_date, truck_count "
                "FROM tg_billing WHERE fleet_id = %s",
                (fleet_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or not row["stripe_schedule_id"]:
        return {"success": False, "error": "No pilot schedule found for this fleet."}

    schedule        = stripe.SubscriptionSchedule.retrieve(row["stripe_schedule_id"])
    current_iters   = schedule["phases"][0].get("iterations", PILOT_MONTHS)
    truck_count     = row["truck_count"]

    # Rebuild phases with phase 1's iteration count extended
    stripe.SubscriptionSchedule.modify(
        row["stripe_schedule_id"],
        phases=[
            {
                "items": [
                    {"price": _price_id_from_item(i), "quantity": truck_count}
                    for i in schedule["phases"][0]["items"]
                ],
                "iterations": current_iters + additional_months,
            },
            {
                "items": [
                    {"price": _price_id_from_item(i), "quantity": truck_count}
                    for i in schedule["phases"][1]["items"]
                ],
            },
        ],
    )

    old_end = datetime.fromisoformat(row["pilot_end_date"])
    new_end = old_end + timedelta(days=30 * additional_months)

    conn = get_conn()
    try:
        with conn:
            conn.cursor().execute(
                "UPDATE tg_billing SET pilot_end_date=%s, updated_at=%s WHERE fleet_id=%s",
                (new_end.isoformat(), datetime.utcnow().isoformat(), fleet_id),
            )
    finally:
        conn.close()

    logger.info(f"[{fleet_id}] Pilot extended +{additional_months} month(s). New end: {new_end.date()}")
    return {"success": True, "new_pilot_end_date": new_end.isoformat()}


# ── Read ──────────────────────────────────────────────────────────────────────

def get_billing_record(fleet_id: str) -> dict | None:
    """Return the full tg_billing row for a fleet, or None if not found."""
    init_billing_db()
    conn = get_conn()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM tg_billing WHERE fleet_id = %s", (fleet_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


# ── Test onboarding flow ──────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Step 1: Creates Stripe product + prices in TEST MODE and prints the IDs.
    Step 2: Simulates Tim's onboarding (200 trucks, pilot tier).

    Run once to set up Stripe, then copy the price IDs into Railway Variables.
    Everything created here is in Stripe TEST MODE — no real charges.

    Usage:
        python throttleguard_billing.py
    """
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not stripe.api_key:
        print("\nERROR: STRIPE_SECRET_KEY is not set. Add it to your .env file first.\n")
        sys.exit(1)

    mode = "LIVE" if stripe.api_key.startswith("sk_live_") else "TEST"
    print(f"\n{'='*58}")
    print(f"  ThrottleGuard Stripe Setup — {mode} MODE")
    print(f"{'='*58}")

    # ── Step 1: create Stripe objects ─────────────────────────────────────────
    print("\n[1/2] Creating Stripe product and prices...")
    ids = create_stripe_products()

    print(f"\n  ✓ Product ID:        {ids['product_id']}")
    print(f"  ✓ Pilot price ID:    {ids['pilot_price_id']}")
    print(f"  ✓ Standard price ID: {ids['standard_price_id']}")
    print(f"\n  Add these to Railway Variables:")
    print(f"    STRIPE_PRICE_PILOT    = {ids['pilot_price_id']}")
    print(f"    STRIPE_PRICE_STANDARD = {ids['standard_price_id']}")

    # Set them for the test run below without needing to restart
    os.environ["STRIPE_PRICE_PILOT"]    = ids["pilot_price_id"]
    os.environ["STRIPE_PRICE_STANDARD"] = ids["standard_price_id"]

    # ── Step 2: simulate Tim's onboarding ────────────────────────────────────
    print(f"\n{'─'*58}")
    print("[2/2] Simulating Tim's onboarding (200 trucks, pilot tier)...")

    result = onboard_fleet(
        fleet_id    = "tim_freight_co",
        email       = "tim@timfreightco.com",
        truck_count = 200,
        tier        = "pilot",
    )

    pilot_monthly    = result["monthly_amount"]
    standard_monthly = 200 * STANDARD_RATE

    print(f"\n  Fleet:          {result['fleet_id']}")
    print(f"  Tier:           {result['tier']}")
    print(f"  Trucks:         {result['truck_count']}")
    print(f"  Customer ID:    {result['customer_id']}")
    print(f"  Subscription:   {result['subscription_id']}")
    print(f"  Schedule:       {result['schedule_id']}")
    print(f"\n  Month 1–3:  ${pilot_monthly:>8,.2f}/mo  (pilot @ ${PILOT_RATE:.0f}/truck)")
    print(f"  Month 4+:   ${standard_monthly:>8,.2f}/mo  (standard @ ${STANDARD_RATE:.0f}/truck — auto-upgraded by Stripe)")
    print(f"\n{'='*58}")
    print("  Done. Check Stripe Dashboard → Subscriptions to verify.")
    print(f"{'='*58}\n")
