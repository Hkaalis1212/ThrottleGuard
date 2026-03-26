"""
tg_logo.py
----------
ThrottleGuard SVG logo — shield + engine silhouette with 4-color risk band.
No external dependencies. Returns raw SVG string or renders in Streamlit.

Usage:
    from tg_logo import render_logo, get_logo_svg

    render_logo(size="large")   # in Streamlit
    svg = get_logo_svg()        # raw SVG string for embedding
"""

import base64
import streamlit as st


def _svg_to_img_tag(svg: str, width: int) -> str:
    """Convert SVG string to a base64 <img> tag Streamlit can render."""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f'<img src="data:image/svg+xml;base64,{b64}" width="{width}" style="display:block">'

# ── Risk colors — match dashboard exactly ────────────────────────────────────
CRITICAL = "#d32f2f"
HIGH     = "#f57c00"
MEDIUM   = "#fbc02d"
LOW      = "#388e3c"


def get_logo_svg(width=220, show_tagline=True) -> str:
    """
    Returns the ThrottleGuard SVG as a string.

    Layout:
      - Shield outline (charcoal, thick stroke)
      - Engine block silhouette inside the shield (simplified)
      - 4-segment risk band across the shield base (LOW→MEDIUM→HIGH→CRITICAL)
      - THROTTLEGUARD wordmark
      - Optional tagline
    """

    tagline_block = ""
    if show_tagline:
        tagline_block = """
        <text x="50%" y="132" text-anchor="middle"
              font-family="'Barlow Condensed', 'Arial Narrow', Arial, sans-serif"
              font-size="9" font-weight="400" letter-spacing="2"
              fill="#6b7280" text-decoration="none">
            DPF PREDICTIVE MAINTENANCE
        </text>"""

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 145"
     width="{width}" role="img" aria-label="ThrottleGuard logo">

  <!-- ── Shield ── -->
  <!-- Outer shield drop-shadow -->
  <path d="M110 12 L174 34 L174 82 Q174 116 110 134 Q46 116 46 82 L46 34 Z"
        fill="#1a1a2e" opacity="0.25" transform="translate(2,3)"/>

  <!-- Shield fill -->
  <path d="M110 12 L174 34 L174 82 Q174 116 110 134 Q46 116 46 82 L46 34 Z"
        fill="#1c1f2e"/>

  <!-- Shield border -->
  <path d="M110 12 L174 34 L174 82 Q174 116 110 134 Q46 116 46 82 L46 34 Z"
        fill="none" stroke="#374151" stroke-width="2.5"/>

  <!-- ── Risk band — 4 segments across shield base ── -->
  <!-- Clipping mask so band follows shield curve -->
  <defs>
    <clipPath id="shield-clip">
      <path d="M110 12 L174 34 L174 82 Q174 116 110 134 Q46 116 46 82 L46 34 Z"/>
    </clipPath>
  </defs>

  <g clip-path="url(#shield-clip)">
    <!-- LOW (green) — leftmost -->
    <rect x="46"  y="108" width="16" height="30" fill="{LOW}"      opacity="0.90"/>
    <!-- MEDIUM (yellow) -->
    <rect x="62"  y="108" width="16" height="30" fill="{MEDIUM}"   opacity="0.90"/>
    <!-- HIGH (orange) -->
    <rect x="110" y="108" width="16" height="30" fill="{HIGH}"     opacity="0.90"/>
    <!-- CRITICAL (red) — rightmost -->
    <rect x="142" y="108" width="32" height="30" fill="{CRITICAL}" opacity="0.90"/>

    <!-- Band top edge line -->
    <line x1="46" y1="108" x2="174" y2="108" stroke="#0d0f1a" stroke-width="1.5"/>
  </g>

  <!-- ── Engine block silhouette (simplified overhead view) ── -->
  <!-- Main block -->
  <rect x="82" y="38" width="56" height="46" rx="4"
        fill="none" stroke="#e5e7eb" stroke-width="2"/>

  <!-- Cylinder heads — top row -->
  <rect x="88" y="32" width="8"  height="10" rx="2" fill="#9ca3af"/>
  <rect x="100" y="32" width="8" height="10" rx="2" fill="#9ca3af"/>
  <rect x="112" y="32" width="8" height="10" rx="2" fill="#9ca3af"/>
  <rect x="124" y="32" width="8" height="10" rx="2" fill="#9ca3af"/>

  <!-- Exhaust manifold line -->
  <line x1="86" y1="34" x2="134" y2="34" stroke="#6b7280" stroke-width="1.5"
        stroke-dasharray="2,2"/>

  <!-- Internal block detail lines -->
  <line x1="96"  y1="38" x2="96"  y2="84" stroke="#374151" stroke-width="1"/>
  <line x1="110" y1="38" x2="110" y2="84" stroke="#374151" stroke-width="1"/>
  <line x1="124" y1="38" x2="124" y2="84" stroke="#374151" stroke-width="1"/>

  <!-- DPF filter symbol — small canister on right side -->
  <rect x="142" y="52" width="14" height="22" rx="3"
        fill="none" stroke="#f59e0b" stroke-width="1.8"/>
  <line x1="144" y1="57" x2="154" y2="57" stroke="#f59e0b" stroke-width="1"/>
  <line x1="144" y1="61" x2="154" y2="61" stroke="#f59e0b" stroke-width="1"/>
  <line x1="144" y1="65" x2="154" y2="65" stroke="#f59e0b" stroke-width="1"/>
  <line x1="144" y1="69" x2="154" y2="69" stroke="#f59e0b" stroke-width="1"/>
  <!-- Pipe connecting block to DPF -->
  <line x1="138" y1="63" x2="142" y2="63" stroke="#f59e0b" stroke-width="1.8"/>

  <!-- Shield inner highlight edge -->
  <path d="M110 16 L170 36 L170 82 Q170 113 110 130"
        fill="none" stroke="#ffffff" stroke-width="0.8" opacity="0.08"/>

  <!-- ── Wordmark ── -->
  <text x="50%" y="120" text-anchor="middle"
        font-family="'Barlow Condensed', 'Arial Narrow', Arial, sans-serif"
        font-size="15" font-weight="800" letter-spacing="3"
        fill="#ffffff">
    THROTTLEGUARD
  </text>

  {tagline_block}

