"""Visual identity: Equinor-derived palette, IBM Plex Sans, dark well-viewer
canvas as the single bold element; everything else quiet."""
from __future__ import annotations

import html

NAVY = "#00243D"
NAVY_2 = "#0B3350"
MOSS = "#007079"
MOSS_LIGHT = "#73B1B5"
RED = "#EB0037"
PISTACHIO = "#9DBA00"
KARRY = "#FFE7D6"
AMBER = "#FF9200"
INK = "#1B2A36"
MUTED = "#5B6B78"
LINE = "#DCE3E8"
PAPER = "#F4F6F8"
TRAJ = "#9CC3E6"

STATUS = {"pass": (PISTACHIO, "#F3F8E0", "Pass"), "warn": (AMBER, "#FFF4E5", "Check"),
          "fail": (RED, "#FDE7EC", "Fail")}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stTextInput, .stNumberInput, button, input, select, textarea {{
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
}}
.stApp {{ background: {PAPER}; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1500px; }}
h1, h2, h3 {{ color: {NAVY}; font-weight: 600; letter-spacing: -0.01em; }}
h1 {{ font-size: 1.55rem; }} h2 {{ font-size: 1.25rem; }} h3 {{ font-size: 1.05rem; }}

[data-testid="stSidebar"] {{ background: {NAVY}; }}
[data-testid="stSidebar"] * {{ color: #E6EEF3; }}
[data-testid="stSidebar"] .ks-group {{ color: #8FA6B6; font-size: .72rem; margin: 1.1rem 0 .3rem .2rem;
  letter-spacing: .04em; }}
[data-testid="stSidebar"] button {{ background: transparent; border: 0; justify-content: flex-start;
  text-align: left; padding: .35rem .6rem; border-radius: 6px; width: 100%; }}
[data-testid="stSidebar"] button:hover {{ background: {NAVY_2}; }}
[data-testid="stSidebar"] button[kind="primary"] {{ background: {NAVY_2}; box-shadow: inset 3px 0 0 {MOSS_LIGHT}; }}
[data-testid="stSidebar"] button p {{ font-size: .9rem; }}
.ks-brand {{ display:flex; gap:.6rem; align-items:center; margin:.2rem 0 .8rem .2rem; }}
.ks-brand svg {{ flex: none; }}
.ks-brand b {{ font-size:1.05rem; color:#fff; font-weight:600; }}
.ks-brand span {{ display:block; font-size:.72rem; color:#8FA6B6; }}

.ks-metrics {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); background:#fff;
  border:1px solid {LINE}; border-radius:10px; margin-bottom:1rem; }}
.ks-metric {{ padding:.75rem 1.1rem; border-left:1px solid {LINE}; }}
.ks-metric:first-child {{ border-left:0; }}
.ks-metric .l {{ color:{MUTED}; font-size:.8rem; }}
.ks-metric .v {{ color:{NAVY}; font-size:1.55rem; font-weight:600; font-variant-numeric: tabular-nums; line-height:1.2; }}
.ks-metric .u {{ color:{MUTED}; font-size:.8rem; font-weight:500; }}
@media (max-width: 800px) {{ .ks-metrics {{ grid-template-columns: repeat(2, 1fr); }}
  .ks-metric:nth-child(3) {{ border-left:0; }} }}

.ks-check {{ border-left:4px solid; border-radius:4px; padding:.5rem .75rem; margin:.35rem 0; font-size:.86rem; }}
.ks-check .t {{ display:flex; justify-content:space-between; gap:.5rem; font-weight:500; color:{INK}; }}
.ks-check .n {{ color:{MUTED}; font-size:.78rem; margin-top:.15rem; }}
.ks-check .s {{ font-size:.72rem; font-weight:600; }}
.ks-note {{ background:#EAF4F8; border-left:4px solid {MOSS_LIGHT}; padding:.55rem .8rem; border-radius:4px;
  color:{INK}; font-size:.85rem; margin:.4rem 0 .8rem 0; }}
.ks-head {{ display:flex; align-items:baseline; justify-content:space-between; gap:1rem; margin-bottom:.4rem; }}
.ks-head p {{ color:{MUTED}; margin:0; font-size:.9rem; }}
.ks-foot {{ color:{MUTED}; font-size:.75rem; margin-top:2rem; border-top:1px solid {LINE}; padding-top:.6rem; }}
div[data-testid="stForm"] {{ background:#fff; border:1px solid {LINE}; border-radius:10px; }}
[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
.ks-status {{ display:flex; flex-wrap:wrap; align-items:center; gap:.5rem; margin:-.2rem 0 .6rem 0; font-size:.8rem; color:{MUTED}; }}
.ks-tag {{ display:inline-flex; align-items:center; gap:.35rem; padding:.18rem .6rem; border-radius:999px; font-weight:600; font-size:.75rem; }}
.ks-tag::before {{ content:""; width:.5rem; height:.5rem; border-radius:50%; background:currentColor; }}
.ks-tag.mod {{ background:#FFF4E5; color:#B35F00; border:1px solid #FFD199; }}
.ks-tag.clean {{ background:#EAF4F8; color:{MOSS}; border:1px solid #BFDDE2; }}
.ks-tag.saved {{ background:#F3F8E0; color:#5E7000; border:1px solid #D6E6A3; }}
[data-testid="stSidebar"] .ks-tag.mod {{ background:#3A2A12; color:#FFC266; border-color:#6B4A18; }}
[data-testid="stSidebar"] .ks-tag.clean, [data-testid="stSidebar"] .ks-tag.saved {{ background:{NAVY_2}; color:{MOSS_LIGHT}; border-color:#1E4461; }}
button:focus-visible {{ outline: 2px solid {MOSS_LIGHT} !important; outline-offset: 2px; }}
</style>
"""

BRAND = f"""
<div class="ks-brand">
  <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
    <rect x="1" y="1" width="32" height="32" rx="7" fill="none" stroke="{MOSS_LIGHT}" stroke-width="1.5"/>
    <path d="M11 6 V16 Q11 26 23 28" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
    <circle cx="23" cy="28" r="2.4" fill="{AMBER}"/>
  </svg>
  <div><b>Well Planning App</b><span>Well engineering and planning</span></div>
</div>
"""


def metrics_html(items):
    cells = "".join(
        f'<div class="ks-metric"><div class="l">{html.escape(l)}</div>'
        f'<div class="v">{html.escape(v)}</div><div class="u">{html.escape(u)}</div></div>'
        for l, v, u in items)
    return f'<div class="ks-metrics">{cells}</div>'


def check_html(c):
    col, bg, word = STATUS[c["status"]]
    return (f'<div class="ks-check" style="border-color:{col};background:{bg}">'
            f'<div class="t"><span>{html.escape(c["check"])}</span>'
            f'<span class="s" style="color:{col}">{word}</span></div>'
            f'<div class="n">{html.escape(str(c["value"]))} against limit {html.escape(str(c["limit"]))}. {html.escape(c["note"])}</div></div>')


def status_html(modified, unsaved, last, n_changes):
    if modified:
        tag = '<span class="ks-tag mod">Data modified</span>'
        detail = f"{n_changes} change{'s' if n_changes != 1 else ''} applied, last: {html.escape(last['section'])} at {html.escape(last['time'])}"
        detail += " · not yet saved to a project file" if unsaved else " · saved to project file"
    else:
        tag = '<span class="ks-tag clean">No changes</span>'
        detail = "Showing the design as loaded"
    return f'<div class="ks-status">{tag}<span>{detail}. Autosaved; safe to switch pages or refresh.</span></div>'


def note_html(text):
    return f'<div class="ks-note">{html.escape(text)}</div>'


def header_html(title, subtitle=""):
    return f'<div class="ks-head"><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>'


FOOTER = ('<div class="ks-foot">Screening-level engineering tool. Results must be verified by qualified '
          'engineers with approved software before operational use. Not affiliated with or endorsed by Equinor '
          'or any software vendor. MIT licence.</div>')


def plotly_layout(fig, height=420, title=None, dark=False, legend=True):
    bg = NAVY if dark else "#FFFFFF"
    fg = "#C9D6DF" if dark else INK
    grid = "#1E4461" if dark else "#E8EDF1"
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        paper_bgcolor=bg, plot_bgcolor=bg, font=dict(family="IBM Plex Sans, sans-serif", color=fg, size=12),
        title=dict(text=title, x=0.01, font=dict(size=14, color=fg)) if title else None,
        showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font_family="IBM Plex Sans"),
    )
    fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, linecolor=grid)
    fig.update_yaxes(gridcolor=grid, zerolinecolor=grid, linecolor=grid)
    return fig
