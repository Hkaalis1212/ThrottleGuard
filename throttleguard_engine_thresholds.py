"""
throttleguard_engine_thresholds.py
------------------------------------
Single source of truth for all engine-family thresholds in ThrottleGuard.

Import this in the DPF generator, SCR generator, model trainer, and dashboard.
Never hardcode thresholds in individual modules. When real J1939 data validates
or revises a number, change it here and every module updates automatically.

═══════════════════════════════════════════════════════════════════
PROVENANCE — READ BEFORE CHANGING ANY NUMBER
═══════════════════════════════════════════════════════════════════
All DPF regen temperature thresholds are field-validated by the ThrottleGuard
founder from ~20 years of hands-on diesel technician experience diagnosing
DPF/SCR failures on Detroit, Volvo/Mack, and Cummins/PACCAR platforms.

These are NOT OEM datasheet values. They are observed field thresholds derived
from real failure diagnosis. The high-side ranges (e.g. 1180-1200°F) reflect
the actual spread seen across real trucks — the lower bound is encoded as HIGH
warning, the upper bound as CRITICAL pull-truck threshold.

If you update a threshold:
  - Document what changed and why (real data, field observation, OEM bulletin)
  - Record the date and who validated it
  - Never change ENGINE_FAMILY_ENCODING integers — that requires full retrain

═══════════════════════════════════════════════════════════════════
ENGINE FAMILY STRUCTURE
═══════════════════════════════════════════════════════════════════
Three real platform families — not five individual makes.

  DETROIT           DD13 / DD15 / DD16
                    Own architecture. 1-Box design integrates DPF+SCR in a
                    single housing — cannot service DPF independently from SCR.

  VOLVO_MACK        Volvo D11 / D13 / D16  +  Mack MP7 / MP8 / MP10
                    Same underlying platform. Mack is Volvo architecture.
                    Identical regen thresholds across both badges.

  CUMMINS_PACCAR    Cummins ISX / X15  +  PACCAR MX-11 / MX-13
                    Same thresholds confirmed across both makes by founder.
                    Lower high-side ceiling than Detroit and Volvo/Mack.
                    Less tolerance for sustained temps above 1180°F.

═══════════════════════════════════════════════════════════════════
FULL REGEN TEMPERATURE MAP (field-validated, both sides)
═══════════════════════════════════════════════════════════════════

                        DETROIT     VOLVO_MACK  CUMMINS_PACCAR
  Normal target         1000°F      1050°F      1000°F
  Problem floor         1050°F      1050°F      1000°F
  Universal low floor    930°F       930°F       930°F
  High warning          1230°F      1230°F      1180°F
  High critical         1250°F      1250°F      1200°F

LOW SIDE — 930°F UNIVERSAL TRANSITION FLOOR:
  At or below 930°F regens are not fully burning soot — they are compacting
  it into the substrate face. Single event = watch. Two consecutive events
  with rising backpressure = actionable regardless of family.

  Severity at 930°F:
    Detroit:          ~70°F below 1000°F target  → serious warning
    Volvo/Mack:       ~120°F below 1050°F target → near-critical
    Cummins/PACCAR:   ~70°F below 1000°F target  → serious warning

HIGH SIDE:
  High warning = elevated concern, monitor closely, consider pulling if sustained.
  High critical = pull truck now. Primary failure modes:
    - DPF housing discoloration and warping
    - SCR catalyst thermal damage (especially Detroit 1-Box — shared housing)

  Cummins/PACCAR distinction: same trigger as others at 1180°F warning / 1200°F
  critical, but LESS TOLERANCE for sustained temps above 1180°F. Detroit and
  Volvo/Mack can survive brief excursions. Cummins/PACCAR escalates faster
  if the high temp persists. Encode as duration multiplier, not a different number.

COMPOUND LOW-SIDE ESCALATION RULE (field-validated):
  incomplete_regen_streak >= 2  AND  diff_pressure_psi rising  →  escalate
  Neither condition alone is sufficient. Both together is always actionable.
"""

# ─────────────────────────────────────────────────────────────────
# ENGINE FAMILY GROUPINGS
# ─────────────────────────────────────────────────────────────────

# Maps specific engine model string → canonical family key
# Add new variants here as new models arrive — never change existing keys
ENGINE_MODEL_TO_FAMILY = {
    # Detroit
    'Detroit DD13':     'DETROIT',
    'Detroit DD15':     'DETROIT',
    'Detroit DD16':     'DETROIT',

    # Volvo/Mack — same platform, same key
    'Volvo D11':        'VOLVO_MACK',
    'Volvo D13':        'VOLVO_MACK',
    'Volvo D16':        'VOLVO_MACK',
    'Mack MP7':         'VOLVO_MACK',
    'Mack MP8':         'VOLVO_MACK',
    'Mack MP10':        'VOLVO_MACK',

    # Cummins/PACCAR — same thresholds confirmed by founder
    'Cummins ISX':      'CUMMINS_PACCAR',
    'Cummins X15':      'CUMMINS_PACCAR',
    'PACCAR MX-11':     'CUMMINS_PACCAR',
    'PACCAR MX-13':     'CUMMINS_PACCAR',
}

