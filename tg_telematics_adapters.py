"""
tg_telematics_adapters.py
=========================
Shared normalization layer for telematics provider integrations.

ThrottleGuard's scoring engine (scoring_engine.score_row / dpf_expert_system)
takes ONE canonical row shape — the J1939-derived fields documented in
CLAUDE.md's "CSV Input Columns" and produced today by
throttleguard_samsara_poller.normalize_vehicle() for Samsara.

Every telematics provider (Motive, Samsara, Geotab, ...) is ultimately reporting
the same SAE J1939 parameters (SPN/FMI) off the same trucks — so the SPN →
canonical-field knowledge below is shared domain knowledge, not Motive-specific
plumbing. Adding a new provider should mean: map its wire format onto these SPN
tables and write one normalize_<provider>_*() function — not re-deriving which
SPN means what.

ADAPTER CONVENTION
------------------
A provider adapter is a function:

    normalize_<provider>_<event-or-batch>(payload: dict) -> dict | None

that converts that provider's payload into a (possibly partial) canonical row.
- Returns None when the payload carries nothing ThrottleGuard tracks.
- Event-driven providers (Motive webhooks) can usually only report ONE changed
  signal at a time, so most canonical fields will be missing — callers merge
  partial rows into whatever's already known about that vehicle before scoring.
- Keys prefixed with "_" are metadata for logging/merging, not scoring engine
  inputs (mirrors the "_active_fault_spns" convention in the Samsara poller).

KNOWN SPN LABEL DISCREPANCY
---------------------------
SPN 3226 is labeled "NOx Sensor (upstream)" here (matches the SAE J1939
"Aftertreatment 1 Outlet NOx" definition) but throttleguard_samsara_poller.py's
DPF_SPN_LABELS lists it as "Aftertreatment Outlet Temperature" — those can't
both be right. Worth a second look with real Motive/Samsara payloads in hand;
not changed here since the Samsara poller is live and this isn't its bug to fix
in isolation.
"""

import logging

log = logging.getLogger(__name__)


# ── SPNs whose canonical field is itself a boolean flag (0/1) ─────────────────
# A "Fault Code Opened" / "Fault Code Closed" webhook maps onto these with no
# ambiguity: the DTC opening *is* the canonical signal.
SPN_FAULT_FLAG_MAP: dict[int, str] = {
    1238: "egr_flow_fault",      # EGR Mass Flow Rate — fault active
    3563: "nh3_slip_detected",   # NH3 Slip Sensor — ammonia bypassing SCR
    1761: "def_doser_fault",     # DEF Tank Level / doser system fault
}

# ── SPNs whose canonical counterpart is a continuous reading (°F, in.H2O, %) ──
# A fault-code webhook only tells us "this system just tripped a DTC," not the
# underlying number — so we can't populate the canonical field from this event
# type alone. Tracked here so the webhook handler can flag "look closer at
# <field> on this vehicle" without fabricating a reading. A numeric-stats feed
# (poll-based, like Samsara's) would be the source for the actual values.
SPN_NUMERIC_FIELD_HINT: dict[int, str] = {
    3251: "back_pressure_inh2o",            # DPF Differential Pressure
    3479: "dpf_inlet_temp_f",               # DPF Inlet Gas Temperature
    3480: "dpf_outlet_temp_active_regen_f", # DPF Outlet Gas Temperature
    3697: "regen_active",                   # DPF Active Regeneration Status
    3515: "scr_inlet_temp_f",               # SCR Catalyst Intake Gas Temperature
    1127: "turbo_boost_psi",                # Turbocharger 1 Boost Pressure
    4334: "def_concentration_pct",          # DEF Concentration
}

# ── SPNs that show up in aftertreatment fault streams but have no home in the
#    canonical row — either the rule engine doesn't model that exact metric, or
#    computing the canonical value needs more than one SPN (e.g. nox_conversion_pct
#    is derived from a matched upstream + downstream NOx pair, not reported directly).
# Logged for visibility so nothing silently vanishes; not scored on.
SPN_TRACKED_NO_CANONICAL_FIELD: dict[int, str] = {
    3700: "DPF Soot Load — rule engine reasons from temps/pressure/regen frequency instead of a direct soot % field",
    3936: "DPF Ash Load — same; no canonical ash-load field (ash vs. soot is inferred from the backpressure+temp pattern, see CLAUDE.md domain rules)",
    4094: "SCR Catalyst Efficiency — closest canonical concept is nox_conversion_pct, but that's computed from a paired upstream/downstream NOx reading, not reported as one number",
    3226: "NOx Sensor (upstream, pre-SCR) — feeds nox_conversion_pct once paired with its downstream counterpart",
    3227: "NOx Sensor (downstream, post-SCR) — feeds nox_conversion_pct once paired with its upstream counterpart",
}


