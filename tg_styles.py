"""
tg_styles.py — ThrottleGuard UI Style System
=============================================
Warm, customer-facing light theme. All shared constants, CSS injection,
and styled render helpers live here so app.py stays clean.

Fonts: Barlow / Barlow Condensed throughout — no monospace in the UI,
keeps the product feeling like a tool a fleet owner trusts, not a
developer dashboard.
"""

import streamlit as st
import pandas as pd

# ── Design tokens ──────────────────────────────────────────────────────────────
# Mirrors .streamlit/config.toml's [theme] block. Native Streamlit widgets pick
# up config.toml automatically; everything custom (cards, badges, charts) reads
# these constants so the two never drift apart.

BG            = "#FAF8F5"   # page background — warm off-white, not stark white
BG_CARD       = "#FFFFFF"   # card/surface background
BG_SOFT       = "#F2EEE7"   # subtle inset panels (code-ish blocks, sidebar)
BORDER        = "#E8E1D4"   # warm neutral border
TEXT_PRIMARY  = "#1A2B42"   # deep navy — body text, headings
TEXT_MUTED    = "#6B7A8D"   # secondary text, captions, labels
TEXT_FAINT    = "#9AA7B5"   # tertiary text, placeholders
NAVY          = "#1D3557"   # brand navy — headers, nav, primary emphasis
ORANGE        = "#E8732A"   # brand accent — CTAs, highlights
SHADOW        = "0 1px 2px rgba(26,43,66,0.06), 0 1px 3px rgba(26,43,66,0.08)"


# ── Priority constants ────────────────────────────────────────────────────────

PRIORITY_COLOR = {
    "CRITICAL": "#DC2626",
    "HIGH":     "#EA580C",
    "MEDIUM":   "#D97706",
    "LOW":      "#16A34A",
    "ERROR":    "#6B7A8D",
}

