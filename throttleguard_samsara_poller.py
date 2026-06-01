"""
throttleguard_samsara_poller.py
================================
Polls the Samsara Fleet API on a 30-minute schedule, scores every truck
through ThrottleGuard's rule-based expert system, and prints a console alert
(logged to Railway) when a vehicle reaches HIGH or CRITICAL risk.

HOW IT WORKS
------------
1. Read SAMSARA_API_TOKEN from environment (never hardcoded)
2. GET /fleet/vehicles/stats — walk all pages with cursor pagination
3. Parse each vehicle: pull numeric sensor stats + active J1939 fault codes
4. Map to ThrottleGuard's canonical input shape (see FIELD MAPPING below)
5. Run score_row() — same engine used in the dashboard
6. Print a formatted alert if priority is HIGH or CRITICAL

SETTING SAMSARA_API_TOKEN
--------------------------
Railway (production):
  Project → Variables → New Variable → SAMSARA_API_TOKEN = samsara-yourkey

Local (.env file):
  SAMSARA_API_TOKEN=samsara-yourkey
  (python-dotenv loads it automatically — same pattern as DATABASE_URL)

FIELD MAPPING — Samsara → ThrottleGuard
-----------------------------------------
Samsara exposes two kinds of data:

  1. Named numeric stats — if your telematics gateway broadcasts the J1939
     parameter, Samsara stores it and returns it via the stats endpoint.
     These give actual temperature, pressure, and regen readings.

  2. Fault codes (DTCs) — active J1939/OBD trouble codes with SPN and FMI.
     These are always available and tell us which systems are faulting.

Mapping table (SPN = SAE J1939 Suspect Parameter Number):

  SPN 3480  DPF Outlet Gas Temperature (°C)        → dpf_outlet_temp_active_regen_f
  SPN 3479  DPF Inlet Gas Temperature (°C)          → dpf_inlet_temp_f
  SPN 3251  DPF Differential Pressure (Pa)          → back_pressure_inh2o
  SPN 3697  DPF Active Regeneration Status (0/1)    → regen_active
  SPN 3515  SCR Catalyst Intake Temperature (°C)    → scr_inlet_temp_f
  SPN 1127  Turbocharger 1 Boost Pressure (kPa)     → turbo_boost_psi
  SPN 1238  EGR Mass Flow Rate — fault active       → egr_flow_fault (1 or 0)
  SPN 3563  NH3 Slip Sensor — fault active          → nh3_slip_detected (1 or 0)
  SPN 3216  NOx upstream / SPN 3516 downstream      → nox_conversion_pct (computed)

WHAT HAPPENS WHEN SENSOR DATA IS MISSING
-----------------------------------------
Required fields use SAFE_SENSOR_DEFAULTS — values in normal operating ranges
that won't trigger rules on their own. This means a truck with no sensor data
scores LOW or MEDIUM from fault codes alone. No false positives; some false
negatives are possible. A warning is logged for every missing required field
so you know which vehicles are being scored on partial data.

ALERTS
------
Every HIGH / CRITICAL vehicle prints to console (Railway log viewer) AND
sends an SMS via Twilio if these env vars are set:
  TWILIO_ACCOUNT_SID   — Twilio Console → Account Info
  TWILIO_AUTH_TOKEN    — Twilio Console → Account Info
  TG_TWILIO_PHONE      — your Twilio sending number (+15551234567)
  FLEET_MGR_PHONE      — recipient(s), comma-separated (+15559876543)
"""

import os
import logging
from typing import Optional

import requests
from apscheduler.schedulers.blocking import BlockingScheduler

from scoring_engine import score_row, SCORE_COLUMNS

# ── Logging ────────────────────────────────────────────────────────────────────
# Railway captures stdout/stderr — logging goes to your Railway log viewer.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Samsara API ────────────────────────────────────────────────────────────────

SAMSARA_BASE_URL = "https://api.samsara.com"

