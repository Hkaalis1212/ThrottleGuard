"""
ThrottleGuard Scoring Engine
---------------------------
Applies rule-based expert logic to fleet data and outputs:
- rule_score
- priority_label
- failure_mode
- recommended_action
- triggered_rules      (comma-separated list of what fired)
- confidence           (HIGH / MEDIUM / LOW — based on rule count)
- score_trend          (↑ Worsening / ↓ Improving / → Stable)
"""

import pandas as pd

from throttleguard_engine_thresholds import (
    REGEN_OUTLET_CRITICAL_F,
    REGEN_HIGH_CRITICAL_F,
    DIFF_PRESSURE_CRITICAL_PSI,
    ONE_BOX_FAMILIES,
    NOX_CONVERSION_CRITICAL_PCT,
    NOX_CONVERSION_WARNING_PCT,
    SCR_INLET_TEMP_MIN_F,
    DEF_QUALITY_SPEC_PCT,
    DEF_QUALITY_MIN_PCT,
    DEF_QUALITY_MAX_PCT,
    DEF_QUALITY_CRITICAL_PCT,
)

# Priority thresholds
PRIORITY_MAP = {
    (60, 100): "CRITICAL",
    (35, 59):  "HIGH",
    (15, 34):  "MEDIUM",
    (0,  14):  "LOW",
}

# Failure mode hierarchy — first match wins
# NOX_BREAKTHROUGH above CLOGGING: EPA/regulatory consequence + derate risk
FAILURE_PRIORITY = [
    "SENSOR_FAULT",
    "THERMAL_SHOCK",
    "NOX_BREAKTHROUGH",
    "CLOGGING",
    "SCR_CATALYST",
    "DEF_QUALITY",
    "ASH_LOAD",
    "OPERATIONAL",
]

# Human-readable rule labels (keyed to trigger strings)
RULE_LABELS = {
    # ── DPF rules ──────────────────────────────────────────────────
    "CLOGGING_LOW_TEMP":    f"Low regen temp (<{REGEN_OUTLET_CRITICAL_F}°F)",
    "CLOGGING_FREQ":        "Regen frequency high",
    "CLOGGING_BACKPRES":    "Backpressure elevated",
    "THERMAL_SHOCK":        "Peak temp exceeded limit",
    "SENSOR_FAULT":         "Impossible temp delta — sensor fault",
    "ASH_LOAD":             "Ash load / oil consumption elevated",
    "TURBO_EGR":            "Turbo boost low or EGR fault",
    "DUTY_CYCLE":           "Short trips + high idle",
    "DEF_SYSTEM":           "DEF contamination or doser fault",
    "FUEL_QUALITY":         "Water in fuel or filter overdue",
    # ── SCR / aftertreatment rules ─────────────────────────────────
    "NOX_CRITICAL":         f"NOx conversion critical (<{NOX_CONVERSION_CRITICAL_PCT}%) — EPA derate risk",
    "NOX_WARN":             f"NOx conversion degraded ({NOX_CONVERSION_WARNING_PCT}–{NOX_CONVERSION_CRITICAL_PCT}%)",
    "SCR_COLD":             f"SCR inlet temp below catalyst light-off (<{SCR_INLET_TEMP_MIN_F}°F)",
    "DEF_CONC_CRITICAL":    "DEF concentration critically out of spec — possible water contamination",
    "DEF_CONC_WARN":        "DEF concentration outside 31–34% urea spec",
    "NH3_SLIP":             "NH3 slip detected — excess ammonia bypassing SCR",
    "COMPOUND_ATS":         "Compound failure: DPF + SCR both flagged — full aftertreatment system",
}


def get_priority(score):
    for (low, high), label in PRIORITY_MAP.items():
        if low <= score <= high:
            return label
    return "LOW"


def get_confidence(trigger_count):
    if trigger_count >= 3:
        return "HIGH"
    elif trigger_count == 2:
        return "MEDIUM"
    return "LOW"


def get_trend(current_score, previous_score):
    if previous_score is None:
        return "→ Stable"
    if current_score > previous_score:
        return "↑ Worsening"
    elif current_score < previous_score:
        return "↓ Improving"
    return "→ Stable"


def determine_failure_mode(triggers):
    # triggers is a list of raw mode keys (e.g. "CLOGGING", "SENSOR_FAULT")
    for mode in FAILURE_PRIORITY:
        if mode in triggers:
            return mode
    return "OPERATIONAL"


