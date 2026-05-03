"""
throttleguard_passive_regen.py
AHC Developers — ThrottleGuard Platform

Passive Regeneration Health Scoring Module

WHY THIS EXISTS:
Passive regen is the silent killer in DPF failures. Unlike forced/active regen,
the ECM never broadcasts a commanded event — no PGN flag, no service tool alert.
The truck is silently failing to burn soot during normal highway operation, and
the first sign most fleets see is a breakdown-level DPF restriction.

OEM software misses this entirely. ThrottleGuard doesn't.

DOMAIN SOURCE:
Temp ranges validated against field data from diesel tech community sources
covering DD13/DD15/DD16, D13/MP8, ISX15/X15 platforms. Sourced April 2026.
These are field-observed ranges, not OEM spec sheet values.

HOW IT WORKS:
When regen_active = 0 (no commanded regen in progress), exhaust temps in the
575-900°F range during highway operation indicate passive regen is occurring.
Temps that stay below 550°F mean passive regen is NOT happening — soot builds
silently. This module scores how well a truck's normal operation supports
passive regen, and flags when it doesn't.

COLUMN NAMES:
Uses the ThrottleGuard v2 CSV spec (see CLAUDE.md). Key inputs:
  dpf_inlet_temp_f               — exhaust temp entering DPF
  dpf_outlet_temp_peak_f         — peak outlet temp (used for EGT delta)
  regen_active                   — 0=no commanded regen, 1=active/forced regen
  idle_time_pct                  — % time at idle
  engine_load_pct                — engine load (optional, used for duty cycle)
  regen_count_7d                 — forced regens in last 7 days
  water_in_fuel_detected         — fuel contamination flag
  fuel_filter_change_frequency_days — proxy for chronic fuel quality

INTEGRATION:
- High score (0.7-1.0) = highway truck burning clean passively = lower risk pressure
- Low score (0.0-0.3) = city/idle truck dependent on forced regens = higher risk pressure
- Score feeds apply_passive_regen_modifier() to adjust MEDIUM/LOW risk tiers only
- CRITICAL and HIGH are never downgraded by passive regen score
"""

import pandas as pd

from throttleguard_engine_thresholds import (
    PASSIVE_REGEN_FLOOR_F,
    PASSIVE_REGEN_EFFECTIVE_HIGH_F,
    PASSIVE_REGEN_FAILURE_FLOOR_F,
)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE COMPONENT SCORERS
# Each scores one dimension of passive regen health on a 0.0-1.0 scale.
# Parent function composes these with weights — keep each under 25 lines.
# ─────────────────────────────────────────────────────────────────────────────

def _score_exhaust_temp(row: dict, engine_family: str) -> float:
    """Score exhaust temp during non-regen operation against family passive range.

    Core signal: is this truck running hot enough passively to oxidize soot?
    Only meaningful when regen_active = 0 — active regen temps are a different beast.
    """
    if row.get('regen_active', 0) == 1:
        return 0.5  # active regen in progress — this component is neutral

    floor = PASSIVE_REGEN_FLOOR_F[engine_family]
    high  = PASSIVE_REGEN_EFFECTIVE_HIGH_F[engine_family]
    fail  = PASSIVE_REGEN_FAILURE_FLOOR_F[engine_family]
    temp  = row.get('dpf_inlet_temp_f', 0)

    if temp >= floor:
        # In passive regen range — scale linearly to 1.0 at the effective high
        return min(1.0, (temp - floor) / (high - floor))
    elif temp >= fail:
        return 0.3   # marginal — approaching range but not there
    else:
        return 0.0   # below failure floor — passive regen not occurring


def _score_idle(row: dict) -> float:
    """Score idle percentage — high idle means no highway temps, no passive regen.

    Short-haul + high idle is one of the three legs of the fastest DPF clogging
    combination (domain rule). City trucks dependent on forced regens to survive.
    """
    idle = row.get('idle_time_pct', 50)
    if idle <= 10:   return 1.00   # highway runner
    elif idle <= 25: return 0.75   # mixed duty, acceptable
    elif idle <= 40: return 0.45   # city/regional — passive regen marginal
    else:            return 0.10   # heavy idle — passive regen rarely occurring


