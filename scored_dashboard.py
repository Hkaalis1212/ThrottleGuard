"""
scored_dashboard.py
-------------------
ThrottleGuard fleet dashboard for scored_output.csv.
Call display_scored_dashboard() from a Streamlit tab.

Requires:
  - scored_output.csv  (produced by scoring_engine.run_scoring)
  - plotly             (already in ThrottleGuard requirements)
"""

import streamlit as st
import pandas as pd
import plotly.express as px

PRIORITY_COLOR = {
    "CRITICAL": "#d32f2f",
    "HIGH":     "#f57c00",
    "MEDIUM":   "#fbc02d",
    "LOW":      "#388e3c",
}
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
PRIORITY_ICON  = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

TREND_COLOR = {
    "↑ Worsening": "#d32f2f",
    "↓ Improving": "#388e3c",
    "→ Stable":    "#9e9e9e",
}


def _badge(text, color):
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:4px;font-weight:bold;font-size:0.82em">{text}</span>'
    )


def _priority_sorted(df):
    return df.sort_values(
        ["priority_label", "rule_score"],
        key=lambda s: s.map(PRIORITY_ORDER) if s.name == "priority_label" else s,
        ascending=[True, False],
    ).reset_index(drop=True)


def _load(csv_path="scored_output.csv"):
    try:
        df = pd.read_csv(csv_path)
        required = {"vehicle_id", "priority_label", "rule_score", "failure_mode",
                    "recommended_action"}
        missing = required - set(df.columns)
        if missing:
            st.error(f"scored_output.csv is missing columns: {missing}")
            return None
        return df
    except FileNotFoundError:
        return None