def generate_action(mode, row):
    family = row.get('engine_family', '')
    one_box = family in ONE_BOX_FAMILIES

    if mode == "SENSOR_FAULT":
        return (
            f"STOP. Inlet {row['dpf_inlet_temp_f']}°F / "
            f"Outlet {row['dpf_outlet_temp_active_regen_f']}°F impossible delta. "
            "Inspect DPF sensors before dispatch."
        )
    elif mode == "THERMAL_SHOCK":
        action = "STOP. Peak temp exceeded safe limits. Inspect DPF for substrate damage."
        if one_box:
            action += " Detroit 1-Box: thermal event may have damaged SCR catalyst in shared housing — inspect both systems."
        return action
    elif mode == "NOX_BREAKTHROUGH":
        return (
            "STOP. NOx conversion below 50% — EPA derate risk and possible roadside violation. "
            "Inspect SCR catalyst, DEF dosing system, and DEF quality before dispatch."
        )
    elif mode == "CLOGGING":
        action = "STOP. Do not dispatch. Incomplete regen detected. Schedule DPF service within 24-48 hours."
        if one_box:
            action += " Detroit 1-Box: verify SCR catalyst condition during same service visit."
        return action
    elif mode == "SCR_CATALYST":
        return (
            "Schedule SCR inspection within 48-72 hours. "
            "NOx efficiency degraded — check DEF quality, doser function, and catalyst condition."
        )
    elif mode == "DEF_QUALITY":
        return (
            "Replace DEF fluid immediately. Concentration out of spec. "
            "Inspect for water or contamination in DEF tank. Flush and refill with certified fluid."
        )
    elif mode == "ASH_LOAD":
        return "Schedule DPF cleaning within 1-2 weeks. Check oil consumption logs."
    else:
        return "Monitor. Operational conditions may be contributing to DPF load."