# Integer encoding for XGBoost features
# ORDER IS FIXED — never reorder, never delete. Append new families at the end.
# Changing these integers requires full model retrain.
ENGINE_FAMILY_ENCODING = {
    'DETROIT':          0,
    'VOLVO_MACK':       1,
    'CUMMINS_PACCAR':   2,
}

# Reverse map — for dashboard display and logging
ENGINE_FAMILY_DECODING = {v: k for k, v in ENGINE_FAMILY_ENCODING.items()}

# Human-readable labels for Streamlit dropdowns
ENGINE_FAMILY_DISPLAY_NAMES = {
    'DETROIT':          'Detroit  (DD13 / DD15 / DD16)',
    'VOLVO_MACK':       'Volvo / Mack  (D11, D13, D16, MP7, MP8, MP10)',
    'CUMMINS_PACCAR':   'Cummins / PACCAR  (ISX, X15, MX-11, MX-13)',
}


# ─────────────────────────────────────────────────────────────────
# DPF REGEN TEMPERATURE THRESHOLDS (°F)
# Field-validated. See provenance block above before changing.
# ─────────────────────────────────────────────────────────────────

# Normal active regen target — healthy truck should reach and sustain this
REGEN_NORMAL_TARGET_F = {
    'DETROIT':          1000,
    'VOLVO_MACK':       1050,
    'CUMMINS_PACCAR':   1000,
}

# Temp below which incomplete burn begins for each family
REGEN_PROBLEM_FLOOR_F = {
    'DETROIT':          1050,   # must exceed normal target to burn clean
    'VOLVO_MACK':       1050,   # target = floor, no margin
    'CUMMINS_PACCAR':   1000,   # problems start at normal target
}

# Universal low-side transition floor — field validated across all families
# Below this: soot compaction into substrate face begins.
# Single event = watch condition. Streak + rising backpressure = act.
REGEN_TRANSITION_FLOOR_F = 930

# Active regen CRITICAL trigger — outlet temp below this during regen = CRITICAL flag
# Field-validated: 2026-03-23 — founder revised from 930 to 940°F
REGEN_OUTLET_CRITICAL_F = 940

# High-side WARNING threshold (°F) — lower bound of observed field range
# Elevated concern: monitor closely, consider pulling if temp is sustained
REGEN_HIGH_WARNING_F = {
    'DETROIT':          1230,   # field observed range 1230–1250°F
    'VOLVO_MACK':       1230,   # field observed range 1230–1250°F
    'CUMMINS_PACCAR':   1180,   # field observed range 1180–1200°F (lower ceiling)
}

# High-side CRITICAL threshold (°F) — upper bound of observed field range
# Pull truck now. Housing warp and SCR catalyst damage territory.
REGEN_HIGH_CRITICAL_F = {
    'DETROIT':          1250,
    'VOLVO_MACK':       1250,
    'CUMMINS_PACCAR':   1200,   # less sustained tolerance above 1180°F
}

# Duration sensitivity flag — families that escalate faster at sustained high temps
# Detroit and Volvo/Mack can survive brief excursions. Cummins/PACCAR cannot.
# Use this flag to apply a faster escalation multiplier in the simulation.
HIGH_TEMP_DURATION_SENSITIVE = {
    'DETROIT':          False,
    'VOLVO_MACK':       False,
    'CUMMINS_PACCAR':   True,   # escalate to CRITICAL faster if high temp persists
}

# Primary failure modes at high-side critical — for dashboard service notes
REGEN_HIGH_FAILURE_MODES = {
    'DETROIT':          'DPF housing warp + SCR thermal damage (1-Box — DPF and SCR share housing)',
    'VOLVO_MACK':       'DPF housing discoloration and warping',
    'CUMMINS_PACCAR':   'DPF housing warp — less sustained tolerance than Detroit/Volvo/Mack',
}


# ─────────────────────────────────────────────────────────────────
# COMPOUND LOW-SIDE ESCALATION RULE
# ─────────────────────────────────────────────────────────────────

# Minimum consecutive incomplete regens before streak is actionable
# Only actionable when ALSO combined with rising diff_pressure_psi
INCOMPLETE_REGEN_STREAK_THRESHOLD = 2

