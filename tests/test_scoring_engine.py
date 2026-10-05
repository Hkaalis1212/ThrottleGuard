"""
Tests for scoring_engine.py — the rule-based scoring engine behind the Fleet
Scores tab and the landing page. Mirrors test_dpf_expert_system.py's
coverage; the two engines implement the same 17 documented rules
independently, and historically have NOT stayed in sync (see Rule 2 in
test_dpf_expert_system.py) — keeping both test files structurally parallel
makes future drift between them easy to spot.
"""
import pytest

from scoring_engine import score_row, SCORE_COLUMNS


def _result(row, previous_score=None):
    return dict(zip(SCORE_COLUMNS, score_row(row, previous_score=previous_score)))


# ── Rule 1: low outlet temp during regen → clogging ────────────────────────────

def test_rule1_fires_below_outlet_critical(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_active_regen_f=959))
    assert result["failure_mode"] == "CLOGGING"
    assert result["rule_score"] >= 60


def test_rule1_does_not_fire_at_outlet_critical(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_active_regen_f=960))
    assert "Low regen temp" not in result["triggered_rules"]


def test_rule1_gated_by_regen_active(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_active_regen_f=500, regen_active=0))
    assert "Low regen temp" not in result["triggered_rules"]


# ── Rule 2: peak temp too high → thermal shock (engine-family specific) ───────

@pytest.mark.parametrize("family,family_critical_f", [
    ("DETROIT", 1250),
    ("VOLVO_MACK", 1250),
    ("CUMMINS_PACCAR", 1200),
])
def test_rule2_fires_above_family_critical(healthy_row, family, family_critical_f):
    result = _result(healthy_row(engine_family=family, dpf_outlet_temp_peak_f=family_critical_f + 1))
    assert result["failure_mode"] == "THERMAL_SHOCK"
    assert result["rule_score"] >= 50


@pytest.mark.parametrize("family,family_critical_f", [
    ("DETROIT", 1250),
    ("VOLVO_MACK", 1250),
    ("CUMMINS_PACCAR", 1200),
])
def test_rule2_does_not_fire_below_family_critical(healthy_row, family, family_critical_f):
    result = _result(healthy_row(engine_family=family, dpf_outlet_temp_peak_f=family_critical_f - 1))
    assert result["failure_mode"] != "THERMAL_SHOCK"


def test_rule2_gated_by_regen_active(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_peak_f=1400, regen_active=0))
    assert result["failure_mode"] != "THERMAL_SHOCK"


# ── Rule 3: sensor delta fault ──────────────────────────────────────────────────

def test_rule3_fires_on_wide_spread_above_floor(healthy_row):
    result = _result(healthy_row(dpf_inlet_temp_f=1150, dpf_outlet_temp_active_regen_f=1000))
    assert result["failure_mode"] == "SENSOR_FAULT"
    assert result["rule_score"] >= 70


def test_rule3_does_not_fire_below_temp_floor(healthy_row):
    result = _result(healthy_row(dpf_inlet_temp_f=900, dpf_outlet_temp_active_regen_f=700))
    assert result["failure_mode"] != "SENSOR_FAULT"


def test_rule3_does_not_fire_within_spread(healthy_row):
    result = _result(healthy_row(dpf_inlet_temp_f=1040, dpf_outlet_temp_active_regen_f=1000))
    assert result["failure_mode"] != "SENSOR_FAULT"


# ── Rule 4: frequent regen ──────────────────────────────────────────────────────

def test_rule4_fires_on_driver_report(healthy_row):
    result = _result(healthy_row(driver_reported_frequent_regen=1))
    assert "Regen frequency high" in result["triggered_rules"]


def test_rule4_fires_on_telematic_count(healthy_row):
    result = _result(healthy_row(regen_count_7d=3))
    assert "Regen frequency high" in result["triggered_rules"]


def test_rule4_does_not_fire_at_two_regens(healthy_row):
    result = _result(healthy_row(regen_count_7d=2))
    assert "Regen frequency high" not in result["triggered_rules"]


# ── Rule 5: ash load ─────────────────────────────────────────────────────────────

def test_rule5_fires_when_both_conditions_met(healthy_row):
    result = _result(healthy_row(mileage_since_last_dpf_cleaning=350_000, oil_consumption_qt_per_1000mi=0.8))
    assert result["failure_mode"] == "ASH_LOAD"


