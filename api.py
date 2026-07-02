"""
api.py — ThrottleGuard Telematics Ingestion API
------------------------------------------------
FastAPI layer that handles Motive's OAuth flow and real-time webhook events.
This is the FIRST adapter in an ingestion architecture built to be
provider-agnostic — see tg_telematics_adapters.py for why.

HOW IT FITS IN
    Motive pushes fault/engine/vehicle events here via webhook.
    This server normalizes them into ThrottleGuard's canonical J1939 row shape
    (same fields the scoring engine and Streamlit dashboard already use).
    Token persistence lives in Supabase (tg_motive_tokens) so Railway restarts
    don't force fleet operators to re-authorize.

RAILWAY DEPLOYMENT
    Run this as a SEPARATE Railway service in the same project.
    Start command:  uvicorn api:app --host 0.0.0.0 --port $PORT
    Health check:   /health

    Required env vars (copy from your existing service):
        DATABASE_URL          — same Supabase connection string
        MOTIVE_CLIENT_ID      — from Motive developer portal
        MOTIVE_CLIENT_SECRET  — from Motive developer portal
        MOTIVE_REDIRECT_URI   — https://<this-service-domain>.up.railway.app/callback

ROUTES
    GET  /health     — Railway health check
    GET  /authorize  — Start the Motive OAuth flow (redirects to Motive consent screen)
    GET  /callback   — Motive OAuth redirect (exchanges code for token, stored in Supabase)
    POST /webhook    — Real-time fault/engine/vehicle events from Motive (HMAC verified)
    GET  /token      — Internal: confirm token is live without exposing credentials
"""

import hashlib
import hmac
import html
import json
import os
import secrets
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse

from tg_motive_auth import save_token, get_token, token_is_expired, refresh_access_token
from tg_telematics_adapters import (
    normalize_motive_fault_event,
    normalize_motive_engine_event,
    normalize_motive_vehicle_event,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="ThrottleGuard Ingestion API", version="2.0.0")

# ── Motive OAuth config (Railway env vars) ─────────────────────────────────────
MOTIVE_CLIENT_ID      = os.environ.get("MOTIVE_CLIENT_ID")
MOTIVE_CLIENT_SECRET  = os.environ.get("MOTIVE_CLIENT_SECRET")
MOTIVE_REDIRECT_URI   = os.environ.get("MOTIVE_REDIRECT_URI")
MOTIVE_WEBHOOK_SECRET = os.environ.get("MOTIVE_WEBHOOK_SECRET", "")
# Gates /authorize — without this, anyone who finds the URL could connect their
# own Motive account and overwrite the fleet's stored token (save_token() only
# keeps one row per provider). Generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
MOTIVE_SETUP_KEY      = os.environ.get("MOTIVE_SETUP_KEY", "")
MOTIVE_AUTH_URL       = "https://api.gomotive.com/oauth/authorize"
MOTIVE_TOKEN_URL      = "https://api.gomotive.com/oauth/token"
# Scopes your Motive app was approved for — adjust in the developer portal if needed
MOTIVE_SCOPES         = os.environ.get("MOTIVE_SCOPES", "vehicles.read hours_of_service.read")

PROVIDER = "motive"

# CSRF protection: track in-flight OAuth state values (single-process; fine for one Railway instance)
_pending_oauth_states: set[str] = set()