def _score_regen_frequency(row: dict) -> float:
    """Score forced regen frequency relative to duty cycle.

    If passive regen was working, forced regens would be infrequent.
    A highway truck with 4+ forced regens/week = passive regen was failing to keep up.
    City trucks get more headroom — they're expected to regen more often.
    """
    regens   = row.get('regen_count_7d', 3)
    load_pct = row.get('engine_load_pct', 50)

    if load_pct >= 65:
        # Highway/heavy-load truck — passive should handle most soot oxidation
        if regens <= 1:   return 1.0
        elif regens <= 3: return 0.6
        else:             return 0.2   # forced regen overuse despite heavy load = passive failing
    else:
        # City/lower-load — more forced regens expected as normal
        if regens <= 3:   return 0.8
        elif regens <= 6: return 0.5
        else:             return 0.2


def _score_egt_delta(row: dict) -> float:
    """Score EGT spread between DPF inlet and outlet during passive operation.

    Wide delta during normal operation (not active regen) can indicate early
    ash channeling — heat concentrates in one flow path rather than distributing
    evenly. Domain rule: EGT spread > 150°F is an early ash channeling signal.
    """
    if row.get('regen_active', 0) == 1:
        return 0.5  # delta during active regen is always large — neutral

    inlet  = row.get('dpf_inlet_temp_f', 0)
    outlet = row.get('dpf_outlet_temp_peak_f', 0)

    if inlet == 0 or outlet == 0:
        return 0.5  # can't score delta without both readings

    delta = abs(inlet - outlet)
    if delta > 150:  return 0.1   # early ash channeling indicator
    elif delta > 100: return 0.5  # worth watching
    else:            return 1.0   # normal spread


def _score_fuel_quality(row: dict) -> float:
    """Score fuel quality impact using proxy signals from CLAUDE.md CSV spec.

    fuel_quality_score is not a direct J1939 signal — use water contamination
    flag and filter change frequency as observable proxies. Poor fuel accelerates
    soot production and incomplete combustion, degrading passive regen efficiency.
    Domain rule: poor fuel is the third leg of the fastest DPF clogging combination.
    """
    if row.get('water_in_fuel_detected', False):
        return 0.1   # active contamination — serious

    days = row.get('fuel_filter_change_frequency_days', 90)
    if days < 30:    return 0.3   # changing filter constantly = consistently dirty fuel
    elif days < 45:  return 0.6   # frequent, worth watching
    else:            return 1.0   # normal interval — fuel quality likely acceptable


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE SCORER — thin parent, delegates entirely to component functions
# ─────────────────────────────────────────────────────────────────────────────

def calculate_passive_regen_score(row: dict, engine_family: str) -> float:
    """
    Score a truck's passive regen health on a 0.0-1.0 scale.
    See module docstring for full input column list.

    Returns:
        float: 0.0 (passive regen failing) to 1.0 (passive regen healthy)
    """
    components = [
        (_score_exhaust_temp(row, engine_family), 0.35),  # primary signal
        (_score_regen_frequency(row),             0.25),  # forced regen overuse
        (_score_idle(row),                        0.20),  # duty cycle
        (_score_egt_delta(row),                   0.10),  # ash channeling early signal
        (_score_fuel_quality(row),                0.10),  # third leg of clogging combo
    ]
    return round(sum(score * weight for score, weight in components), 3)


# ─────────────────────────────────────────────────────────────────────────────
# FAILURE PATTERN DETECTION — private checkers, one per pattern
# Each returns a result dict if the pattern matches, None if it doesn't.
# ─────────────────────────────────────────────────────────────────────────────