def test_rule5_requires_both_conditions(healthy_row):
    result = _result(healthy_row(mileage_since_last_dpf_cleaning=350_000, oil_consumption_qt_per_1000mi=0.2))
    assert "Ash load" not in result["triggered_rules"]


# ── Rule 6: turbo / EGR ─────────────────────────────────────────────────────────

def test_rule6_fires_on_low_turbo_boost(healthy_row):
    result = _result(healthy_row(turbo_boost_psi=15.0))
    assert "Turbo boost low or EGR fault" in result["triggered_rules"]


def test_rule6_fires_on_egr_fault(healthy_row):
    result = _result(healthy_row(egr_flow_fault=1))
    assert "Turbo boost low or EGR fault" in result["triggered_rules"]


# ── Rule 7: short-trip / high-idle duty cycle ───────────────────────────────────

def test_rule7_fires_on_short_trip_high_idle(healthy_row):
    result = _result(healthy_row(avg_trip_distance_mi=10, idle_time_pct=40))
    assert "Short trips + high idle" in result["triggered_rules"]


def test_rule7_does_not_fire_with_only_one_factor(healthy_row):
    result = _result(healthy_row(avg_trip_distance_mi=10, idle_time_pct=20))
    assert "Short trips + high idle" not in result["triggered_rules"]


# ── Rule 8: DEF contamination / doser fault ─────────────────────────────────────

def test_rule8_fires_on_def_contamination(healthy_row):
    result = _result(healthy_row(def_quality_ppm=75))
    assert "DEF contamination or doser fault" in result["triggered_rules"]


def test_rule8_fires_on_doser_fault(healthy_row):
    result = _result(healthy_row(def_doser_fault=1))
    assert "DEF contamination or doser fault" in result["triggered_rules"]


# ── Rule 9: fuel quality ────────────────────────────────────────────────────────

def test_rule9_fires_on_water_in_fuel(healthy_row):
    result = _result(healthy_row(water_in_fuel_detected=1))
    assert "Water in fuel or filter overdue" in result["triggered_rules"]


def test_rule9_fires_on_early_filter_change(healthy_row):
    result = _result(healthy_row(fuel_filter_change_frequency_days=30))
    assert "Water in fuel or filter overdue" in result["triggered_rules"]


# ── Rule 10: elevated backpressure ──────────────────────────────────────────────

def test_rule10_fires_above_critical_backpressure(healthy_row):
    result = _result(healthy_row(back_pressure_inh2o=4.1))
    assert "Backpressure elevated" in result["triggered_rules"]


def test_rule10_does_not_fire_at_critical_boundary(healthy_row):
    result = _result(healthy_row(back_pressure_inh2o=4.0))
    assert "Backpressure elevated" not in result["triggered_rules"]


# ── Rule 11 / 12: NOx conversion ────────────────────────────────────────────────

def test_rule11_fires_below_critical_nox(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_peak_f=900, nox_conversion_pct=40))
    assert result["failure_mode"] == "NOX_BREAKTHROUGH"
    assert result["rule_score"] >= 40


def test_rule12_fires_in_nox_warning_band(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_peak_f=900, nox_conversion_pct=60))
    assert result["failure_mode"] == "SCR_CATALYST"


def test_rule11_and_12_mutually_exclusive(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_peak_f=900, nox_conversion_pct=40))
    assert result["rule_score"] == 40


def test_nox_rules_gated_below_800f_peak_temp(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_peak_f=700, nox_conversion_pct=10))
    assert result["failure_mode"] != "NOX_BREAKTHROUGH"


# ── Rule 13: SCR inlet below catalyst light-off ─────────────────────────────────

def test_rule13_fires_below_light_off(healthy_row):
    result = _result(healthy_row(scr_inlet_temp_f=350))
    assert "catalyst light-off" in result["triggered_rules"].lower()


def test_rule13_does_not_fire_at_light_off(healthy_row):
    result = _result(healthy_row(scr_inlet_temp_f=400))
    assert "catalyst light-off" not in result["triggered_rules"].lower()


# ── Rule 14: DEF concentration (two-tier) ───────────────────────────────────────

def test_rule14_critical_tier_fires_below_20pct(healthy_row):
    result = _result(healthy_row(def_concentration_pct=15.0))
    assert result["failure_mode"] == "DEF_QUALITY"
    assert result["rule_score"] >= 25


