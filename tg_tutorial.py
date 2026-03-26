"""
tg_tutorial.py
--------------
6-step click-through tutorial for ThrottleGuard.
Uses session state — no extra packages required.

Usage:
    from tg_tutorial import render_tutorial_sidebar, tutorial_callout, is_tutorial_active

    # In sidebar:
    render_tutorial_sidebar()

    # At each section of the dashboard:
    tutorial_callout("kpi")
    tutorial_callout("alert")
    tutorial_callout("detail")
    tutorial_callout("rules")
    tutorial_callout("scores_tab")
"""

import streamlit as st

# ── Step definitions ──────────────────────────────────────────────────────────

STEPS = [
    {
        "id":      "welcome",
        "title":   "Welcome to ThrottleGuard",
        "icon":    "👋",
        "body":    (
            "ThrottleGuard monitors your fleet's DPF health in real time — "
            "so you know which trucks are safe to dispatch **before** they break down on the road.\n\n"
            "This tour takes about 2 minutes. Click **Next** to begin."
        ),
        "tip":     None,
    },
    {
        "id":      "demo",
        "title":   "Load the Demo Fleet",
        "icon":    "🚛",
        "body":    (
            "We've pre-loaded **30 trucks** across Detroit, Volvo/Mack, and Cummins/PACCAR platforms "
            "with a realistic mix of DPF health conditions.\n\n"
            "Click **Load Demo Fleet** in the sidebar if you haven't already."
        ),
        "tip":     "demo",
    },
    {
        "id":      "kpi",
        "title":   "Your Morning Brief",
        "icon":    "📊",
        "body":    (
            "These four tiles are the first thing your dispatcher sees every morning.\n\n"
            "**CRITICAL** = do not put this truck on the load board today.\n"
            "**HIGH** = schedule service this week.\n"
            "**MEDIUM** = watch it, plan ahead.\n"
            "**LOW** = healthy, dispatch normally."
        ),
        "tip":     "kpi",
    },
    {
        "id":      "alert",
        "title":   "Immediate Attention Required",
        "icon":    "🚨",
        "body":    (
            "Every CRITICAL and HIGH truck is listed here with a plain-English reason — "
            "not a fault code, not a raw sensor number.\n\n"
            "Your dispatcher can read this without any training.\n\n"
            "No more calling a tech to decode an error code at 5 AM."
        ),
        "tip":     "alert",
    },
    {
        "id":      "detail",
        "title":   "Truck Detail — Why This Score?",
        "icon":    "🔍",
        "body":    (
            "Expand any truck to see:\n\n"
            "- **Exact rules that fired** — e.g. 'Low regen temp (<940°F)'\n"
            "- **Confidence** — how many rules agreed (HIGH = 3+ rules, MEDIUM = 2, LOW = 1)\n"
            "- **Trend** — is this truck getting worse, improving, or stable?\n"
            "- **Recommended action** — specific next step for your tech\n\n"
            "Try expanding **TRK-001** — it has 3 rules fired."
        ),
        "tip":     "detail",
    },
    {
        "id":      "scores_tab",
        "title":   "Fleet Scores — Full Picture",
        "icon":    "📋",
        "body":    (
            "Switch to the **Fleet Scores** tab in the navigation above.\n\n"
            "Every truck in the fleet, sorted Priority → Score. "
            "Filter by priority, upload a scored CSV, or use the pre-loaded demo.\n\n"
            "This is what you send to your shop foreman each morning."
        ),
        "tip":     "scores_tab",
    },
]

TOTAL_STEPS = len(STEPS)


# ── Session state helpers ─────────────────────────────────────────────────────

def _init():
    if "tg_tour_active" not in st.session_state:
        st.session_state.tg_tour_active = False
    if "tg_tour_step" not in st.session_state:
        st.session_state.tg_tour_step = 0


def is_tutorial_active() -> bool:
    _init()
    return st.session_state.tg_tour_active


