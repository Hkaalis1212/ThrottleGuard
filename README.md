# ThrottleGuard

**Know before it breaks.** ThrottleGuard reads your fleet's J1939 sensor data and flags DPF + SCR problems before they become roadside breakdowns — scoring every truck CRITICAL → HIGH → MEDIUM → LOW with a plain-English reason your dispatcher can act on immediately.

Built on 20 years of field experience with Detroit, Volvo/Mack, and Cummins/PACCAR aftertreatment systems.

---

## How it works

ThrottleGuard uses an **18-rule expert system** — not a black box ML model. Every flag shows exactly which rule fired and what action to take. Rules cover the full aftertreatment system:

- **DPF**: regen temperatures, backpressure, regen frequency, mileage, oil consumption, duty cycle
- **SCR**: NOx conversion efficiency, catalyst inlet temp, DEF concentration, NH3 slip
- **Passive regen**: silent soot buildup detection — flags trucks whose normal operation never reaches passive regen temperatures, before backpressure climbs
- **Compound**: DPF + SCR flagged simultaneously (higher penalty for Detroit 1-Box single housing)

Scoring is engine-family aware. Thermal thresholds differ between Detroit DD13/DD15, Volvo/Mack D13/MP8, and Cummins/PACCAR X15/MX-13.

---

## Features

- Upload a CSV of fleet sensor data and score every truck in seconds
- 30-truck live demo — no upload required
- CRITICAL/HIGH/MEDIUM/LOW priority with risk score (0–100)
- Expandable per-truck breakdown: which rules fired, recommended action
- Do-Not-Dispatch list for CRITICAL and HIGH units
- Passive regen health score per truck — catches silent failures OEM tools miss
- Prediction history logged to Supabase PostgreSQL (survives redeploys)
- Outcome tracking — log real-world results after service to validate accuracy
- Role-based access: Admin, Technician, Viewer
- Downloadable CSV template with all required and optional columns

---

## Subscription

Priced per truck (see `PRICING_TIERS` in `tg_subscription.py` — the source of truth):

| Plan | Fleet size | Price |
|---|---|---|
| Starter | 1–10 trucks | $39/truck/mo |
| Growth | 11–50 trucks | $29/truck/mo |
| Fleet | 51–250 trucks | $19/truck/mo |
| Enterprise | 250+ trucks | Custom quote (no automated checkout) |
| Free trial | — | 14 days — full access, no credit card required |

No annual plan. Billing is handled by Stripe. One subscription per Railway deployment covers the full fleet (fleet size is entered at checkout time).

---

## Roles

| Role | Can do |
|---|---|
| Admin | Everything — upload, view, outcomes, manage users |
| Technician | Upload CSVs, view results, log outcomes after service |
| Viewer | Read-only — view results and history |

---

## Local setup

```bash
# 1. Clone and create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the env template and fill in your values
cp .env.example .env

# 4. Run
streamlit run app.py
```

App will be available at **[http://localhost:8501](http://localhost:8501)**

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection string |
| `TG_ADMIN_PASSWORD` | Yes | Default admin password (set before first launch) |
| `STRIPE_SECRET_KEY` | Yes | Stripe secret key (`sk_test_...` or `sk_live_...`) |
| `STRIPE_PUBLISHABLE_KEY` | Yes | Stripe publishable key |
| `THROTTLEGUARD_API_URL` | No | Enables Fleet Optimizer integration (optional) |
| `THROTTLEGUARD_API_KEY` | No | API key for Fleet Optimizer requests |

All database tables (`tg_users`, `tg_predictions`, `tg_subscriptions`, `tg_payment_history`) are created automatically on first launch. No migrations needed.

**Change the admin password immediately after first login** via User Management.

---

## CSV format

Download the template from the landing page, or see the columns below.

**Required** (6 columns):

| Column | Description |
|---|---|
| `vehicle_id` | Unit identifier |
| `dpf_outlet_temp_active_regen_f` | DPF outlet temp during active regen (°F) |
| `dpf_outlet_temp_peak_f` | Peak DPF outlet temp (°F) |
| `dpf_inlet_temp_f` | DPF inlet temp (°F) |
| `regen_count_7d` | Number of regens in the last 7 days |
| `back_pressure_inh2o` | Exhaust backpressure (in.H₂O) |

**Optional** — more columns = more accurate score. See the in-app template for the full list including SCR fields (`nox_conversion_pct`, `scr_inlet_temp_f`, `def_concentration_pct`), passive regen fields (`regen_active`, `idle_time_pct`), and fuel quality fields (`water_in_fuel_detected`, `fuel_filter_change_frequency_days`).

---

## Deploy to Railway

1. Push this repo to GitHub
2. Create a new Railway project → Deploy from GitHub repo
3. Set environment variables in Railway → Settings → Variables (see table above)
4. Railway uses `railway.toml` for the start command automatically

---

## Fleet Optimizer integration (optional)

ThrottleGuard can share DPF risk scores with Fleet Optimizer to block high-risk trucks from dispatch assignments. Enable by setting `THROTTLEGUARD_API_URL` and `THROTTLEGUARD_API_KEY` in your environment. ThrottleGuard works fully standalone without this.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Scoring | Rule-based expert system (`dpf_expert_system.py`, `scoring_engine.py`) |
| Passive regen | `throttleguard_passive_regen.py` |
| Thresholds | `throttleguard_engine_thresholds.py` (single source of truth) |
| Database | Supabase PostgreSQL (psycopg2) |
| Billing | Stripe |
| Charts | Plotly |
| Deploy | Railway |

---

*AHC Developers · ThrottleGuard v2*
