# ThrottleGuard — Claude Code Context

## Product
ThrottleGuard is a DPF + SCR predictive maintenance SaaS for commercial diesel fleets, built by AHC Developers.
The founder has ~20 years diesel technician experience (Detroit, Volvo/Mack, Cummins/PACCAR).
Code must be practical, well-commented, and explainable to someone who knows trucks but not ML.

## Business Model
- **Standalone SaaS** — per-fleet subscription via Stripe ($59.99/month or $575.90/year)
- **14-day free trial** — no credit card required, full access
- **Optional bundle** with Fleet Optimizer (TruckFleetOptimizer) — gated by env var
- ThrottleGuard MUST work fully standalone. Never hard-depend on Fleet Optimizer.

## Scoring Engine
**NOT XGBoost. NOT ML.** ThrottleGuard v2 uses a rule-based expert system.

- **16 rules** covering the full aftertreatment system (DPF + SCR)
- **3 engine families** with different thresholds: DETROIT, VOLVO_MACK, CUMMINS_PACCAR
- Score 0–100 → priority: CRITICAL (≥60) / HIGH (≥35) / MEDIUM (≥15) / LOW (<15)
- Every flag shows the exact rule that fired and a plain-English action
- NOx conversion rules gate on peak_regen_temp_f ≥ 800°F (sensor not valid below this)

### Rule summary
| # | System | Trigger | Pts |
|---|---|---|---|
| 1 | DPF | Outlet temp <940°F during regen — clogging | 60 |
| 2 | DPF | Peak temp above family limit — thermal shock | 50 |
| 3 | DPF | Sensor delta fault (outlet <500°F AND inlet >1000°F) | 70 |
| 4 | DPF | Regen count >2 in 7 days OR driver reports frequent regen | 30 |
| 5 | DPF | Mileage >300k since cleaning AND oil consumption >0.5 qt/1000mi | 25 |
| 6 | DPF | Turbo boost <20 PSI OR EGR flow fault | 25 |
| 7 | DPF | Avg trip <15 mi AND idle >35% — short haul duty cycle | 15 |
| 8 | DPF | DEF contamination >50 ppm OR DEF doser fault | 15 |
| 9 | DPF | Water in fuel OR fuel filter changed <45 days | 10 |
| 10 | DPF | Backpressure >4.0 in.H2O | 10 |
| 11 | SCR | NOx conversion <50% — EPA derate risk | 40 |
| 12 | SCR | NOx conversion 50–70% — catalyst degrading | 20 |
| 13 | SCR | SCR inlet temp <400°F — below catalyst light-off | 15 |
| 14 | SCR | DEF concentration critically wrong (<20% or >40%) | 25 |
| 14 | SCR | DEF concentration moderately wrong (outside 31–34%) | 10 |
| 15 | SCR | NH3 slip detected | 10 |
| 16 | BOTH | Compound DPF+SCR failure (+20 Detroit 1-Box, +15 others) | 15–20 |

## CSV Input Columns

### Required (6)
vehicle_id, dpf_outlet_temp_active_regen_f, dpf_outlet_temp_peak_f,
dpf_inlet_temp_f, regen_count_7d, back_pressure_inh2o

### Optional DPF (11)
engine_family, driver_reported_frequent_regen, mileage_since_last_dpf_cleaning,
oil_consumption_qt_per_1000mi, turbo_boost_psi, egr_flow_fault,
avg_trip_distance_mi, idle_time_pct, def_quality_ppm, def_doser_fault,
water_in_fuel_detected, fuel_filter_change_frequency_days

### Optional SCR (5)
nox_conversion_pct, scr_inlet_temp_f, def_concentration_pct,
nh3_slip_detected, regen_active

## Engine Thresholds (throttleguard_engine_thresholds.py)
- REGEN_OUTLET_CRITICAL_F = 940 (outlet temp below this during regen = clogging)
- DIFF_PRESSURE_CRITICAL_PSI = 4.0 (backpressure limit, in.H2O)
- REGEN_HIGH_CRITICAL_F: DETROIT=1250, VOLVO_MACK=1250, CUMMINS_PACCAR=1200
- NOX_CONVERSION_CRITICAL_PCT = 50, NOX_CONVERSION_WARNING_PCT = 70
- SCR_INLET_TEMP_MIN_F = 400
- DEF_QUALITY_SPEC_PCT = 32.5, DEF_QUALITY_MIN_PCT = 31.0, DEF_QUALITY_MAX_PCT = 34.0
- DEF_QUALITY_CRITICAL_PCT = 20.0
- ONE_BOX_FAMILIES = {"DETROIT"} — DPF and SCR share single housing