def current_step_id() -> str:
    _init()
    idx = st.session_state.tg_tour_step
    return STEPS[idx]["id"] if idx < TOTAL_STEPS else ""


# ── Sidebar panel ─────────────────────────────────────────────────────────────

def render_tutorial_sidebar():
    """Call this inside a `with st.sidebar:` block."""
    _init()

    st.markdown("---")

    if not st.session_state.tg_tour_active:
        if st.button("▶ Start Tour", use_container_width=True, type="primary"):
            st.session_state.tg_tour_active = True
            st.session_state.tg_tour_step = 0
            st.rerun()
        return

    # ── Tour is active ──
    step = STEPS[st.session_state.tg_tour_step]
    step_num = st.session_state.tg_tour_step + 1

    # Progress bar
    st.markdown(
        f"<div style='font-size:0.75rem;color:#9ca3af;margin-bottom:4px'>"
        f"Step {step_num} of {TOTAL_STEPS}</div>",
        unsafe_allow_html=True,
    )
    st.progress(step_num / TOTAL_STEPS)

    # Step card
    st.markdown(
        f"""
        <div style="background:#1a1f2e;border:1px solid #2d3748;border-left:3px solid #f59e0b;
                    border-radius:8px;padding:1rem;margin:0.5rem 0">
            <div style="font-size:1.4rem">{step['icon']}</div>
            <div style="font-weight:700;color:#ffffff;margin:0.3rem 0;font-size:0.95rem">
                {step['title']}
            </div>
            <div style="font-size:0.82rem;color:#9ca3af;line-height:1.5">
                {step['body'].replace(chr(10), '<br>')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.tg_tour_step > 0:
            if st.button("← Back", use_container_width=True):
                st.session_state.tg_tour_step -= 1
                st.rerun()
    with col2:
        if st.session_state.tg_tour_step < TOTAL_STEPS - 1:
            if st.button("Next →", use_container_width=True, type="primary"):
                st.session_state.tg_tour_step += 1
                st.rerun()
        else:
            if st.button("Finish ✓", use_container_width=True, type="primary"):
                st.session_state.tg_tour_active = False
                st.session_state.tg_tour_step = 0
                st.rerun()

    if st.button("✕ Skip Tour", use_container_width=True):
        st.session_state.tg_tour_active = False
        st.session_state.tg_tour_step = 0
        st.rerun()


# ── Inline callouts — injected at each dashboard section ─────────────────────

def tutorial_callout(section: str):
    """
    Call at the top of each dashboard section.
    Only renders when the tour is active AND the current step matches this section.

    Sections:  "demo" | "kpi" | "alert" | "detail" | "scores_tab"
    """
    _init()
    if not st.session_state.tg_tour_active:
        return

    step = STEPS[st.session_state.tg_tour_step]
    if step.get("tip") != section:
        return

    icons = {
        "demo":       "🚛",
        "kpi":        "📊",
        "alert":      "🚨",
        "detail":     "🔍",
        "scores_tab": "📋",
    }

    labels = {
        "demo":       "Load demo data first — click the button in the sidebar.",
        "kpi":        "👆 These four tiles are your morning brief.",
        "alert":      "👆 Every flagged truck is listed here with a plain-English reason.",
        "detail":     "👆 Expand any truck to see which rules fired and why.",
        "scores_tab": "👆 Click Fleet Scores in the navigation to see the full fleet table.",
    }

    icon  = icons.get(section, "ℹ️")
    label = labels.get(section, "")

    st.markdown(
        f"""
        <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.4);
                    border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem;
                    display:flex;align-items:flex-start;gap:0.75rem">
            <span style="font-size:1.3rem">{icon}</span>
            <div>
                <span style="font-weight:700;color:#f59e0b;font-size:0.85rem">
                    TOUR — Step {st.session_state.tg_tour_step + 1} of {TOTAL_STEPS}:
                    {step['title']}
                </span><br>
                <span style="color:#d1d5db;font-size:0.85rem">{label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
