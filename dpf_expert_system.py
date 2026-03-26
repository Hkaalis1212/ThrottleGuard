"""
dpf_expert_system.py
====================
Rule-based expert system for DPF failure prediction.
Encodes 20 years of diesel technician knowledge as weighted rules.

Usage:
    from dpf_expert_system import calculate_expert_score

    result = calculate_expert_score({
        'vehicle_id': '247',
        'dpf_outlet_temp_active_regen_f': 890,
        'dpf_outlet_temp_peak_f': 1050,
        'dpf_inlet_temp_f': 940,
        'regen_count_7d': 4,
        'back_pressure_inh2o': 3.2,
        'driver_reported_frequent_regen': True,
    })
"""

from __future__ import annotations
from typing import Any

from throttleguard_engine_thresholds import (
    REGEN_OUTLET_CRITICAL_F,
    REGEN_TRANSITION_FLOOR_F,
    REGEN_HIGH_WARNING_F,
    REGEN_HIGH_CRITICAL_F,
    DIFF_PRESSURE_WARNING_PSI,
    DIFF_PRESSURE_CRITICAL_PSI,
    INCOMPLETE_REGEN_STREAK_THRESHOLD,
    ONE_BOX_FAMILIES,
    ONE_BOX_SERVICE_NOTE,
    NOX_CONVERSION_CRITICAL_PCT,
    NOX_CONVERSION_WARNING_PCT,
    SCR_INLET_TEMP_MIN_F,
    DEF_QUALITY_SPEC_PCT,
    DEF_QUALITY_MIN_PCT,
    DEF_QUALITY_MAX_PCT,
    DEF_QUALITY_CRITICAL_PCT,
)

# ── Constants ─────────────────────────────────────────────────────────────────

VERSION = "expert_system_v1"

# Required fields -validation will fail without these
REQUIRED_FIELDS = [
    "vehicle_id",
    "dpf_outlet_temp_active_regen_f",   # Critical: <940degF = clogging
    "dpf_outlet_temp_peak_f",           # Critical: >1190degF = thermal shock
    "dpf_inlet_temp_f",                 # Used in sensor-fault delta check
    "regen_count_7d",                   # Regen frequency over 7 days
    "back_pressure_inh2o",              # Exhaust backpressure (in.H2O)
]

# Optional fields -missing values are treated as "not triggered"
OPTIONAL_FIELDS = [
    # ── DPF fields ───────────────────────────────────────────────
    "driver_reported_frequent_regen",       # bool
    "mileage_since_last_dpf_cleaning",      # miles
    "oil_consumption_qt_per_1000mi",        # qts per 1,000 mi
    "turbo_boost_psi",                      # PSI
    "egr_flow_fault",                       # bool
    "avg_trip_distance_mi",                 # miles
    "idle_time_pct",                        # 0–100
    "def_quality_ppm",                      # contaminant ppm (existing)
    "def_doser_fault",                      # bool
    "water_in_fuel_detected",               # bool
    "fuel_filter_change_frequency_days",    # days between changes
    # ── SCR / aftertreatment fields ──────────────────────────────
    "nox_conversion_pct",                   # (1 - nox_downstream/nox_upstream)*100
    "scr_inlet_temp_f",                     # °F at SCR catalyst inlet
    "def_concentration_pct",               # urea % — spec is 32.5 ± 1.5%
    "nh3_slip_detected",                    # bool — ammonia bypassing SCR
    "regen_active",                         # J1939 PGN 64892 — 1=active regen
]

# Priority thresholds (applied AFTER capping score at 100)
PRIORITY_THRESHOLDS = {
    "CRITICAL": 60,
    "HIGH":     35,
    "MEDIUM":   15,
    "LOW":       0,
}

# Failure-mode priority order -highest wins when multiple are triggered
# NOX_BREAKTHROUGH above CLOGGING: EPA/regulatory consequence + derate risk
FAILURE_MODE_PRIORITY = [
    "SENSOR_FAULT",      # data integrity — can't trust readings
    "THERMAL_SHOCK",     # structural damage imminent
    "NOX_BREAKTHROUGH",  # EPA violation + derate risk
    "CLOGGING",          # DPF blocked
    "SCR_CATALYST",      # SCR degraded
    "DEF_QUALITY",       # DEF concentration out of spec
    "ASH_LOAD",          # maintenance overdue
    "OPERATIONAL",       # duty cycle / minor issues
    "NONE",
]


