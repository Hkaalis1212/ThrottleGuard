"""
ThrottleGuard DPF Dashboard
===========================
Production predictor: rule-based expert system (dpf_expert_system.py)
XGBoost removed — negative R2, 5% critical recall.

Workflow:
  1. Upload CSV with DPF sensor / service columns
  2. Expert system scores every row
  3. Results displayed by priority, with reasons and actions
  4. Every prediction logged to Supabase PostgreSQL for future validation
"""

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from dpf_expert_system import calculate_expert_score, REQUIRED_FIELDS, OPTIONAL_FIELDS
from outcome_db import log_prediction, log_predictions_batch, init_db, get_predictions, record_outcome, get_validation_summary, get_calibration_data
from tg_auth import init_auth_db, login_page, can_do, user_management_panel
from tg_tutorial import render_tutorial_sidebar, tutorial_callout
from tg_subscription import (
    is_active, start_trial, get_subscription,
    create_payment_intent, confirm_payment, get_payment_history,
    cancel_subscription, PRICING,
)
from tg_styles import (
    inject_styles,
    PRIORITY_COLOR, PRIORITY_ORDER,
    render_kpi_row,
    render_section_header,
    render_vehicle_expander,
    render_app_header,
    render_dispatch_blocklist_styled,
)

# ── Auth gate ─────────────────────────────────────────────────────────────────
# Guard init_auth_db() so it only opens a DB connection once per session,
# not on every Streamlit rerun (every tab click / widget interaction).
if "_auth_db_ready" not in st.session_state:
    init_auth_db()
    st.session_state["_auth_db_ready"] = True

if "tg_user" not in st.session_state or not st.session_state["tg_user"]:
    login_page()
    st.stop()

# ── Subscription gate ─────────────────────────────────────────────────────────
_fleet_id = "admin"

# Cache the subscription active-check per session so we don't open a new
# DB connection on every rerun. Cleared on sign-out and after payment.
if "_sub_active" not in st.session_state:
    st.session_state["_sub_active"] = is_active(_fleet_id)

if not st.session_state["_sub_active"]:
    _sub = get_subscription(_fleet_id)

    st.set_page_config(page_title="ThrottleGuard — Subscription", page_icon="🚛", layout="centered")
    inject_styles()

    from tg_logo import render_logo
    render_logo("medium")
    st.markdown("---")

    if _sub is None:
        st.markdown("## Start Your Free Trial")
        st.markdown(
            f"Get **{PRICING['trial_days']} days free** — full access, no credit card required.\n\n"
            f"After your trial: **${PRICING['starter']:.2f}/mo** (1–25 trucks), "
            f"**${PRICING['growth']:.2f}/mo** (26–100 trucks), or "
            f"**${PRICING['fleet']:.2f}/mo** (101–500 trucks)."
        )
        if st.button("Start Free Trial", type="primary", use_container_width=True):
            result = start_trial(_fleet_id)
            if result["success"]:
                st.success(f"Trial started — {PRICING['trial_days']} days of full access.")
                st.session_state.pop("_sub_active", None)  # force re-check on next run
                st.rerun()
            else:
                st.error(result["error"])
    else:
        st.markdown("## Your Trial Has Ended")
        st.markdown("Choose a plan to continue accessing ThrottleGuard.")

        col_s, col_g, col_f = st.columns(3)
        with col_s:
            st.markdown(
                f"### Starter\n"
                f"**1–25 trucks**\n\n"
                f"**${PRICING['starter']:.2f}** / month\n\n"
                "Cancel anytime."
            )
            if st.button("Subscribe — Starter", use_container_width=True):
                st.session_state["tg_plan_selected"] = "starter"

        with col_g:
            st.markdown(
                f"### Growth\n"
                f"**26–100 trucks**\n\n"
                f"**${PRICING['growth']:.2f}** / month\n\n"
                "Cancel anytime."
            )
            if st.button("Subscribe — Growth", type="primary", use_container_width=True):
                st.session_state["tg_plan_selected"] = "growth"

        with col_f:
            st.markdown(
                f"### Fleet\n"
                f"**101–500 trucks**\n\n"
                f"**${PRICING['fleet']:.2f}** / month\n\n"
                "Cancel anytime."
            )
            if st.button("Subscribe — Fleet", type="primary", use_container_width=True):
                st.session_state["tg_plan_selected"] = "fleet"

        plan = st.session_state.get("tg_plan_selected")
        plan_labels = {
            "starter": "Starter (1–25 trucks)",
            "growth":  "Growth (26–100 trucks)",
            "fleet":   "Fleet (101–500 trucks)",
        }
        if plan:
            st.markdown("---")
            st.markdown(f"**{plan_labels.get(plan, plan)} — ${PRICING[plan]:.2f}/mo**")
            intent_result = create_payment_intent(_fleet_id, plan)
            if not intent_result["success"]:
                st.error(intent_result["error"])
            else:
                st.info("Enter your payment details below. After payment, paste the Payment Intent ID to activate.")
                payment_intent_id = st.text_input("Payment Intent ID (from Stripe)")
                if st.button("Confirm Payment", type="primary"):
                    if not payment_intent_id.strip():
                        st.error("Enter the Payment Intent ID from Stripe.")
                    else:
                        result = confirm_payment(_fleet_id, plan, payment_intent_id.strip())
                        if result["success"]:
                            st.success(f"Subscribed! Access active until {result['end_date'].strftime('%B %d, %Y')}.")
                            st.session_state.pop("_sub_active", None)
                            st.rerun()
                        else:
                            st.error(result["error"])

    st.markdown("---")
    if st.button("Sign out"):
        for _k in ["tg_user", "tg_plan_selected", "_active_df", "_active_optional",
                   "_active_src", "_scored_key", "_scored_results", "demo_df",
                   "tg_tour_active", "tg_tour_step", "scored_df",
                   "_sub_active", "_auth_db_ready"]:
            st.session_state.pop(_k, None)
        st.rerun()
    st.stop()


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ThrottleGuard DPF Dashboard",
    page_icon="🚛",
    layout="wide",
)