def _check_low_temp_duty_cycle(row: dict, engine_family: str) -> dict | None:
    """Pattern: city/stop-and-go truck — exhaust temps never reach passive regen range."""
    fail_floor = PASSIVE_REGEN_FAILURE_FLOOR_F[engine_family]
    if (row.get('idle_time_pct', 0) > 35
            and row.get('dpf_inlet_temp_f', 0) < fail_floor
            and row.get('regen_active', 0) == 0):
        return {
            'failure_detected': True,
            'failure_type': 'LOW_TEMP_DUTY_CYCLE',
            'recommendation': (
                'Truck operating in stop-and-go conditions. Exhaust temps too low for '
                'passive regen. Soot accumulating between forced regens. '
                'Consider scheduled highway runs or more frequent DPF service intervals.'
            ),
        }
    return None


def _check_highway_passive_failure(row: dict, engine_family: str) -> dict | None:
    """Pattern: highway truck forcing too many regens — passive not keeping up."""
    if (row.get('engine_load_pct', 0) >= 65
            and row.get('regen_count_7d', 0) >= 4
            and row.get('regen_active', 0) == 0):
        return {
            'failure_detected': True,
            'failure_type': 'PASSIVE_INSUFFICIENT_HIGHWAY',
            'recommendation': (
                f'Highway-duty truck ({engine_family}) initiating forced regens too frequently. '
                'Passive regen not sustaining soot oxidation at expected highway temps. '
                'Inspect DOC catalyst efficiency and fuel quality.'
            ),
        }
    return None


def _check_marginal_passive_temp(row: dict, engine_family: str) -> dict | None:
    """Pattern: exhaust temps at edge of passive regen range — incomplete or intermittent burn."""
    floor      = PASSIVE_REGEN_FLOOR_F[engine_family]
    fail_floor = PASSIVE_REGEN_FAILURE_FLOOR_F[engine_family]
    temp       = row.get('dpf_inlet_temp_f', 0)

    if fail_floor <= temp < floor and row.get('regen_active', 0) == 0:
        return {
            'failure_detected': True,
            'failure_type': 'MARGINAL_PASSIVE_TEMP',
            'recommendation': (
                'Exhaust temps marginally below passive regen threshold. '
                'Passive regen may be incomplete or intermittent. '
                'Monitor soot load trend — if climbing, inspect DOC and fuel system.'
            ),
        }
    return None


def detect_passive_regen_failure(row: dict, engine_family: str) -> dict:
    """
    Identify the specific passive regen failure pattern for a truck.
    Returns the first matching pattern, or a clean no-failure dict.
    """
    checkers = [
        _check_low_temp_duty_cycle(row, engine_family),
        _check_highway_passive_failure(row, engine_family),
        _check_marginal_passive_temp(row, engine_family),
    ]
    for result in checkers:
        if result is not None:
            return result

    return {'failure_detected': False, 'failure_type': None, 'recommendation': None}