# ── Validation ────────────────────────────────────────────────────────────────

def validate_inputs(row: dict[str, Any]) -> list[str]:
    """
    Check that all required fields are present in the input dict.

    Returns a list of missing field names (empty list = valid).
    """
    return [f for f in REQUIRED_FIELDS if f not in row]


# ── Action text ───────────────────────────────────────────────────────────────

def get_action(score: int, priority: str, failure_mode: str, row: dict[str, Any]) -> str:
    """
    Return a specific, technician-grade action string based on the
    score, priority, and dominant failure mode.

    The action text is intentionally prescriptive — mirrors what an
    experienced diesel tech would tell a fleet manager.
    """
    vid    = row.get("vehicle_id", "UNKNOWN")
    family = row.get("engine_family", "")
    one_box = family in ONE_BOX_FAMILIES

    if failure_mode == "SENSOR_FAULT":
        inlet  = row.get("dpf_inlet_temp_f", "?")
        outlet = row.get("dpf_outlet_temp_active_regen_f", "?")
        return (
            f"STOP: Vehicle {vid} — suspect sensor failure or DPF breach. "
            f"Inlet {inlet}°F / Outlet {outlet}°F delta is physically impossible. "
            "Inspect DPF inlet/outlet temp sensors and wiring harness before next dispatch. "
            "Do NOT clear codes without physical inspection."
        )

    if failure_mode == "THERMAL_SHOCK":
        peak   = row.get("dpf_outlet_temp_peak_f", "?")
        action = (
            f"STOP: Vehicle {vid} — thermal damage likely. "
            f"Peak DPF temp {peak}°F exceeds substrate limit. "
            "Pull vehicle for DPF inspection — cracked substrate or runaway regen. "
            "Check fuel injector function and ECM regen logic before return to service."
        )
        if one_box:
            action += " Detroit 1-Box: thermal event may have damaged SCR catalyst in shared housing — inspect both."
        return action

    if failure_mode == "NOX_BREAKTHROUGH":
        return (
            f"STOP: Vehicle {vid} — NOx conversion below {NOX_CONVERSION_CRITICAL_PCT}%. "
            "EPA derate risk and possible roadside violation. "
            "Inspect SCR catalyst, DEF dosing system, and DEF quality before dispatch."
        )

    if failure_mode == "CLOGGING":
        outlet = row.get("dpf_outlet_temp_active_regen_f", "?")
        action = (
            f"STOP: Do not dispatch vehicle {vid}. "
            f"Incomplete burn detected (outlet {outlet}°F, threshold {REGEN_OUTLET_CRITICAL_F}°F). "
            "Schedule DPF service within 24-48 hours. "
            "Risk of forced derate or limp-mode on next trip."
        )
        if one_box:
            action += " Detroit 1-Box: verify SCR catalyst condition during same service visit."
        return action

    if failure_mode == "SCR_CATALYST":
        return (
            f"SCHEDULE: Vehicle {vid} — SCR catalyst efficiency degraded. "
            "Inspect DEF quality, doser function, and catalyst condition within 48-72 hours. "
            "Check NOx sensor calibration upstream and downstream."
        )

    if failure_mode == "DEF_QUALITY":
        return (
            f"ACTION: Vehicle {vid} — DEF concentration out of spec. "
            "Replace DEF fluid immediately. Inspect for water or contamination in DEF tank. "
            "Flush and refill with certified ISO 22241 fluid before next dispatch."
        )

    if failure_mode == "ASH_LOAD":
        miles = row.get("mileage_since_last_dpf_cleaning", "?")
        return (
            f"WARNING: Vehicle {vid} — excessive ash accumulation. "
            f"DPF last cleaned {miles} miles ago with elevated oil consumption. "
            "Schedule DPF cleaning/replacement within 1-2 weeks. "
            "Check for oil leaks or worn piston rings contributing to ash buildup."
        )

    # OPERATIONAL / general
    if priority == "HIGH":
        return (
            f"MONITOR: Vehicle {vid} — multiple operational risk factors active. "
            "Inspect DPF, DEF system, and turbo/EGR within 1 week. "
            "Assign to shorter routes until inspection is complete."
        )

    if priority == "MEDIUM":
        return (
            f"SCHEDULE: Vehicle {vid} — duty-cycle or fuel-quality issues detected. "
            "Review driver routes and idle habits. "
            "Service DEF/fuel system at next scheduled maintenance interval."
        )

    return (
        f"OK: Vehicle {vid} — no significant aftertreatment risk detected. "
        "Continue standard maintenance schedule."
    )