# ── Column aliases ────────────────────────────────────────────────────────────
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
    # Strip leading/trailing whitespace from column names first
    df = df.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)

    lower_cols = {c.lower(): c for c in df.columns}
    rename_map: dict = {}

    # Canonical names + aliases, all matched case-insensitively.
    # Also handles the common case where someone exports a CSV with
    # Title_Case or UPPER_CASE column names.
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical not in df.columns:
            for name in [canonical] + aliases:
                if name.lower() in lower_cols:
                    rename_map[lower_cols[name.lower()]] = canonical
                    break

    # Lowercase any optional columns that arrived with different casing
    # (e.g. "NOX_Conversion_Pct" → "nox_conversion_pct")
    all_expected = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    for col in list(df.columns):
        target = col.lower()
        if col not in rename_map and target in all_expected and col != target:
            rename_map[col] = target

    return df.rename(columns=rename_map)


# ── Prediction engine ─────────────────────────────────────────────────────────

def run_expert_system(df: pd.DataFrame) -> pd.DataFrame:
    # Score every row. Using a list comprehension over iterrows() is faster
    # than iterrows() alone, and avoids the overhead of df.apply() boxing.
    results = [
        calculate_expert_score(row.where(pd.notna(row), other=None).to_dict())
        for _, row in df.iterrows()
    ]

    result_df = pd.DataFrame(results)

    try:
        # Single batch INSERT instead of one DB round-trip per truck.
        # On a 100-truck fleet this cuts ~100 network calls to Supabase down to 1.
        # Wrapped in try/except so a DB outage never blocks scoring display.
        log_predictions_batch([
            {
                "vehicle_id":              str(r["vehicle_id"]),
                "predicted_priority":      str(r["priority"]),
                "predicted_failure_mode":  str(r["failure_mode"]),
                "risk_score":              r["risk_score"] if r["risk_score"] is not None else -1,
            }
            for r in results
        ])
    except Exception:
        pass  # logging failure must not block the UI

    return result_df


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _chart_layout(fig, height=300):
    """Apply consistent dark industrial chart theme."""
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f1217",
        font=dict(family="Barlow, sans-serif", color="#8fa3b8", size=11),
        margin=dict(t=36, b=10, l=10, r=10),
        title_font=dict(
            family="Barlow Condensed, sans-serif",
            size=13,
            color="#e8edf2",
        ),
        title_x=0,
    )
    fig.update_xaxes(
        gridcolor="#1a2130",
        linecolor="#252d3a",
        tickfont=dict(family="JetBrains Mono, monospace", size=10, color="#4a6070"),
    )
    fig.update_yaxes(
        gridcolor="#1a2130",
        linecolor="#252d3a",
        tickfont=dict(family="JetBrains Mono, monospace", size=10, color="#4a6070"),
    )
    return fig


def render_priority_chart(results: pd.DataFrame):
    order   = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
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
        title="FLEET HEALTH DISTRIBUTION",
        text="Trucks",
    )
    fig.update_traces(
        textposition="outside",
        textfont=dict(family="JetBrains Mono, monospace", size=13, color="#e8edf2"),
        marker_line_width=0,
    )
    fig.update_layout(showlegend=False)
    _chart_layout(fig, height=320)
    st.plotly_chart(fig, use_container_width=True)


def render_score_histogram(results: pd.DataFrame):
    fig = px.histogram(
        results, x="risk_score", nbins=20,
        title="RISK SCORE DISTRIBUTION",
        labels={"risk_score": "Risk Score (0–100)"},
        color_discrete_sequence=["#f57c00"],
    )
    fig.update_traces(marker_line_color="#0f1217", marker_line_width=1)
    _chart_layout(fig, height=320)
    st.plotly_chart(fig, use_container_width=True)


def render_failure_mode_chart(results: pd.DataFrame):
    fm = results["failure_mode"].value_counts().reset_index()
    fm.columns = ["Failure Mode", "Count"]
    fig = px.pie(
        fm, names="Failure Mode", values="Count",
        title="PREDICTED FAILURE MODES",
        hole=0.55,
        color_discrete_sequence=["#e53935", "#f57c00", "#f9a825", "#43a047", "#546e7a"],
    )
    fig.update_traces(
        textfont=dict(family="Barlow Condensed, sans-serif", size=11),
        marker=dict(line=dict(color="#080a0c", width=2)),
    )
    _chart_layout(fig, height=320)
    st.plotly_chart(fig, use_container_width=True)


