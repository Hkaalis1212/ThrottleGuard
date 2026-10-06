"""
Tests for throttleguard_passive_regen.py's app-facing integration:
apply_passive_regen_modifier()'s tier-adjustment contract, and
layer_onto_scored_results() (the helper app.py / tg_demo_data.py use to
wire it onto dpf_expert_system.py / scoring_engine.py output).

Not covered: the component scorers (_score_exhaust_temp etc.) — this
module isn't part of the main 18-rule engine's drift-tracked test suite,
and the component math is exercised by the module's own __main__ self-test.
"""
import pandas as pd
import pytest

from throttleguard_passive_regen import (
    apply_passive_regen_modifier,
    layer_onto_scored_results,
)


# ── apply_passive_regen_modifier: the core safety invariant ───────────────────

@pytest.mark.parametrize("tier", ["CRITICAL", "HIGH"])
@pytest.mark.parametrize("score", [0.0, 0.25, 0.5, 0.8, 1.0])
def test_critical_and_high_never_move(tier, score):
    assert apply_passive_regen_modifier(tier, score) == tier


def test_medium_downgrades_to_low_on_excellent_passive_health():
    assert apply_passive_regen_modifier("MEDIUM", 0.80) == "LOW"
    assert apply_passive_regen_modifier("MEDIUM", 0.95) == "LOW"


def test_medium_stays_medium_below_downgrade_threshold():
    assert apply_passive_regen_modifier("MEDIUM", 0.79) == "MEDIUM"


def test_low_escalates_to_medium_on_failing_passive_health():
    assert apply_passive_regen_modifier("LOW", 0.25) == "MEDIUM"
    assert apply_passive_regen_modifier("LOW", 0.0) == "MEDIUM"


def test_low_stays_low_above_escalation_threshold():
    assert apply_passive_regen_modifier("LOW", 0.26) == "LOW"


def test_medium_also_escalates_to_medium_on_failing_passive_health():
    # Already MEDIUM, failing score — stays MEDIUM (can't escalate above it)
    assert apply_passive_regen_modifier("MEDIUM", 0.1) == "MEDIUM"


# ── layer_onto_scored_results ──────────────────────────────────────────────────

def _row(**overrides):
    row = {
        "vehicle_id": "TEST-001",
        "engine_family": "CUMMINS_PACCAR",
        "regen_active": 0,
        "dpf_inlet_temp_f": 650,
        "dpf_outlet_temp_peak_f": 650,
        "idle_time_pct": 10,
        "engine_load_pct": 75,
        "regen_count_7d": 1,
        "water_in_fuel_detected": False,
        "fuel_filter_change_frequency_days": 90,
    }
    row.update(overrides)
    return row


def test_layer_adds_expected_columns():
    df = pd.DataFrame([_row()])
    results = pd.DataFrame([{"priority": "LOW"}])
    out = layer_onto_scored_results(df, results, priority_col="priority")
    for col in ["passive_regen_score", "passive_regen_failure",
                "passive_failure_type", "passive_recommendation", "adjusted_priority"]:
        assert col in out.columns


def test_blank_engine_family_does_not_crash():
    # engine_family is an OPTIONAL CSV column and routinely blank on real
    # uploads — PASSIVE_REGEN_FLOOR_F indexes it directly ([...], not .get),
    # so this must default rather than raise KeyError.
    df = pd.DataFrame([_row(engine_family="")])
    results = pd.DataFrame([{"priority": "LOW"}])
    out = layer_onto_scored_results(df, results, priority_col="priority")
    assert pd.notna(out.loc[0, "passive_regen_score"])


def test_missing_engine_family_column_does_not_crash():
    row = _row()
    del row["engine_family"]
    df = pd.DataFrame([row])
    results = pd.DataFrame([{"priority": "LOW"}])
    out = layer_onto_scored_results(df, results, priority_col="priority")
    assert pd.notna(out.loc[0, "passive_regen_score"])


def test_non_standard_priority_passed_through_unmodified():
    # dpf_expert_system.py's "ERROR" tier (failed required-field validation)
    df = pd.DataFrame([_row()])
    results = pd.DataFrame([{"priority": "ERROR"}])
    out = layer_onto_scored_results(df, results, priority_col="priority")
    assert out.loc[0, "adjusted_priority"] == "ERROR"
    assert out.loc[0, "passive_regen_score"] is None


def test_critical_row_untouched_even_with_failing_passive_health():
    df = pd.DataFrame([_row(
        dpf_inlet_temp_f=400, idle_time_pct=80, engine_load_pct=20,
        regen_count_7d=8, water_in_fuel_detected=True,
    )])
    results = pd.DataFrame([{"priority": "CRITICAL"}])
    out = layer_onto_scored_results(df, results, priority_col="priority")
    assert out.loc[0, "adjusted_priority"] == "CRITICAL"


def test_low_row_escalates_to_medium_on_failing_passive_health():
    df = pd.DataFrame([_row(
        dpf_inlet_temp_f=400, dpf_outlet_temp_peak_f=600,
        idle_time_pct=60, engine_load_pct=20,
        regen_count_7d=1, water_in_fuel_detected=True,
    )])
    results = pd.DataFrame([{"priority": "LOW"}])
    out = layer_onto_scored_results(df, results, priority_col="priority")
    assert out.loc[0, "passive_regen_score"] <= 0.25
    assert out.loc[0, "adjusted_priority"] == "MEDIUM"