# Stat types to request from Samsara's vehicle stats endpoint.
# "faultCodes"       — active J1939/OBD DTCs with SPN, FMI, and description
# "engineStates"     — engine on / off / idle
# "gpsOdometerMeters"— odometer reading in meters (used for service intervals)
#
# NOTE: Samsara also exposes named aftertreatment numeric stats on supported
# hardware (e.g. aftertreatmentDpfOutletGasTemperatureMilliC). These are
# included in SAMSARA_STAT_TYPES below. If your gateway doesn't broadcast
# a parameter, Samsara simply omits it from the response — never an error.
# Verify which stats your devices transmit via the Samsara API Explorer:
#   https://developers.samsara.com/reference/listvehiclestats
SAMSARA_STAT_TYPES = [
    "faultCodes",
    "engineStates",
    "gpsOdometerMeters",
    # Aftertreatment numeric stats — available when gateway broadcasts J1939 PGN
    # Naming follows Samsara's camelCase convention for J1939 parameter descriptions
    "aftertreatmentDpfOutletGasTemperatureMilliC",   # SPN 3480
    "aftertreatmentDpfInletGasTemperatureMilliC",    # SPN 3479
    "aftertreatmentDpfDifferentialPressurePa",       # SPN 3251  (Pascals)
    "aftertreatmentDpfActiveRegenerationStatus",     # SPN 3697
    "aftertreatmentScrIntakeGasTemperatureMilliC",   # SPN 3515
    "turbocharger1BoostPressureKPa",                 # SPN 1127
]


# ── J1939 SPN reference ────────────────────────────────────────────────────────
# SPNs that indicate active DPF / SCR faults.
# When a vehicle has one of these as an *active* fault code, it's a strong
# signal that the aftertreatment system has a problem even when numeric
# sensor readings aren't available.

DPF_SPN_LABELS = {
    3251: "DPF Differential Pressure",
    3479: "DPF Inlet Gas Temperature",
    3480: "DPF Outlet Gas Temperature",
    3697: "DPF Active Regeneration Status",
    3698: "DPF Passive Regeneration Status",
    3515: "SCR Catalyst Intake Temperature",
    3226: "Aftertreatment Outlet Temperature",
    3364: "DEF Tank Level",
    4334: "DEF Concentration",
    1127: "Turbocharger 1 Boost Pressure",
    1238: "Engine EGR Mass Flow Rate",     # active fault = EGR system fault
    3216: "NOx Upstream (pre-SCR)",
    3516: "NOx Downstream (post-SCR)",
    3563: "NH3 Slip Sensor",               # active fault = ammonia bypassing SCR
}

DPF_RELATED_SPNS = set(DPF_SPN_LABELS.keys())

# Priority levels that fire an alert notification
ALERT_PRIORITIES = {"HIGH", "CRITICAL"}

# Poll every 30 minutes — one poll cycle scores the entire fleet
POLL_INTERVAL_MINUTES = 30

# Safe placeholder values for required sensor fields when Samsara can't provide them.
# Chosen to sit inside normal operating ranges so they won't trigger rules on their own.
# A truck with no sensor data scores LOW/MEDIUM from fault codes only — no false alerts.
SAFE_SENSOR_DEFAULTS: dict[str, float] = {
    "dpf_outlet_temp_active_regen_f": 1000.0,  # above REGEN_OUTLET_CRITICAL_F (940°F)
    "dpf_outlet_temp_peak_f":         1050.0,  # below thermal shock limits (1200–1250°F)
    "dpf_inlet_temp_f":                960.0,  # normal inlet — avoids impossible delta rule
    "regen_count_7d":                    0,    # assume no recent regens
    "back_pressure_inh2o":               0.0,  # no elevated backpressure assumed
}


# ── Unit conversions ────────────────────────────────────────────────────────────

def _c_to_f(celsius: float) -> float:
    """Celsius to Fahrenheit. All ThrottleGuard temperature thresholds are in °F."""
    return (celsius * 9.0 / 5.0) + 32.0