# ── Column validation ─────────────────────────────────────────────────────────

def check_columns(df: pd.DataFrame) -> tuple[list, list]:
    missing  = [f for f in REQUIRED_FIELDS if f not in df.columns]
    optional = [f for f in OPTIONAL_FIELDS if f in df.columns]
    return missing, optional


# ── Tab renderers ─────────────────────────────────────────────────────────────

def _render_dashboard_tab(results: pd.DataFrame, optional_present: list):
    total          = len(results)
    critical_count = (results["priority"] == "CRITICAL").sum()

    if critical_count > 0:
        st.markdown(f"""
        <div style="
            background: rgba(229,57,53,0.08);
            border: 1px solid rgba(229,57,53,0.4);
            border-left: 3px solid #e53935;
            border-radius: 4px;
            padding: 0.75rem 1.25rem;
            margin-bottom: 1rem;
            font-family: 'Barlow Condensed', sans-serif;
            font-size: 0.92rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: #e53935;
        ">⚠ {critical_count} of {total} vehicles require immediate attention — do not dispatch until inspected</div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="
            background: rgba(67,160,71,0.06);
            border: 1px solid rgba(67,160,71,0.25);
            border-left: 3px solid #43a047;
            border-radius: 4px;
            padding: 0.75rem 1.25rem;
            margin-bottom: 1rem;
            font-family: 'Barlow Condensed', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            color: #43a047;
        ">✓ Assessment complete — {total} vehicles scored. No critical alerts.</div>
        """, unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#4a6070;margin-bottom:1rem;">'
        f'Optional columns detected: {len(optional_present)} / {len(OPTIONAL_FIELDS)}'
        f'{" · " + ", ".join(optional_present) if optional_present else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    tutorial_callout("kpi")
    render_kpi_row(results)

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
    tutorial_callout("alert")

    col1, col2, col3 = st.columns(3)
    with col1:
        render_priority_chart(results)
    with col2:
        render_score_histogram(results)
    with col3:
        render_failure_mode_chart(results)


def _render_dispatch_tab(results: pd.DataFrame):
    render_section_header(
        "Do-Not-Dispatch List",
        "Vehicles with CRITICAL or HIGH risk that must not leave the yard without inspection",
    )
    render_dispatch_blocklist_styled(results)


def _render_detail_tab(results: pd.DataFrame):
    tutorial_callout("detail")
    tutorial_callout("rules")
    render_section_header("Vehicle Detail", "Sorted by priority · Expand any vehicle for full diagnosis")

    col_filter, col_search = st.columns([1, 2])
    with col_filter:
        priority_filter = st.selectbox(
            "Filter by priority",
            ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
            key="detail_priority_filter",
        )
    with col_search:
        search_term = st.text_input(
            "Search vehicle ID",
            placeholder="e.g. T-247",
            key="detail_search",
        ).strip().upper()

    sorted_results = results.sort_values(
        "priority", key=lambda s: s.map(PRIORITY_ORDER)
    ).reset_index(drop=True)

    if priority_filter != "ALL":
        sorted_results = sorted_results[sorted_results["priority"] == priority_filter]

    if search_term:
        sorted_results = sorted_results[
            sorted_results["vehicle_id"].astype(str).str.upper().str.contains(search_term, na=False)
        ]

    if sorted_results.empty:
        st.info("No vehicles match the current filter.")
        return

    st.caption(f"Showing {len(sorted_results)} of {len(results)} vehicles")

    for _, row in sorted_results.iterrows():
        try:
            render_vehicle_expander(row)
        except Exception as _ve:
            st.warning(f"Could not render vehicle {row.get('vehicle_id', '?')}: {_ve}")


def _render_data_tab(results: pd.DataFrame):
    render_section_header("Full Assessment Results", "All vehicles · sortable · downloadable")

    display_cols = [c for c in ["vehicle_id", "risk_score", "priority", "failure_mode", "reasons", "action"] if c in results.columns]

    if not display_cols:
        st.warning(f"Unexpected result columns: {list(results.columns)}")
        st.dataframe(results, use_container_width=True, hide_index=True)
    else:
        sort_col = "risk_score" if "risk_score" in display_cols else display_cols[0]
        try:
            display_df = results[display_cols].sort_values(sort_col, ascending=False, na_position="last")
        except Exception:
            display_df = results[display_cols]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    csv_out = results.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Download Results CSV",
        data=csv_out,
        file_name=f"throttleguard_assessment_{date.today()}.csv",
        mime="text/csv",
        key="download_results_csv",
    )


def _render_fleet_scores_tab():
    tutorial_callout("scores_tab")
    from scored_dashboard import display_scored_dashboard
    from tg_demo_data import get_demo_scored

    if "scored_df" not in st.session_state:
        st.session_state["scored_df"] = get_demo_scored()

    display_scored_dashboard(preloaded_df=st.session_state["scored_df"])