</svg>
"""
    return svg


def get_logo_icon_svg(size=48) -> str:
    """
    Compact shield-only icon — for favicons, small headers, tab icons.
    No wordmark, just the shield + risk band.
    """
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 72" width="{size}">
  <path d="M32 4 L58 14 L58 40 Q58 60 32 68 Q6 60 6 40 L6 14 Z"
        fill="#1c1f2e" stroke="#374151" stroke-width="2"/>
  <defs>
    <clipPath id="ic">
      <path d="M32 4 L58 14 L58 40 Q58 60 32 68 Q6 60 6 40 L6 14 Z"/>
    </clipPath>
  </defs>
  <g clip-path="url(#ic)">
    <rect x="6"  y="52" width="13" height="20" fill="{LOW}"      opacity="0.9"/>
    <rect x="19" y="52" width="13" height="20" fill="{MEDIUM}"   opacity="0.9"/>
    <rect x="32" y="52" width="13" height="20" fill="{HIGH}"     opacity="0.9"/>
    <rect x="45" y="52" width="13" height="20" fill="{CRITICAL}" opacity="0.9"/>
    <line x1="6" y1="52" x2="58" y2="52" stroke="#0d0f1a" stroke-width="1.5"/>
  </g>
  <!-- engine block -->
  <rect x="20" y="18" width="24" height="22" rx="2"
        fill="none" stroke="#e5e7eb" stroke-width="1.8"/>
  <rect x="22" y="13" width="5" height="7" rx="1" fill="#9ca3af"/>
  <rect x="29" y="13" width="5" height="7" rx="1" fill="#9ca3af"/>
  <rect x="36" y="13" width="5" height="7" rx="1" fill="#9ca3af"/>
  <line x1="27" y1="18" x2="27" y2="40" stroke="#374151" stroke-width="0.8"/>
  <line x1="34" y1="18" x2="34" y2="40" stroke="#374151" stroke-width="0.8"/>
  <!-- DPF canister -->
  <rect x="46" y="23" width="7" height="12" rx="2"
        fill="none" stroke="#f59e0b" stroke-width="1.5"/>
  <line x1="44" y1="29" x2="46" y2="29" stroke="#f59e0b" stroke-width="1.5"/>
</svg>
"""


def render_logo(size="medium", show_tagline=True):
    """
    Render the logo in Streamlit.
    size: "small" | "medium" | "large"
    """
    widths = {"small": 140, "medium": 220, "large": 320}
    w = widths.get(size, 220)
    svg = get_logo_svg(width=w, show_tagline=show_tagline)
    st.markdown(_svg_to_img_tag(svg, w), unsafe_allow_html=True)


def render_logo_icon(size=48):
    """Render the compact icon only (no wordmark)."""
    svg = get_logo_icon_svg(size=size)
    st.markdown(_svg_to_img_tag(svg, size), unsafe_allow_html=True)


if __name__ == "__main__":
    # Quick preview — run: streamlit run tg_logo.py
    st.set_page_config(page_title="ThrottleGuard Logo Preview", layout="centered")
    st.markdown("## Logo Preview")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("Small")
        render_logo("small")
    with col2:
        st.caption("Medium")
        render_logo("medium")
    with col3:
        st.caption("Large")
        render_logo("large")

    st.markdown("---")
    st.markdown("## Icon only")
    cols = st.columns(4)
    for col, sz in zip(cols, [24, 32, 48, 64]):
        with col:
            st.caption(f"{sz}px")
            render_logo_icon(sz)
