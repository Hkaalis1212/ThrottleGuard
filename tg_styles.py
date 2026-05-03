"""
tg_styles.py — ThrottleGuard UI Style System
=============================================
Dark industrial theme. All shared constants, CSS injection,
and styled render helpers live here so app.py stays clean.

Fonts: Barlow / Barlow Condensed (headings), JetBrains Mono (data/code)
"""

import streamlit as st
import pandas as pd

# ── Priority constants ────────────────────────────────────────────────────────

PRIORITY_COLOR = {
    "CRITICAL": "#e53935",
    "HIGH":     "#f57c00",
    "MEDIUM":   "#f9a825",
    "LOW":      "#43a047",
    "ERROR":    "#546e7a",
}

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "ERROR": 4}

_PRIORITY_ICON = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🟢",
    "ERROR":    "⚪",
}


# ── CSS injection ─────────────────────────────────────────────────────────────

def inject_styles() -> None:
    """Inject Google Fonts and global dark-industrial CSS overrides."""
    st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <style>
    /* ── Global typography ── */
    html, body, [class*="css"] {
        font-family: 'Barlow', sans-serif;
    }
    h1, h2, h3 {
        font-family: 'Barlow Condensed', sans-serif !important;
        letter-spacing: 0.04em;
    }
    code, pre, .stCode {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #080a0c;
        border-right: 1px solid #1a2130;
    }
    [data-testid="stSidebar"] * {
        font-family: 'Barlow', sans-serif;
    }

    /* ── Main area ── */
    .main .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    /* ── Streamlit tabs ── */
    [data-testid="stTabs"] button {
        font-family: 'Barlow Condensed', sans-serif !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        font-weight: 600 !important;
    }

    /* ── Buttons ── */
    .stButton > button {
        font-family: 'Barlow Condensed', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        font-size: 0.82rem !important;
    }

    /* ── Expanders ── */
    [data-testid="stExpander"] summary {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.82rem !important;
    }

    /* ── Metric labels ── */
    [data-testid="stMetricLabel"] {
        font-family: 'Barlow Condensed', sans-serif !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Component helpers ─────────────────────────────────────────────────────────

def priority_badge_html(priority: str) -> str:
    """Return an inline HTML priority badge span."""
    color = PRIORITY_COLOR.get(priority, "#546e7a")
    return (
        f'<span style="'
        f'background:{color};color:#fff;'
        f'font-family:\'Barlow Condensed\',sans-serif;'
        f'font-size:0.75rem;font-weight:700;'
        f'letter-spacing:0.1em;text-transform:uppercase;'
        f'padding:2px 8px;border-radius:3px;">'
        f'{priority}</span>'
    )


def render_section_header(title: str, subtitle: str = "", centered: bool = False) -> None:
    """Render a styled section header with optional subtitle."""
    align = "center" if centered else "left"
    st.markdown(
        f'<div style="margin-bottom:0.75rem;text-align:{align};">'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
        f'font-size:1.05rem;font-weight:700;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:#e8edf2;">{title}</div>'
        + (
            f'<div style="font-family:\'Barlow\',sans-serif;'
            f'font-size:0.78rem;color:#4a6070;margin-top:2px;">{subtitle}</div>'
            if subtitle else ""
        )
        + '</div>',
        unsafe_allow_html=True,
    )


def render_app_header(user: dict) -> None:
    """Render the top application header: logo, title, user badge."""
    from tg_logo import render_logo_icon

    col_logo, col_title, col_user = st.columns([0.5, 4, 1.2])
    with col_logo:
        render_logo_icon(48)
    with col_title:
        st.markdown(
            '<div style="padding-top:0.15rem;">'
            '<span style="font-family:\'Barlow Condensed\',sans-serif;'
            'font-size:1.5rem;font-weight:700;letter-spacing:0.06em;color:#e8edf2;">'
            'THROTTLEGUARD</span>'
            '<span style="font-family:\'Barlow Condensed\',sans-serif;'
            'font-size:0.78rem;letter-spacing:0.12em;color:#4a6070;'
            'text-transform:uppercase;margin-left:0.75rem;">'
            'DPF + SCR Expert System v2</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    with col_user:
        role_color = {"Admin": "#f57c00", "Technician": "#42a5f5", "Viewer": "#546e7a"}.get(
            user.get("role", ""), "#546e7a"
        )
        st.markdown(
            f'<div style="text-align:right;padding-top:0.4rem;">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;'
            f'font-size:0.78rem;color:#8fa3b8;">{user["username"]}</span>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;'
            f'font-size:0.7rem;font-weight:700;letter-spacing:0.08em;'
            f'text-transform:uppercase;color:{role_color};'
            f'background:rgba(0,0,0,0.3);padding:1px 6px;border-radius:3px;margin-left:6px;">'
            f'{user["role"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_kpi_row(results: pd.DataFrame) -> None:
    """Render 4 KPI cards: CRITICAL / HIGH / MEDIUM / LOW counts."""
    counts = results["priority"].value_counts()
    total  = len(results)

    kpis = [
        ("CRITICAL", counts.get("CRITICAL", 0), "#e53935", "Immediate action required"),
        ("HIGH",     counts.get("HIGH",     0), "#f57c00", "Service within 7 days"),
        ("MEDIUM",   counts.get("MEDIUM",   0), "#f9a825", "Monitor / schedule"),
        ("LOW",      counts.get("LOW",      0), "#43a047", "Normal operation"),
    ]

    cols = st.columns(4)
    for col, (label, count, color, hint) in zip(cols, kpis):
        pct = f"{count / total * 100:.0f}%" if total else "0%"
        col.markdown(f"""
        <div style="
            background: #0f1217;
            border: 1px solid #1a2130;
            border-top: 3px solid {color};
            border-radius: 6px;
            padding: 1rem 1.25rem;
        ">
            <div style="
                font-family: 'Barlow Condensed', sans-serif;
                font-size: 0.65rem;
                font-weight: 700;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: {color};
                margin-bottom: 0.3rem;
            ">{label}</div>
            <div style="
                font-family: 'JetBrains Mono', monospace;
                font-size: 2rem;
                font-weight: 600;
                color: #e8edf2;
                line-height: 1;
            ">{count}</div>
            <div style="
                font-family: 'Barlow', sans-serif;
                font-size: 0.72rem;
                color: #4a6070;
                margin-top: 0.3rem;
            ">{pct} of fleet · {hint}</div>
        </div>
        """, unsafe_allow_html=True)


def render_vehicle_expander(row: "pd.Series") -> None:
    """Render a styled expander for a single vehicle's assessment result."""
    priority = row["priority"]
    color    = PRIORITY_COLOR.get(priority, "#546e7a")
    icon     = _PRIORITY_ICON.get(priority, "⚪")
    score    = row["risk_score"] if row["risk_score"] is not None else "N/A"
    vid      = row["vehicle_id"]
    fm       = row["failure_mode"]
    reasons  = row.get("reasons", "") or ""
    action   = row.get("action", "") or ""

    with st.expander(
        f"{icon} {vid}  ·  {priority} ({score}/100)  ·  {fm}",
        expanded=(priority == "CRITICAL"),
    ):
        col_left, col_right = st.columns([1, 2])

        with col_left:
            st.markdown(
                f'<table style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
                f'color:#8fa3b8;border-collapse:collapse;">'
                f'<tr><td style="color:#4a6070;padding-right:0.75rem;">Priority</td>'
                f'<td>{priority_badge_html(priority)}</td></tr>'
                f'<tr><td style="color:#4a6070;padding:2px 0.75rem 2px 0;">Score</td>'
                f'<td style="color:#e8edf2;">{score} / 100</td></tr>'
                f'<tr><td style="color:#4a6070;padding:2px 0.75rem 2px 0;">Mode</td>'
                f'<td style="color:{color};">{fm}</td></tr>'
                f'</table>',
                unsafe_allow_html=True,
            )

        with col_right:
            if action:
                st.markdown(
                    f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
                    f'font-size:0.65rem;letter-spacing:0.12em;text-transform:uppercase;'
                    f'color:#4a6070;margin-bottom:0.3rem;">Recommended Action</div>'
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
                    f'color:#e8edf2;background:#0f1217;border:1px solid #1a2130;'
                    f'border-left:3px solid {color};border-radius:4px;'
                    f'padding:0.6rem 0.85rem;line-height:1.5;">{action}</div>',
                    unsafe_allow_html=True,
                )

        if reasons and reasons not in ("No risk factors triggered", "VALIDATION_ERROR"):
            st.markdown(
                '<div style="font-family:\'Barlow Condensed\',sans-serif;'
                'font-size:0.65rem;letter-spacing:0.12em;text-transform:uppercase;'
                'color:#4a6070;margin:0.75rem 0 0.4rem;">Rules Fired</div>',
                unsafe_allow_html=True,
            )
            for reason in reasons.split(";"):
                r = reason.strip()
                if r:
                    st.markdown(
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;'
                        f'color:#8fa3b8;padding:3px 0 3px 0.75rem;'
                        f'border-left:2px solid #1a2130;margin-bottom:3px;">{r}</div>',
                        unsafe_allow_html=True,
                    )


def render_dispatch_blocklist_styled(results: pd.DataFrame) -> None:
    """Render the do-not-dispatch list for CRITICAL and HIGH vehicles."""
    blocked = results[results["priority"].isin(["CRITICAL", "HIGH"])].copy()

    if blocked.empty:
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
        ">✓ No trucks flagged for dispatch restriction today.</div>
        """, unsafe_allow_html=True)
        return

    st.markdown(f"""
    <div style="
        background: rgba(229,57,53,0.06);
        border: 1px solid rgba(229,57,53,0.3);
        border-left: 3px solid #e53935;
        border-radius: 4px;
        padding: 0.75rem 1.25rem;
        margin-bottom: 1rem;
        font-family: 'Barlow Condensed', sans-serif;
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #e53935;
    ">⚠ {len(blocked)} truck{'s' if len(blocked) != 1 else ''} flagged — do not dispatch without inspection</div>
    """, unsafe_allow_html=True)

    blocked_sorted = blocked.sort_values("priority", key=lambda s: s.map(PRIORITY_ORDER))

    for _, row in blocked_sorted.iterrows():
        priority = row["priority"]
        color    = PRIORITY_COLOR.get(priority, "#546e7a")
        score    = row["risk_score"] if row["risk_score"] is not None else "N/A"

        st.markdown(f"""
        <div style="
            background: #0f1217;
            border: 1px solid #1a2130;
            border-left: 3px solid {color};
            border-radius: 4px;
            padding: 0.85rem 1.1rem;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: flex-start;
            gap: 1rem;
        ">
            <div style="min-width:120px;">
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.9rem;
                    font-weight:600;color:#e8edf2;">{row['vehicle_id']}</div>
                <div style="margin-top:4px;">{priority_badge_html(priority)}</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.72rem;
                    color:#4a6070;margin-top:4px;">{score}/100</div>
            </div>
            <div style="flex:1;">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.7rem;
                    letter-spacing:0.1em;text-transform:uppercase;color:{color};
                    margin-bottom:3px;">{row['failure_mode']}</div>
                <div style="font-family:'Barlow',sans-serif;font-size:0.82rem;
                    color:#8fa3b8;line-height:1.5;">{row.get('action','')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