# ── Motive adapter ─────────────────────────────────────────────────────────────

def normalize_motive_fault_event(payload: dict) -> dict | None:
    """
    Convert a Motive "Fault Code Opened/Closed" webhook into a partial canonical row.

    Returns None if the payload is missing what we need, or the SPN isn't one
    ThrottleGuard tracks at all. Otherwise returns a dict with:
      - vehicle_id            (always, when present)
      - <canonical_field>     populated ONLY for SPNs in SPN_FAULT_FLAG_MAP
      - _needs_numeric_lookup the canonical field name, for SPNs in SPN_NUMERIC_FIELD_HINT
      - _source / _spn / _fmi / _fault_open   metadata for logging/merging
    """
    vehicle_id = payload.get("vehicle_id") or payload.get("asset_id")
    spn        = payload.get("spn")
    if vehicle_id is None or spn is None:
        return None

    try:
        spn = int(spn)
    except (TypeError, ValueError):
        return None

    status    = str(payload.get("status") or payload.get("event_type") or "").lower()
    is_open   = "open" in status or "active" in status

    row: dict = {
        "vehicle_id":  str(vehicle_id),
        "_source":     "motive",
        "_spn":        spn,
        "_fmi":        payload.get("fmi"),
        "_fault_open": is_open,
    }

    if spn in SPN_FAULT_FLAG_MAP:
        row[SPN_FAULT_FLAG_MAP[spn]] = 1 if is_open else 0
        return row

    if spn in SPN_NUMERIC_FIELD_HINT:
        field = SPN_NUMERIC_FIELD_HINT[spn]
        row["_needs_numeric_lookup"] = field
        log.info(f"[Motive] SPN {spn} fault {'opened' if is_open else 'closed'} on "
                 f"{vehicle_id} — relates to '{field}', but the actual reading needs a numeric-stats source")
        return row

    if spn in SPN_TRACKED_NO_CANONICAL_FIELD:
        log.info(f"[Motive] SPN {spn} tracked but unscorable — {SPN_TRACKED_NO_CANONICAL_FIELD[spn]}")
        return row

    # Not an SPN ThrottleGuard cares about — not a DPF/SCR signal
    return None


def normalize_motive_engine_event(payload: dict) -> dict | None:
    """
    Convert a Motive "Engine On/Off" webhook into a canonical-shaped record.

    Feeds CLAUDE.md Rule 7 (short-haul + high idle = fastest DPF clogging
    combination) — but idle_time_pct is a rolling percentage, which a single
    on/off transition can't compute alone. This normalizes the event into the
    same shape an idle-hour aggregator would consume from any provider; the
    aggregation itself is future work (TODO in api.py).
    """
    vehicle_id = payload.get("vehicle_id")
    if not vehicle_id:
        return None

    state = str(payload.get("engine_state") or payload.get("status") or "").lower()
    if "on" in state:
        engine_state = "on"
    elif "off" in state:
        engine_state = "off"
    else:
        engine_state = state or "unknown"

    return {
        "vehicle_id":     str(vehicle_id),
        "_source":        "motive",
        "_event":         "engine_state_change",
        "_engine_state":  engine_state,
        "_timestamp":     payload.get("timestamp"),
    }


def normalize_motive_vehicle_event(payload: dict) -> dict | None:
    """
    Convert a Motive "Vehicle Upserted" webhook into a canonical-shaped record.

    Just enough to onboard the truck (match vehicle_id across providers) —
    sensor fields are intentionally absent until the truck reports real data.
    """
    vehicle_id = payload.get("id")
    if not vehicle_id:
        return None

    return {
        "vehicle_id": str(vehicle_id),
        "_source":    "motive",
        "_event":     "vehicle_upserted",
        "_name":      payload.get("name"),
        "_vin":       payload.get("vin"),
    }
