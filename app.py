"""
ThrottleGuard DPF Dashboard
===========================
Production predictor: rule-based expert system (dpf_expert_system.py)
XGBoost removed — negative R2, 5% critical recall.

Workflow:
  1. Upload CSV with DPF sensor / service columns
  2. Expert system scores every row
  3. Results displayed by priority, with reasons and actions
  4. Every prediction logged to SQLite for future validation
"""

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from dpf_expert_system import calculate_expert_score, REQUIRED_FIELDS, OPTIONAL_FIELDS
from outcome_db import log_prediction, init_db
from tg_auth import init_auth_db, login_page, can_do, user_management_panel
from tg_tutorial import render_tutorial_sidebar, tutorial_callout

# ── Auth gate — runs before anything else ─────────────────────────────────────
# Initialize auth DB on every cold start (creates table + default admin if needed)
init_auth_db()

# If not logged in, show login page and stop rendering the rest of the app
if "tg_user" not in st.session_state or not st.session_state["tg_user"]:
    login_page()
    st.stop()

# ── Page config ───────────────────────────────────────────────────────────────
# Only reached after successful login

st.set_page_config(
    page_title="ThrottleGuard DPF Dashboard",
    page_icon="🚛",
    layout="wide",
)

# Priority display config
PRIORITY_COLOR = {
    "CRITICAL": "#d32f2f",
    "HIGH":     "#f57c00",
    "MEDIUM":   "#fbc02d",
    "LOW":      "#388e3c",
    "ERROR":    "#757575",
}
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "ERROR": 4}

# ── Column mapping helper ─────────────────────────────────────────────────────

# Maps common alternative column names in uploaded CSVs to the canonical names
# the expert system expects.
COLUMN_ALIASES = {
    "dpf_outlet_temp_active_regen_f": [
        "outlet_temp_regen", "outlet_temp_f", "dpf_outlet_temp",
        "regen_outlet_temp_f", "outlet_regen_f",
    ],
    "dpf_outlet_temp_peak_f": [
        "peak_temp_f", "dpf_peak_temp", "peak_dpf_temp_f",
    ],
    "dpf_inlet_temp_f": [
        "inlet_temp_f", "dpf_inlet_temp", "inlet_dpf_temp_f",
    ],
    "regen_count_7d": [
        "regens_7d", "regen_count", "regens_last_7_days",
    ],
    "back_pressure_inh2o": [
        "back_pressure", "backpressure_inh2o", "exhaust_backpressure",
    ],
    "vehicle_id": [
        "truck_id", "unit_id", "asset_id", "vin", "unit_number",
    ],
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename CSV columns to canonical expert-system names where possible."""
    rename_map = {}
    lower_cols = {c.lower(): c for c in df.columns}
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical not in df.columns:
            for alias in aliases:
                if alias.lower() in lower_cols:
                    rename_map[lower_cols[alias.lower()]] = canonical
                    break
    return df.rename(columns=rename_map)


# ── Prediction engine ─────────────────────────────────────────────────────────

def run_expert_system(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run calculate_expert_score on every row of the DataFrame.
    Returns the original df with result columns appended.
    """
    results = []
    for _, row in df.iterrows():
        row_dict = row.where(pd.notna(row), other=None).to_dict()
        result = calculate_expert_score(row_dict)
        results.append(result)

    result_df = pd.DataFrame(results)

    # Log every prediction to SQLite for future validation
    for _, r in result_df.iterrows():
        log_prediction(
            vehicle_id=str(r["vehicle_id"]),
            predicted_priority=str(r["priority"]),
            predicted_failure_mode=str(r["failure_mode"]),
            risk_score=r["risk_score"] if r["risk_score"] is not None else -1,
        )

    return result_df


# ── UI helpers ────────────────────────────────────────────────────────────────

def priority_badge(priority: str) -> str:
    color = PRIORITY_COLOR.get(priority, "#757575")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:0.85em">{priority}</span>'


def render_fleet_summary(results: pd.DataFrame):
    """Top-of-page KPI tiles."""
    counts = results["priority"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 CRITICAL", counts.get("CRITICAL", 0), help="Immediate action required")
    c2.metric("🟠 HIGH",     counts.get("HIGH", 0),     help="Service within 1 week")
    c3.metric("🟡 MEDIUM",   counts.get("MEDIUM", 0),   help="Monitor / schedule")
    c4.metric("🟢 LOW",      counts.get("LOW", 0),      help="Normal operation")


def render_priority_chart(results: pd.DataFrame):
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    summary = (
        results["priority"]
        .value_counts()
        .reindex(order, fill_value=0)
        .reset_index()
    )
    summary.columns = ["Priority", "Trucks"]
    fig = px.bar(
        summary, x="Priority", y="Trucks", color="Priority",
        color_discrete_map=PRIORITY_COLOR,
        title="Fleet DPF Health Distribution",
        text="Trucks",
    )
    fig.update_layout(showlegend=False, height=320)
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)


def render_score_histogram(results: pd.DataFrame):
    fig = px.histogram(
        results, x="risk_score", nbins=20,
        title="Risk Score Distribution",
        labels={"risk_score": "Risk Score (0-100)"},
        color_discrete_sequence=["#ef5350"],
    )
    fig.update_layout(height=280)
    st.plotly_chart(fig, use_container_width=True)


def render_failure_mode_chart(results: pd.DataFrame):
    fm = results["failure_mode"].value_counts().reset_index()
    fm.columns = ["Failure Mode", "Count"]
    fig = px.pie(
        fm, names="Failure Mode", values="Count",
        title="Predicted Failure Modes",
        hole=0.4,
    )
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)


