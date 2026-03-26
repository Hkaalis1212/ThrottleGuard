"""
throttleguard_scr_data_generator.py
------------------------------------
Generates synthetic DEF/SCR health data for ThrottleGuard's SCR module.

TWO prediction targets:
  1. scr_catalyst_risk   — days until SCR catalyst needs service (slow degradation)
  2. def_runout_risk     — likelihood of DEF runout causing derating (short-term)

═══════════════════════════════════════════════════════════════════
CRITICAL — REGEN ACTIVE FLAG
═══════════════════════════════════════════════════════════════════
The J1939 CAN bus broadcasts continuously, but regen temperature readings
are only meaningful during an active regen event. Outside of a regen the
EGT sensors are reading normal exhaust temps — a 700°F reading when the
truck is NOT regenerating tells you nothing about DPF health and must NOT
trigger a low-temp alert.

ThrottleGuard uses the regen_active flag (sourced from J1939 PGN 64892)
to gate all regen-temperature-based logic:

  regen_active = 1  → regen temp readings are valid, apply thresholds
  regen_active = 0  → regen temp readings are IGNORED, no temp-based alerts

This prevents a flood of false CRITICAL flags every time a truck is
cruising at normal exhaust temps (~400-700°F) between regens.

In synthetic data: regen_active is simulated probabilistically.
In real J1939 data: filter on PGN 64892 regen status flag before
feeding rows into the model or threshold checks.

Features used (J1939-sourced):
  - regen_active                : 1 = active regen, 0 = normal operation
  - def_level_pct               : current DEF tank level
  - def_consumption_rate_lph    : liters per hour (rising = dosing compensation)
  - scr_inlet_temp_f            : temp entering SCR catalyst (valid during regen only)
  - scr_outlet_temp_f           : temp exiting SCR catalyst (valid during regen only)
  - scr_temp_delta_f            : delta across catalyst (valid during regen only)
  - nox_ppm                     : raw NOx — always valid, not regen-gated
  - engine_hours_total          : total engine hours
  - idle_pct                    : high idle = low SCR temps = urea crystal deposits
  - engine_load_pct             : load affects exhaust temp window
  - ambient_temp_f              : cold weather drops SCR below activation threshold
  - engine_family_encoded       : integer-encoded platform family (3 families)

Domain knowledge encoded:
  - SCR activation temp: ~400-600°F inlet — below this, urea doesn't convert
  - DD15 is extremely DEF-sensitive; X15 burns more DEF at higher loads
  - High idle deposits urea crystals (ammonia slip at low temps)
  - Catalyst degrades faster with thermal cycling and sulfur poisoning
  - DEF runout derates engine to ~5 mph
  - Temp readings ONLY meaningful during active regen (PGN 64892 flag)
"""

import pandas as pd
import numpy as np
import random

# Import the single source of truth for engine families and thresholds
# Never hardcode engine family mappings here — use the thresholds file
from throttleguard_engine_thresholds import (
    ENGINE_FAMILY_ENCODING,
    ENGINE_FAMILY_DECODING,
    ENGINE_FAMILY_DISPLAY_NAMES,
    REGEN_WARMUP_FLOOR_F,
    REGEN_HIGH_WARNING_F,
    REGEN_HIGH_CRITICAL_F,
    REGEN_TRANSITION_FLOOR_F,
    REGEN_PHASE_ENCODING,
)

# Seed for reproducibility
np.random.seed(42)
random.seed(42)