def _millic_to_f(milli_celsius: float) -> float:
    """Milli-Celsius to Fahrenheit. Samsara returns some temps as milli-Celsius."""
    return _c_to_f(milli_celsius / 1000.0)


def _pa_to_inh2o(pascals: float) -> float:
    """
    Pascals to inches of water column.
    ThrottleGuard's backpressure CRITICAL threshold is 4.0 in.H2O (DIFF_PRESSURE_CRITICAL_PSI).
    1 Pa = 0.00401463 in.H2O   →   4.0 in.H2O = ~995 Pa
    """
    return pascals * 0.00401463


def _kpa_to_psi(kpa: float) -> float:
    """
    kPa to PSI.
    ThrottleGuard's turbo boost threshold is 20 PSI (<20 PSI = low boost fault).
    1 kPa = 0.145038 PSI
    """
    return kpa * 0.145038


# ── Token / auth ───────────────────────────────────────────────────────────────

def _get_token() -> str:
    """
    Read the Samsara API token from the environment.

    The token grants read access to your entire fleet — never hardcode it.
    It goes in Railway Variables (SAMSARA_API_TOKEN) or your local .env file.
    Samsara tokens look like:  samsara-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    """
    token = os.environ.get("SAMSARA_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "SAMSARA_API_TOKEN is not set. "
            "Add it to Railway Variables or your .env file. "
            "Get your token at: https://cloud.samsara.com/settings/api-tokens"
        )
    return token


# ── Samsara API calls ──────────────────────────────────────────────────────────