# Soft tint backgrounds for pill badges — same hue family as PRIORITY_COLOR,
# low-saturation so text stays the readable part, not the fill.
PRIORITY_TINT = {
    "CRITICAL": "#FDE8E8",
    "HIGH":     "#FDEBDD",
    "MEDIUM":   "#FBEFD9",
    "LOW":      "#E3F5E9",
    "ERROR":    "#EEF1F4",
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
    """Inject Google Fonts and global warm/light CSS overrides."""
    st.markdown(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">

    <style>
    /* ── Global typography ──
       Scoped to text-bearing elements, not a blanket html/body/[class*="css"]
       rule — that cascade used to override Streamlit's own icon font
       (Material Symbols ligatures like "keyboard_double_arrow_left" would
       render as literal text instead of the arrow glyph). */
    body, p, span, div, label, li, td, th, input, textarea, button {{
        font-family: 'Barlow', sans-serif;
    }}
    h1, h2, h3 {{
        font-family: 'Barlow Condensed', sans-serif !important;
        letter-spacing: 0.01em;
        color: {NAVY};
    }}
    [data-testid="stIconMaterial"] {{
        font-family: 'Material Symbols Rounded' !important;
    }}

    /* ── App background ── */
    [data-testid="stAppViewContainer"], .stApp {{
        background: {BG};
    }}
    .main .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {{
        background: {BG_SOFT};
        border-right: 1px solid {BORDER};
    }}

    /* ── Streamlit tabs ── */
    [data-testid="stTabs"] button {{
        font-family: 'Barlow Condensed', sans-serif !important;
        font-size: 0.92rem !important;
        font-weight: 600 !important;
        color: {TEXT_MUTED};
    }}
    [data-testid="stTabs"] button[aria-selected="true"] {{
        color: {ORANGE} !important;
    }}

    /* ── Buttons ── */
    .stButton > button {{
        font-family: 'Barlow Condensed', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        border-radius: 8px !important;
    }}
    .stButton > button[kind="primary"] {{
        background: {ORANGE} !important;
        border-color: {ORANGE} !important;
    }}

    /* ── Expanders ── */
    [data-testid="stExpander"] {{
        border: 1px solid {BORDER} !important;
        border-radius: 12px !important;
        box-shadow: {SHADOW};
        background: {BG_CARD};
    }}
    [data-testid="stExpander"] summary {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.92rem !important;
        font-weight: 500 !important;
    }}

    /* ── Metric labels ── */
    [data-testid="stMetricLabel"] {{
        font-family: 'Barlow Condensed', sans-serif !important;
        letter-spacing: 0.04em !important;
        color: {TEXT_MUTED} !important;
    }}
    [data-testid="stMetricValue"] {{
        color: {NAVY} !important;
    }}
    </style>
    """, unsafe_allow_html=True)


# ── Component helpers ─────────────────────────────────────────────────────────

def priority_badge_html(priority: str) -> str:
    """Return an inline HTML priority badge — a soft-tint rounded pill."""
    color = PRIORITY_COLOR.get(priority, TEXT_MUTED)
    tint  = PRIORITY_TINT.get(priority, BG_SOFT)
    return (
        f'<span style="'
        f'background:{tint};color:{color};'
        f'font-family:\'Barlow Condensed\',sans-serif;'
        f'font-size:0.75rem;font-weight:700;'
        f'letter-spacing:0.04em;'
        f'padding:3px 10px;border-radius:999px;">'
        f'{priority}</span>'
    )


def render_section_header(title: str, subtitle: str = "", centered: bool = False) -> None:
    """Render a styled section header with optional subtitle."""
    align = "center" if centered else "left"
    st.markdown(
        f'<div style="margin-bottom:0.75rem;text-align:{align};">'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
        f'font-size:1.2rem;font-weight:700;color:{NAVY};">{title}</div>'
        + (
            f'<div style="font-family:\'Barlow\',sans-serif;'
            f'font-size:0.85rem;color:{TEXT_MUTED};margin-top:2px;">{subtitle}</div>'
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
            f'<div style="padding-top:0.15rem;">'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;'
            f'font-size:1.5rem;font-weight:700;color:{NAVY};">'
            f'ThrottleGuard</span>'
            f'<span style="font-family:\'Barlow\',sans-serif;'
            f'font-size:0.82rem;color:{TEXT_MUTED};'
            f'margin-left:0.75rem;">'
            f'DPF + SCR Health Monitor</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_user:
        role_color = {"Admin": ORANGE, "Technician": "#2563EB", "Viewer": TEXT_MUTED}.get(
            user.get("role", ""), TEXT_MUTED
        )
        st.markdown(
            f'<div style="text-align:right;padding-top:0.4rem;">'
            f'<span style="font-family:\'Barlow\',sans-serif;'
            f'font-size:0.85rem;color:{TEXT_PRIMARY};">{user["username"]}</span>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;'
            f'font-size:0.72rem;font-weight:700;'
            f'color:{role_color};'
            f'background:{BG_SOFT};padding:2px 8px;border-radius:999px;margin-left:6px;">'
            f'{user["role"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_kpi_row(results: pd.DataFrame) -> None:
    """Render 4 KPI cards: CRITICAL / HIGH / MEDIUM / LOW counts."""
    counts = results["priority"].value_counts()
    total  = len(results)

    kpis = [
        ("CRITICAL", counts.get("CRITICAL", 0), "Immediate action required"),
        ("HIGH",     counts.get("HIGH",     0), "Service within 7 days"),
        ("MEDIUM",   counts.get("MEDIUM",   0), "Monitor / schedule"),
        ("LOW",      counts.get("LOW",      0), "Normal operation"),
    ]

    cols = st.columns(4)
    for col, (label, count, hint) in zip(cols, kpis):
        color = PRIORITY_COLOR[label]
        pct = f"{count / total * 100:.0f}%" if total else "0%"
        col.markdown(f"""
        <div style="
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 14px;
            box-shadow: {SHADOW};
            padding: 1.1rem 1.25rem;
        ">
            <div style="
                font-family: 'Barlow Condensed', sans-serif;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.06em;
                color: {color};
                margin-bottom: 0.4rem;
            ">{label}</div>
            <div style="
                font-family: 'Barlow Condensed', sans-serif;
                font-size: 2.1rem;
                font-weight: 700;
                color: {NAVY};
                line-height: 1;
            ">{count}</div>
            <div style="
                font-family: 'Barlow', sans-serif;
                font-size: 0.78rem;
                color: {TEXT_MUTED};
                margin-top: 0.35rem;
            ">{pct} of fleet · {hint}</div>
        </div>
        """, unsafe_allow_html=True)


def render_vehicle_expander(row: "pd.Series") -> None:
    """Render a styled expander for a single vehicle's assessment result."""
    priority = row["priority"]
    color    = PRIORITY_COLOR.get(priority, TEXT_MUTED)
    icon     = _PRIORITY_ICON.get(priority, "⚪")
    score    = row["risk_score"] if row["risk_score"] is not None else "N/A"
    vid      = row["vehicle_id"]
    fm       = row["failure_mode"]
    reasons  = row.get("reasons", "") or ""
    action   = row.get("action", "") or ""

    # Passive regen is an advisory signal that can move MEDIUM/LOW trucks —
    # row["priority"] is already the adjusted value (see app.py's
    # run_expert_system); priority_raw is only present when it differed.
    priority_raw   = row.get("priority_raw")
    passive_score  = row.get("passive_regen_score")
    passive_rec    = row.get("passive_recommendation")

    with st.expander(
        f"{icon} {vid}  ·  {priority} ({score}/100)  ·  {fm}",
        expanded=(priority == "CRITICAL"),
    ):
        col_left, col_right = st.columns([1, 2])

        with col_left:
            st.markdown(
                f'<table style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
                f'color:{TEXT_MUTED};border-collapse:collapse;">'
                f'<tr><td style="padding-right:0.75rem;padding-bottom:4px;">Priority</td>'
                f'<td style="padding-bottom:4px;">{priority_badge_html(priority)}</td></tr>'
                f'<tr><td style="padding:4px 0.75rem 4px 0;">Score</td>'
                f'<td style="color:{TEXT_PRIMARY};font-weight:600;padding:4px 0;">{score} / 100</td></tr>'
                f'<tr><td style="padding:4px 0.75rem 4px 0;">Mode</td>'
                f'<td style="color:{color};font-weight:600;padding:4px 0;">{fm}</td></tr>'
                f'</table>',
                unsafe_allow_html=True,
            )

        with col_right:
            if action:
                st.markdown(
                    f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
                    f'font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
                    f'color:{TEXT_MUTED};margin-bottom:0.3rem;">Recommended Action</div>'
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.9rem;'
                    f'color:{TEXT_PRIMARY};background:{BG_SOFT};'
                    f'border-left:3px solid {color};border-radius:8px;'
                    f'padding:0.65rem 0.9rem;line-height:1.5;">{action}</div>',
                    unsafe_allow_html=True,
                )

        if reasons and reasons not in ("No risk factors triggered", "VALIDATION_ERROR"):
            st.markdown(
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
                f'font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
                f'color:{TEXT_MUTED};margin:0.9rem 0 0.4rem;">Rules Fired</div>',
                unsafe_allow_html=True,
            )
            for reason in reasons.split(";"):
                r = reason.strip()
                if r:
                    st.markdown(
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.86rem;'
                        f'color:{TEXT_PRIMARY};padding:4px 0 4px 0.75rem;'
                        f'border-left:2px solid {BORDER};margin-bottom:3px;">{r}</div>',
                        unsafe_allow_html=True,
                    )

        if passive_score is not None and pd.notna(passive_score):
            st.markdown(
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
                f'font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
                f'color:{TEXT_MUTED};margin:0.9rem 0 0.4rem;">Passive Regen Health</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.86rem;'
                f'color:{TEXT_PRIMARY};padding:4px 0 4px 0.75rem;'
                f'border-left:2px solid {BORDER};margin-bottom:3px;">'
                f'Score: {float(passive_score):.2f} / 1.00 '
                f'(0 = silently failing · 1 = healthy highway cruise)</div>',
                unsafe_allow_html=True,
            )
            if priority_raw is not None and priority_raw != priority:
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.86rem;'
                    f'color:{TEXT_PRIMARY};padding:4px 0 4px 0.75rem;'
                    f'border-left:2px solid {BORDER};margin-bottom:3px;">'
                    f'Adjusted from <b>{priority_raw}</b> based on passive regen health</div>',
                    unsafe_allow_html=True,
                )
            if passive_rec:
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.86rem;'
                    f'color:{TEXT_PRIMARY};padding:4px 0 4px 0.75rem;'
                    f'border-left:2px solid {BORDER};margin-bottom:3px;">{passive_rec}</div>',
                    unsafe_allow_html=True,
                )