def _kpi_strip(df):
    counts = df["priority_label"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 CRITICAL", counts.get("CRITICAL", 0), help="Immediate action required")
    c2.metric("🟠 HIGH",     counts.get("HIGH", 0),     help="Service within 1 week")
    c3.metric("🟡 MEDIUM",   counts.get("MEDIUM", 0),   help="Monitor / schedule")
    c4.metric("🟢 LOW",      counts.get("LOW", 0),      help="Normal operation")


def _alert_banner(df):
    urgent = df[df["priority_label"].isin(["CRITICAL", "HIGH"])]
    if urgent.empty:
        st.success("No trucks require immediate attention.")
        return
    with st.container():
        st.error(f"🚨 **Immediate Attention Required — {len(urgent)} truck(s)**")
        for _, row in urgent.iterrows():
            icon  = PRIORITY_ICON.get(row["priority_label"], "")
            color = PRIORITY_COLOR.get(row["priority_label"], "#757575")
            st.markdown(
                f"&nbsp;&nbsp;{icon} **Truck {row['vehicle_id']}** → "
                + _badge(row["priority_label"], color)
                + f" &nbsp;`{row['failure_mode']}`",
                unsafe_allow_html=True,
            )


def _charts(df):
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    col1, col2 = st.columns(2)

    with col1:
        summary = (
            df["priority_label"]
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
        fig.update_layout(showlegend=False, height=300)
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fm = df["failure_mode"].value_counts().reset_index()
        fm.columns = ["Failure Mode", "Count"]
        fig2 = px.pie(
            fm, names="Failure Mode", values="Count",
            title="Predicted Failure Modes",
            hole=0.4,
        )
        fig2.update_layout(height=300)
        st.plotly_chart(fig2, use_container_width=True)


def _fleet_table(df):
    st.markdown("### All Trucks — Priority DESC · Score DESC")
    sorted_df = _priority_sorted(df)

    # Quick-scan summary table with truck number visible
    summary = sorted_df[["vehicle_id", "rule_score", "priority_label", "failure_mode"]].copy()
    summary.columns = ["Truck", "Score", "Priority", "Failure Mode"]
    summary.insert(0, " ", summary["Priority"].map(PRIORITY_ICON))
    st.dataframe(summary.drop(columns="Priority"), use_container_width=True, hide_index=True)
    st.markdown("---")

    for _, row in sorted_df.iterrows():
        p      = row["priority_label"]
        color  = PRIORITY_COLOR.get(p, "#757575")
        icon   = PRIORITY_ICON.get(p, "")
        score  = row["rule_score"]
        vid    = row["vehicle_id"]
        fm     = row["failure_mode"]
        action = row["recommended_action"]

        # Optional new columns from scoring_engine v2
        # Guard against NaN when loaded from CSV (float NaN has no .split())
        triggered  = str(row.get("triggered_rules", "") or "")
        confidence = str(row.get("confidence", "") or "")
        trend      = str(row.get("score_trend", "→ Stable") or "→ Stable")
        trend_color = TREND_COLOR.get(trend, "#9e9e9e")

        with st.expander(
            f"{icon} **{vid}** — {p} ({score}/100) — {fm}  {trend}",
            expanded=(p == "CRITICAL"),
        ):
            col1, col2 = st.columns([1, 2])

            with col1:
                st.markdown(
                    f"**Priority:** {_badge(p, color)}", unsafe_allow_html=True
                )
                st.markdown(f"**Score:** `{score} / 100`")
                st.markdown(f"**Failure Mode:** `{fm}`")
                if confidence:
                    conf_color = {"HIGH": "#d32f2f", "MEDIUM": "#f57c00", "LOW": "#388e3c"}.get(confidence, "#757575")
                    st.markdown(
                        f"**Confidence:** {_badge(confidence, conf_color)}",
                        unsafe_allow_html=True,
                    )
                if trend:
                    st.markdown(
                        f"**Trend:** <span style='color:{trend_color};font-weight:bold'>{trend}</span>",
                        unsafe_allow_html=True,
                    )

            with col2:
                st.markdown("**Recommended Action:**")
                if p in ("CRITICAL", "HIGH"):
                    st.error(action)
                elif p == "MEDIUM":
                    st.warning(action)
                else:
                    st.info(action)

                if triggered and triggered != "None":
                    st.markdown("**Triggered Rules:**")
                    for rule in triggered.split(", "):
                        st.markdown(f"- {rule.strip()}")


def _truck_detail(df):
    st.markdown("---")
    st.markdown("### Truck Detail View")

    sorted_df = _priority_sorted(df)
    options = sorted_df["vehicle_id"].tolist()
    truck_id = st.selectbox("Select Truck", options)
    truck = sorted_df[sorted_df["vehicle_id"] == truck_id].iloc[0]

    p      = truck["priority_label"]
    color  = PRIORITY_COLOR.get(p, "#757575")
    score  = truck["rule_score"]
    fm     = truck["failure_mode"]
    action = truck["recommended_action"]

    triggered  = str(truck.get("triggered_rules", "") or "")
    confidence = str(truck.get("confidence", "") or "")
    trend      = str(truck.get("score_trend", "→ Stable") or "→ Stable")
    trend_color = TREND_COLOR.get(trend, "#9e9e9e")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score",        f"{score}/100")
    c2.metric("Priority",     p)
    c3.metric("Failure Mode", fm)
    c4.metric("Confidence",   confidence or "—")

    st.markdown(
        f"**Trend:** <span style='color:{trend_color};font-weight:bold;font-size:1.1em'>{trend}</span>",
        unsafe_allow_html=True,
    )

    st.markdown("**Recommended Action:**")
    if p in ("CRITICAL", "HIGH"):
        st.error(action)
    elif p == "MEDIUM":
        st.warning(action)
    else:
        st.info(action)

    if triggered and triggered != "None":
        st.markdown("**Triggered Rules:**")
        for rule in triggered.split(", "):
            st.markdown(f"- {rule.strip()}")

    with st.expander("Raw sensor data"):
        st.write(truck.to_dict())


def display_scored_dashboard(csv_path="scored_output.csv", preloaded_df=None):
    """
    Entry point — call from a Streamlit tab or page.

    Args:
        csv_path:     Fallback path to read scored_output.csv from disk.
        preloaded_df: Pass a DataFrame directly (preferred on Railway —
                      avoids writing to the ephemeral container filesystem).
    """
    st.markdown("## ThrottleGuard Fleet Dashboard")

    # --- Sidebar controls ---
    with st.sidebar:
        st.markdown("### Dashboard Filters")
        priority_filter = st.radio(
            "Priority", ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]
        )
        uploaded = st.file_uploader(
            "Load different scored CSV", type="csv", key="scored_upload"
        )

    # --- Load data — priority: uploaded > preloaded > disk file ---
    if uploaded:
        df = pd.read_csv(uploaded)
    elif preloaded_df is not None:
        df = preloaded_df.copy()
    else:
        df = _load(csv_path)

    if df is None:
        st.info(
            "No scored output found. Click **Load Demo Fleet** in the sidebar, "
            "or upload a scored CSV above."
        )
        return

    # --- Apply filter ---
    if priority_filter != "ALL":
        df_view = df[df["priority_label"] == priority_filter].copy()
    else:
        df_view = df.copy()

    # --- Render ---
    _kpi_strip(df)          # always show full fleet KPIs
    st.markdown("---")
    _alert_banner(df_view)
    st.markdown("---")
    _charts(df_view)
    st.markdown("---")
    _fleet_table(df_view)
    _truck_detail(df_view)


# ── Standalone run ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    display_scored_dashboard()