# ── Route 1: Health check ──────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Railway uses this to verify the service is alive."""
    return {
        "status": "ok",
        "service": "ThrottleGuard Ingestion API",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Route 2: OAuth – start the flow ───────────────────────────────────────────

@app.get("/authorize")
async def motive_authorize(key: str = ""):
    """
    Send the fleet operator to Motive's consent screen.

    Open this URL in a browser (query param, not a header, since a human is
    clicking a link and can't set custom headers):
        https://<api-service>.up.railway.app/authorize?key=<MOTIVE_SETUP_KEY>

    Motive will show the operator a permission grant page, then redirect to
    /callback with an authorization code. The state param is a random token
    stored in memory to detect CSRF — if the callback arrives with an unknown
    state we reject it. Gating /authorize with MOTIVE_SETUP_KEY also protects
    /callback indirectly: without a valid key, no state ever gets created, so
    an attacker hitting /callback directly has no state that will pass.
    """
    if not MOTIVE_SETUP_KEY:
        raise HTTPException(
            status_code=500,
            detail="MOTIVE_SETUP_KEY must be set in Railway env vars before /authorize can be used",
        )
    if not hmac.compare_digest(MOTIVE_SETUP_KEY, key):
        raise HTTPException(status_code=401, detail="Missing or invalid ?key= parameter")

    if not MOTIVE_CLIENT_ID or not MOTIVE_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="MOTIVE_CLIENT_ID and MOTIVE_REDIRECT_URI must be set in Railway env vars",
        )

    state = secrets.token_urlsafe(32)
    _pending_oauth_states.add(state)

    params = (
        f"?client_id={MOTIVE_CLIENT_ID}"
        f"&redirect_uri={MOTIVE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={MOTIVE_SCOPES.replace(' ', '%20')}"
        f"&state={state}"
    )
    log.info(f"Starting Motive OAuth flow — state: {state[:8]}...")
    return RedirectResponse(url=MOTIVE_AUTH_URL + params)


# ── Route 3: OAuth – callback ──────────────────────────────────────────────────

