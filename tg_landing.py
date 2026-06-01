"""
tg_landing.py — ThrottleGuard Lead-Capture Landing Page
=========================================================
Standalone page. No login required.

Flow:
  1. Hero: headline + value prop
  2. Email field + CSV upload form
  3. Single-truck score breakdown (highest-risk truck from uploaded CSV)
  4. Blurred preview of remaining fleet rows (creates FOMO)
  5. CTA → Stripe Checkout (14-day free trial, no card needed until day 15)

Run standalone (local dev):
  streamlit run tg_landing.py --server.port 8502

Deploy on Railway as a second service pointing to this file.

Env vars used:
  STRIPE_SECRET_KEY    — Stripe secret key
  TG_LANDING_URL       — Full base URL of THIS page (e.g. https://landing.throttleguard.app)
                         Used to build Stripe success/cancel URLs.
                         Defaults to http://localhost:8502
  TG_APP_URL           — URL of the main app (shown in success redirect hint).
                         Defaults to http://localhost:8501
"""

import io
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import stripe

from scoring_engine import score_row, SCORE_COLUMNS
from tg_logo import _svg_to_img_tag, get_logo_svg

# ── Stripe config ─────────────────────────────────────────────────────────────

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Per-truck / month tiers — amount = fleet_size × per_truck rate.
# Enterprise (250+) is custom — no automated checkout.
PRICING_TIERS = [
    {"key": "starter", "label": "Starter", "min": 1,   "max": 10,  "per_truck": 39.00},
    {"key": "growth",  "label": "Growth",  "min": 11,  "max": 50,  "per_truck": 29.00},
    {"key": "fleet",   "label": "Fleet",   "min": 51,  "max": 250, "per_truck": 19.00},
]

TRIAL_DAYS = 14

BASE_URL = os.getenv("TG_LANDING_URL", "http://localhost:8502")
APP_URL  = os.getenv("TG_APP_URL",     "http://localhost:8501")

# ── CSV validation ────────────────────────────────────────────────────────────

REQUIRED_COLS = [
    "vehicle_id",
    "dpf_outlet_temp_active_regen_f",
    "dpf_outlet_temp_peak_f",
    "dpf_inlet_temp_f",
    "regen_count_7d",
    "back_pressure_inh2o",
]

# ── Risk colors ───────────────────────────────────────────────────────────────

PRIORITY_COLOR = {
    "CRITICAL": "#e53935",
    "HIGH":     "#f57c00",
    "MEDIUM":   "#f9a825",
    "LOW":      "#43a047",
}

PRIORITY_ICON = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🟢",
}


# ── Styles ────────────────────────────────────────────────────────────────────