def _render_outcomes_tab():
    render_section_header(
        "Outcome Tracking",
        "Log service outcomes to build ground truth and validate expert system accuracy over time",
    )

    # Cache pending predictions per session — DB query only on first load or after
    # an outcome is recorded (the record_outcome handler clears this key).
    if "_pending_predictions" not in st.session_state:
        st.session_state["_pending_predictions"] = get_predictions(unvalidated_only=True)
    pending = st.session_state["_pending_predictions"]

    render_section_header("Log Outcome", "")

    if not pending:
        st.markdown("""
        <div style="
            background: rgba(67,160,71,0.06);
            border: 1px solid rgba(67,160,71,0.25);
            border-left: 3px solid #43a047;
            border-radius: 4px;
            padding: 0.85rem 1.25rem;
            font-family: 'Barlow', sans-serif;
            font-size: 0.88rem;
            color: #43a047;
        ">✓ No pending predictions — all logged predictions have been validated.</div>
        """, unsafe_allow_html=True)
    else:
        pending_df = pd.DataFrame(pending)
        pending_df["label"] = (
            pending_df["vehicle_id"]
            + " · " + pending_df["prediction_date"]
            + " · " + pending_df["predicted_priority"]
        )
        label_to_row = dict(zip(pending_df["label"], pending_df.to_dict("records")))

        with st.form("log_outcome_form"):
            selected_label = st.selectbox("Select prediction to validate", list(label_to_row.keys()))
            row = label_to_row[selected_label]

            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;'
                f'color:#8fa3b8;margin:0.5rem 0;">'
                f'Predicted: {row["predicted_failure_mode"]} · Risk score {row["risk_score"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

            failure_occurred = st.radio(
                "Did a DPF/SCR failure actually occur?",
                ["Yes — failure confirmed", "No — false alarm"],
                horizontal=True,
            )
            outcome_date = st.date_input("Date of service / outcome", value=date.today())
            notes        = st.text_area(
                "Technician notes (optional)",
                placeholder="e.g. DPF removed and cleaned, 68% ash load confirmed",
            )

            if st.form_submit_button("Save Outcome", type="primary"):
                updated = record_outcome(
                    vehicle_id=row["vehicle_id"],
                    prediction_date=row["prediction_date"],
                    actual_failure_occurred=(failure_occurred.startswith("Yes")),
                    actual_outcome_date=outcome_date.isoformat(),
                    notes=notes or None,
                )
                if updated:
                    st.success(f"Outcome saved for {row['vehicle_id']}.")
                    st.session_state.pop("_pending_predictions", None)  # refresh on next run
                    st.rerun()
                else:
                    st.error("Could not save — prediction record not found.")

    st.divider()

    render_section_header(f"Awaiting Validation ({len(pending)})", "")
    if pending:
        cols_to_show = ["vehicle_id", "prediction_date", "predicted_priority",
                        "predicted_failure_mode", "risk_score"]
        st.dataframe(
            pd.DataFrame(pending)[cols_to_show],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    render_section_header("Expert System Accuracy", "Precision per priority level across all validated predictions")

    summary  = get_validation_summary()
    cal_data = get_calibration_data()

    if not summary:
        st.markdown("""
        <div style="
            background: rgba(84,110,122,0.08);
            border: 1px solid #252d3a;
            border-left: 3px solid #546e7a;
            border-radius: 4px;
            padding: 0.85rem 1.25rem;
            font-family: 'Barlow', sans-serif;
            font-size: 0.88rem;
            color: #8fa3b8;
        ">No validated predictions yet — accuracy stats appear here after outcomes are logged.</div>
        """, unsafe_allow_html=True)
    else:
        summary_df = pd.DataFrame(summary)
        summary_df.columns = ["Priority", "Total", "True Positives", "False Positives", "Pending"]
        summary_df["Precision"] = summary_df.apply(
            lambda r: f"{r['True Positives'] / (r['True Positives'] + r['False Positives']) * 100:.0f}%"
            if (r["True Positives"] + r["False Positives"]) > 0 else "—",
            axis=1,
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        if len(cal_data) >= 10:
            st.divider()
            render_section_header(
                "Threshold Calibration",
                "True failures vs false alarms by risk score — well-calibrated thresholds separate the two cleanly",
            )
            cal_df = pd.DataFrame(cal_data)
            cal_df["outcome"] = cal_df["actual_failure_occurred"].map(
                {1: "Failure confirmed", 0: "False alarm"}
            )

            fig = px.histogram(
                cal_df,
                x="risk_score",
                color="outcome",
                nbins=20,
                barmode="overlay",
                opacity=0.75,
                color_discrete_map={
                    "Failure confirmed": "#e53935",
                    "False alarm":       "#42a5f5",
                },
                labels={"risk_score": "Risk Score", "count": "Predictions"},
            )
            for score, label, color in [
                (60, "CRITICAL", "#e53935"),
                (35, "HIGH",     "#f57c00"),
                (15, "MEDIUM",   "#f9a825"),
            ]:
                fig.add_vline(
                    x=score, line_dash="dash", line_color=color, line_width=1.5,
                    annotation_text=label,
                    annotation_font=dict(family="Barlow Condensed, sans-serif", color=color, size=11),
                    annotation_position="top",
                )

            _chart_layout(fig, height=340)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
                'letter-spacing:0.1em;text-transform:uppercase;color:#4a6070;margin-bottom:0.5rem;">'
                'Calibration Notes</div>',
                unsafe_allow_html=True,
            )
            for _, row in summary_df.iterrows():
                tp    = row["True Positives"]
                fp    = row["False Positives"]
                total = tp + fp
                if total == 0:
                    continue
                precision = tp / total
                priority  = row["Priority"]
                if precision >= 0.80:
                    st.success(f"**{priority}** — {precision*100:.0f}% precision. Threshold is well-calibrated.")
                elif precision >= 0.60:
                    st.warning(f"**{priority}** — {precision*100:.0f}% precision. Consider raising this threshold slightly.")
                else:
                    st.error(
                        f"**{priority}** — {precision*100:.0f}% precision. "
                        f"Too many false alarms — raise the {priority} score cutoff in throttleguard_engine_thresholds.py."
                    )
        elif cal_data:
            st.caption(f"Calibration chart appears after 10 validated predictions ({len(cal_data)} so far).")


def _render_subscription_tab():
    render_section_header("Subscription", "Billing and plan management")

    if "_sub_info" not in st.session_state:
        st.session_state["_sub_info"] = get_subscription("admin")
    sub = st.session_state["_sub_info"]
    if sub:
        status_color = "#43a047" if sub["status"] == "active" else "#e53935"
        st.markdown(
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;color:#8fa3b8;'
            f'background:#0f1217;border:1px solid #252d3a;border-radius:4px;padding:0.7rem 1rem;margin-bottom:1rem;">'
            f'Plan: <span style="color:#e8edf2;">{sub["plan_type"].upper()}</span> &nbsp;·&nbsp; '
            f'Status: <span style="color:{status_color};">{sub["status"].upper()}</span> &nbsp;·&nbsp; '
            f'Expires: <span style="color:#e8edf2;">{sub["end_date"][:10]}</span> &nbsp;·&nbsp; '
            f'<span style="color:#f57c00;">{sub["days_remaining"]} days remaining</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    if not sub or sub["status"] != "active" or sub["plan_type"] == "trial":
        render_section_header("Upgrade Plan", "")
        col_s, col_g, col_f = st.columns(3)
        with col_s:
            st.markdown(f"**Starter** — 1–25 trucks\n\n${PRICING['starter']:.2f}/mo · Cancel anytime.")
            if st.button("Subscribe — Starter", use_container_width=True, key="sub_starter"):
                st.session_state["tg_plan_selected"] = "starter"
        with col_g:
            st.markdown(f"**Growth** — 26–100 trucks\n\n${PRICING['growth']:.2f}/mo · Cancel anytime.")
            if st.button("Subscribe — Growth", type="primary", use_container_width=True, key="sub_growth"):
                st.session_state["tg_plan_selected"] = "growth"
        with col_f:
            st.markdown(f"**Fleet** — 101–500 trucks\n\n${PRICING['fleet']:.2f}/mo · Cancel anytime.")
            if st.button("Subscribe — Fleet", type="primary", use_container_width=True, key="sub_fleet"):
                st.session_state["tg_plan_selected"] = "fleet"

        plan = st.session_state.get("tg_plan_selected")
        plan_labels = {
            "starter": "Starter (1–25 trucks)",
            "growth":  "Growth (26–100 trucks)",
            "fleet":   "Fleet (101–500 trucks)",
        }
        if plan:
            st.markdown(f"**{plan_labels.get(plan, plan)} — ${PRICING[plan]:.2f}/mo**")
            intent_result = create_payment_intent("admin", plan)
            if not intent_result["success"]:
                st.error(intent_result["error"])
            else:
                st.code(intent_result["client_secret"], language=None)
                st.caption("Use this client secret with your Stripe payment form.")
                payment_intent_id = st.text_input("Payment Intent ID (from Stripe)")
                if st.button("Confirm Payment", type="primary"):
                    result = confirm_payment("admin", plan, payment_intent_id.strip())
                    if result["success"]:
                        st.success(f"Subscribed until {result['end_date'].strftime('%B %d, %Y')}.")
                        for _k in ("tg_plan_selected", "_sub_info", "_sub_active", "_payment_history"):
                            st.session_state.pop(_k, None)
                        st.rerun()
                    else:
                        st.error(result["error"])

    st.markdown("---")

    if sub and sub["status"] == "active" and sub["plan_type"] != "trial":
        render_section_header("Cancel Subscription", "")
        st.caption("You keep access until the end of your current billing period.")
        if st.button("Cancel Subscription", type="secondary"):
            result = cancel_subscription("admin")
            if result["success"]:
                st.success("Subscription cancelled. Access continues until expiry.")
                st.session_state.pop("_sub_info", None)
                st.session_state.pop("_sub_active", None)
                st.rerun()
            else:
                st.error(result["error"])
        st.markdown("---")

    render_section_header("Payment History", "")
    if "_payment_history" not in st.session_state:
        st.session_state["_payment_history"] = get_payment_history("admin")
    history = st.session_state["_payment_history"]
    if history:
        st.dataframe(
            pd.DataFrame(history)[["payment_date", "plan_type", "amount", "status", "transaction_id"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.markdown(
            '<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;color:#4a6070;">No payments yet.</div>',
            unsafe_allow_html=True,
        )


# ── Landing / no-data state ───────────────────────────────────────────────────

def _render_landing():
    from tg_logo import render_logo

    st.markdown("""
<style>
/* Force full viewport height and center content */
.stApp {
    background-color: #0e0e0e;
}

/* Remove default Streamlit padding that pushes content down */
.block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}

/* Full-height centering wrapper */
[data-testid="stVerticalBlock"] > [style*="flex-direction: column"] > [data-testid="stVerticalBlock"] {
    justify-content: center;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

/* Tighten the left-column bullet points */
.login-left ul {
    margin-top: 0.5rem;
    line-height: 1.6;
}
</style>
""", unsafe_allow_html=True)

    # Hero — constrained width so it reads as centered on wide layout
    _, col_hero, _ = st.columns([1, 3, 1])
    with col_hero:
        render_logo("large")
        st.markdown(
            "<p style='text-align:center;font-family:\"Barlow Condensed\",sans-serif;"
            "font-size:1rem;letter-spacing:0.15em;text-transform:uppercase;"
            "color:#4a6070;margin:0.25rem 0 2rem;'>Know Before It Breaks</p>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    value_props = [
        (
            "Stop Roadside Breakdowns",
            "A clogged DPF on the highway means a forced derate to 5 mph, "
            "an emergency tow, and $3,000–$8,000 in unplanned repair costs. "
            "ThrottleGuard flags the truck before it leaves the yard.",
            "#e53935",
        ),
        (
            "Plain-English Alerts",
            "Not fault codes. Not raw sensor numbers. Your dispatcher sees: "
            "TRK-001 — do not dispatch. Incomplete burn detected. "
            "Schedule DPF service within 24–48 hours.",
            "#f57c00",
        ),
        (
            "20 Years in the Field",
            "Every threshold — Detroit, Volvo/Mack, Cummins/PACCAR — is "
            "field-validated from real failure diagnosis, not OEM datasheets. "
            "The system knows what a failing DPF actually looks like.",
            "#f9a825",
        ),
    ]

    for col, (title, body, color) in zip([c1, c2, c3], value_props):
        col.markdown(f"""
        <div style="
            background: #0f1217;
            border: 1px solid #1a2130;
            border-top: 3px solid {color};
            border-radius: 6px;
            padding: 1.25rem;
        ">
            <div style="
                font-family: 'Barlow Condensed', sans-serif;
                font-size: 1rem;
                font-weight: 700;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                color: {color};
                margin-bottom: 0.6rem;
            ">{title}</div>
            <div style="
                font-family: 'Barlow', sans-serif;
                font-size: 0.85rem;
                color: #8fa3b8;
                line-height: 1.6;
            ">{body}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    render_section_header("How It Works", "Four steps from raw data to dispatch decisions", centered=True)

    h1, h2, h3, h4 = st.columns(4)
    steps = [
        ("01", "Upload fleet data", "CSV from your telematics system or ELD export"),
        ("02", "Expert system scores", "16 rules across DPF + SCR, 3 engine families"),
        ("03", "See who needs action", "CRITICAL → HIGH → MEDIUM → LOW priority"),
        ("04", "Act on specific reasons", "Not a black box — every flag has a cause"),
    ]

    for col, (num, title, desc) in zip([h1, h2, h3, h4], steps):
        col.markdown(f"""
        <div style="
            background: #0f1217;
            border: 1px solid #1a2130;
            border-radius: 6px;
            padding: 1rem;
            text-align: center;
        ">
            <div style="
                font-family: 'JetBrains Mono', monospace;
                font-size: 1.8rem;
                font-weight: 600;
                color: #1a2130;
                margin-bottom: 0.3rem;
            ">{num}</div>
            <div style="
                font-family: 'Barlow Condensed', sans-serif;
                font-size: 0.9rem;
                font-weight: 700;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                color: #e8edf2;
                margin-bottom: 0.3rem;
            ">{title}</div>
            <div style="
                font-family: 'Barlow', sans-serif;
                font-size: 0.78rem;
                color: #4a6070;
                line-height: 1.4;
            ">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
    _, _hint_col, _ = st.columns([1, 3, 1])
    with _hint_col:
        st.info("👈 Click **Load Demo Fleet** in the sidebar to see a live 30-truck demo, or upload your own CSV.")

    st.markdown("---")
    render_section_header("Expected CSV Format", "Bold columns are required · optional columns improve accuracy", centered=True)

    template_rows = [
        {
            "vehicle_id": "TRUCK-001",
            "dpf_outlet_temp_active_regen_f": 870,
            "dpf_outlet_temp_peak_f": 1190,
            "dpf_inlet_temp_f": 920,
            "regen_count_7d": 3,
            "back_pressure_inh2o": 3.8,
            "engine_family": "DETROIT",
            "driver_reported_frequent_regen": True,
            "mileage_since_last_dpf_cleaning": 310000,
            "oil_consumption_qt_per_1000mi": 0.6,
            "nox_conversion_pct": 62,
            "scr_inlet_temp_f": 415,
        },
        {
            "vehicle_id": "TRUCK-002",
            "dpf_outlet_temp_active_regen_f": 960,
            "dpf_outlet_temp_peak_f": 1080,
            "dpf_inlet_temp_f": 950,
            "regen_count_7d": 1,
            "back_pressure_inh2o": 1.9,
            "engine_family": "CUMMINS_PACCAR",
            "driver_reported_frequent_regen": False,
            "mileage_since_last_dpf_cleaning": 95000,
            "oil_consumption_qt_per_1000mi": 0.2,
            "nox_conversion_pct": 93,
            "scr_inlet_temp_f": 568,
        },
    ]
    template_df = pd.DataFrame(template_rows)
    st.dataframe(template_df, use_container_width=True, hide_index=True)

    csv_bytes = template_df.to_csv(index=False).encode()
    st.download_button(
        label="⬇ Download CSV Template",
        data=csv_bytes,
        file_name="throttleguard_template.csv",
        mime="text/csv",
    )

    st.markdown("---")
    render_section_header("Scoring Rules", "DPF + SCR aftertreatment rule set", centered=True)

    rules = pd.DataFrame([
        {"Pts": "70", "Level": "CRITICAL", "System": "DPF",  "Rule": "Outlet <500°F AND Inlet >1000°F during regen — sensor fault or DPF breach"},
        {"Pts": "60", "Level": "CRITICAL", "System": "DPF",  "Rule": "Outlet temp <940°F during active regen — incomplete burn, clogging"},
        {"Pts": "50", "Level": "CRITICAL", "System": "DPF",  "Rule": "Peak temp above family limit — thermal shock risk"},
        {"Pts": "40", "Level": "CRITICAL", "System": "SCR",  "Rule": "NOx conversion <50% — EPA derate risk, SCR catalyst failing"},
        {"Pts": "30", "Level": "HIGH",     "System": "DPF",  "Rule": "Regen count >2 in 7 days OR driver reports frequent regen"},
        {"Pts": "25", "Level": "HIGH",     "System": "DPF",  "Rule": "Mileage >300k since DPF cleaning AND oil consumption >0.5 qt/1000mi"},
        {"Pts": "25", "Level": "HIGH",     "System": "DPF",  "Rule": "Turbo boost <20 PSI OR EGR flow fault"},
        {"Pts": "25", "Level": "HIGH",     "System": "SCR",  "Rule": "DEF concentration critically out of spec — water contamination"},
        {"Pts": "20", "Level": "HIGH",     "System": "SCR",  "Rule": "NOx conversion 50–70% — catalyst degraded"},
        {"Pts": "20", "Level": "HIGH",     "System": "BOTH", "Rule": "Compound: DPF + SCR both flagged (+20 Detroit 1-Box, +15 other)"},
        {"Pts": "15", "Level": "MEDIUM",   "System": "DPF",  "Rule": "Avg trip <15 mi AND idle time >35% — DPF unable to self-clean"},
        {"Pts": "15", "Level": "MEDIUM",   "System": "DPF",  "Rule": "DEF contamination >50 ppm OR DEF doser fault"},
        {"Pts": "15", "Level": "MEDIUM",   "System": "SCR",  "Rule": "SCR inlet temp <400°F — catalyst below light-off"},
        {"Pts": "10", "Level": "MEDIUM",   "System": "DPF",  "Rule": "Water in fuel detected OR fuel filter changed <45 days"},
        {"Pts": "10", "Level": "MEDIUM",   "System": "DPF",  "Rule": "Back pressure >4.0 in.H2O — approaching DPF blockage"},
        {"Pts": "10", "Level": "MEDIUM",   "System": "SCR",  "Rule": "DEF concentration out of spec OR NH3 slip detected"},
    ])
    st.dataframe(rules, use_container_width=True, hide_index=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    init_db()
    inject_styles()

    user = st.session_state["tg_user"]

    # ── App header ────────────────────────────────────────────────────────────
    col_header, col_signout = st.columns([5, 1])
    with col_header:
        render_app_header(user)
    with col_signout:
        st.markdown("<div style='padding-top:0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("Sign Out", use_container_width=True):
            for _k in [
                "tg_user", "_active_df", "_active_optional", "_active_src",
                "_scored_key", "_scored_results", "demo_df", "tg_plan_selected",
                "tg_tour_active", "tg_tour_step", "scored_df",
                "_sub_active", "_auth_db_ready", "_pending_predictions",
                "_sub_info", "_payment_history",
            ]:
                st.session_state.pop(_k, None)
            st.rerun()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1rem;'
            'font-weight:700;letter-spacing:0.1em;text-transform:uppercase;'
            'color:#e8edf2;margin-bottom:1rem;">Upload Fleet Data</div>',
            unsafe_allow_html=True,
        )

        if not can_do("upload"):
            st.info("Your role (Viewer) is read-only. Contact your Admin to upload data.")
            uploaded = None
        else:
            if st.button("Load Demo Fleet (30 trucks)", type="primary", use_container_width=True):
                from tg_demo_data import get_demo_fleet
                st.session_state["demo_df"] = get_demo_fleet()
                st.success("Demo fleet loaded — 30 trucks across Detroit, Volvo/Mack, Cummins/PACCAR")

            uploaded = st.file_uploader("Or upload your own CSV", type="csv")

        st.divider()

        st.markdown(
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
            'letter-spacing:0.1em;text-transform:uppercase;color:#4a6070;margin-bottom:0.4rem;">'
            'Required Columns</div>',
            unsafe_allow_html=True,
        )
        for f in REQUIRED_FIELDS:
            st.markdown(
                f'<code style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;'
                f'color:#f57c00;background:rgba(245,124,0,0.08);padding:1px 5px;'
                f'border-radius:3px;display:inline-block;margin-bottom:2px;">{f}</code>',
                unsafe_allow_html=True,
            )

        st.divider()

        st.markdown(
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
            'letter-spacing:0.1em;text-transform:uppercase;color:#4a6070;margin-bottom:0.4rem;">'
            'Optional Columns</div>',
            unsafe_allow_html=True,
        )
        for f in OPTIONAL_FIELDS:
            st.markdown(
                f'<code style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;'
                f'color:#546e7a;background:#0f1217;padding:1px 5px;border-radius:3px;'
                f'display:inline-block;margin-bottom:2px;">{f}</code>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.caption("Predictions logged to Supabase · Log outcomes after service to build ground truth.")

        render_tutorial_sidebar()

    # ── Build tab list ────────────────────────────────────────────────────────
    tab_labels = ["Dashboard", "Fleet Scores"]
    if can_do("outcomes"):
        tab_labels.append("Outcomes")
    if can_do("manage_users"):
        tab_labels.append("User Management")
        tab_labels.append("Subscription")

    tab_objects = st.tabs(tab_labels)
    tab_map     = dict(zip(tab_labels, tab_objects))

    # ── Fleet Scores (no data required) ──────────────────────────────────────
    with tab_map["Fleet Scores"]:
        try:
            _render_fleet_scores_tab()
        except Exception as _e:
            st.error(f"Fleet Scores error: {_e}")
            st.exception(_e)

    # ── Outcomes (no data required) ───────────────────────────────────────────
    if "Outcomes" in tab_map:
        with tab_map["Outcomes"]:
            try:
                _render_outcomes_tab()
            except Exception as _e:
                st.error(f"Outcomes error: {_e}")
                st.exception(_e)

    # ── User Management ───────────────────────────────────────────────────────
    if "User Management" in tab_map:
        with tab_map["User Management"]:
            try:
                user_management_panel()
            except Exception as _e:
                st.error(f"User Management error: {_e}")
                st.exception(_e)

    # ── Subscription ──────────────────────────────────────────────────────────
    if "Subscription" in tab_map:
        with tab_map["Subscription"]:
            try:
                _render_subscription_tab()
            except Exception as _e:
                st.error(f"Subscription error: {_e}")
                st.exception(_e)

    # ── Dashboard tab — data-dependent ───────────────────────────────────────
    with tab_map["Dashboard"]:
        tutorial_callout("demo")

        # When a sub-tab widget is clicked, Streamlit reruns the script.
        # On that rerun, st.file_uploader returns None (file gone from uploader state)
        # which previously triggered the early return and left sub-tabs empty.
        # Fix: store df in session state on first upload so it survives reruns.
        if uploaded is not None:
            df = normalize_columns(pd.read_csv(uploaded))
            missing_cols, optional_present = check_columns(df)
            if missing_cols:
                st.error(
                    f"**Missing required columns:** {', '.join(missing_cols)}\n\n"
                    "Rename your CSV columns to match or add them before uploading."
                )
                st.markdown(
                    f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;color:#4a6070;">'
                    f'Columns found: {", ".join(df.columns.tolist())}</div>',
                    unsafe_allow_html=True,
                )
                st.session_state.pop("_scored_key", None)  # clear stale cache
                return
            # Persist the parsed df so reruns (tab clicks) can use it
            st.session_state["_active_df"]       = df
            st.session_state["_active_optional"] = optional_present

        elif "demo_df" in st.session_state:
            df               = st.session_state["demo_df"].copy()
            df               = normalize_columns(df)
            _, optional_present = check_columns(df)
            st.session_state["_active_df"]       = df
            st.session_state["_active_optional"] = optional_present

        elif "_active_df" in st.session_state:
            # Tab-click rerun: file uploader is empty but we still have the df
            df               = st.session_state["_active_df"]
            optional_present = st.session_state.get("_active_optional", [])

        else:
            _render_landing()
            return

        optional_present = st.session_state.get("_active_optional", [])

        # Only rescore when the data actually changes (filename + row count as key)
        src_name  = getattr(uploaded, 'name', 'demo') if uploaded is not None else st.session_state.get("_active_src", "demo")
        cache_key = f"{src_name}_{len(df)}"
        if uploaded is not None:
            st.session_state["_active_src"] = uploaded.name

        if st.session_state.get("_scored_key") != cache_key:
            with st.spinner("Running DPF health assessment..."):
                try:
                    results = run_expert_system(df)
                except Exception as _score_err:
                    st.error(
                        f"**Scoring failed:** {_score_err}\n\n"
                        "Check that your CSV has the required columns with numeric values "
                        "and no blank cells in required fields."
                    )
                    return
            st.session_state["_scored_results"] = results
            st.session_state["_scored_key"]     = cache_key
        else:
            results = st.session_state["_scored_results"]

        sub_tabs = st.tabs(["Fleet Overview", "Dispatch Blocklist", "Vehicle Detail", "Raw Data"])

        with sub_tabs[0]:
            _render_dashboard_tab(results, optional_present)

        with sub_tabs[1]:
            _render_dispatch_tab(results)

        with sub_tabs[2]:
            _render_detail_tab(results)

        with sub_tabs[3]:
            _render_data_tab(results)


if __name__ == "__main__":
    main()