@app.get("/callback")
async def motive_oauth_callback(request: Request):
    """
    Motive redirects here after the fleet operator authorizes your app.
    URL looks like: /callback?code=ABC123&state=xyz

    Exchange the code for a token, persist it to Supabase via tg_motive_auth —
    token survives Railway restarts so the fleet doesn't have to re-authorize.
    """
    code  = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        log.error(f"Motive OAuth error: {error}")
        safe_error = html.escape(error)
        return HTMLResponse(content=f"<h2>Authorization failed: {safe_error}</h2>", status_code=400)

    if not code:
        log.error("No authorization code in OAuth callback")
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # CSRF check — state must match one we issued from /authorize
    if state not in _pending_oauth_states:
        log.error(f"OAuth callback with unknown state '{state}' — possible CSRF or stale link")
        raise HTTPException(status_code=400, detail="Invalid state parameter — start the flow again via /authorize")
    _pending_oauth_states.discard(state)

    log.info(f"OAuth callback received — code: {code[:8]}... state: {state}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                MOTIVE_TOKEN_URL,
                data={
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "redirect_uri":  MOTIVE_REDIRECT_URI,
                    "client_id":     MOTIVE_CLIENT_ID,
                    "client_secret": MOTIVE_CLIENT_SECRET,
                },
            )

        if response.status_code != 200:
            log.error(f"Motive token exchange failed: {response.status_code} {response.text}")
            raise HTTPException(status_code=500, detail="Token exchange failed")

        token_data    = response.json()
        access_token  = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in    = int(token_data.get("expires_in") or 3600)

    except HTTPException:
        raise
    except Exception as exc:
        log.error(f"Token exchange exception: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    save_token(PROVIDER, access_token, refresh_token, expires_in)
    log.info(f"Motive token saved to Supabase — expires in {expires_in}s")

    success_html = """
    <html>
      <body style="font-family: sans-serif; background: #1a1a1a; color: #FFB300;
                  text-align: center; padding-top: 80px;">
        <h1>ThrottleGuard Connected to Motive</h1>
        <p style="color: #ccc;">Authorization successful. You can close this tab.</p>
      </body>
    </html>
    """
    return HTMLResponse(content=success_html)


# ── Route 3: Motive webhook receiver ──────────────────────────────────────────

@app.post("/webhook")
async def motive_webhook(request: Request):
    """
    Motive POSTs real-time events here as JSON.

    Each event is routed to the appropriate Motive-specific handler, which
    calls a normalize_motive_*() function from tg_telematics_adapters to
    produce a canonical J1939 row (or partial row). That normalized shape is
    what the scoring engine and dashboard already consume — adding Samsara or
    Geotab webhooks later means adding adapters in tg_telematics_adapters.py,
    not changing this routing layer.

    Motive expects a 200 back or it will retry.

    Signature header: X-Motive-Hmac-SHA256 (verify exact name in your Motive
    developer portal → Webhooks → your endpoint settings).
    MOTIVE_WEBHOOK_SECRET must be set in Railway env vars — without it, every
    call is rejected with 503 rather than silently accepting unsigned
    payloads from any sender.
    """
    if not MOTIVE_WEBHOOK_SECRET:
        log.error("Webhook rejected — MOTIVE_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="Webhook receiver not configured — set MOTIVE_WEBHOOK_SECRET")

    body = await request.body()

    sig_header = (
        request.headers.get("X-Motive-Hmac-SHA256")
        or request.headers.get("X-Hub-Signature-256", "")
    )
    expected = hmac.new(
        MOTIVE_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    # Motive may prefix the value with "sha256=" — strip it before comparing
    received = sig_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, received):
        log.warning("Webhook rejected — HMAC signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception:
        log.error("Webhook payload is not valid JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = str(payload.get("event_type") or payload.get("type") or "unknown")
    log.info(f"Webhook received — event_type: {event_type}")

    if "fault" in event_type.lower():
        _handle_fault_event(payload)
    elif "engine" in event_type.lower():
        _handle_engine_event(payload)
    elif "vehicle" in event_type.lower():
        _handle_vehicle_event(payload)
    else:
        log.info(f"Unhandled event type '{event_type}' — logged, no action taken")

    return JSONResponse(content={"received": True})


# ── Webhook handlers ───────────────────────────────────────────────────────────

def _handle_fault_event(payload: dict) -> None:
    """
    Handles Fault Code Opened/Closed events from Motive.

    Calls normalize_motive_fault_event() to map Motive's SPN/FMI payload into
    ThrottleGuard's canonical J1939 row shape. The normalized result is what
    any downstream scoring trigger or Supabase write should work with — no
    Motive-specific fields beyond this point.
    """
    row = normalize_motive_fault_event(payload)

    if row is None:
        spn = payload.get("spn")
        log.debug(f"Fault event for SPN {spn} — not a tracked DPF/SCR signal, skipped")
        return

    vid        = row["vehicle_id"]
    spn        = row.get("_spn")
    fault_open = row.get("_fault_open")

    canonical = {k: v for k, v in row.items() if not k.startswith("_") and k != "vehicle_id"}
    if canonical:
        detail = f"canonical fields updated: {canonical}"
    else:
        detail = f"relates to '{row.get('_needs_numeric_lookup', '?')}' — needs numeric-stats feed for actual value"

    log.info(f"[{vid}] Fault {'OPENED' if fault_open else 'CLOSED'} — SPN {spn} — {detail}")
    if fault_open:
        log.warning(f"[{vid}] DPF/SCR fault OPEN — SPN {spn}")

    # TODO: write normalized row to Supabase tg_fault_events table
    # TODO: trigger scoring engine re-run for this vehicle if fault_open
    # TODO: if scoring returns CRITICAL, flag for AI dispatcher to block load assignment


def _handle_engine_event(payload: dict) -> None:
    """
    Handles Engine On/Off events.

    Normalizes into a canonical engine-state record. Used for idle-hour tracking
    (Rule 7: excessive idle accelerates DPF clogging). Aggregating on/off events
    into an idle_time_pct that the scoring engine can use is a future pipeline step.
    """
    row = normalize_motive_engine_event(payload)
    if row is None:
        return

    log.info(f"[{row['vehicle_id']}] Engine {row.get('_engine_state', '?')} at {row.get('_timestamp')}")

    # TODO: write to tg_engine_events; aggregate idle_time_pct per vehicle per 24h window


def _handle_vehicle_event(payload: dict) -> None:
    """
    Handles Vehicle Upserted events — fires when a truck is added to the Motive fleet.
    Auto-onboards the truck into ThrottleGuard using the normalized canonical record.
    """
    row = normalize_motive_vehicle_event(payload)
    if row is None:
        return

    log.info(f"New vehicle — ID: {row['vehicle_id']} | Name: {row.get('_name')} | VIN: {row.get('_vin')}")

    # TODO: upsert into tg_fleet (or tg_predictions scaffold) so the dashboard knows this truck exists


# ── Route 4: token status (internal) ──────────────────────────────────────────

@app.get("/token")
async def token_status():
    """
    Internal endpoint — confirms a Motive token is stored and its expiry state.
    Attempts a token refresh automatically if the token is expired or close to expiry.

    Returns metadata only (no access/refresh token values) so this can safely be
    hit by health-check scripts. Pollers that need the actual token call
    tg_motive_auth.get_token("motive") directly inside the service process.
    """
    stored = get_token(PROVIDER)
    if not stored:
        raise HTTPException(status_code=404, detail="No token stored — visit /authorize to connect Motive")

    refreshed = False
    if token_is_expired(PROVIDER):
        log.info("Token expired or expiring soon — attempting refresh")
        ok = refresh_access_token(PROVIDER, MOTIVE_CLIENT_ID, MOTIVE_CLIENT_SECRET, MOTIVE_TOKEN_URL)
        if ok:
            stored    = get_token(PROVIDER)
            refreshed = True
        else:
            log.warning("Token refresh failed — re-authorization needed via /authorize")

    return {
        "provider":   PROVIDER,
        "expires_at": stored["expires_at"],
        "updated_at": stored["updated_at"],
        "expired":    token_is_expired(PROVIDER),
        "refreshed":  refreshed,
    }


# ── Route 5: DPF status feed for Mya (AI dispatcher) ──────────────────────────

# Optional API key — set THROTTLEGUARD_API_KEY to require callers to present it.
# If unset, the endpoint is open (suitable for internal Railway private networking).
_TG_API_KEY = os.environ.get("THROTTLEGUARD_API_KEY", "")

# Days-until-cleaning estimate per priority — used when no service date is stored.
_DAYS_UNTIL_CLEANING = {"CRITICAL": 2, "HIGH": 7, "MEDIUM": 14, "LOW": 30}


@app.get("/api/dpf-status")
async def dpf_status(request: Request):
    """
    Returns the latest DPF risk score per vehicle for Mya (AI dispatcher).

    Response shape matches what fleet-context.ts in the ai-receptionist expects:
        [{ "truck_id": "...", "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
           "days_until_cleaning": <int> }, ...]

    Secured by X-Api-Key header when THROTTLEGUARD_API_KEY env var is set.
    If the env var is empty the endpoint is open — fine for Railway private networking.
    """
    if _TG_API_KEY:
        provided = request.headers.get("X-Api-Key", "")
        if not hmac.compare_digest(_TG_API_KEY, provided):
            raise HTTPException(status_code=401, detail="Invalid API key")

    import psycopg2
    import psycopg2.extras

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")

    try:
        conn = psycopg2.connect(db_url, connect_timeout=8)
        try:
            with conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                # Latest prediction per vehicle (highest id = most recent insert)
                cur.execute(
                    """
                    SELECT DISTINCT ON (vehicle_id)
                        vehicle_id,
                        predicted_priority,
                        risk_score
                    FROM tg_predictions
                    ORDER BY vehicle_id, id DESC
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        log.error(f"/api/dpf-status DB error: {exc}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    return [
        {
            "truck_id":            row["vehicle_id"],
            "risk_level":          row["predicted_priority"],
            "days_until_cleaning": _DAYS_UNTIL_CLEANING.get(row["predicted_priority"], 30),
        }
        for row in rows
    ]


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True)
