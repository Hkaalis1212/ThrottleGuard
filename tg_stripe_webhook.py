"""
tg_stripe_webhook.py
====================
Flask server that receives and processes Stripe webhook events.

Deploy as a SEPARATE Railway service pointing to this file.
  Start command: python tg_stripe_webhook.py
  Railway assigns $PORT automatically — no hardcoding needed.

Register the webhook URL in Stripe:
  Dashboard → Developers → Webhooks → Add endpoint
  URL: https://<your-webhook-service>.railway.app/stripe/webhook
  Events to send:
    invoice.payment_succeeded
    invoice.payment_failed
    customer.subscription.deleted
    customer.subscription.updated

Events handled:
  invoice.payment_succeeded    → subscription_status = 'active'
  invoice.payment_failed       → subscription_status = 'past_due'  + alert log
  customer.subscription.deleted → subscription_status = 'cancelled'
  customer.subscription.updated → sync tier + truck_count after pilot → standard upgrade

Signature verification:
  Every request is verified against STRIPE_WEBHOOK_SECRET before processing.
  Without this, an attacker could fake events and manipulate billing records.

Environment variables (Railway → Variables):
  STRIPE_SECRET_KEY       — same key used in throttleguard_billing.py
  STRIPE_WEBHOOK_SECRET   — whsec_... from Stripe Dashboard → Webhooks → endpoint detail
  DATABASE_URL            — Supabase PostgreSQL (same as main app)
  PORT                    — set automatically by Railway (don't set this yourself)
"""

import os
import logging
from datetime import datetime

import stripe
from flask import Flask, request, jsonify

from tg_db import get_conn
from throttleguard_billing import PILOT_RATE, STANDARD_RATE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

stripe.api_key      = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET      = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

app = Flask(__name__)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _set_status(stripe_customer_id: str, status: str) -> None:
    """Update subscription_status in tg_billing by Stripe customer ID."""
    conn = get_conn()
    try:
        with conn:
            conn.cursor().execute(
                "UPDATE tg_billing SET subscription_status=%s, updated_at=%s "
                "WHERE stripe_customer_id=%s",
                (status, datetime.utcnow().isoformat(), stripe_customer_id),
            )
    finally:
        conn.close()


# ── Event handlers ────────────────────────────────────────────────────────────

def _handle_payment_succeeded(data: dict) -> None:
    """
    invoice.payment_succeeded
    Fleet paid — confirm their access is active.
    Stripe fires this on every successful monthly charge.
    """
    customer_id = data["customer"]
    _set_status(customer_id, "active")
    logger.info(f"Payment succeeded — customer={customer_id} → status=active")


def _handle_payment_failed(data: dict) -> None:
    """
    invoice.payment_failed
    Payment bounced or card declined.
    Stripe will retry automatically (configurable in Dashboard → Billing → Retry rules).
    We flag the fleet so the app can show a payment warning.

    TODO: call _send_sms() from the Samsara poller to alert the fleet manager.
    """
    customer_id  = data["customer"]
    invoice_id   = data.get("id", "unknown")
    attempt_count = data.get("attempt_count", "?")

    _set_status(customer_id, "past_due")
    logger.warning(
        f"Payment FAILED — customer={customer_id}, invoice={invoice_id}, "
        f"attempt #{attempt_count} → status=past_due"
    )


def _handle_subscription_cancelled(data: dict) -> None:
    """
    customer.subscription.deleted
    Subscription ended — could be customer-initiated, auto-expired after retries,
    or cancelled manually via Stripe Dashboard.
    """
    customer_id = data["customer"]
    _set_status(customer_id, "cancelled")
    logger.info(f"Subscription cancelled — customer={customer_id} → status=cancelled")


def _handle_subscription_updated(data: dict) -> None:
    """
    customer.subscription.updated
    Fires whenever anything changes on the subscription.
    Most importantly: Stripe Subscription Schedule auto-transitions from
    pilot (phase 1) to standard (phase 2) at month 3 — this event syncs
    the tier in our Supabase record so billing reports stay accurate.
    """
    customer_id = data["customer"]
    items       = data.get("items", {}).get("data", [])
    if not items:
        return

    item        = items[0]
    new_quantity = item.get("quantity", 1)

    # Price tier comes from the metadata we attached when creating the price object
    price_meta   = item.get("price", {}).get("metadata", {})
    new_tier     = price_meta.get("tier", "standard")
    rate         = PILOT_RATE if new_tier == "pilot" else STANDARD_RATE
    new_monthly  = new_quantity * rate

    conn = get_conn()
    try:
        with conn:
            conn.cursor().execute(
                """UPDATE tg_billing
                   SET tier=%s, truck_count=%s, monthly_amount=%s, updated_at=%s
                   WHERE stripe_customer_id=%s""",
                (new_tier, new_quantity, new_monthly, datetime.utcnow().isoformat(), customer_id),
            )
    finally:
        conn.close()

    logger.info(
        f"Subscription updated — customer={customer_id}, "
        f"tier={new_tier}, trucks={new_quantity}, ${new_monthly:.2f}/mo"
    )


# ── Webhook endpoint ──────────────────────────────────────────────────────────

# Map Stripe event types to handler functions
EVENT_HANDLERS = {
    "invoice.payment_succeeded":      _handle_payment_succeeded,
    "invoice.payment_failed":         _handle_payment_failed,
    "customer.subscription.deleted":  _handle_subscription_cancelled,
    "customer.subscription.updated":  _handle_subscription_updated,
}


@app.route("/stripe/webhook", methods=["POST"])
def webhook():
    """
    Stripe sends all subscribed events here as HTTP POST requests.
    We verify the signature first — if it doesn't match STRIPE_WEBHOOK_SECRET,
    we reject it immediately with a 400. Never skip this check.
    """
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    if not WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not set — all webhooks rejected.")
        return jsonify({"error": "Webhook secret not configured"}), 500

    # Verify the request came from Stripe (not a spoofed request)
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature — request rejected.")
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    event_data = event["data"]["object"]

    logger.info(f"Stripe event received: {event_type} (id={event['id']})")

    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            handler(event_data)
        except Exception as exc:
            # Log and return 500 so Stripe retries the event
            logger.error(f"Handler error for {event_type}: {exc}")
            return jsonify({"error": "Handler failed"}), 500
    else:
        # Not an event we handle — acknowledge receipt so Stripe doesn't retry
        logger.debug(f"Unhandled event type: {event_type}")

    # Return 200 to tell Stripe the event was received successfully
    return jsonify({"received": True}), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check for Railway's uptime monitoring. Returns 200 when the server is up."""
    return jsonify({"status": "ok", "service": "throttleguard-webhook"}), 200


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Railway injects $PORT — always use it instead of hardcoding
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"ThrottleGuard webhook server starting on port {port}")

    if not WEBHOOK_SECRET:
        logger.warning(
            "STRIPE_WEBHOOK_SECRET is not set. "
            "Add it from Stripe Dashboard → Developers → Webhooks → your endpoint → Signing secret."
        )

    # debug=False in production — Railway's log viewer shows all output anyway
    app.run(host="0.0.0.0", port=port, debug=False)