# ─────────────────────────────────────────────────────────────────────────────
# BATCH SCORING — apply to full fleet DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def score_fleet_passive_regen(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add passive regen score and failure columns to a fleet DataFrame.

    Expects an 'engine_family' column (DETROIT / VOLVO_MACK / CUMMINS_PACCAR).
    Missing engine_family defaults to CUMMINS_PACCAR (most conservative thresholds).

    Adds four columns:
        passive_regen_score     — 0.0 to 1.0
        passive_regen_failure   — True/False
        passive_failure_type    — failure pattern string or None
        passive_recommendation  — action string or None
    """
    df = df.copy()

    scores, failures, types, recs = [], [], [], []

    for _, row in df.iterrows():
        family = row.get('engine_family', 'CUMMINS_PACCAR')
        score  = calculate_passive_regen_score(row, family)
        info   = detect_passive_regen_failure(row, family)

        scores.append(score)
        failures.append(info['failure_detected'])
        types.append(info['failure_type'])
        recs.append(info['recommendation'])

    df['passive_regen_score']    = scores
    df['passive_regen_failure']  = failures
    df['passive_failure_type']   = types
    df['passive_recommendation'] = recs

    failure_count = sum(failures)
    print(f"[passive_regen] Scored {len(df)} trucks | failures detected: {failure_count}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# RISK MODIFIER — adjusts the main risk tier based on passive regen health
# ─────────────────────────────────────────────────────────────────────────────

def apply_passive_regen_modifier(risk_tier: str, passive_score: float) -> str:
    """
    Adjust risk tier based on passive regen health score.

    Rules:
    - CRITICAL and HIGH are never downgraded — hard fault conditions stand
    - MEDIUM can drop to LOW if passive regen is excellent (score >= 0.80)
    - Any tier below HIGH can escalate to MEDIUM if passive regen is failing (score <= 0.25)
    - LOW escalates to MEDIUM when passive score is poor — silent risk building

    Passive score alone cannot push a truck above MEDIUM.
    The main expert system controls CRITICAL and HIGH via hard fault rules.
    """
    if risk_tier in ('CRITICAL', 'HIGH'):
        return risk_tier  # passive history never overrules a hard fault

    if passive_score <= 0.25:
        return 'MEDIUM'   # silent soot buildup — escalate regardless of current tier

    if passive_score >= 0.80 and risk_tier == 'MEDIUM':
        return 'LOW'      # highway truck burning clean — give it credit

    return risk_tier


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 65)
    print("ThrottleGuard — Passive Regen Module Test")
    print("=" * 65)

    test_trucks = [
        {
            'name': 'Highway DD15 (healthy)',
            'engine_family':                    'DETROIT',
            'dpf_inlet_temp_f':                 655,
            'dpf_outlet_temp_peak_f':           620,
            'regen_active':                     0,
            'idle_time_pct':                    8,
            'engine_load_pct':                  75,
            'regen_count_7d':                   1,
            'water_in_fuel_detected':           False,
            'fuel_filter_change_frequency_days': 90,
        },
        {
            'name': 'City MP8 (passive regen failing)',
            'engine_family':                    'VOLVO_MACK',
            'dpf_inlet_temp_f':                 480,
            'dpf_outlet_temp_peak_f':           450,
            'regen_active':                     0,
            'idle_time_pct':                    45,
            'engine_load_pct':                  35,
            'regen_count_7d':                   7,
            'water_in_fuel_detected':           False,
            'fuel_filter_change_frequency_days': 28,
        },
        {
            'name': 'Highway X15 (marginal passive)',
            'engine_family':                    'CUMMINS_PACCAR',
            'dpf_inlet_temp_f':                 560,
            'dpf_outlet_temp_peak_f':           390,  # wide delta — ash channeling signal
            'regen_active':                     0,
            'idle_time_pct':                    20,
            'engine_load_pct':                  68,
            'regen_count_7d':                   5,
            'water_in_fuel_detected':           True,
            'fuel_filter_change_frequency_days': 90,
        },
    ]

    for truck in test_trucks:
        family  = truck['engine_family']
        score   = calculate_passive_regen_score(truck, family)
        failure = detect_passive_regen_failure(truck, family)
        adjusted_tier = apply_passive_regen_modifier('MEDIUM', score)

        print(f"\nTruck: {truck['name']}")
        print(f"  Passive Regen Score : {score}")
        print(f"  Failure Detected    : {failure['failure_detected']}")
        print(f"  Failure Type        : {failure['failure_type']}")
        print(f"  Adjusted Risk Tier  : MEDIUM -> {adjusted_tier}")
        if failure['recommendation']:
            print(f"  Recommendation      : {failure['recommendation'][:90]}...")

    print("\n" + "=" * 65)
    print("Passive Regen Thresholds by Engine Family")
    print("=" * 65)
    for family in ['DETROIT', 'VOLVO_MACK', 'CUMMINS_PACCAR']:
        print(f"\n{family}")
        print(f"  Passive floor        : {PASSIVE_REGEN_FLOOR_F[family]}°F")
        print(f"  Effective high       : {PASSIVE_REGEN_EFFECTIVE_HIGH_F[family]}°F")
        print(f"  Failure floor        : {PASSIVE_REGEN_FAILURE_FLOOR_F[family]}°F")
