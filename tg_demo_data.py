"""
tg_demo_data.py
---------------
Pre-built demo fleet for ThrottleGuard.
30 trucks across all three engine families with a realistic risk spread.

Risk distribution:
  CRITICAL  5 trucks  — do not dispatch, clear failure signals
  HIGH      8 trucks  — service this week
  MEDIUM    9 trucks  — watch list
  LOW       8 trucks  — healthy

Sensor values are deliberately chosen to fire specific expert system rules
so the demo shows meaningful triggered_rules and confidence output.

Call:  df = get_demo_fleet()
       Returns a DataFrame ready to pass to run_expert_system() or score_row()
"""

import pandas as pd

# ── Demo fleet definition ─────────────────────────────────────────────────────
# Each dict = one truck. Values chosen to hit specific scoring rules.
# See dpf_expert_system.py rules 1-10 for threshold reference.

DEMO_TRUCKS = [

    # ══════════════════════════════════════════════════════
    # CRITICAL — 5 trucks
    # ══════════════════════════════════════════════════════

    {   # DPF: Rule 1 (+60) + Rule 4 (+30) + Rule 10 (+10). SCR: Rule 11 NOx critical (+40). Compound 1-Box (+20). Capped 100.
        # Compound aftertreatment failure — incomplete regen poisoned SCR catalyst
        "vehicle_id": "TRK-001", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 867,   # well below 940 — clear clogging
        "dpf_outlet_temp_peak_f": 1120,
        "dpf_inlet_temp_f": 980,
        "regen_count_7d": 4,                     # >2 — excessive
        "back_pressure_inh2o": 5.8,              # >4.0 — elevated
        "driver_reported_frequent_regen": 1,
        "mileage_since_last_dpf_cleaning": 210000,
        "oil_consumption_qt_per_1000mi": 0.3,
        "turbo_boost_psi": 28, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 45, "idle_time_pct": 18,
        "def_quality_ppm": 20, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 90,
        # SCR sensors — NOx breakthrough from HC poisoning the catalyst
        "nox_upstream_ppm": 480, "nox_downstream_ppm": 273, "nox_conversion_pct": 43,
        "scr_inlet_temp_f": 565, "def_concentration_pct": 32.4, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 1 (+60) + Rule 5 (+25) + Rule 6 (+25). SCR: Rule 14 DEF conc critical (+25). Compound (+15). Capped 100.
        # DEF tank contaminated — water substitution detected, catalyst starved of urea
        "vehicle_id": "TRK-007", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 891,
        "dpf_outlet_temp_peak_f": 1080,
        "dpf_inlet_temp_f": 955,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 3.1,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 340000,  # >300k
        "oil_consumption_qt_per_1000mi": 0.7,        # >0.5 — ash rule fires
        "turbo_boost_psi": 16,                       # <20 — turbo rule fires
        "egr_flow_fault": 0,
        "avg_trip_distance_mi": 320, "idle_time_pct": 12,
        "def_quality_ppm": 25, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 120,
        # SCR sensors — critically diluted DEF (likely water contamination in tank)
        "nox_upstream_ppm": 510, "nox_downstream_ppm": 390, "nox_conversion_pct": 76,
        "scr_inlet_temp_f": 488, "def_concentration_pct": 17.8, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 3 sensor fault (+70). SCR: healthy — fault is DPF-side sensor only.
        "vehicle_id": "TRK-012", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 430,   # <500 — impossible low
        "dpf_outlet_temp_peak_f": 1050,
        "dpf_inlet_temp_f": 1080,                # >1000 — sensor fault confirmed
        "regen_count_7d": 1,
        "back_pressure_inh2o": 2.2,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 180000,
        "oil_consumption_qt_per_1000mi": 0.2,
        "turbo_boost_psi": 32, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 280, "idle_time_pct": 15,
        "def_quality_ppm": 18, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 75,
        # SCR sensors — healthy (DPF sensor fault, SCR functioning normally)
        "nox_upstream_ppm": 440, "nox_downstream_ppm": 44, "nox_conversion_pct": 90,
        "scr_inlet_temp_f": 512, "def_concentration_pct": 32.6, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 1 (+60) + Rule 4 (+30) + Rule 10 (+10). SCR: Rule 11 NOx critical (+40) + Rule 13 SCR cold (+15) + Rule 15 NH3 (+10). Compound (+15). Capped 100.
        # Full aftertreatment collapse — DPF clogged, SCR below light-off, catalyst non-functional
        "vehicle_id": "TRK-019", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 843,   # very low — active clogging
        "dpf_outlet_temp_peak_f": 1090,
        "dpf_inlet_temp_f": 970,
        "regen_count_7d": 5,                     # extremely frequent
        "back_pressure_inh2o": 6.2,              # high backpressure
        "driver_reported_frequent_regen": 1,
        "mileage_since_last_dpf_cleaning": 290000,
        "oil_consumption_qt_per_1000mi": 0.4,
        "turbo_boost_psi": 25, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 38, "idle_time_pct": 22,
        "def_quality_ppm": 30, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 60,
        # SCR sensors — NOx breakthrough + catalyst below light-off temp + NH3 slip
        "nox_upstream_ppm": 520, "nox_downstream_ppm": 327, "nox_conversion_pct": 37,
        "scr_inlet_temp_f": 378, "def_concentration_pct": 32.2, "nh3_slip_detected": 1,
    },
    {   # DPF: Rule 2 thermal shock (+50) + Rule 4 (+30). SCR: Rule 12 NOx warn (+20) + Compound 1-Box (+20). = 120 → capped 100.
        # Detroit 1-Box — thermal shock in shared housing degraded SCR catalyst
        "vehicle_id": "TRK-023", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1010,
        "dpf_outlet_temp_peak_f": 1265,          # >1250 Detroit critical — thermal shock
        "dpf_inlet_temp_f": 1050,
        "regen_count_7d": 3,                     # >2 — frequent
        "back_pressure_inh2o": 2.8,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 155000,
        "oil_consumption_qt_per_1000mi": 0.3,
        "turbo_boost_psi": 30, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 410, "idle_time_pct": 10,
        "def_quality_ppm": 15, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 90,
        # SCR sensors — thermal event damaged catalyst in shared 1-Box housing
        "nox_upstream_ppm": 495, "nox_downstream_ppm": 228, "nox_conversion_pct": 54,
        "scr_inlet_temp_f": 498, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },

    # ══════════════════════════════════════════════════════
    # HIGH — 8 trucks
    # ══════════════════════════════════════════════════════

    {   # DPF: Rule 4 (+30) + Rule 6 (+25) = 55. SCR: healthy.
        "vehicle_id": "TRK-003", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 995,
        "dpf_outlet_temp_peak_f": 1080,
        "dpf_inlet_temp_f": 1010,
        "regen_count_7d": 3,
        "back_pressure_inh2o": 2.5,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 200000,
        "oil_consumption_qt_per_1000mi": 0.3,
        "turbo_boost_psi": 17,                   # <20 — turbo rule fires
        "egr_flow_fault": 0,
        "avg_trip_distance_mi": 290, "idle_time_pct": 14,
        "def_quality_ppm": 22, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 80,
        "nox_upstream_ppm": 420, "nox_downstream_ppm": 71, "nox_conversion_pct": 83,
        "scr_inlet_temp_f": 538, "def_concentration_pct": 32.7, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 5 (+25) + Rule 6 EGR (+25) = 50. SCR: healthy.
        "vehicle_id": "TRK-008", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1035,
        "dpf_outlet_temp_peak_f": 1140,
        "dpf_inlet_temp_f": 1060,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 2.1,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 325000,  # >300k
        "oil_consumption_qt_per_1000mi": 0.65,      # >0.5 — ash fires
        "turbo_boost_psi": 28,
        "egr_flow_fault": 1,                        # EGR fault fires
        "avg_trip_distance_mi": 380, "idle_time_pct": 11,
        "def_quality_ppm": 20, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 100,
        "nox_upstream_ppm": 465, "nox_downstream_ppm": 60, "nox_conversion_pct": 87,
        "scr_inlet_temp_f": 562, "def_concentration_pct": 32.4, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 4 (+30) + Rule 8 DEF contamination (+15) = 45. SCR: healthy.
        "vehicle_id": "TRK-015", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1005,
        "dpf_outlet_temp_peak_f": 1100,
        "dpf_inlet_temp_f": 1020,
        "regen_count_7d": 3,
        "back_pressure_inh2o": 1.8,
        "driver_reported_frequent_regen": 1,
        "mileage_since_last_dpf_cleaning": 190000,
        "oil_consumption_qt_per_1000mi": 0.3,
        "turbo_boost_psi": 29, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 55, "idle_time_pct": 20,
        "def_quality_ppm": 65,                   # >50 — DEF contamination fires
        "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 70,
        "nox_upstream_ppm": 438, "nox_downstream_ppm": 75, "nox_conversion_pct": 83,
        "scr_inlet_temp_f": 544, "def_concentration_pct": 32.8, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 5 (+25) + Rule 6 EGR (+25) = 50. SCR: healthy.
        "vehicle_id": "TRK-022", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 1000,
        "dpf_outlet_temp_peak_f": 1110,
        "dpf_inlet_temp_f": 1005,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 3.5,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 310000,
        "oil_consumption_qt_per_1000mi": 0.55,
        "turbo_boost_psi": 26,
        "egr_flow_fault": 1,
        "avg_trip_distance_mi": 440, "idle_time_pct": 9,
        "def_quality_ppm": 28, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 85,
        "nox_upstream_ppm": 448, "nox_downstream_ppm": 67, "nox_conversion_pct": 85,
        "scr_inlet_temp_f": 518, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 4 (+30) + Rule 7 duty cycle (+15) = 45. SCR: healthy.
        "vehicle_id": "TRK-027", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1045,
        "dpf_outlet_temp_peak_f": 1095,
        "dpf_inlet_temp_f": 1055,
        "regen_count_7d": 4,
        "back_pressure_inh2o": 2.0,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 140000,
        "oil_consumption_qt_per_1000mi": 0.2,
        "turbo_boost_psi": 27, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 11,              # <15 — short trip
        "idle_time_pct": 42,                     # >35 — high idle, duty cycle fires
        "def_quality_ppm": 30, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 90,
        "nox_upstream_ppm": 455, "nox_downstream_ppm": 82, "nox_conversion_pct": 82,
        "scr_inlet_temp_f": 550, "def_concentration_pct": 32.3, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 6 turbo (+25) + Rule 10 (+10) + Rule 8 DEF (+15) = 50. SCR: healthy.
        "vehicle_id": "TRK-031", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1008,
        "dpf_outlet_temp_peak_f": 1130,
        "dpf_inlet_temp_f": 1025,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 4.5,              # >4.0 — backpressure fires
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 220000,
        "oil_consumption_qt_per_1000mi": 0.35,
        "turbo_boost_psi": 14,                   # <20 — turbo fires
        "egr_flow_fault": 0,
        "avg_trip_distance_mi": 200, "idle_time_pct": 18,
        "def_quality_ppm": 72,                   # >50 — DEF contamination fires
        "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 95,
        "nox_upstream_ppm": 442, "nox_downstream_ppm": 71, "nox_conversion_pct": 84,
        "scr_inlet_temp_f": 530, "def_concentration_pct": 32.6, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 5 (+25) + Rule 9 fuel (+10) + Rule 10 (+10) = 45. SCR: healthy.
        "vehicle_id": "TRK-035", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 998,
        "dpf_outlet_temp_peak_f": 1090,
        "dpf_inlet_temp_f": 1008,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 4.2,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 305000,
        "oil_consumption_qt_per_1000mi": 0.58,
        "turbo_boost_psi": 31, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 350, "idle_time_pct": 16,
        "def_quality_ppm": 30, "def_doser_fault": 0,
        "water_in_fuel_detected": 1,             # water in fuel fires
        "fuel_filter_change_frequency_days": 110,
        "nox_upstream_ppm": 430, "nox_downstream_ppm": 60, "nox_conversion_pct": 86,
        "scr_inlet_temp_f": 522, "def_concentration_pct": 32.7, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 4 (+30) + Rule 6 turbo (+25) = 55. SCR: healthy.
        "vehicle_id": "TRK-041", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 988,
        "dpf_outlet_temp_peak_f": 1070,
        "dpf_inlet_temp_f": 1000,
        "regen_count_7d": 3,
        "back_pressure_inh2o": 2.3,
        "driver_reported_frequent_regen": 1,
        "mileage_since_last_dpf_cleaning": 175000,
        "oil_consumption_qt_per_1000mi": 0.28,
        "turbo_boost_psi": 18,
        "egr_flow_fault": 0,
        "avg_trip_distance_mi": 180, "idle_time_pct": 20,
        "def_quality_ppm": 25, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 80,
        "nox_upstream_ppm": 452, "nox_downstream_ppm": 54, "nox_conversion_pct": 88,
        "scr_inlet_temp_f": 558, "def_concentration_pct": 32.4, "nh3_slip_detected": 0,
    },

    # ══════════════════════════════════════════════════════
    # MEDIUM — 9 trucks
    # ══════════════════════════════════════════════════════

    {   # DPF: Rule 7 duty (+15) + Rule 8 DEF contamination (+15) = 30. SCR: healthy.
        "vehicle_id": "TRK-005", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1040,
        "dpf_outlet_temp_peak_f": 1085,
        "dpf_inlet_temp_f": 1050,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.5,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 120000,
        "oil_consumption_qt_per_1000mi": 0.2,
        "turbo_boost_psi": 30, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 9,               # <15 — short trips
        "idle_time_pct": 38,                     # >35 — high idle
        "def_quality_ppm": 58,                   # >50 — DEF contamination fires
        "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 80,
        "nox_upstream_ppm": 408, "nox_downstream_ppm": 45, "nox_conversion_pct": 89,
        "scr_inlet_temp_f": 548, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 8 doser fault (+15) + Rule 9 filter (+10) = 25. SCR: healthy.
        "vehicle_id": "TRK-009", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 1002,
        "dpf_outlet_temp_peak_f": 1060,
        "dpf_inlet_temp_f": 1010,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 1.9,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 160000,
        "oil_consumption_qt_per_1000mi": 0.25,
        "turbo_boost_psi": 33, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 250, "idle_time_pct": 15,
        "def_quality_ppm": 20,
        "def_doser_fault": 1,                    # doser fault fires
        "water_in_fuel_detected": 0,
        "fuel_filter_change_frequency_days": 40, # <45 — filter overdue
        "nox_upstream_ppm": 398, "nox_downstream_ppm": 44, "nox_conversion_pct": 89,
        "scr_inlet_temp_f": 534, "def_concentration_pct": 32.8, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 7 duty (+15) + Rule 10 backpressure (+10) = 25. SCR: healthy.
        "vehicle_id": "TRK-014", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1012,
        "dpf_outlet_temp_peak_f": 1095,
        "dpf_inlet_temp_f": 1018,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 4.1,              # just over 4.0
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 95000,
        "oil_consumption_qt_per_1000mi": 0.18,
        "turbo_boost_psi": 26, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 12,              # <15
        "idle_time_pct": 39,                     # >35
        "def_quality_ppm": 18, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 70,
        "nox_upstream_ppm": 418, "nox_downstream_ppm": 50, "nox_conversion_pct": 88,
        "scr_inlet_temp_f": 552, "def_concentration_pct": 32.3, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 9 fuel (+10) + Rule 7 duty (+15) = 25. SCR: healthy.
        "vehicle_id": "TRK-018", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1048,
        "dpf_outlet_temp_peak_f": 1100,
        "dpf_inlet_temp_f": 1055,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.7,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 110000,
        "oil_consumption_qt_per_1000mi": 0.22,
        "turbo_boost_psi": 28, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 8,
        "idle_time_pct": 41,
        "def_quality_ppm": 25, "def_doser_fault": 0,
        "water_in_fuel_detected": 1,             # water in fuel
        "fuel_filter_change_frequency_days": 55,
        "nox_upstream_ppm": 412, "nox_downstream_ppm": 41, "nox_conversion_pct": 90,
        "scr_inlet_temp_f": 540, "def_concentration_pct": 32.6, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 8 DEF contamination (+15) + Rule 10 backpressure (+10) = 25. SCR: healthy.
        "vehicle_id": "TRK-024", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 1005,
        "dpf_outlet_temp_peak_f": 1070,
        "dpf_inlet_temp_f": 1012,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 4.3,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 145000,
        "oil_consumption_qt_per_1000mi": 0.30,
        "turbo_boost_psi": 29, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 190, "idle_time_pct": 18,
        "def_quality_ppm": 80,                   # >50 — elevated contamination
        "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 90,
        "nox_upstream_ppm": 435, "nox_downstream_ppm": 56, "nox_conversion_pct": 87,
        "scr_inlet_temp_f": 528, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 7 duty (+15) + Rule 9 filter (+10) = 25. SCR: healthy.
        "vehicle_id": "TRK-028", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1018,
        "dpf_outlet_temp_peak_f": 1090,
        "dpf_inlet_temp_f": 1022,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 2.0,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 88000,
        "oil_consumption_qt_per_1000mi": 0.15,
        "turbo_boost_psi": 31, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 10,
        "idle_time_pct": 37,
        "def_quality_ppm": 22, "def_doser_fault": 0,
        "water_in_fuel_detected": 0,
        "fuel_filter_change_frequency_days": 38, # <45
        "nox_upstream_ppm": 422, "nox_downstream_ppm": 34, "nox_conversion_pct": 92,
        "scr_inlet_temp_f": 562, "def_concentration_pct": 32.4, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 8 DEF contamination (+15) + Rule 9 water (+10) = 25. SCR: healthy.
        "vehicle_id": "TRK-033", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1052,
        "dpf_outlet_temp_peak_f": 1095,
        "dpf_inlet_temp_f": 1060,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.6,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 130000,
        "oil_consumption_qt_per_1000mi": 0.28,
        "turbo_boost_psi": 30, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 310, "idle_time_pct": 13,
        "def_quality_ppm": 55,
        "def_doser_fault": 0,
        "water_in_fuel_detected": 1,
        "fuel_filter_change_frequency_days": 75,
        "nox_upstream_ppm": 402, "nox_downstream_ppm": 44, "nox_conversion_pct": 89,
        "scr_inlet_temp_f": 544, "def_concentration_pct": 32.7, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 7 duty (+15) + Rule 8 doser fault (+15) = 30. SCR: healthy.
        "vehicle_id": "TRK-038", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 1000,
        "dpf_outlet_temp_peak_f": 1060,
        "dpf_inlet_temp_f": 1008,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 2.2,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 170000,
        "oil_consumption_qt_per_1000mi": 0.32,
        "turbo_boost_psi": 27, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 13,
        "idle_time_pct": 36,
        "def_quality_ppm": 20,
        "def_doser_fault": 1,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 90,
        "nox_upstream_ppm": 415, "nox_downstream_ppm": 37, "nox_conversion_pct": 91,
        "scr_inlet_temp_f": 536, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {   # DPF: Rule 9 filter (+10) + Rule 10 backpressure (+10) = 20. SCR: healthy.
        "vehicle_id": "TRK-042", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1020,
        "dpf_outlet_temp_peak_f": 1080,
        "dpf_inlet_temp_f": 1025,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 4.6,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 95000,
        "oil_consumption_qt_per_1000mi": 0.20,
        "turbo_boost_psi": 28, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 220, "idle_time_pct": 19,
        "def_quality_ppm": 25, "def_doser_fault": 0,
        "water_in_fuel_detected": 0,
        "fuel_filter_change_frequency_days": 42,
        "nox_upstream_ppm": 428, "nox_downstream_ppm": 51, "nox_conversion_pct": 88,
        "scr_inlet_temp_f": 558, "def_concentration_pct": 32.6, "nh3_slip_detected": 0,
    },

    # ══════════════════════════════════════════════════════
    # LOW — 8 trucks
    # ══════════════════════════════════════════════════════

    {   # All healthy — 0 rules fire. Excellent NOx conversion.
        "vehicle_id": "TRK-002", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1010,
        "dpf_outlet_temp_peak_f": 1120,
        "dpf_inlet_temp_f": 1025,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.2,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 85000,
        "oil_consumption_qt_per_1000mi": 0.18,
        "turbo_boost_psi": 32, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 480, "idle_time_pct": 8,
        "def_quality_ppm": 10, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 120,
        "nox_upstream_ppm": 390, "nox_downstream_ppm": 27, "nox_conversion_pct": 93,
        "scr_inlet_temp_f": 572, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-004", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1050,
        "dpf_outlet_temp_peak_f": 1100,
        "dpf_inlet_temp_f": 1060,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.4,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 65000,
        "oil_consumption_qt_per_1000mi": 0.15,
        "turbo_boost_psi": 35, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 520, "idle_time_pct": 7,
        "def_quality_ppm": 8, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 150,
        "nox_upstream_ppm": 375, "nox_downstream_ppm": 19, "nox_conversion_pct": 95,
        "scr_inlet_temp_f": 580, "def_concentration_pct": 32.6, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-006", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 995,
        "dpf_outlet_temp_peak_f": 1070,
        "dpf_inlet_temp_f": 1005,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.8,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 110000,
        "oil_consumption_qt_per_1000mi": 0.20,
        "turbo_boost_psi": 30, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 390, "idle_time_pct": 11,
        "def_quality_ppm": 12, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 90,
        "nox_upstream_ppm": 385, "nox_downstream_ppm": 31, "nox_conversion_pct": 92,
        "scr_inlet_temp_f": 560, "def_concentration_pct": 32.4, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-010", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1005,
        "dpf_outlet_temp_peak_f": 1110,
        "dpf_inlet_temp_f": 1015,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 2.0,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 72000,
        "oil_consumption_qt_per_1000mi": 0.22,
        "turbo_boost_psi": 29, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 440, "idle_time_pct": 9,
        "def_quality_ppm": 15, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 100,
        "nox_upstream_ppm": 402, "nox_downstream_ppm": 24, "nox_conversion_pct": 94,
        "scr_inlet_temp_f": 568, "def_concentration_pct": 32.7, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-016", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1045,
        "dpf_outlet_temp_peak_f": 1095,
        "dpf_inlet_temp_f": 1055,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.3,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 55000,
        "oil_consumption_qt_per_1000mi": 0.12,
        "turbo_boost_psi": 34, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 610, "idle_time_pct": 6,
        "def_quality_ppm": 9, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 130,
        "nox_upstream_ppm": 368, "nox_downstream_ppm": 18, "nox_conversion_pct": 95,
        "scr_inlet_temp_f": 585, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-020", "engine_family": "CUMMINS_PACCAR",
        "dpf_outlet_temp_active_regen_f": 1002,
        "dpf_outlet_temp_peak_f": 1065,
        "dpf_inlet_temp_f": 1010,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.6,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 92000,
        "oil_consumption_qt_per_1000mi": 0.19,
        "turbo_boost_psi": 31, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 370, "idle_time_pct": 12,
        "def_quality_ppm": 11, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 95,
        "nox_upstream_ppm": 378, "nox_downstream_ppm": 30, "nox_conversion_pct": 92,
        "scr_inlet_temp_f": 562, "def_concentration_pct": 32.6, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-029", "engine_family": "DETROIT",
        "dpf_outlet_temp_active_regen_f": 1015,
        "dpf_outlet_temp_peak_f": 1105,
        "dpf_inlet_temp_f": 1020,
        "regen_count_7d": 2,
        "back_pressure_inh2o": 1.9,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 78000,
        "oil_consumption_qt_per_1000mi": 0.21,
        "turbo_boost_psi": 30, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 510, "idle_time_pct": 10,
        "def_quality_ppm": 14, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 110,
        "nox_upstream_ppm": 395, "nox_downstream_ppm": 27, "nox_conversion_pct": 93,
        "scr_inlet_temp_f": 575, "def_concentration_pct": 32.5, "nh3_slip_detected": 0,
    },
    {
        "vehicle_id": "TRK-036", "engine_family": "VOLVO_MACK",
        "dpf_outlet_temp_active_regen_f": 1042,
        "dpf_outlet_temp_peak_f": 1088,
        "dpf_inlet_temp_f": 1052,
        "regen_count_7d": 1,
        "back_pressure_inh2o": 1.5,
        "driver_reported_frequent_regen": 0,
        "mileage_since_last_dpf_cleaning": 48000,
        "oil_consumption_qt_per_1000mi": 0.16,
        "turbo_boost_psi": 33, "egr_flow_fault": 0,
        "avg_trip_distance_mi": 580, "idle_time_pct": 8,
        "def_quality_ppm": 7, "def_doser_fault": 0,
        "water_in_fuel_detected": 0, "fuel_filter_change_frequency_days": 140,
        "nox_upstream_ppm": 372, "nox_downstream_ppm": 22, "nox_conversion_pct": 94,
        "scr_inlet_temp_f": 580, "def_concentration_pct": 32.4, "nh3_slip_detected": 0,
    },
]


def get_demo_fleet() -> pd.DataFrame:
    """Return the 30-truck demo fleet as a DataFrame."""
    return pd.DataFrame(DEMO_TRUCKS)


def get_demo_scored() -> pd.DataFrame:
    """
    Return the demo fleet pre-scored through scoring_engine.
    Ready to pass directly to display_scored_dashboard().
    """
    from scoring_engine import score_row, SCORE_COLUMNS

    df = get_demo_fleet()
    df[SCORE_COLUMNS] = df.apply(score_row, axis=1)
    return df


if __name__ == "__main__":
    df = get_demo_scored()
    print(df[["vehicle_id", "engine_family", "rule_score",
              "priority_label", "failure_mode", "confidence", "triggered_rules"]].to_string())
    print(f"\nDistribution:\n{df['priority_label'].value_counts()}")