def score_row(row, previous_score=None):
    """
    Score a single row dict/Series.

    Args:
        row:            dict or pd.Series of sensor readings
        previous_score: last known score for this truck (for trend calc), or None

    Returns:
        pd.Series with columns:
            rule_score, priority_label, failure_mode, recommended_action,
            triggered_rules, confidence, score_trend
    """
    score = 0
    failure_triggers = []   # failure mode keys for hierarchy
    rule_labels = []        # human-readable labels for display

    # regen_active gate — temp rules only fire during an active regen event
    # Source: J1939 PGN 64892. If not present, assume active (conservative).
    # Normal exhaust temps (400-700°F) during cruise are NOT DPF problems.
    regen_active = bool(row.get('regen_active', 1))

    # Rule 1: Low outlet temp during regen — GATED on regen_active
    if regen_active and row['dpf_outlet_temp_active_regen_f'] < REGEN_OUTLET_CRITICAL_F:
        score += 60
        failure_triggers.append("CLOGGING")
        rule_labels.append(RULE_LABELS["CLOGGING_LOW_TEMP"])

    # Rule 2: Peak temp too high — GATED on regen_active
    family = row.get('engine_family', 'DETROIT')
    peak_critical = REGEN_HIGH_CRITICAL_F.get(family, REGEN_HIGH_CRITICAL_F['DETROIT'])
    if regen_active and row['dpf_outlet_temp_peak_f'] > peak_critical:
        score += 50
        failure_triggers.append("THERMAL_SHOCK")
        rule_labels.append(RULE_LABELS["THERMAL_SHOCK"])

    # Rule 3: Impossible temp delta — sensor fault — GATED on regen_active
    if regen_active and row['dpf_outlet_temp_active_regen_f'] < 500 and row['dpf_inlet_temp_f'] > 1000:
        score += 70
        failure_triggers.append("SENSOR_FAULT")
        rule_labels.append(RULE_LABELS["SENSOR_FAULT"])

    # Rule 4: Frequent regen
    if row['regen_count_7d'] > 2 or row.get('driver_reported_frequent_regen', 0) == 1:
        score += 30
        failure_triggers.append("CLOGGING")
        rule_labels.append(RULE_LABELS["CLOGGING_FREQ"])

    # Rule 5: Ash load
    if row.get('mileage_since_last_dpf_cleaning', 0) > 300000 and row.get('oil_consumption_qt_per_1000mi', 0) > 0.5:
        score += 25
        failure_triggers.append("ASH_LOAD")
        rule_labels.append(RULE_LABELS["ASH_LOAD"])

    # Rule 6: Turbo/EGR
    if row.get('turbo_boost_psi', 100) < 20 or row.get('egr_flow_fault', 0) == 1:
        score += 25
        failure_triggers.append("OPERATIONAL")
        rule_labels.append(RULE_LABELS["TURBO_EGR"])

    # Rule 7: Duty cycle
    if row.get('avg_trip_distance_mi', 100) < 15 and row.get('idle_time_pct', 0) > 35:
        score += 15
        failure_triggers.append("OPERATIONAL")
        rule_labels.append(RULE_LABELS["DUTY_CYCLE"])

    # Rule 8: DEF system
    if row.get('def_quality_ppm', 0) > 50 or row.get('def_doser_fault', 0) == 1:
        score += 15
        failure_triggers.append("OPERATIONAL")
        rule_labels.append(RULE_LABELS["DEF_SYSTEM"])

    # Rule 9: Fuel quality
    if row.get('water_in_fuel_detected', 0) == 1 or row.get('fuel_filter_change_frequency_days', 999) < 45:
        score += 10
        failure_triggers.append("OPERATIONAL")
        rule_labels.append(RULE_LABELS["FUEL_QUALITY"])

    # Rule 10: Backpressure
    if row['back_pressure_inh2o'] > DIFF_PRESSURE_CRITICAL_PSI:
        score += 10
        failure_triggers.append("CLOGGING")
        rule_labels.append(RULE_LABELS["CLOGGING_BACKPRES"])

    # ── SCR / Aftertreatment rules ────────────────────────────────────────────
    # NOx conversion = (1 - nox_downstream / nox_upstream) * 100
    # Default 100 when not present — conservative (assume healthy if no sensor)

    # Rule 11: NOx conversion — CRITICAL breach (<50%) — EPA derate risk
    nox_conv = row.get('nox_conversion_pct', 100)
    if nox_conv < NOX_CONVERSION_CRITICAL_PCT:
        score += 40
        failure_triggers.append("NOX_BREAKTHROUGH")
        rule_labels.append(RULE_LABELS["NOX_CRITICAL"])

    # Rule 12: NOx conversion — WARNING (50–70%) — catalyst degrading
    elif nox_conv < NOX_CONVERSION_WARNING_PCT:
        score += 20
        failure_triggers.append("SCR_CATALYST")
        rule_labels.append(RULE_LABELS["NOX_WARN"])

    # Rule 13: SCR inlet temp below catalyst light-off floor
    if row.get('scr_inlet_temp_f', 500) < SCR_INLET_TEMP_MIN_F:
        score += 15
        failure_triggers.append("SCR_CATALYST")
        rule_labels.append(RULE_LABELS["SCR_COLD"])

    # Rule 14: DEF concentration out of spec
    # Separate from existing def_quality_ppm (contamination) — this checks urea %
    def_conc = row.get('def_concentration_pct', DEF_QUALITY_SPEC_PCT)
    if def_conc < DEF_QUALITY_CRITICAL_PCT or def_conc > 40:
        # Water substitution or severely wrong concentration
        score += 25
        failure_triggers.append("DEF_QUALITY")
        rule_labels.append(RULE_LABELS["DEF_CONC_CRITICAL"])
    elif def_conc < DEF_QUALITY_MIN_PCT or def_conc > DEF_QUALITY_MAX_PCT:
        score += 10
        failure_triggers.append("DEF_QUALITY")
        rule_labels.append(RULE_LABELS["DEF_CONC_WARN"])

    # Rule 15: NH3 slip — excess ammonia passing through SCR unreacted
    if row.get('nh3_slip_detected', 0) == 1:
        score += 10
        failure_triggers.append("SCR_CATALYST")
        rule_labels.append(RULE_LABELS["NH3_SLIP"])

    # Rule 16: Compound aftertreatment failure — DPF + SCR both flagged
    # Both systems down simultaneously is always worse than either alone.
    # Detroit 1-Box gets higher penalty — shared housing means both fail together.
    dpf_flagged = any(t in failure_triggers for t in ["CLOGGING", "THERMAL_SHOCK"])
    scr_flagged = any(t in failure_triggers for t in ["NOX_BREAKTHROUGH", "SCR_CATALYST", "DEF_QUALITY"])
    if dpf_flagged and scr_flagged:
        family = row.get('engine_family', '')
        bonus = 20 if family in ONE_BOX_FAMILIES else 15
        score += bonus
        rule_labels.append(RULE_LABELS["COMPOUND_ATS"])

    score        = min(score, 100)
    failure_mode = determine_failure_mode(failure_triggers)
    priority     = get_priority(score)
    action       = generate_action(failure_mode, row)
    confidence   = get_confidence(len(rule_labels))
    trend        = get_trend(score, previous_score)
    triggered    = ", ".join(rule_labels) if rule_labels else "None"

    return pd.Series([score, priority, failure_mode, action, triggered, confidence, trend])


SCORE_COLUMNS = [
    'rule_score', 'priority_label', 'failure_mode',
    'recommended_action', 'triggered_rules', 'confidence', 'score_trend',
]


def run_scoring(input_csv, output_csv="scored_output.csv", history_csv=None):
    """
    Score every truck in input_csv.

    Args:
        input_csv:   path to input CSV with sensor readings
        output_csv:  path to write scored output
        history_csv: optional path to a previous scored output — used for trend calc.
                     Must have 'vehicle_id' and 'rule_score' columns.
    """
    df = pd.read_csv(input_csv)

    # Build previous score lookup if history provided
    prev_scores = {}
    if history_csv:
        try:
            hist = pd.read_csv(history_csv)[['vehicle_id', 'rule_score']]
            prev_scores = dict(zip(hist['vehicle_id'], hist['rule_score']))
        except Exception:
            pass

    def _score(row):
        prev = prev_scores.get(row.get('vehicle_id'))
        return score_row(row, previous_score=prev)

    df[SCORE_COLUMNS] = df.apply(_score, axis=1)

    df.to_csv(output_csv, index=False)
    print(f"Scoring complete. Output saved to {output_csv}")


if __name__ == "__main__":
    run_scoring("throttle_guard_full_mock.csv")
