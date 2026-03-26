# ThrottleGuard — Claude Code Context

## Product
ThrottleGuard is a DPF predictive maintenance SaaS platform by AHC Developers.
Founder has ~20 years diesel technician experience. Code must be practical, well-commented, and explainable.

## Business Model
- Sells as a **standalone** product (per-truck/month pricing)
- Also sold as a **bundle** with Fleet Optimizer (TruckFleetOptimizer)
- Integration with Fleet Optimizer is **optional** — gated by THROTTLEGUARD_API_URL env var
- Never build hard dependencies on Fleet Optimizer — ThrottleGuard must work alone

## Tech Stack
- ML: XGBoost (primary), RandomForest (fallback)
- Dashboard: Streamlit
- Data: Pandas, NumPy, Scikit-learn
- Auth: Simple username/password with role-based access (Admin, Technician, Viewer)
- Hosting: Railway
- GitHub: Hkaalis1212 (Windows + Git Bash)

## J1939 Features (core model inputs)
soot_load_pct, diff_pressure_psi, peak_regen_temp_f, regen_completion_rate,
incomplete_regen_streak, regens_last_7_days, nox_ppm, pm_level_mg,
egt_pre_turbo_f, egt_post_turbo_f, egt_pre_dpf_f, egt_post_dpf_f,
egt_dpf_delta_f, def_level_pct, idle_hours_24h, idle_pct, engine_load_pct,
engine_hours_total, miles_on_dpf, engine_age_years, ambient_temp_f,
baro_pressure_kpa, coolant_temp_f, fuel_quality_score

## Risk Classification
CRITICAL: <= 3 days  (weight: 10) — MUST achieve recall > 0.50 or flag unacceptable
HIGH:     <= 7 days  (weight: 5)
MEDIUM:   <= 21 days (weight: 2)
LOW:      >  21 days (weight: 1)

## Model Rules
- ALWAYS drop `predicted_days` column before training (causes label leakage)
- Always use stratify=y in train_test_split
- Always use StratifiedKFold(n_splits=5) for CV
- Report: classification report, confusion matrix, CRITICAL recall, CV score ± std
- CRITICAL recall > 0.50 is non-negotiable — flag loudly if not met

## Engine Profiles
- Cummins X15: high regen temps (1050-1250°F), frequent regens, fuel-quality sensitive
- Detroit DD15: cooler (950-1150°F), longer intervals, DEF-dependent
- PACCAR MX-13: moderate, idle-pattern sensitive
- Volvo D13 / Mack MP8: conservative, good cold-weather tolerance

## Domain Rules (20 years experience)
- High backpressure can exist even with low active soot — both matter independently
- Uneven EGT distribution across 4 sensors = early ash channeling (weeks before backpressure climbs)
- Regen requesting at lower temps over time = DPF degrading, not just dirty
- Short-haul + excessive idle + poor fuel = fastest DPF clogging combination

## Data Generation Targets
- 1000-2000 rows minimum
- Distribution: ~10% CRITICAL, ~20% HIGH, ~35% MEDIUM, ~35% LOW
- Never derive cleaning_priority directly from predicted_days (circular logic)
- Simulate time-series degradation curves, not random noise

## API
- FastAPI on port 8001
- All endpoints except /health require X-Api-Key header
- Set THROTTLEGUARD_API_KEY in Railway env vars
- Key endpoints: GET /api/dpf-status, POST /predict, POST /predict/batch, POST /validate

## Fleet Optimizer Integration (optional)
- Only active when FLEET_OPTIMIZER_URL env var is set
- Never import Fleet Optimizer code directly — communicate via API only
- If env var not set, ThrottleGuard runs fully standalone with no errors

## File Naming
throttleguard_[module]_[version].py
throttleguard_data_generator.py
throttleguard_dashboard.py

## Risk Colors (Streamlit)
CRITICAL: #FF0000 | HIGH: #FF6600 | MEDIUM: #FFB300 | LOW: #00AA00

## Code Style
1. Always add comments — explain WHY not just WHAT
2. No over-engineering — practical over elegant
3. Include print() diagnostics during dev
4. Functions single-purpose, under 30 lines where possible
5. NEVER hardcode API keys — use environment variables
6. Always include if __name__ == '__main__': block

## Project Structure
ThrottleGuard/
├── CLAUDE.md
├── api.py                        ← FastAPI server (port 8001)
├── app.py                        ← Streamlit dashboard
├── train_model.py                ← Model training script
├── data_processing.py            ← Feature preprocessing
├── throttleguard_data_generator.py
├── model.xgb                     ← Trained model (not committed if large)
├── requirements.txt
└── tests/

## Environment Variables (Railway)
THROTTLEGUARD_API_KEY     — API key for external clients
THROTTLEGUARD_DATA_PATH   — path to live sensor CSV (optional)
MODEL_PATH                — path to model file (default: model.xgb)
THROTTLEGUARD_PORT        — API port (default: 8001)
FLEET_OPTIMIZER_URL       — Fleet Optimizer base URL (optional, enables integration)