# -------------------------------------------------------------------
# Engine family profiles — DEF consumption and SCR temp behavior
# Keyed by canonical family name matching ENGINE_FAMILY_ENCODING
# -------------------------------------------------------------------
ENGINE_PROFILES = {
    'DETROIT': {
        'base_def_consumption_lph': 0.9,    # higher baseline — emissions-focused 1-Box
        'scr_inlet_temp_range':     (420, 780),
        'nox_baseline_ppm':         180,
        'def_sensitivity':          'high', # most affected by DEF quality issues
    },
    'VOLVO_MACK': {
        'base_def_consumption_lph': 0.81,   # Volvo/Mack shared platform — moderate consumption
        'scr_inlet_temp_range':     (400, 745),
        'nox_baseline_ppm':         173,
        'def_sensitivity':          'low',
    },
    'CUMMINS_PACCAR': {
        'base_def_consumption_lph': 0.98,   # Cummins/PACCAR — higher at load, confirmed same family
        'scr_inlet_temp_range':     (435, 790),
        'nox_baseline_ppm':         203,
        'def_sensitivity':          'medium',
    },
}

# Probability a given snapshot was taken during an active regen
# Real fleets: regens happen roughly every 4-8 hours of operation
# ~15-20% of snapshots will be during an active regen
REGEN_ACTIVE_PROBABILITY = 0.18


# -------------------------------------------------------------------
# SCR catalyst risk thresholds (mirrors DPF logic)
# -------------------------------------------------------------------
def assign_scr_catalyst_risk(days_to_service):
    """
    Classify catalyst health risk by days until service needed.
    Same tier structure as DPF for consistency across the dashboard.
    """
    if days_to_service <= 3:
        return 'CRITICAL'   # Catalyst failing NOW
    elif days_to_service <= 7:
        return 'HIGH'       # Schedule service this week
    elif days_to_service <= 21:
        return 'MEDIUM'     # Plan within 3 weeks
    else:
        return 'LOW'        # Monitor normally


# -------------------------------------------------------------------
# DEF runout risk thresholds (short-term, hours-based)
# -------------------------------------------------------------------
def assign_def_runout_risk(hours_to_empty):
    """
    Classify DEF runout risk by estimated hours until tank empty.
    DEF runout = engine derates to ~5 mph.
    """
    if hours_to_empty <= 4:
        return 'CRITICAL'   # Fill NOW
    elif hours_to_empty <= 12:
        return 'HIGH'       # Fill at next stop
    elif hours_to_empty <= 24:
        return 'MEDIUM'     # Fill today
    else:
        return 'LOW'        # Adequate supply