def inject_styles() -> None:
    st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=Barlow:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <style>
    /* ── Reset & global ── */
    html, body, [class*="css"] { font-family: 'Barlow', sans-serif; }
    h1, h2, h3 { font-family: 'Barlow Condensed', sans-serif !important; letter-spacing: 0.04em; }
    code, pre { font-family: 'JetBrains Mono', monospace !important; }

    /* ── Hide Streamlit chrome ── */
    #MainMenu, footer, header { visibility: hidden; }
    [data-testid="stSidebar"] { display: none; }

    /* ── Page background ── */
    .stApp { background: #080a0c; }
    .main .block-container { padding-top: 0 !important; max-width: 780px; }

    /* ── Form inputs ── */
    .stTextInput input, .stFileUploader {
        background: #0f1217 !important;
        border: 1px solid #1a2130 !important;
        border-radius: 6px !important;
        color: #e8edf2 !important;
        font-family: 'Barlow', sans-serif !important;
    }
    .stTextInput label, .stFileUploader label {
        font-family: 'Barlow Condensed', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        color: #8fa3b8 !important;
        font-size: 0.75rem !important;
    }

    /* ── Primary button ── */
    .stFormSubmitButton > button,
    [data-testid="stFormSubmitButton"] button {
        background: #e53935 !important;
        color: #fff !important;
        font-family: 'Barlow Condensed', sans-serif !important;
        font-weight: 800 !important;
        font-size: 1rem !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 0.65rem 2rem !important;
        width: 100% !important;
    }
    .stFormSubmitButton > button:hover {
        background: #c62828 !important;
    }

    /* ── CTA button ── */
    .stButton > button {
        font-family: 'Barlow Condensed', sans-serif !important;
        font-weight: 800 !important;
        font-size: 1.1rem !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        border-radius: 6px !important;
        width: 100% !important;
        padding: 0.75rem 2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ── CSV scoring ───────────────────────────────────────────────────────────────

def score_fleet_csv(file_bytes: bytes) -> tuple[pd.DataFrame | None, str | None]:
    """
    Parse and score the uploaded CSV. Returns (scored_df, error_msg).
    Picks the highest-risk truck for display in the preview card.
    """
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as exc:
        return None, f"Could not parse CSV: {exc}"

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        return None, (
            f"CSV is missing required columns: **{', '.join(missing)}**\n\n"
            f"Required: `{', '.join(REQUIRED_COLS)}`"
        )

    if df.empty:
        return None, "CSV contains no data rows."

    df[SCORE_COLUMNS] = df.apply(score_row, axis=1)
    return df, None


# ── Stripe checkout ───────────────────────────────────────────────────────────

def recommended_tier(fleet_size: int) -> dict:
    """Return the PRICING_TIERS entry matching fleet_size (defaults to starter for 0)."""
    for t in PRICING_TIERS:
        if t["min"] <= fleet_size <= t["max"]:
            return t
    return PRICING_TIERS[0]  # default: starter


def create_checkout_url(email: str, fleet_size: int = 10) -> tuple[str | None, str | None]:
    """
    Create a Stripe Checkout Session with dynamic per-truck pricing.
    Amount = fleet_size × per_truck rate. 14-day free trial, no card charged until day 15.
    Returns (checkout_url, error_msg).
    """
    if not stripe.api_key or stripe.api_key.startswith("sk_test_..."):
        return APP_URL, None

    tier = recommended_tier(fleet_size)
    amount_cents = int(round(fleet_size * tier["per_truck"] * 100))
    product_name = f"ThrottleGuard {tier['label']} ({fleet_size} trucks)"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email if email else None,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product_name},
                    "unit_amount": amount_cents,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            subscription_data={"trial_period_days": TRIAL_DAYS},
            success_url=f"{BASE_URL}/?checkout=success",
            cancel_url=f"{BASE_URL}/",
        )
        return session.url, None
    except stripe.error.StripeError as exc:
        return None, str(exc)


# ── Score card ────────────────────────────────────────────────────────────────