# Backpressure thresholds (PSI)
DIFF_PRESSURE_WARNING_PSI  = 2.0   # approaching blockage — watch
DIFF_PRESSURE_CRITICAL_PSI = 4.0   # critical blockage territory


# ─────────────────────────────────────────────────────────────────
# REGEN PHASE — warmup floor and phase encoding
# ─────────────────────────────────────────────────────────────────

# Temp at which active regen begins — DOC must reach this before sustained burn
# Derived from: REGEN_NORMAL_TARGET_F - 200°F (midpoint offset used in SCR generator)
# warmup phase = below this floor, no threshold alerts
# active phase = above this floor, CRITICAL+HIGH alerts enabled
REGEN_WARMUP_FLOOR_F = {
    'DETROIT':          800,    # 1000°F target - 200°F offset
    'VOLVO_MACK':       850,    # 1050°F target - 200°F offset
    'CUMMINS_PACCAR':   800,    # 1000°F target - 200°F offset
}

# Integer encoding for regen phase — ORDER IS FIXED, never reorder
# no_regen=3 is added at point of use: {'no_regen': 3, **REGEN_PHASE_ENCODING}
# Changing these integers requires full model retrain
REGEN_PHASE_ENCODING = {
    'warmup':   0,
    'active':   1,
    'cooldown': 2,
}

# Reverse map
REGEN_PHASE_DECODING = {v: k for k, v in REGEN_PHASE_ENCODING.items()}
REGEN_PHASE_DECODING[3] = 'no_regen'


# ─────────────────────────────────────────────────────────────────
# 1-BOX FLAG (Detroit DD-series only)
# ─────────────────────────────────────────────────────────────────
# Detroit 1-Box integrates DPF and SCR in a single housing.
# A DPF service visit on a 1-Box truck touches both systems.
# NOT an automatic SCR risk escalation — field experience shows DPF-side
# failures on 1-Box where SCR was still serviceable. Surface as a soft
# verification flag so the technician checks SCR during the same visit.
ONE_BOX_FAMILIES = {'DETROIT'}

ONE_BOX_SERVICE_NOTE = (
    "Detroit 1-Box: DPF and SCR share a single housing. "
    "Verify SCR catalyst condition during this service visit."
)


# ─────────────────────────────────────────────────────────────────
# SCR (SELECTIVE CATALYTIC REDUCTION) THRESHOLDS
# ─────────────────────────────────────────────────────────────────
# SCR reduces NOx using DEF (urea) injection. It sits downstream of the DPF.
# On Detroit 1-Box (ONE_BOX_FAMILIES), DPF and SCR share a single housing —
# a DPF thermal event directly exposes the SCR catalyst to the same damage.
#
# Key J1939 signals: upstream NOx (pre-SCR), downstream NOx (post-SCR),
# SCR inlet temp, DEF quality (urea concentration), DEF doser status.
#
# NOx conversion efficiency = (1 - nox_downstream / nox_upstream) * 100
# Healthy range: > 85%. Below 70% = investigate. Below 50% = pull truck.

# NOx conversion efficiency floors (universal — not family-specific)
# Below CRITICAL: EPA derate territory, possible roadside violation
NOX_CONVERSION_CRITICAL_PCT = 50
# Below WARNING: catalyst degraded — investigate before next dispatch
NOX_CONVERSION_WARNING_PCT  = 70

# SCR catalyst requires minimum inlet temp to activate urea chemistry
# Below this threshold: ammonia does not react, NOx passes through catalyst
SCR_INLET_TEMP_MIN_F = 400   # °F — catalyst light-off floor, all families

# SCR inlet temp high-side limits by family (sustained = catalyst damage)
SCR_INLET_TEMP_HIGH_F = {
    'DETROIT':          800,   # 1-Box: shared housing with DPF, less margin
    'VOLVO_MACK':       820,
    'CUMMINS_PACCAR':   800,
}

# DEF (Diesel Exhaust Fluid) urea concentration spec
# AdBlue/DEF must be 32.5% urea solution (ISO 22241).
# Too dilute: reduced NOx conversion. Too concentrated: ammonia slip risk.
# Critically dilute (< 20%): effectively water — system will fault or derate.
DEF_QUALITY_SPEC_PCT      = 32.5   # nominal center (ISO spec)
DEF_QUALITY_MIN_PCT       = 31.0   # lower acceptance limit
DEF_QUALITY_MAX_PCT       = 34.0   # upper acceptance limit
DEF_QUALITY_CRITICAL_PCT  = 20.0   # below this: water contamination / severe dilution


# ─────────────────────────────────────────────────────────────────
# DUTY CYCLE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────
# Manual input — dispatcher or fleet manager sets this per truck/route.
# Multipliers intentionally neutral (1.0) until real fleet data validates
# actual degradation rates per duty cycle.
# DO NOT adjust multipliers from guesswork — wait for real data.