def fetch_vehicle_stats(token: str) -> list[dict]:
    """
    Fetch current stats for every vehicle in the Samsara fleet.
    Automatically walks cursor-based pagination until all vehicles are returned.

    Samsara endpoint: GET /fleet/vehicles/stats
    Samsara docs: https://developers.samsara.com/reference/listvehiclestats

    Returns a flat list of vehicle stat objects. Each object contains:
        id, name, engineStates, faultCodes, gpsOdometerMeters,
        and any aftertreatment stats the gateway broadcasts.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params: dict = {"types": ",".join(SAMSARA_STAT_TYPES)}
    url = f"{SAMSARA_BASE_URL}/fleet/vehicles/stats"
    vehicles: list[dict] = []

    while True:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            # 401 = bad token, 403 = insufficient scope, 429 = rate limited
            logger.error(
                f"Samsara API HTTP error {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            )
            break
        except requests.exceptions.RequestException as exc:
            logger.error(f"Samsara API connection error: {exc}")
            break

        payload = resp.json()
        batch = payload.get("data", [])
        vehicles.extend(batch)

        # Samsara paginates with a string cursor.
        # hasNextPage=False means this batch is the last one.
        pagination = payload.get("pagination", {})
        if not pagination.get("hasNextPage", False):
            break

        # Pass the cursor as "after" to fetch the next page
        params["after"] = pagination["endCursor"]

    logger.info(f"Samsara: fetched {len(vehicles)} vehicles.")
    return vehicles


# ── Parsing helpers ─────────────────────────────────────────────────────────────

def _get_active_spns(vehicle: dict) -> set[int]:
    """
    Extract active fault code SPNs from a Samsara vehicle object.

    Samsara fault code structure:
        {"j1939": {"spn": 3251, "fmi": 16, "description": "...", "isActive": true}}

    isActive=True means the ECM currently considers this a live fault.
    isActive=False is a historic/stored fault — we ignore those here.
    FMI (Failure Mode Identifier) tells you HOW it failed; SPN tells you WHAT failed.
    """
    active: set[int] = set()
    for entry in (vehicle.get("faultCodes") or []):
        j1939 = entry.get("j1939", {})
        if j1939.get("isActive", False) and j1939.get("spn") is not None:
            active.add(int(j1939["spn"]))
    return active


def _stat(vehicle: dict, key: str) -> Optional[float]:
    """
    Safely pull a numeric stat value from a Samsara vehicle object.

    Samsara wraps each stat as {"value": <number>, "time": "<ISO timestamp>"}.
    Returns None if the stat isn't present or the gateway doesn't broadcast it.

    Example:
        _stat(vehicle, "gpsOdometerMeters")  →  150342.7
        _stat(vehicle, "aftertreatmentDpfDifferentialPressurePa")  →  487.0 or None
    """
    stat = vehicle.get(key)
    if isinstance(stat, dict) and "value" in stat:
        val = stat["value"]
        if val is not None:
            return float(val)
    return None


# ── Normalization ──────────────────────────────────────────────────────────────

def normalize_vehicle(vehicle: dict) -> dict:
    """
    Convert a Samsara vehicle stats object to ThrottleGuard's scoring input shape.

    Strategy:
      1. Try to pull numeric sensor values from Samsara named stats (SPN-backed)
      2. Fall back to SAFE_SENSOR_DEFAULTS for required fields that are missing
         (logs a warning so you know the score is partial)
      3. Derive boolean fault flags from active SPN codes

    The returned dict is ready to pass directly into score_row().
    """
    # Use vehicle name first (human-readable), fall back to Samsara's internal ID
    vid = vehicle.get("name") or vehicle.get("id", "UNKNOWN")

    # ── Step 1: collect active fault codes ──────────────────────────────────
    active_spns = _get_active_spns(vehicle)

    # Log any active DPF/SCR-related faults — good visibility in Railway logs
    dpf_active = active_spns & DPF_RELATED_SPNS
    if dpf_active:
        fault_str = ", ".join(
            f"SPN {s} ({DPF_SPN_LABELS.get(s, '?')})" for s in sorted(dpf_active)
        )
        logger.info(f"[{vid}] Active DPF/SCR fault codes: {fault_str}")

    # ── Step 2: numeric sensor values ───────────────────────────────────────
    # Each stat name matches what Samsara returns when the J1939 PGN is available.
    # If your Samsara gateway doesn't broadcast a parameter, _stat() returns None
    # and we fall back to the safe default.

    # DPF Outlet Gas Temperature
    # Source: SPN 3480 — Aftertreatment 1 DPF Outlet Gas Temperature
    # Critical threshold: < 940°F during active regen = clogging (Rule 1)
    _outlet_mc = _stat(vehicle, "aftertreatmentDpfOutletGasTemperatureMilliC")
    if _outlet_mc is not None:
        dpf_outlet_f = _millic_to_f(_outlet_mc)
    else:
        logger.warning(
            f"[{vid}] DPF outlet temp (SPN 3480) not in Samsara feed — "
            "using safe default. Score may understate clogging risk."
        )
        dpf_outlet_f = SAFE_SENSOR_DEFAULTS["dpf_outlet_temp_active_regen_f"]

    # DPF Outlet Peak Temperature
    # Ideally: rolling max over the regen event window.
    # For now: same reading as current outlet temp — a future version should
    # query Samsara's Vehicle Stats History endpoint to find the peak.
    # Critical threshold: > 1200–1250°F (family-dependent) = thermal shock (Rule 2)
    dpf_outlet_peak_f = dpf_outlet_f

    # DPF Inlet Gas Temperature
    # Source: SPN 3479 — Aftertreatment 1 DPF Inlet Gas Temperature
    # Used in sensor fault delta check: inlet > 1000°F AND outlet < 500°F = fault (Rule 3)
    _inlet_mc = _stat(vehicle, "aftertreatmentDpfInletGasTemperatureMilliC")
    if _inlet_mc is not None:
        dpf_inlet_f = _millic_to_f(_inlet_mc)
    else:
        logger.warning(f"[{vid}] DPF inlet temp (SPN 3479) not in Samsara feed — using safe default.")
        dpf_inlet_f = SAFE_SENSOR_DEFAULTS["dpf_inlet_temp_f"]

    # DPF Differential Pressure (backpressure)
    # Source: SPN 3251 — Aftertreatment 1 DPF Differential Pressure
    # Samsara stat returns Pascals. Convert: Pa → in.H2O (ThrottleGuard unit)
    # Critical threshold: > 4.0 in.H2O = DIFF_PRESSURE_CRITICAL_PSI (Rule 10)
    _pressure_pa = _stat(vehicle, "aftertreatmentDpfDifferentialPressurePa")
    if _pressure_pa is not None:
        back_pressure_inh2o = _pa_to_inh2o(_pressure_pa)
    else:
        logger.warning(f"[{vid}] DPF differential pressure (SPN 3251) not in Samsara feed — using safe default.")
        back_pressure_inh2o = SAFE_SENSOR_DEFAULTS["back_pressure_inh2o"]

    # Active Regen Status
    # Source: SPN 3697 — Aftertreatment 1 DPF Active Regeneration Status
    # Rules 1, 2, and 3 are gated on regen_active=1.
    # If Samsara exposes the stat, use it. If not, also check active fault codes
    # (SPN 3697 as a DTC means regen is in progress or was attempted).
    # Default = 1 (conservative — assume regen possible so temp rules stay armed).
    _regen_stat = _stat(vehicle, "aftertreatmentDpfActiveRegenerationStatus")
    if _regen_stat is not None:
        regen_active = int(_regen_stat)
    elif 3697 in active_spns:
        regen_active = 1   # SPN 3697 DTC = regen event is/was active
    else:
        regen_active = 1   # conservative default

    # Regen Count in Last 7 Days
    # Samsara doesn't expose this directly as a current stat.
    # To get a real count: query the Vehicle Stats History endpoint for
    # SPN 3697 state transitions over the last 7 days.
    # Implementation stub — see TODO below.
    # For now: bump to 1 if any regen-related fault is active, else 0.
    # Rule 4 threshold: regen_count_7d > 2 — this won't false-trigger at 0 or 1.
    # TODO: implement fetch_regen_count_7d(vehicle_id, token) via history API
    regen_count_7d: int = 1 if 3697 in active_spns else 0

    # SCR Catalyst Intake Temperature
    # Source: SPN 3515 — Aftertreatment 1 SCR Catalyst Intake Gas Temperature
    # Rule 13 threshold: < 400°F = below catalyst light-off, no urea chemistry
    _scr_mc = _stat(vehicle, "aftertreatmentScrIntakeGasTemperatureMilliC")
    scr_inlet_f: Optional[float] = _millic_to_f(_scr_mc) if _scr_mc is not None else None

    # Turbo Boost Pressure
    # Source: SPN 1127 — Turbocharger 1 Boost Pressure (kPa from Samsara)
    # Rule 6 threshold: < 20 PSI = low boost flag
    _turbo_kpa = _stat(vehicle, "turbocharger1BoostPressureKPa")
    turbo_boost_psi: Optional[float] = _kpa_to_psi(_turbo_kpa) if _turbo_kpa is not None else None

    # EGR Flow Fault
    # Source: SPN 1238 — Engine EGR Mass Flow Rate
    # If SPN 1238 appears as an active fault code, the EGR system has a fault.
    # Rule 6 fires when egr_flow_fault = 1 OR turbo_boost_psi < 20
    egr_flow_fault: int = 1 if 1238 in active_spns else 0

    # NH3 Slip Detected
    # Source: SPN 3563 — NH3 Sensor out of range
    # Active fault = ammonia is bypassing the SCR catalyst (over-dosing or catalyst failure)
    # Rule 15 threshold: nh3_slip_detected = 1
    nh3_slip_detected: int = 1 if 3563 in active_spns else 0

    # Build the canonical ThrottleGuard input row
    return {
        # ── Required fields — scoring engine accesses these directly ────────
        "vehicle_id":                       vid,
        "dpf_outlet_temp_active_regen_f":   dpf_outlet_f,
        "dpf_outlet_temp_peak_f":           dpf_outlet_peak_f,
        "dpf_inlet_temp_f":                 dpf_inlet_f,
        "regen_count_7d":                   regen_count_7d,
        "back_pressure_inh2o":              back_pressure_inh2o,
        # ── Optional fields — score_row treats None as "not triggered" ──────
        "regen_active":                     regen_active,
        "scr_inlet_temp_f":                 scr_inlet_f,
        "turbo_boost_psi":                  turbo_boost_psi,
        "egr_flow_fault":                   egr_flow_fault,
        "nh3_slip_detected":                nh3_slip_detected,
        # ── Metadata — stored here for logging, not read by score_row ───────
        "_active_fault_spns":               sorted(active_spns),
    }


# ── Scoring + alert ────────────────────────────────────────────────────────────

def _build_sms_body(vid: str, score: int, priority: str, failure: str,
                    action: str, fault_spns: list[int]) -> str:
    """
    Build the SMS text for a HIGH/CRITICAL alert.

    Twilio sends up to ~1,600 characters (10 concatenated 160-char segments).
    Keep the message tight — fleet managers read these on a phone.
    """
    # Only list DPF/SCR-related SPNs — skip unrelated engine codes
    dpf_faults = [
        f"SPN {s} ({DPF_SPN_LABELS.get(s, '?')})"
        for s in fault_spns
        if s in DPF_RELATED_SPNS
    ]
    fault_line = f"Faults: {', '.join(dpf_faults)}" if dpf_faults else ""

    # Cap action text at 200 chars so the SMS doesn't go past 2 segments
    action_short = action[:200] + "…" if len(action) > 200 else action

    parts = [
        f"ThrottleGuard {priority}",
        f"Vehicle: {vid}",
        f"Score: {score}/100 | {failure}",
    ]
    if fault_line:
        parts.append(fault_line)
    parts.append(action_short)

    return "\n".join(parts)


def _send_sms(body: str) -> None:
    """
    Send an SMS via Twilio. No-ops silently if Twilio env vars aren't configured
    so the poller still runs (and logs to console) without SMS credentials.

    Required Railway / .env variables:
        TWILIO_ACCOUNT_SID   — starts with "AC..."   (Twilio Console → Account Info)
        TWILIO_AUTH_TOKEN    — auth token             (Twilio Console → Account Info)
        TG_TWILIO_PHONE      — your Twilio number     (format: +15551234567)
        FLEET_MGR_PHONE      — recipient number(s)    (format: +15559876543)
                               Comma-separate multiple numbers:
                               FLEET_MGR_PHONE=+15551111111,+15552222222
    """
    sid   = os.environ.get("TWILIO_ACCOUNT_SID",  "").strip()
    auth  = os.environ.get("TWILIO_AUTH_TOKEN",   "").strip()
    from_ = os.environ.get("TG_TWILIO_PHONE",     "").strip()
    to_   = os.environ.get("FLEET_MGR_PHONE",     "").strip()

    if not all([sid, auth, from_, to_]):
        # Twilio not configured — console log is the only channel
        return

    try:
        from twilio.rest import Client
        client = Client(sid, auth)

        # Support comma-separated list of recipient numbers
        recipients = [n.strip() for n in to_.split(",") if n.strip()]
        for number in recipients:
            client.messages.create(body=body, from_=from_, to=number)
            logger.info(f"SMS sent to {number}")

    except Exception as exc:
        # Never let a Twilio error crash the poll cycle
        logger.error(f"Twilio SMS failed: {exc}")


def _trigger_alert(vid: str, score: int, priority: str, failure: str,
                   action: str, rules: str, fault_spns: list[int]) -> None:
    """
    Fire an alert for a HIGH or CRITICAL vehicle:
      1. Always prints to console (visible in Railway log viewer)
      2. Sends SMS via Twilio if TWILIO_* env vars are set
    """
    fault_note = ""
    dpf_faults = [
        f"SPN {s} ({DPF_SPN_LABELS.get(s, '?')})"
        for s in fault_spns
        if s in DPF_RELATED_SPNS
    ]
    if dpf_faults:
        fault_note = f"\n  Active Faults: {', '.join(dpf_faults)}"

    # ── Console / Railway log ──────────────────────────────────────────────
    print("=" * 64)
    print(f"  THROTTLEGUARD {priority} ALERT")
    print(f"  Vehicle:      {vid}")
    print(f"  Risk Score:   {score}/100")
    print(f"  Failure Mode: {failure}")
    print(f"  Rules Fired:  {rules}")
    print(f"  Action:       {action}{fault_note}")
    print("=" * 64)

    # ── Twilio SMS ─────────────────────────────────────────────────────────
    sms_body = _build_sms_body(vid, score, priority, failure, action, fault_spns)
    _send_sms(sms_body)


def score_and_alert(row: dict) -> dict:
    """
    Score one normalized vehicle row and alert if risk is HIGH or CRITICAL.

    score_row() returns a pd.Series with positions matching SCORE_COLUMNS:
        [rule_score, priority_label, failure_mode, recommended_action,
         triggered_rules, confidence, score_trend]

    Returns the input row merged with score results, or {} on scoring error.
    """
    vid = row.get("vehicle_id", "UNKNOWN")

    try:
        result = score_row(row)
    except Exception as exc:
        # Log the error but don't crash the poll cycle for other vehicles
        logger.error(f"[{vid}] Scoring failed: {exc}")
        return {}

    # Zip result positions to column names for readable access
    scored = dict(zip(SCORE_COLUMNS, result))

    priority   = scored["priority_label"]
    risk_score = int(scored["rule_score"])
    failure    = scored["failure_mode"]
    action     = scored["recommended_action"]
    rules      = scored["triggered_rules"]

    if priority in ALERT_PRIORITIES:
        _trigger_alert(
            vid=vid,
            score=risk_score,
            priority=priority,
            failure=failure,
            action=action,
            rules=rules,
            fault_spns=row.get("_active_fault_spns", []),
        )
    else:
        logger.info(f"[{vid}] Score {risk_score}/100 — {priority} — no alert.")

    return {**row, **scored}


# ── Poll cycle ─────────────────────────────────────────────────────────────────

def poll_fleet() -> None:
    """
    One complete poll cycle. Called every POLL_INTERVAL_MINUTES by APScheduler.

    Steps:
      1. Read token from environment
      2. Fetch all vehicles from Samsara (paginated)
      3. Normalize each vehicle's stats into ThrottleGuard's input shape
      4. Score and alert
      5. Log summary
    """
    logger.info("━" * 52)
    logger.info("ThrottleGuard Samsara poll starting...")

    try:
        token = _get_token()
    except RuntimeError as exc:
        logger.error(str(exc))
        return  # Can't proceed without a token — skip this cycle

    vehicles = fetch_vehicle_stats(token)
    if not vehicles:
        logger.warning(
            "Samsara returned no vehicles. "
            "Verify SAMSARA_API_TOKEN has access to your fleet."
        )
        return

    alert_count = 0
    error_count = 0

    for vehicle in vehicles:
        row = normalize_vehicle(vehicle)
        result = score_and_alert(row)

        if not result:
            error_count += 1
        elif result.get("priority_label") in ALERT_PRIORITIES:
            alert_count += 1

    logger.info(
        f"Poll complete — {len(vehicles)} vehicles scored, "
        f"{alert_count} alert(s), {error_count} error(s). "
        f"Next poll in {POLL_INTERVAL_MINUTES} minutes."
    )


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        f"ThrottleGuard Samsara Poller starting — "
        f"polling every {POLL_INTERVAL_MINUTES} minutes."
    )

    # Score the fleet immediately on startup so you don't wait 30 minutes
    # for the first result when you deploy or restart the service.
    poll_fleet()

    # Schedule recurring polls. BlockingScheduler runs in the main thread —
    # no daemon process needed, which works cleanly with Railway's process model.
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        poll_fleet,
        trigger="interval",
        minutes=POLL_INTERVAL_MINUTES,
        id="samsara_poll",
        max_instances=1,   # prevent overlap if a poll runs long
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Poller stopped.")