def render_score_card(row: pd.Series) -> None:
    """Render the full score breakdown card for the highest-risk truck."""
    score    = int(row["rule_score"])
    priority = row["priority_label"]
    mode     = row["failure_mode"]
    action   = row["recommended_action"]
    rules    = row["triggered_rules"]
    conf     = row["confidence"]
    trend    = row["score_trend"]
    vid      = row["vehicle_id"]
    color    = PRIORITY_COLOR.get(priority, "#546e7a")
    icon     = PRIORITY_ICON.get(priority, "⚪")

    # Score bar — filled width as percentage, capped at 100
    bar_pct = min(score, 100)

    rules_html = ""
    if rules and rules != "None":
        for r in rules.split(", "):
            if r.strip():
                rules_html += (
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.83rem;'
                    f'color:#8fa3b8;padding:4px 0 4px 0.85rem;'
                    f'border-left:2px solid {color};margin-bottom:4px;">'
                    f'{r.strip()}</div>'
                )
    else:
        rules_html = '<div style="font-size:0.8rem;color:#4a6070;">No rules triggered</div>'

    st.markdown(f"""
    <div style="
        background: #0f1217;
        border: 1px solid #1a2130;
        border-top: 3px solid {color};
        border-radius: 8px;
        padding: 1.5rem 1.75rem 1.25rem;
        margin-top: 0.5rem;
    ">
        <!-- Truck ID + priority -->
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.2rem;">
            <div>
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.65rem;
                    letter-spacing:0.14em;text-transform:uppercase;color:#4a6070;
                    margin-bottom:2px;">Vehicle</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1.35rem;
                    font-weight:600;color:#e8edf2;">{vid}</div>
            </div>
            <span style="
                background:{color};color:#fff;
                font-family:'Barlow Condensed',sans-serif;
                font-size:0.85rem;font-weight:800;
                letter-spacing:0.14em;text-transform:uppercase;
                padding:4px 14px;border-radius:4px;
            ">{icon} {priority}</span>
        </div>

        <!-- Score gauge -->
        <div style="margin-bottom:1.25rem;">
            <div style="display:flex;justify-content:space-between;
                font-family:'Barlow Condensed',sans-serif;font-size:0.65rem;
                letter-spacing:0.12em;text-transform:uppercase;color:#4a6070;
                margin-bottom:6px;">
                <span>Risk Score</span>
                <span style="font-family:'JetBrains Mono',monospace;
                    font-size:1.5rem;font-weight:600;color:{color};">{score}<span
                    style="font-size:0.9rem;color:#4a6070;">/100</span></span>
            </div>
            <div style="background:#1a2130;border-radius:4px;height:10px;overflow:hidden;">
                <div style="background:{color};width:{bar_pct}%;height:100%;
                    border-radius:4px;transition:width 0.4s ease;"></div>
            </div>
        </div>

        <!-- Two-column: Mode + Action -->
        <div style="display:grid;grid-template-columns:1fr 2fr;gap:1rem;margin-bottom:1.25rem;">
            <div>
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.62rem;
                    letter-spacing:0.12em;text-transform:uppercase;color:#4a6070;
                    margin-bottom:6px;">Failure Mode</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;
                    color:{color};font-weight:600;">{mode}</div>
                <div style="margin-top:0.75rem;">
                    <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.62rem;
                        letter-spacing:0.12em;text-transform:uppercase;color:#4a6070;
                        margin-bottom:6px;">Confidence</div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;
                        color:#8fa3b8;">{conf}</div>
                </div>
                <div style="margin-top:0.75rem;">
                    <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.62rem;
                        letter-spacing:0.12em;text-transform:uppercase;color:#4a6070;
                        margin-bottom:6px;">Trend</div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;
                        color:#8fa3b8;">{trend}</div>
                </div>
            </div>
            <div>
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.62rem;
                    letter-spacing:0.12em;text-transform:uppercase;color:#4a6070;
                    margin-bottom:6px;">Recommended Action</div>
                <div style="
                    font-family:'Barlow',sans-serif;font-size:0.85rem;
                    color:#e8edf2;background:#080a0c;
                    border:1px solid #1a2130;border-left:3px solid {color};
                    border-radius:4px;padding:0.7rem 0.9rem;line-height:1.55;
                ">{action}</div>
            </div>
        </div>

        <!-- Rules fired -->
        <div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.62rem;
                letter-spacing:0.12em;text-transform:uppercase;color:#4a6070;
                margin-bottom:8px;">Rules Fired</div>
            {rules_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Blurred fleet preview ─────────────────────────────────────────────────────

def render_blurred_preview(df: pd.DataFrame, shown_vid: str) -> None:
    """
    Show remaining trucks as a blurred/locked preview row.
    The teaser drives clicks on the CTA below.
    """
    rest = df[df["vehicle_id"] != shown_vid].copy()
    if rest.empty:
        return

    # Sort by rule_score descending so worst trucks are visible first
    rest = rest.sort_values("rule_score", ascending=False).head(6)

    rows_html = ""
    for _, row in rest.iterrows():
        c = PRIORITY_COLOR.get(row["priority_label"], "#546e7a")
        rows_html += f"""
        <div style="
            background:#0f1217;border:1px solid #1a2130;border-left:3px solid {c};
            border-radius:5px;padding:0.6rem 0.9rem;margin-bottom:6px;
            display:flex;align-items:center;justify-content:space-between;
        ">
            <span style="font-family:'JetBrains Mono',monospace;
                font-size:0.88rem;color:#e8edf2;">{row['vehicle_id']}</span>
            <span style="font-family:'JetBrains Mono',monospace;
                font-size:0.82rem;color:{c};font-weight:600;">
                {int(row['rule_score'])}/100 · {row['priority_label']}</span>
        </div>"""

    more = len(df) - 1 - len(rest)
    more_line = (
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
        f'color:#4a6070;text-align:center;margin-top:4px;">+{more} more trucks…</div>'
        if more > 0 else ""
    )

    st.markdown(f"""
    <div style="position:relative;margin-top:0.75rem;">
        <!-- blurred trucks -->
        <div style="filter:blur(4px);pointer-events:none;user-select:none;">
            {rows_html}
            {more_line}
        </div>
        <!-- lock overlay -->
        <div style="
            position:absolute;top:0;left:0;right:0;bottom:0;
            display:flex;flex-direction:column;align-items:center;justify-content:center;
            background:rgba(8,10,12,0.55);border-radius:5px;
        ">
            <div style="font-size:1.6rem;margin-bottom:6px;">🔒</div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;
                font-weight:700;letter-spacing:0.08em;text-transform:uppercase;
                color:#8fa3b8;">
                {len(df) - 1} more truck{'s' if len(df) - 1 != 1 else ''} — start free trial to unlock
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Hero ──────────────────────────────────────────────────────────────────────

def render_hero() -> None:
    logo_svg = get_logo_svg(width=200, show_tagline=False)

    st.markdown(f"""
    <div style="
        background: linear-gradient(180deg, #0d1117 0%, #080a0c 100%);
        border-bottom: 1px solid #1a2130;
        padding: 2.5rem 0 2rem;
        text-align: center;
        margin-bottom: 2rem;
    ">
        <div style="display:flex;justify-content:center;margin-bottom:1.2rem;">
            {_svg_to_img_tag(logo_svg, 200)}
        </div>
        <h1 style="
            font-family:'Barlow Condensed',sans-serif;
            font-size:clamp(1.8rem, 5vw, 2.6rem);
            font-weight:800;
            letter-spacing:0.02em;
            color:#e8edf2;
            line-height:1.15;
            margin:0 auto 0.75rem;
            max-width:640px;
        ">
            Upload your fleet CSV.<br>
            Get DPF + SCR risk scores<br>
            <span style="color:#e53935;">in 30 seconds.</span>
        </h1>
        <p style="
            font-family:'Barlow',sans-serif;
            font-size:1.05rem;
            color:#6b7280;
            margin:0 auto;
            max-width:480px;
            line-height:1.6;
        ">
            16 expert rules. 20 years of diesel field experience.<br>
            No login. No credit card. See your highest-risk truck right now.
        </p>
    </div>
    """, unsafe_allow_html=True)


# ── Upload form ───────────────────────────────────────────────────────────────

def render_upload_form() -> tuple[str | None, bytes | None]:
    """Render the email + CSV upload form. Returns (email, csv_bytes) or (None, None)."""
    st.markdown("""
    <div style="
        font-family:'Barlow Condensed',sans-serif;
        font-size:0.65rem;font-weight:700;
        letter-spacing:0.14em;text-transform:uppercase;
        color:#4a6070;margin-bottom:1rem;
    ">Step 1 — Enter your email &amp; upload your fleet data</div>
    """, unsafe_allow_html=True)

    with st.form("upload_form", clear_on_submit=False):
        email = st.text_input(
            "Work email",
            placeholder="you@yourfleet.com",
        )
        csv_file = st.file_uploader(
            "Fleet CSV  (required columns: vehicle_id, dpf temps, regen count, backpressure)",
            type=["csv"],
            help=(
                "Required columns: vehicle_id, dpf_outlet_temp_active_regen_f, "
                "dpf_outlet_temp_peak_f, dpf_inlet_temp_f, regen_count_7d, back_pressure_inh2o"
            ),
        )
        submitted = st.form_submit_button("Score My Fleet →")

    if submitted:
        if not email or "@" not in email:
            st.error("Please enter a valid email address.")
            return None, None
        if csv_file is None:
            st.error("Please upload a CSV file.")
            return None, None
        return email, csv_file.read()

    return None, None


# ── CTA section ───────────────────────────────────────────────────────────────

def render_cta(email: str, fleet_size: int = 0) -> None:
    """
    Render the full-fleet CTA with per-truck pricing.
    fleet_size pre-fills the truck count from the uploaded CSV.
    """
    st.markdown("""
    <div style="border-top:1px solid #1a2130;margin-top:1.75rem;padding-top:1.5rem;">
        <div style="text-align:center;margin-bottom:1.25rem;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.3rem;
                font-weight:700;letter-spacing:0.04em;color:#e8edf2;margin-bottom:0.35rem;">
                See your full fleet — free for 14 days
            </div>
            <div style="font-family:'Barlow',sans-serif;font-size:0.88rem;color:#6b7280;">
                Every truck. Every rule. DPF + SCR. Do-not-dispatch list.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Per-truck pricing cards (informational, no tier selection needed)
    tier_cols = st.columns(3)
    for col, t in zip(tier_cols, PRICING_TIERS):
        col.markdown(f"""
        <div style="
            background:#0f1217;border:1px solid #1a2130;
            border-radius:6px;padding:0.9rem 1rem;text-align:center;
        ">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1rem;
                font-weight:700;color:#e8edf2;">{t['label']}</div>
            <div style="font-family:'Barlow',sans-serif;font-size:0.72rem;
                color:#6b7280;margin:2px 0 6px;">{t['min']}–{t['max']} trucks</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:1.2rem;
                font-weight:600;color:#e8edf2;">${t['per_truck']:.0f}<span
                style="font-size:0.75rem;color:#4a6070;">/truck/mo</span></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Fleet size input — pre-filled from CSV if available
    _default_size = max(1, fleet_size) if fleet_size > 0 else 10
    _size = st.number_input(
        "Your fleet size (trucks)",
        min_value=1,
        max_value=10000,
        value=_default_size,
        step=1,
        key="tg_landing_fleet_size",
    )

    # Dynamic monthly total
    _tier = recommended_tier(_size)
    _total = _size * _tier["per_truck"]
    st.markdown(
        f"<div style='font-family:\"Barlow\",sans-serif;font-size:0.9rem;color:#8fa3b8;"
        f"text-align:center;margin:0.4rem 0 0.75rem;'>"
        f"{_tier['label']} tier · {_size} trucks × ${_tier['per_truck']:.0f} = "
        f"<strong style='color:#e8edf2;'>${_total:,.2f}/mo</strong> after trial"
        f"</div>",
        unsafe_allow_html=True,
    )

    if st.button(
        f"Start Free Trial — ${_total:,.2f}/mo after 14 days →",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Opening secure checkout…"):
            url, err = create_checkout_url(email, fleet_size=int(_size))
        if err:
            st.error(f"Checkout error: {err}")
        elif url:
            components.html(
                f'<script>window.parent.location.href = "{url}";</script>',
                height=0,
                width=0,
            )

    st.markdown("""
    <div style="font-family:'Barlow',sans-serif;font-size:0.75rem;color:#374151;
        text-align:center;margin-top:0.75rem;">
        🔒 Secure checkout via Stripe · No card charged until day 15 · Cancel any time
    </div>
    """, unsafe_allow_html=True)


# ── Trust bar ─────────────────────────────────────────────────────────────────

def render_trust_bar() -> None:
    st.markdown("""
    <div style="
        border-top:1px solid #1a2130;
        margin-top:3rem;padding-top:1.25rem;
        display:flex;justify-content:center;gap:2.5rem;flex-wrap:wrap;
    ">
        <div style="text-align:center;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;
                font-weight:800;color:#e8edf2;">16</div>
            <div style="font-family:'Barlow',sans-serif;font-size:0.72rem;
                color:#4a6070;text-transform:uppercase;letter-spacing:0.08em;">Expert Rules</div>
        </div>
        <div style="text-align:center;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;
                font-weight:800;color:#e8edf2;">3</div>
            <div style="font-family:'Barlow',sans-serif;font-size:0.72rem;
                color:#4a6070;text-transform:uppercase;letter-spacing:0.08em;">Engine Families</div>
        </div>
        <div style="text-align:center;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;
                font-weight:800;color:#e8edf2;">20 yrs</div>
            <div style="font-family:'Barlow',sans-serif;font-size:0.72rem;
                color:#4a6070;text-transform:uppercase;letter-spacing:0.08em;">Diesel Field Experience</div>
        </div>
        <div style="text-align:center;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;
                font-weight:800;color:#e53935;">$0</div>
            <div style="font-family:'Barlow',sans-serif;font-size:0.72rem;
                color:#4a6070;text-transform:uppercase;letter-spacing:0.08em;">For 14 Days</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Checkout success banner ───────────────────────────────────────────────────

def render_success_banner() -> None:
    st.markdown("""
    <div style="
        background:rgba(67,160,71,0.08);
        border:1px solid rgba(67,160,71,0.3);
        border-left:4px solid #43a047;
        border-radius:6px;
        padding:1rem 1.25rem;
        margin-bottom:1.5rem;
        font-family:'Barlow',sans-serif;
        font-size:0.9rem;
        color:#43a047;
    ">
        ✓ <strong>Trial started!</strong>
        Your 14-day free trial is active. Check your email for login instructions.
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="ThrottleGuard — DPF + SCR Risk Scores in 30 Seconds",
        page_icon="🛡️",
        layout="centered",
    )
    inject_styles()

    # Check for Stripe success redirect
    params = st.query_params
    if params.get("checkout") == "success":
        render_success_banner()

    render_hero()

    # ── Upload form ───────────────────────────────────────────────────────────
    email, csv_bytes = render_upload_form()

    # Persist across rerenders (Streamlit re-runs on every interaction)
    if email and csv_bytes:
        st.session_state["lead_email"]  = email
        st.session_state["lead_csv"]    = csv_bytes

    # Use stored values if form was already submitted
    active_email    = st.session_state.get("lead_email")
    active_csv      = st.session_state.get("lead_csv")

    if not (active_email and active_csv):
        # Nothing scored yet — show sample column hint
        st.markdown("""
        <div style="
            background:#0f1217;border:1px dashed #1a2130;border-radius:6px;
            padding:1.25rem 1.5rem;margin-top:1rem;
            font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:#4a6070;
        ">
        <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.65rem;
            letter-spacing:0.12em;text-transform:uppercase;color:#374151;
            margin-bottom:8px;">Required CSV Columns</div>
        vehicle_id, dpf_outlet_temp_active_regen_f, dpf_outlet_temp_peak_f,<br>
        dpf_inlet_temp_f, regen_count_7d, back_pressure_inh2o<br><br>
        <span style="color:#374151;">Optional (adds SCR + engine-family scoring):</span><br>
        engine_family, nox_conversion_pct, scr_inlet_temp_f, def_concentration_pct,<br>
        regen_active, mileage_since_last_dpf_cleaning, idle_time_pct, …
        </div>
        """, unsafe_allow_html=True)

        render_trust_bar()
        return

    # ── Score the fleet ───────────────────────────────────────────────────────
    with st.spinner("Scoring your fleet…"):
        scored_df, err = score_fleet_csv(active_csv)

    if err:
        st.error(err)
        return

    # Show worst-risk truck in the score card
    worst_idx = scored_df["rule_score"].idxmax()
    worst_row = scored_df.loc[worst_idx]

    # Section header
    fleet_size  = len(scored_df)
    n_critical  = int((scored_df["priority_label"] == "CRITICAL").sum())
    n_high      = int((scored_df["priority_label"] == "HIGH").sum())

    alert_color = "#e53935" if n_critical > 0 else ("#f57c00" if n_high > 0 else "#43a047")
    alert_text  = (
        f"{n_critical} CRITICAL · {n_high} HIGH across {fleet_size} trucks"
        if (n_critical + n_high) > 0
        else f"All {fleet_size} trucks LOW / MEDIUM risk"
    )

    st.markdown(f"""
    <div style="
        display:flex;align-items:center;justify-content:space-between;
        margin-bottom:0.75rem;
    ">
        <div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.65rem;
                letter-spacing:0.14em;text-transform:uppercase;color:#4a6070;">
                Step 2 — Highest-risk truck in your fleet
            </div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1rem;
                font-weight:700;color:#e8edf2;margin-top:2px;">Score Breakdown</div>
        </div>
        <div style="
            font-family:'Barlow Condensed',sans-serif;font-size:0.75rem;font-weight:700;
            letter-spacing:0.06em;text-transform:uppercase;
            color:{alert_color};background:rgba(0,0,0,0.3);
            padding:4px 10px;border-radius:4px;border:1px solid {alert_color}33;
        ">{alert_text}</div>
    </div>
    """, unsafe_allow_html=True)

    render_score_card(worst_row)

    # Blurred preview of remaining trucks
    render_blurred_preview(scored_df, shown_vid=str(worst_row["vehicle_id"]))

    # CTA
    render_cta(active_email, fleet_size=len(scored_df))

    render_trust_bar()


if __name__ == "__main__":
    main()