DUTY_CYCLES = ['highway', 'regional', 'construction']

DUTY_CYCLE_DISPLAY_NAMES = {
    'highway':      'Highway  (long-haul, sustained speed)',
    'regional':     'Regional  (mixed, some stop-and-go)',
    'construction': 'Construction  (heavy stop-and-go, thermal shock)',
}

# TODO: update from real fleet data before using in production model
DUTY_CYCLE_DEGRADATION_MULTIPLIER = {
    'highway':      1.0,   # baseline
    'regional':     1.0,   # expected slightly higher — validate from data
    'construction': 1.0,   # expected highest (MP8 construction thermal shock case)
}


# ─────────────────────────────────────────────────────────────────
# QUICK REFERENCE — run this file directly to verify all values
# ─────────────────────────────────────────────────────────────────
def print_threshold_summary():
    """Print a readable summary of all thresholds. Run to verify import."""
    families = ['DETROIT', 'VOLVO_MACK', 'CUMMINS_PACCAR']
    print("\n" + "="*65)
    print("ThrottleGuard Engine Thresholds — Field Validated")
    print("="*65)
    print(f"\n{'Threshold':<32} {'DETROIT':>10} {'VOLVO_MACK':>12} {'CUMMINS_PACCAR':>14}")
    print("-"*68)
    rows = [
        ("Normal regen target (°F)",    REGEN_NORMAL_TARGET_F),
        ("Problem floor (°F)",          REGEN_PROBLEM_FLOOR_F),
        ("Low transition floor (°F)",   {f: REGEN_TRANSITION_FLOOR_F for f in families}),
        ("Outlet CRITICAL trigger (°F)", {f: REGEN_OUTLET_CRITICAL_F for f in families}),
        ("High warning (°F)",           REGEN_HIGH_WARNING_F),
        ("High critical (°F)",          REGEN_HIGH_CRITICAL_F),
        ("High temp duration sensitive",HIGH_TEMP_DURATION_SENSITIVE),
    ]
    for label, d in rows:
        vals = [str(d[f]) for f in families]
        print(f"{label:<32} {vals[0]:>10} {vals[1]:>12} {vals[2]:>14}")
    print(f"\nCompound low-side rule:  streak >= {INCOMPLETE_REGEN_STREAK_THRESHOLD} AND backpressure rising")
    print(f"Backpressure warning:    {DIFF_PRESSURE_WARNING_PSI} PSI")
    print(f"Backpressure critical:   {DIFF_PRESSURE_CRITICAL_PSI} PSI")
    print(f"1-Box families:          {ONE_BOX_FAMILIES}")
    print(f"Duty cycles:             {DUTY_CYCLES}")
    print("="*65 + "\n")


# ─────────────────────────────────────────────────────────────────
# PASSIVE REGEN TEMPERATURE THRESHOLDS (°F)
# Field-validated April 2026 — diesel tech community field observations
#
# These are NORMAL OPERATION exhaust temps (no commanded regen in progress).
# Entirely different range from active regen temps above — do not mix them.
#
# Passive regen occurs when exhaust temps from normal highway driving are
# hot enough to oxidize soot without a commanded regen event. City/idle
# trucks never reach these temps — soot accumulates silently.
# ─────────────────────────────────────────────────────────────────

# Floor of passive regen range — exhaust must exceed this during normal op
PASSIVE_REGEN_FLOOR_F = {
    'DETROIT':          600,   # DD13/DD15/DD16 — passive starts above 600°F
    'VOLVO_MACK':       600,   # D13/MP8 — 600-700°F range without 7th injector active
    'CUMMINS_PACCAR':   575,   # ISX15/X15 — passive begins at 575°F
}

# Upper end of passive range — above this, active regen territory begins
PASSIVE_REGEN_EFFECTIVE_HIGH_F = {
    'DETROIT':          700,
    'VOLVO_MACK':       700,   # 7th injector off keeps temps in this band
    'CUMMINS_PACCAR':   900,   # can sustain higher temps under heavy highway load
}

# Below this during highway operation = passive regen definitely not occurring
# Soot is accumulating silently between forced regen events
PASSIVE_REGEN_FAILURE_FLOOR_F = {
    'DETROIT':          550,
    'VOLVO_MACK':       550,
    'CUMMINS_PACCAR':   550,
}

PASSIVE_REGEN_NOTES = {
    'DETROIT':          'DD15 especially sensitive to DEF system health affecting regen temps',
    'VOLVO_MACK':       '7th injector status changes behavior — passive range is 600-700°F without it',
    'CUMMINS_PACCAR':   'Cummins initiates active regen aggressively when passive temps are marginal',
}


if __name__ == '__main__':
    print_threshold_summary()