def render_detailed_table(results: pd.DataFrame):
    """Sortable, color-coded detail table with expandable reasons."""
    sorted_results = results.sort_values(
        "priority", key=lambda s: s.map(PRIORITY_ORDER)
    ).reset_index(drop=True)

    st.markdown("### Vehicle Detail — Sorted by Priority")

    for _, row in sorted_results.iterrows():
        color   = PRIORITY_COLOR.get(row["priority"], "#757575")
        score   = row["risk_score"] if row["risk_score"] is not None else "N/A"
        vid     = row["vehicle_id"]
        fm      = row["failure_mode"]
        reasons = row["reasons"]
        action  = row["action"]

        with st.expander(
            f"{'🔴' if row['priority']=='CRITICAL' else '🟠' if row['priority']=='HIGH' else '🟡' if row['priority']=='MEDIUM' else '🟢'} "
            f"**{vid}** — {row['priority']} ({score}/100) — {fm}",
            expanded=(row["priority"] == "CRITICAL"),
        ):
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"**Priority:** {priority_badge(row['priority'])}", unsafe_allow_html=True)
                st.markdown(f"**Risk Score:** `{score}/100`")
                st.markdown(f"**Failure Mode:** `{fm}`")
            with col2:
                st.markdown(f"**Recommended Action:**")
                st.info(action)

            if reasons and reasons != "No risk factors triggered":
                st.markdown("**Why this score:**")
                for reason in reasons.split(";"):
                    r = reason.strip()
                    if r:
                        st.markdown(f"- {r}")


def render_dispatch_blocklist(results: pd.DataFrame):
    """Show CRITICAL and HIGH trucks in a compact do-not-dispatch list."""
    blocked = results[results["priority"].isin(["CRITICAL", "HIGH"])].copy()
    if blocked.empty:
        st.success("No trucks flagged for dispatch restriction today.")
        return

    st.error(f"**{len(blocked)} truck(s) flagged — review before dispatching**")
    display = blocked[["vehicle_id", "priority", "risk_score", "failure_mode", "action"]].copy()
    display.columns = ["Vehicle", "Priority", "Score", "Failure Mode", "Action"]
    st.dataframe(display, use_container_width=True, hide_index=True)


# ── Column validation helper ──────────────────────────────────────────────────