# -------------------------------------------------------------------
# Main data generation function
# -------------------------------------------------------------------
def generate_scr_data(n_trucks=1500):
    """
    Generate synthetic SCR/DEF health records.
    Each row = one truck's current snapshot.

    REGEN ACTIVE FLAG BEHAVIOR:
      - regen_active = 1: SCR temps are simulated as regen-valid readings
      - regen_active = 0: SCR temps are simulated as normal exhaust temps
        (~300-700°F) and are NOT used for threshold evaluation.
        The model learns to ignore temp features when regen_active = 0.

    When integrating real J1939 data:
      - Source regen_active from PGN 64892 regen status flag
      - Only pass regen_temp_f values to threshold checks when regen_active = 1
      - Never alert on low regen temps during normal operation
    """
    rows = []
    family_keys = list(ENGINE_PROFILES.keys())

    for i in range(n_trucks):
        family = random.choice(family_keys)
        profile = ENGINE_PROFILES[family]

        # --- Base operating conditions ---
        engine_hours_total = np.random.uniform(5000, 750000)
        idle_pct           = np.random.uniform(5, 45)
        engine_load_pct    = np.random.uniform(30, 95)
        ambient_temp_f     = np.random.uniform(-10, 105)

        # --- SCR catalyst degradation score ---
        catalyst_age_factor  = min(engine_hours_total / 300000, 1.0)
        idle_stress_factor   = idle_pct / 45.0
        catalyst_degradation = (catalyst_age_factor * 0.6) + (idle_stress_factor * 0.4)
        catalyst_degradation = np.clip(
            catalyst_degradation + np.random.normal(0, 0.05), 0, 1
        )

        # --- Regen phase classification (temp-based, per family) ---
        # Phase is determined by where the truck is in its regen cycle.
        # NOT time-based — each family runs on its own clock depending on
        # soot load, ambient temp, and duty cycle.
        #
        # warmup   = DOC heating up, below active floor, no threshold evaluation
        # active   = sustained burn, CRITICAL+HIGH alerts enabled
        # cooldown = temps falling from peak, suppress CRITICAL+HIGH
        # no_regen = normal operation between regens, all temp alerts suppressed
        #
        # ~18% of snapshots during a regen event, distributed across phases
        # ~82% of snapshots are normal operation (no_regen)
        regen_roll = random.random()
        warmup_floor = REGEN_WARMUP_FLOOR_F[family]
        high_warn    = REGEN_HIGH_WARNING_F[family]
        high_crit    = REGEN_HIGH_CRITICAL_F[family]
        low_floor    = REGEN_TRANSITION_FLOOR_F

        if regen_roll < 0.82:
            # Normal operation — no regen in progress
            regen_phase = 'no_regen'
            # Normal exhaust temps: ~300-700°F, load-dependent
            temp_penalty     = max(0, (32 - ambient_temp_f) * 1.2) if ambient_temp_f < 32 else 0
            normal_base      = 300 + (engine_load_pct * 3.5) - temp_penalty
            regen_avg_temp_f = np.clip(normal_base + np.random.normal(0, 40), 250, 720)

        elif regen_roll < 0.88:
            # Warmup phase — DOC heating, below active floor
            regen_phase      = 'warmup'
            regen_avg_temp_f = np.random.uniform(350, warmup_floor)

        elif regen_roll < 0.96:
            # Active phase — sustained regen burn, thresholds apply here
            # Average temp across the active burn window (not a single snapshot)
            # Degraded catalyst = harder to sustain high temps consistently
            regen_phase  = 'active'
            temp_penalty = max(0, (32 - ambient_temp_f) * 1.5) if ambient_temp_f < 32 else 0
            idle_penalty = idle_pct * 2.0

            # Healthy truck targets the family normal — degraded truck runs lower
            target_temp      = REGEN_WARMUP_FLOOR_F[family] + 200  # midpoint of active range
            degradation_drag = catalyst_degradation * 150           # degraded = lower avg
            regen_avg_temp_f = np.clip(
                target_temp - degradation_drag - temp_penalty - idle_penalty
                + np.random.normal(0, 30),
                low_floor,        # never below universal transition floor
                high_crit + 20    # allow slight overshoot for simulation realism
            )

        else:
            # Cooldown phase — temps falling from peak, suppress CRITICAL+HIGH
            regen_phase      = 'cooldown'
            regen_avg_temp_f = np.random.uniform(warmup_floor - 100, warmup_floor + 50)

        # Encode regen_phase as integer for XGBoost
        # no_regen added to encoding — model needs to learn this state too
        phase_encoding_full = {'no_regen': 3, **REGEN_PHASE_ENCODING}
        regen_phase_encoded = phase_encoding_full[regen_phase]

        # SCR outlet and delta — derived from avg temp (outlet is always cooler)
        scr_outlet_temp_f = regen_avg_temp_f - np.random.uniform(20, 80)
        scr_temp_delta_f  = regen_avg_temp_f - scr_outlet_temp_f

        # --- DEF consumption ---
        base_consumption        = profile['base_def_consumption_lph']
        compensation_multiplier = 1.0 + (catalyst_degradation * 0.6)
        load_multiplier         = 0.7 + (engine_load_pct / 100) * 0.6

        def_consumption_rate_lph = max(
            base_consumption * compensation_multiplier * load_multiplier
            + np.random.normal(0, 0.05),
            0.1
        )

        # --- DEF level ---
        def_level_base = np.random.uniform(5, 100)
        if catalyst_degradation > 0.7:
            def_level_base = min(def_level_base, np.random.uniform(10, 55))
        def_level_pct = np.clip(def_level_base, 0, 100)

        # --- Hours until DEF empty ---
        tank_remaining_liters = (def_level_pct / 100) * 56.8  # ~15 gallon Class 8 tank
        hours_to_def_empty    = np.clip(
            tank_remaining_liters / def_consumption_rate_lph if def_consumption_rate_lph > 0 else 999,
            0, 200
        )

        # --- NOx — always valid, not regen-gated ---
        nox_ppm = max(
            profile['nox_baseline_ppm'] * (1 + catalyst_degradation * 1.8)
            + np.random.normal(0, 15),
            50
        )

        # --- Days until SCR catalyst service ---
        remaining_life_fraction = max(0, 1 - catalyst_degradation)
        days_to_scr_service     = np.clip(
            remaining_life_fraction * 180 + np.random.normal(0, 8), 1, 180
        )

        # --- Assign labels ---
        scr_catalyst_risk = assign_scr_catalyst_risk(days_to_scr_service)
        def_runout_risk   = assign_def_runout_risk(hours_to_def_empty)

        rows.append({
            # Identifiers
            'truck_id':                   f'TRK-{1000 + i}',
            'engine_family':              family,
            'engine_family_encoded':      ENGINE_FAMILY_ENCODING[family],

            # Regen phase — gates threshold evaluation
            # no_regen=3, warmup=0, active=1, cooldown=2
            # CRITICAL+HIGH alerts only fire during active phase (encoded=1)
            # Source from J1939 PGN 64892 in real data
            'regen_phase':                regen_phase,
            'regen_phase_encoded':        regen_phase_encoded,

            # Primary DPF health temp feature — average across active regen phase
            # Replaces scr_inlet_temp_f (single snapshot) entirely
            # In real data: mean(temp readings where regen_phase='active') per event
            'regen_avg_temp_f':           round(regen_avg_temp_f, 1),

            # SCR outlet and delta — derived from regen_avg_temp_f
            'scr_outlet_temp_f':          round(scr_outlet_temp_f, 1),
            'scr_temp_delta_f':           round(scr_temp_delta_f, 1),

            # DEF/SCR features — always valid regardless of regen phase
            'def_level_pct':              round(def_level_pct, 1),
            'def_consumption_rate_lph':   round(def_consumption_rate_lph, 3),
            'nox_ppm':                    round(nox_ppm, 1),

            # Supporting context
            'engine_hours_total':         round(engine_hours_total, 0),
            'idle_pct':                   round(idle_pct, 1),
            'engine_load_pct':            round(engine_load_pct, 1),
            'ambient_temp_f':             round(ambient_temp_f, 1),

            # Intermediate values (debug only — exclude from model training)
            'catalyst_degradation_score': round(catalyst_degradation, 3),
            'hours_to_def_empty':         round(hours_to_def_empty, 1),
            'days_to_scr_service':        round(days_to_scr_service, 1),

            # Target labels
            'scr_catalyst_risk':          scr_catalyst_risk,
            'def_runout_risk':            def_runout_risk,
        })

    df = pd.DataFrame(rows)
    return df


# -------------------------------------------------------------------
# Run and save
# -------------------------------------------------------------------
if __name__ == '__main__':
    print("Generating SCR/DEF synthetic dataset...")
    df = generate_scr_data(n_trucks=1500)

    print("\n--- Engine Family Distribution ---")
    print(df['engine_family'].value_counts())

    print("\n--- Regen Phase Distribution ---")
    print(df['regen_phase'].value_counts())
    active_pct = (df['regen_phase'] == 'active').mean() * 100
    print(f"  ({active_pct:.1f}% of snapshots during active regen)")

    print("\n--- SCR Catalyst Risk Distribution ---")
    print(df['scr_catalyst_risk'].value_counts())

    print("\n--- DEF Runout Risk Distribution ---")
    print(df['def_runout_risk'].value_counts())

    print(f"\nTotal rows: {len(df)}")

    output_path = 'throttleguard_scr_data.csv'
    df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")