# ── Core scoring engine ───────────────────────────────────────────────────────

def calculate_expert_score(row: dict[str, Any]) -> dict[str, Any]:
    """
    Apply all weighted DPF rules to a telematics/service data dictionary
    and return a full risk assessment.

    Parameters
    ----------
    row : dict
        Must contain all REQUIRED_FIELDS.  OPTIONAL_FIELDS are safe to omit.

    Returns
    -------
    dict with keys:
        vehicle_id, risk_score, priority, failure_mode,
        action, reasons, predicted_by
    """
    # ── 1. Validate inputs ────────────────────────────────────────────────────
    missing = validate_inputs(row)
    if missing:
        return {
            "vehicle_id":   row.get("vehicle_id", "UNKNOWN"),
            "risk_score":   None,
            "priority":     "ERROR",
            "failure_mode": "NONE",
            "action":       f"Cannot assess -missing required fields: {', '.join(missing)}",
            "reasons":      "VALIDATION_ERROR",
            "predicted_by": VERSION,
        }

    # ── 2. Extract required sensor readings ───────────────────────────────────
    vid          = row["vehicle_id"]
    outlet_regen = float(row["dpf_outlet_temp_active_regen_f"])
    peak_temp    = float(row["dpf_outlet_temp_peak_f"])
    inlet_temp   = float(row["dpf_inlet_temp_f"])
    regen_7d     = float(row["regen_count_7d"])
    backpressure = float(row["back_pressure_inh2o"])

    # ── 3. Extract optional readings (default to safe values) ─────────────────
    driver_freq_regen    = bool(row.get("driver_reported_frequent_regen", False))
    dpf_mileage          = row.get("mileage_since_last_dpf_cleaning")
    oil_consumption      = row.get("oil_consumption_qt_per_1000mi")
    turbo_boost          = row.get("turbo_boost_psi")
    egr_fault            = bool(row.get("egr_flow_fault", False))
    avg_trip             = row.get("avg_trip_distance_mi")
    idle_pct             = row.get("idle_time_pct")
    def_quality          = row.get("def_quality_ppm")
    def_doser_fault      = bool(row.get("def_doser_fault", False))
    water_in_fuel        = bool(row.get("water_in_fuel_detected", False))
    fuel_filter_days     = row.get("fuel_filter_change_frequency_days")

    # regen_active: 1 = active regen in progress (J1939 PGN 64892)
    #               0 = normal operation — temp readings are normal exhaust, NOT regen temps
    # If not present in data, assume active (conservative — score the reading)
    regen_active = bool(row.get("regen_active", 1))

    # SCR / aftertreatment fields
    # nox_conversion_pct: default 100 (assume healthy when sensor not present)
    nox_conv     = float(row.get("nox_conversion_pct", 100))
    scr_inlet    = row.get("scr_inlet_temp_f")
    def_conc     = row.get("def_concentration_pct")
    nh3_slip     = bool(row.get("nh3_slip_detected", False))
    family       = row.get("engine_family", "")

    # ── 4. Apply rules ────────────────────────────────────────────────────────
    score         = 0
    reasons       = []
    failure_modes = []   # collect all triggered modes; highest-priority wins

    # ── CRITICAL RULES ────────────────────────────────────────────────────────

    # Rule 1 -Low outlet temp during active regen → incomplete burn / clogging
    # GATED: only fires when regen_active=1. Normal exhaust temps (400-700°F)
    # during cruise are NOT a DPF problem and must not trigger this rule.
    if regen_active and outlet_regen < REGEN_OUTLET_CRITICAL_F:
        score += 60
        failure_modes.append("CLOGGING")
        reasons.append(
            f"DPF outlet temp {outlet_regen:.0f}degF during regen (threshold {REGEN_OUTLET_CRITICAL_F}degF) -incomplete burn"
        )

    # Rule 2 -Peak temp too high → thermal shock / cracked substrate
    # GATED: peak temp reading is only meaningful during active regen
    if regen_active and peak_temp > 1190:
        score += 50
        failure_modes.append("THERMAL_SHOCK")
        reasons.append(
            f"DPF peak temp {peak_temp:.0f}degF exceeds 1190degF limit -thermal damage risk"
        )

    # Rule 3 -Impossible temp delta → sensor fault or DPF breach
    # GATED: delta check only valid when regen is active and temps should be elevated
    if regen_active and outlet_regen < 500 and inlet_temp > 1000:
        score += 70
        failure_modes.append("SENSOR_FAULT")
        reasons.append(
            f"Temp delta anomaly: inlet {inlet_temp:.0f}degF / outlet {outlet_regen:.0f}degF -"
            "sensor fault or DPF breach"
        )

    # ── HIGH RULES ────────────────────────────────────────────────────────────

    # Rule 4 -Frequent regen (driver-reported OR telematic count)
    if driver_freq_regen or regen_7d > 2:
        score += 30
        failure_modes.append("OPERATIONAL")
        detail = []
        if driver_freq_regen:
            detail.append("driver reports frequent regen (>2x/week)")
        if regen_7d > 2:
            detail.append(f"telematic regen count {regen_7d:.0f} in 7 days")
        reasons.append("High regen frequency -" + " and ".join(detail))

    # Rule 5 -High ash load (mileage + oil consumption combined)
    if dpf_mileage is not None and oil_consumption is not None:
        if float(dpf_mileage) > 300_000 and float(oil_consumption) > 0.5:
            score += 25
            failure_modes.append("ASH_LOAD")
            reasons.append(
                f"High ash load: {float(dpf_mileage):,.0f} miles since last DPF clean, "
                f"oil consumption {float(oil_consumption):.2f} qt/1000mi"
            )

    # Rule 6 -Turbo / EGR problems
    turbo_low = turbo_boost is not None and float(turbo_boost) < 20
    if turbo_low or egr_fault:
        score += 25
        failure_modes.append("OPERATIONAL")
        detail = []
        if turbo_low:
            detail.append(f"turbo boost {float(turbo_boost):.1f} PSI (threshold 20 PSI)")
        if egr_fault:
            detail.append("EGR flow fault active")
        reasons.append("Turbo/EGR issue -" + "; ".join(detail))

    # ── MEDIUM RULES ──────────────────────────────────────────────────────────

    # Rule 7 -Short-trip / high-idle duty cycle (passive regen never completes)
    if avg_trip is not None and idle_pct is not None:
        if float(avg_trip) < 15 and float(idle_pct) > 35:
            score += 15
            failure_modes.append("OPERATIONAL")
            reasons.append(
                f"Short-trip duty cycle: avg trip {float(avg_trip):.1f} mi, "
                f"idle time {float(idle_pct):.0f}% -DPF unable to self-clean"
            )

    # Rule 8 -DEF quality / doser fault
    def_contaminated = def_quality is not None and float(def_quality) > 50
    if def_contaminated or def_doser_fault:
        score += 15
        failure_modes.append("OPERATIONAL")
        detail = []
        if def_contaminated:
            detail.append(f"DEF contamination {float(def_quality):.0f} ppm (limit 50 ppm)")
        if def_doser_fault:
            detail.append("DEF doser fault active")
        reasons.append("DEF system issue -" + "; ".join(detail))

    # Rule 9 -Fuel quality (water or frequent filter changes)
    fuel_filter_early = (
        fuel_filter_days is not None and float(fuel_filter_days) < 45
    )
    if water_in_fuel or fuel_filter_early:
        score += 10
        failure_modes.append("OPERATIONAL")
        detail = []
        if water_in_fuel:
            detail.append("water-in-fuel detected")
        if fuel_filter_early:
            detail.append(
                f"fuel filter change interval {float(fuel_filter_days):.0f} days (normal ≥45 days)"
            )
        reasons.append("Fuel quality concern -" + "; ".join(detail))

    # Rule 10 — Elevated back pressure
    if backpressure > DIFF_PRESSURE_CRITICAL_PSI:
        score += 10
        failure_modes.append("CLOGGING")
        reasons.append(
            f"Elevated back pressure {backpressure:.1f} in.H2O "
            f"(threshold {DIFF_PRESSURE_CRITICAL_PSI})"
        )

    # ── SCR / Aftertreatment rules ────────────────────────────────────────────
    # DPF and SCR are one aftertreatment system. Incomplete DPF regens push HC
    # through the system and poison the SCR catalyst over time. On Detroit 1-Box,
    # DPF and SCR share a single housing — a thermal event damages both at once.

    # Rule 11 — NOx conversion CRITICAL (<50%) — EPA derate risk
    if nox_conv < NOX_CONVERSION_CRITICAL_PCT:
        score += 40
        failure_modes.append("NOX_BREAKTHROUGH")
        reasons.append(
            f"NOx conversion {nox_conv:.0f}% — below {NOX_CONVERSION_CRITICAL_PCT}% threshold. "
            "EPA derate risk. SCR catalyst may be poisoned or failing."
        )

    # Rule 12 — NOx conversion WARNING (50–70%) — catalyst degrading
    elif nox_conv < NOX_CONVERSION_WARNING_PCT:
        score += 20
        failure_modes.append("SCR_CATALYST")
        reasons.append(
            f"NOx conversion {nox_conv:.0f}% — degraded "
            f"(warning below {NOX_CONVERSION_WARNING_PCT}%). "
            "Inspect SCR catalyst and DEF system."
        )

    # Rule 13 — SCR inlet temp below catalyst light-off
    # Below 400°F the urea chemistry doesn't activate — NOx passes through unreacted
    if scr_inlet is not None and float(scr_inlet) < SCR_INLET_TEMP_MIN_F:
        score += 15
        failure_modes.append("SCR_CATALYST")
        reasons.append(
            f"SCR inlet temp {float(scr_inlet):.0f}°F below catalyst light-off "
            f"({SCR_INLET_TEMP_MIN_F}°F). Urea not converting — NOx bypass risk."
        )

    # Rule 14 — DEF concentration out of spec
    # ISO 22241 spec: 32.5% ± 1.5% (31–34%). Below 20% = effectively water.
    if def_conc is not None:
        def_conc_f = float(def_conc)
        if def_conc_f < DEF_QUALITY_CRITICAL_PCT or def_conc_f > 40:
            score += 25
            failure_modes.append("DEF_QUALITY")
            reasons.append(
                f"DEF concentration {def_conc_f:.1f}% — critically out of spec "
                f"(spec 31–34%). Possible water contamination. Replace immediately."
            )
        elif def_conc_f < DEF_QUALITY_MIN_PCT or def_conc_f > DEF_QUALITY_MAX_PCT:
            score += 10
            failure_modes.append("DEF_QUALITY")
            reasons.append(
                f"DEF concentration {def_conc_f:.1f}% — outside spec range "
                f"({DEF_QUALITY_MIN_PCT}–{DEF_QUALITY_MAX_PCT}%). "
                "Verify fluid source and refill."
            )

    # Rule 15 — NH3 slip: excess ammonia passing through SCR unreacted
    if nh3_slip:
        score += 10
        failure_modes.append("SCR_CATALYST")
        reasons.append(
            "NH3 slip detected — ammonia bypassing SCR without reacting with NOx. "
            "Check DEF dosing rate and catalyst condition."
        )

    # Rule 16 — Compound aftertreatment failure (DPF + SCR both flagged)
    # Both down simultaneously = always worse than either alone.
    # Detroit 1-Box gets a higher penalty — shared housing means both fail together.
    dpf_flagged = any(m in failure_modes for m in ["CLOGGING", "THERMAL_SHOCK"])
    scr_flagged = any(m in failure_modes for m in ["NOX_BREAKTHROUGH", "SCR_CATALYST", "DEF_QUALITY"])
    if dpf_flagged and scr_flagged:
        bonus = 20 if family in ONE_BOX_FAMILIES else 15
        score += bonus
        note = "Detroit 1-Box: shared housing — both systems compromised." if family in ONE_BOX_FAMILIES else ""
        reasons.append(
            f"Compound failure: DPF and SCR both flagged — full aftertreatment system affected. {note}".strip()
        )

    # ── 5. Finalise score and priority ────────────────────────────────────────
    risk_score = min(score, 100)

    priority = "LOW"
    for p, threshold in PRIORITY_THRESHOLDS.items():
        if risk_score >= threshold:
            priority = p
            break

    # ── 6. Dominant failure mode (highest priority in triggered list) ─────────
    failure_mode = "NONE"
    for fm in FAILURE_MODE_PRIORITY:
        if fm in failure_modes:
            failure_mode = fm
            break

    # ── 7. Action text ────────────────────────────────────────────────────────
    action = get_action(risk_score, priority, failure_mode, row)

    return {
        "vehicle_id":   vid,
        "risk_score":   risk_score,
        "priority":     priority,
        "failure_mode": failure_mode,
        "action":       action,
        "reasons":      "; ".join(reasons) if reasons else "No risk factors triggered",
        "predicted_by": VERSION,
    }