def test_rule14_warning_tier_fires_outside_spec(healthy_row):
    result = _result(healthy_row(def_concentration_pct=29.0))
    assert result["failure_mode"] == "DEF_QUALITY"
    assert result["rule_score"] == 10


def test_rule14_does_not_fire_within_spec(healthy_row):
    result = _result(healthy_row(def_concentration_pct=32.5))
    assert result["failure_mode"] != "DEF_QUALITY"


# ── Rule 15: NH3 slip ────────────────────────────────────────────────────────────

def test_rule15_fires_on_nh3_slip(healthy_row):
    result = _result(healthy_row(nh3_slip_detected=1))
    assert "NH3 slip" in result["triggered_rules"]


# ── Rule 16: compound DPF + SCR failure bonus ───────────────────────────────────

def test_rule16_compound_bonus_fires(healthy_row):
    # NH3 slip (SCR side) + backpressure (DPF side) — both flag-driven, no
    # temperature fields involved, so this can't cross-trigger Rule 17's
    # SCR-inlet-vs-DPF-outlet spread check the way overriding scr_inlet_temp_f
    # near a "clogged" outlet reading would.
    row = healthy_row(
        engine_family="CUMMINS_PACCAR",
        nh3_slip_detected=1,             # Rule 15 -> SCR_CATALYST (10 pts, SCR side)
        back_pressure_inh2o=4.5,         # Rule 10 -> CLOGGING (10 pts, DPF side)
    )
    result = _result(row)
    assert "Compound failure" in result["triggered_rules"]
    assert result["rule_score"] == 10 + 10 + 15   # +15 bonus for non-1-box family


def test_rule16_compound_bonus_is_higher_for_one_box(healthy_row):
    common = dict(nh3_slip_detected=1, back_pressure_inh2o=4.5)
    detroit = _result(healthy_row(engine_family="DETROIT", **common))
    cummins = _result(healthy_row(engine_family="CUMMINS_PACCAR", **common))
    assert detroit["rule_score"] == 10 + 10 + 20   # +20 bonus for 1-Box
    assert cummins["rule_score"] == 10 + 10 + 15   # +15 bonus otherwise
    assert detroit["rule_score"] > cummins["rule_score"]


# ── Rule 17: SCR inlet vs. DPF outlet spread ────────────────────────────────────

def test_rule17_fires_on_wide_scr_dpf_spread(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_active_regen_f=1000, scr_inlet_temp_f=1100))
    assert "SCR inlet / DPF outlet temp spread" in result["triggered_rules"]


def test_rule17_does_not_fire_within_spread(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_active_regen_f=1000, scr_inlet_temp_f=1030))
    assert "SCR inlet / DPF outlet temp spread" not in result["triggered_rules"]


# ── Priority, confidence, trend ─────────────────────────────────────────────────

def test_priority_critical(healthy_row):
    result = _result(healthy_row(dpf_outlet_temp_active_regen_f=900))
    assert result["priority_label"] == "CRITICAL"


def test_priority_low_when_nothing_triggered(healthy_row):
    result = _result(healthy_row())
    assert result["priority_label"] == "LOW"
    assert result["triggered_rules"] == "None"


def test_score_capped_at_100(healthy_row):
    row = healthy_row(
        dpf_outlet_temp_active_regen_f=900,
        dpf_inlet_temp_f=1100,
        regen_count_7d=5,
        back_pressure_inh2o=5.0,
    )
    result = _result(row)
    assert result["rule_score"] == 100


def test_confidence_scales_with_trigger_count(healthy_row):
    low = _result(healthy_row())
    high = _result(healthy_row(
        dpf_outlet_temp_active_regen_f=900, regen_count_7d=5, back_pressure_inh2o=5.0,
    ))
    assert low["confidence"] == "LOW"
    assert high["confidence"] == "HIGH"


def test_trend_reflects_score_change(healthy_row):
    worse = _result(healthy_row(regen_count_7d=5), previous_score=10)
    assert worse["score_trend"] == "↑ Worsening"
    better = _result(healthy_row(), previous_score=50)
    assert better["score_trend"] == "↓ Improving"
    stable = _result(healthy_row(), previous_score=0)
    assert stable["score_trend"] == "→ Stable"