def check_columns(df: pd.DataFrame) -> tuple[list, list]:
    """Return (missing_required, present_optional)."""
    missing  = [f for f in REQUIRED_FIELDS if f not in df.columns]
    optional = [f for f in OPTIONAL_FIELDS if f in df.columns]
    return missing, optional


# ── Main app ──────────────────────────────────────────────────────────────────

def main():
    # Ensure SQLite prediction table exists
    init_db()

    user = st.session_state["tg_user"]

    # ── Header with logo, user info and logout ───────────────────────────────
    from tg_logo import render_logo_icon
    col_logo, col_title, col_user = st.columns([0.5, 3.5, 1])
    with col_logo:
        render_logo_icon(52)
    with col_title:
        st.markdown(
            "<h2 style='margin:0;padding-top:0.2rem'>ThrottleGuard</h2>"
            "<p style='margin:0;color:#6b7280;font-size:0.85rem'>"
            "DPF Health Assessment · Expert System v1</p>",
            unsafe_allow_html=True,
        )
    with col_user:
        st.markdown(f"<div style='text-align:right;padding-top:0.4rem'>"
                    f"<b>{user['username']}</b> · {user['role']}</div>",
                    unsafe_allow_html=True)
        if st.button("Sign Out", use_container_width=True):
            st.session_state["tg_user"] = None
            st.rerun()

    # ── Navigation (Admin gets extra tabs) ───────────────────────────────────
    tabs = ["Dashboard", "Fleet Scores"]
    if can_do("manage_users"):
        tabs.append("User Management")

    tab_selection = st.radio("Navigation", tabs, horizontal=True, label_visibility="collapsed")

    if tab_selection == "User Management":
        user_management_panel()
        return

    if tab_selection == "Fleet Scores":
        tutorial_callout("scores_tab")
        from scored_dashboard import display_scored_dashboard
        from tg_demo_data import get_demo_scored

        # Cache scored demo in session state — avoids writing to disk.
        # Railway containers have ephemeral filesystems; session state survives
        # within a user session and is per-user (no cross-session file collisions).
        if "scored_df" not in st.session_state:
            st.session_state["scored_df"] = get_demo_scored()

        display_scored_dashboard(preloaded_df=st.session_state["scored_df"])
        return

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Upload Fleet Data")
        # Viewers cannot upload — show a clear message instead of a broken uploader
        if not can_do("upload"):
            st.info("Your role (Viewer) is read-only. Contact your Admin to upload data.")
            uploaded = None
        else:
            # Load Demo Data button
            if st.button("Load Demo Fleet (30 trucks)", type="primary", use_container_width=True):
                from tg_demo_data import get_demo_fleet
                st.session_state["demo_df"] = get_demo_fleet()
                st.success("Demo fleet loaded — 30 trucks across Detroit, Volvo/Mack, Cummins/PACCAR")

            uploaded = st.file_uploader("Or upload your own CSV", type="csv")

        st.divider()
        st.markdown("**Required columns:**")
        for f in REQUIRED_FIELDS:
            st.markdown(f"- `{f}`")

        st.divider()
        st.markdown("**Optional columns** *(improve accuracy)*:")
        for f in OPTIONAL_FIELDS:
            st.markdown(f"- `{f}`")

        st.divider()
        st.caption(
            "Predictions are logged to `predictions.db` for fleet validation. "
            "Fill in `actual_failure_occurred` after service to build ground truth."
        )

        render_tutorial_sidebar()

    # ── No file uploaded — check for demo data in session state ──────────────
    tutorial_callout("demo")

    if uploaded is None and "demo_df" in st.session_state:
        uploaded = None  # keep None so we use demo path below

    if uploaded is None and "demo_df" not in st.session_state:

        # ── Hero section ──────────────────────────────────────────────────────
        from tg_logo import render_logo
        _, col_b, _ = st.columns([1, 1, 1])
        with col_b:
            render_logo("large")
        st.markdown(
            "<p style='text-align:center;font-size:1.1rem;color:#9ca3af;margin:0'>"
            "Know before it breaks</p>",
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # ── Value props ───────────────────────────────────────────────────────
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("""
            **🔴 Stop Roadside Breakdowns**

            A clogged DPF on the highway means a forced derate to 5 mph,
            an emergency tow, and $3,000–$8,000 in unplanned repair costs.
            ThrottleGuard flags the truck before it leaves the yard.
            """)
        with c2:
            st.markdown("""
            **📊 Plain-English Alerts**

            Not fault codes. Not raw sensor numbers.
            Your dispatcher sees: *"TRK-001 — do not dispatch.
            Incomplete burn detected. Schedule DPF service within 24–48 hours."*
            """)
        with c3:
            st.markdown("""
            **⚙️ Built on 20 Years in the Field**

            Every threshold — Detroit, Volvo/Mack, Cummins/PACCAR — is
            field-validated from real failure diagnosis, not OEM datasheets.
            The system knows what a failing DPF actually looks like.
            """)

        st.markdown("---")

        # ── How it works ─────────────────────────────────────────────────────
        st.markdown("### How It Works")
        h1, h2, h3, h4 = st.columns(4)
        with h1:
            st.markdown("**1️⃣ Upload fleet data**\nCSV from your telematics system or ELD export")
        with h2:
            st.markdown("**2️⃣ Expert system scores every truck**\n16 rules across DPF + SCR, 3 engine families")
        with h3:
            st.markdown("**3️⃣ See who needs action today**\nCRITICAL → HIGH → MEDIUM → LOW")
        with h4:
            st.markdown("**4️⃣ Act on specific reasons**\nNot a black box — every flag has a cause")

        st.markdown("---")
        st.info("👈 Click **Load Demo Fleet** in the sidebar to see a live 30-truck demo, or upload your own CSV.")

        st.markdown("### Expected CSV format")
        sample = pd.DataFrame([{
            "vehicle_id": "TRUCK-001",
            "dpf_outlet_temp_active_regen_f": 890,
            "dpf_outlet_temp_peak_f": 1050,
            "dpf_inlet_temp_f": 940,
            "regen_count_7d": 4,
            "back_pressure_inh2o": 3.2,
            "driver_reported_frequent_regen": True,
            "mileage_since_last_dpf_cleaning": 280000,
            "oil_consumption_qt_per_1000mi": 0.4,
        }])
        st.dataframe(sample, use_container_width=True, hide_index=True)

        st.markdown("### Aftertreatment Scoring Rules (DPF + SCR)")
        rules = pd.DataFrame([
            # ── DPF rules ─────────────────────────────────────────────────────
            {"Pts": "70", "Level": "CRITICAL", "System": "DPF",  "Rule": "Outlet <500°F AND Inlet >1000°F during regen — sensor fault or DPF breach"},
            {"Pts": "60", "Level": "CRITICAL", "System": "DPF",  "Rule": "Outlet temp <940°F during active regen — incomplete burn, clogging"},
            {"Pts": "50", "Level": "CRITICAL", "System": "DPF",  "Rule": "Peak temp above family limit (Detroit/Volvo 1250°F, Cummins 1200°F) — thermal shock"},
            {"Pts": "40", "Level": "CRITICAL", "System": "SCR",  "Rule": "NOx conversion <50% — EPA derate risk, SCR catalyst failing"},
            {"Pts": "30", "Level": "HIGH",     "System": "DPF",  "Rule": "Regen count >2 in 7 days OR driver reports frequent regen"},
            {"Pts": "25", "Level": "HIGH",     "System": "DPF",  "Rule": "Mileage >300k since DPF cleaning AND oil consumption >0.5 qt/1000mi"},
            {"Pts": "25", "Level": "HIGH",     "System": "DPF",  "Rule": "Turbo boost <20 PSI OR EGR flow fault"},
            {"Pts": "25", "Level": "HIGH",     "System": "SCR",  "Rule": "DEF concentration critically out of spec (<20% or >40%) — water contamination"},
            {"Pts": "20", "Level": "HIGH",     "System": "SCR",  "Rule": "NOx conversion 50–70% — catalyst degraded, schedule SCR inspection"},
            {"Pts": "20", "Level": "HIGH",     "System": "BOTH", "Rule": "Compound: DPF + SCR both flagged (+20 Detroit 1-Box, +15 other families)"},
            {"Pts": "15", "Level": "MEDIUM",   "System": "DPF",  "Rule": "Avg trip <15 mi AND idle time >35% — DPF unable to self-clean"},
            {"Pts": "15", "Level": "MEDIUM",   "System": "DPF",  "Rule": "DEF contamination >50 ppm OR DEF doser fault"},
            {"Pts": "15", "Level": "MEDIUM",   "System": "SCR",  "Rule": "SCR inlet temp <400°F — catalyst below light-off, NOx bypass risk"},
            {"Pts": "10", "Level": "MEDIUM",   "System": "DPF",  "Rule": "Water in fuel detected OR fuel filter changed <45 days"},
            {"Pts": "10", "Level": "MEDIUM",   "System": "DPF",  "Rule": "Back pressure >4.0 in.H2O — approaching DPF blockage"},
            {"Pts": "10", "Level": "MEDIUM",   "System": "SCR",  "Rule": "DEF concentration out of spec (31–34% urea required) OR NH3 slip detected"},
        ])
        st.dataframe(rules, use_container_width=True, hide_index=True)
        return

    # ── Load and normalize CSV (or demo data) ────────────────────────────────
    if uploaded is not None:
        df = pd.read_csv(uploaded)
    elif "demo_df" in st.session_state:
        df = st.session_state["demo_df"].copy()
    else:
        return
    df = normalize_columns(df)

    missing_cols, optional_present = check_columns(df)

    if missing_cols:
        st.error(
            f"**Missing required columns:** {', '.join(missing_cols)}\n\n"
            "Rename your CSV columns to match or add them before uploading."
        )
        st.markdown("**Columns found in your file:**")
        st.write(list(df.columns))
        return

    # ── Run expert system ─────────────────────────────────────────────────────
    with st.spinner("Running DPF health assessment..."):
        results = run_expert_system(df)

    total = len(results)
    critical_count = (results["priority"] == "CRITICAL").sum()

    # ── Summary banner ────────────────────────────────────────────────────────
    if critical_count > 0:
        st.error(
            f"**{critical_count} of {total} vehicles** require immediate attention. "
            "Do not dispatch until inspected."
        )
    else:
        st.success(f"Assessment complete — {total} vehicles scored. No CRITICAL alerts.")

    st.markdown(
        f"*Optional columns detected: {len(optional_present)} of {len(OPTIONAL_FIELDS)} "
        f"({', '.join(optional_present) if optional_present else 'none'}) — "
        "more columns = more accurate scoring.*"
    )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_overview, tab_dispatch, tab_detail, tab_data = st.tabs([
        "Fleet Overview", "Dispatch Blocklist", "Vehicle Detail", "Raw Data"
    ])

    with tab_overview:
        tutorial_callout("kpi")
        render_fleet_summary(results)
        st.divider()
        tutorial_callout("alert")
        col1, col2, col3 = st.columns(3)
        with col1:
            render_priority_chart(results)
        with col2:
            render_score_histogram(results)
        with col3:
            render_failure_mode_chart(results)

    with tab_dispatch:
        st.markdown("### Do-Not-Dispatch List")
        st.caption("Vehicles with CRITICAL or HIGH risk scores that should not leave the yard until inspected.")
        render_dispatch_blocklist(results)

    with tab_detail:
        tutorial_callout("detail")
        tutorial_callout("rules")
        render_detailed_table(results)

    with tab_data:
        st.markdown("### Full Assessment Results")
        st.dataframe(
            results[["vehicle_id", "risk_score", "priority", "failure_mode", "reasons", "action"]]
            .sort_values("risk_score", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        csv_out = results.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download results as CSV",
            data=csv_out,
            file_name=f"throttleguard_assessment_{date.today()}.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