## Domain Rules (20 years field experience)
- High backpressure can exist with low soot — ash buildup, not just soot clogging
- Uneven EGT distribution across 4 sensors = early ash channeling
- Regen requesting at lower temps over time = DPF degrading, not just dirty
- Short-haul + excessive idle + poor fuel = fastest DPF clogging combination
- NOx sensors invalid below 800°F peak regen temp — ECM suppresses DEF dosing below this
- Detroit 1-Box: DPF and SCR share single housing — thermal event damages both simultaneously
- SCR catalyst requires >400°F inlet temp to activate urea chemistry (light-off threshold)
- DEF spec: ISO 22241 — 32.5% urea ±1.5% (31–34% acceptable, <20% = water contamination)

## Tech Stack
- **Dashboard**: Streamlit (app.py)
- **Scoring**: dpf_expert_system.py (Dashboard tab), scoring_engine.py (Fleet Scores tab)
- **Database**: Supabase PostgreSQL via psycopg2 (DATABASE_URL env var)
- **Auth**: tg_auth.py — SHA-256 + per-user salt, roles: Admin / Technician / Viewer
- **Subscriptions**: tg_subscription.py — Stripe PaymentIntent, psycopg2 backend
- **Hosting**: Railway (railway.toml configured)
- **GitHub**: Hkaalis1212

## Database Tables (all prefixed tg_ to avoid collision with Fleet Optimizer)
- tg_users — authentication (created by tg_auth.py)
- tg_predictions — prediction history + outcome tracking (created by outcome_db.py)
- tg_subscriptions — fleet subscription status (created by tg_subscription.py)
- tg_payment_history — Stripe payment records (created by tg_subscription.py)

All tables auto-created on first launch. No migrations needed.

## Key Files
```
ThrottleGuard/
├── CLAUDE.md
├── app.py                          ← Streamlit dashboard + auth/subscription gates
├── dpf_expert_system.py            ← Scoring engine for Dashboard tab
├── scoring_engine.py               ← Scoring engine for Fleet Scores tab
├── throttleguard_engine_thresholds.py ← All numeric thresholds (single source of truth)
├── tg_auth.py                      ← User auth + login page + user management panel
├── tg_db.py                        ← Shared psycopg2 connection (get_conn())
├── tg_subscription.py              ← Stripe subscription management
├── outcome_db.py                   ← Prediction logging + outcome tracking
├── scored_dashboard.py             ← Fleet Scores tab UI
├── tg_demo_data.py                 ← 30-truck demo fleet (5 CRITICAL/8 HIGH/9 MEDIUM/8 LOW)
├── tg_logo.py                      ← Logo renderer
├── tg_tutorial.py                  ← In-app tutorial steps
├── .env                            ← Local secrets (never commit)
├── .env.example                    ← Documents all env vars
├── .gitignore
├── railway.toml                    ← Railway deploy config
└── requirements.txt
```

## Dead Code (do not restore)
- api.py — v1 FastAPI server (XGBoost-based, incompatible schema, removed)
- data_processing.py — v1 feature preprocessing (XGBoost pipeline, removed)
- train_model.py — v1 model training (XGBoost, removed)

## Environment Variables
| Variable | Required | Description |
|---|---|---|
| DATABASE_URL | Yes | Supabase PostgreSQL connection string |
| TG_ADMIN_PASSWORD | Yes | Default admin password (set before first deploy) |
| STRIPE_SECRET_KEY | Yes | Stripe secret key (sk_test_... or sk_live_...) |
| STRIPE_PUBLISHABLE_KEY | Yes | Stripe publishable key |
| THROTTLEGUARD_API_URL | No | Enables Fleet Optimizer integration (optional) |
| THROTTLEGUARD_API_KEY | No | API key for Fleet Optimizer requests |

## Roles & Permissions
| Role | upload | view | outcomes | manage_users | history |
|---|---|---|---|---|---|
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ |
| Technician | ✓ | ✓ | ✓ | | ✓ |
| Viewer | | ✓ | | | ✓ |

## Subscription Gate
Sits between auth and dashboard in app.py.
- fleet_id = "admin" (one subscription per Railway deployment)
- No active subscription → trial start page or upgrade page
- Trial: 14 days free, full access, no card
- Paid: monthly $59.99 or yearly $575.90 (18% off)

## Fleet Optimizer Integration (optional)
- File: TruckFleetOptimizer/throttleguard_integration.py
- Enabled only when THROTTLEGUARD_API_URL env var is set
- Currently calls /api/dpf-status — needs updating to read from tg_predictions in Supabase
- Both apps share the same Supabase project (tg_ prefix prevents table collision)

## Code Style
1. Comments explain WHY not just WHAT
2. No over-engineering — practical over elegant
3. psycopg2 %s placeholders (not ?) — this is PostgreSQL not SQLite
4. All thresholds in throttleguard_engine_thresholds.py — never hardcode in rules
5. Never hardcode secrets — use environment variables
6. tg_ prefix on all DB tables