# ── Test cases ────────────────────────────────────────────────────────────────

def _run_tests():
    """
    Four representative failure scenarios that exercise every rule tier.
    Prints a formatted summary to stdout.
    """

    test_cases = [
        # ── Test 1: Active clogging + frequent regen (matches sample output) ──
        {
            "label": "Test 1 -Clogging (incomplete burn + frequent regen)",
            "data": {
                "vehicle_id": "247",
                "dpf_outlet_temp_active_regen_f": 890,   # Rule 1 -CRITICAL
                "dpf_outlet_temp_peak_f": 1050,
                "dpf_inlet_temp_f": 940,
                "regen_count_7d": 4,                     # Rule 4 -HIGH
                "back_pressure_inh2o": 3.2,
                "driver_reported_frequent_regen": True,  # Rule 4 -HIGH
            },
        },

        # ── Test 2: Thermal shock + ash overload ──────────────────────────────
        {
            "label": "Test 2 -Thermal shock + ash load",
            "data": {
                "vehicle_id": "118",
                "dpf_outlet_temp_active_regen_f": 960,
                "dpf_outlet_temp_peak_f": 1250,          # Rule 2 -CRITICAL
                "dpf_inlet_temp_f": 1100,
                "regen_count_7d": 1,
                "back_pressure_inh2o": 6.1,              # Rule 10 -MEDIUM
                "mileage_since_last_dpf_cleaning": 340000,  # Rule 5 -HIGH
                "oil_consumption_qt_per_1000mi": 0.8,
            },
        },

        # ── Test 3: Sensor fault (impossible temp delta) ──────────────────────
        {
            "label": "Test 3 -Sensor fault / DPF breach",
            "data": {
                "vehicle_id": "502",
                "dpf_outlet_temp_active_regen_f": 420,   # Rule 1 AND Rule 3
                "dpf_outlet_temp_peak_f": 1080,
                "dpf_inlet_temp_f": 1150,                # Rule 3 -CRITICAL (70 pts)
                "regen_count_7d": 2,
                "back_pressure_inh2o": 4.5,
                "egr_flow_fault": True,                  # Rule 6 -HIGH
                "turbo_boost_psi": 16.0,                 # Rule 6 -HIGH
            },
        },

        # ── Test 4: Low-risk operational issues only ──────────────────────────
        {
            "label": "Test 4 -Low-risk / operational (short trips + DEF issue)",
            "data": {
                "vehicle_id": "031",
                "dpf_outlet_temp_active_regen_f": 980,
                "dpf_outlet_temp_peak_f": 1020,
                "dpf_inlet_temp_f": 890,
                "regen_count_7d": 1,
                "back_pressure_inh2o": 2.8,
                "avg_trip_distance_mi": 11,              # Rule 7 -MEDIUM
                "idle_time_pct": 42,                     # Rule 7 -MEDIUM
                "def_quality_ppm": 75,                   # Rule 8 -MEDIUM
                "water_in_fuel_detected": False,
            },
        },
    ]

    for case in test_cases:
        result = calculate_expert_score(case["data"])
        print(f"\n{'='*65}")
        print(f"  {case['label']}")
        print(f"{'='*65}")
        print(f"  Vehicle       : {result['vehicle_id']}")
        print(f"  Risk Score    : {result['risk_score']}/100")
        print(f"  Priority      : {result['priority']}")
        print(f"  Failure Mode  : {result['failure_mode']}")
        print(f"  Action        : {result['action']}")
        print(f"  Reasons       : {result['reasons']}")
        print(f"  Predicted by  : {result['predicted_by']}")


if __name__ == "__main__":
    _run_tests()