def render_dispatch_blocklist_styled(results: pd.DataFrame) -> None:
    """Render the do-not-dispatch list for CRITICAL and HIGH vehicles."""
    blocked = results[results["priority"].isin(["CRITICAL", "HIGH"])].copy()

    if blocked.empty:
        st.markdown(f"""
        <div style="
            background: {PRIORITY_TINT['LOW']};
            border-radius: 10px;
            padding: 0.9rem 1.25rem;
            font-family: 'Barlow', sans-serif;
            font-size: 0.92rem;
            color: {PRIORITY_COLOR['LOW']};
        ">✓ No trucks flagged for dispatch restriction today.</div>
        """, unsafe_allow_html=True)
        return

    st.markdown(f"""
    <div style="
        background: {PRIORITY_TINT['CRITICAL']};
        border-radius: 10px;
        padding: 0.8rem 1.25rem;
        margin-bottom: 1rem;
        font-family: 'Barlow Condensed', sans-serif;
        font-size: 0.92rem;
        font-weight: 700;
        color: {PRIORITY_COLOR['CRITICAL']};
    ">⚠ {len(blocked)} truck{'s' if len(blocked) != 1 else ''} flagged — do not dispatch without inspection</div>
    """, unsafe_allow_html=True)

    blocked_sorted = blocked.sort_values("priority", key=lambda s: s.map(PRIORITY_ORDER))

    for _, row in blocked_sorted.iterrows():
        priority = row["priority"]
        color    = PRIORITY_COLOR.get(priority, TEXT_MUTED)
        score    = row["risk_score"] if row["risk_score"] is not None else "N/A"

        st.markdown(f"""
        <div style="
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-left: 3px solid {color};
            border-radius: 12px;
            box-shadow: {SHADOW};
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.6rem;
            display: flex;
            align-items: flex-start;
            gap: 1rem;
        ">
            <div style="min-width:120px;">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:1rem;
                    font-weight:700;color:{NAVY};">{row['vehicle_id']}</div>
                <div style="margin-top:4px;">{priority_badge_html(priority)}</div>
                <div style="font-family:'Barlow',sans-serif;font-size:0.76rem;
                    color:{TEXT_MUTED};margin-top:4px;">{score}/100</div>
            </div>
            <div style="flex:1;">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.76rem;
                    font-weight:600;color:{color};
                    margin-bottom:3px;">{row['failure_mode']}</div>
                <div style="font-family:'Barlow',sans-serif;font-size:0.86rem;
                    color:{TEXT_PRIMARY};line-height:1.5;">{row.get('action','')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
