"""08 Time & cost: section plan, time-depth curve, AFE and Monte Carlo."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ks_engine.cost import SECTION_FIELDS

from .. import model, state, theme
from ..compute import cost_mc

CC = st.column_config


def _musd(x):
    return f"{x/1e6:,.1f}"


def render():
    p = state.project()
    c = p["cost"]
    st.markdown(theme.header_html("Time & cost", "Section-based duration, time-depth curve, AFE build-up and P10/P50/P90 uncertainty"), unsafe_allow_html=True)
    a, b, cc, d = st.columns(4)
    state.num("Rig rate (USD/day)", "cost", "rig_rate", a, step=10000.0, min_value=0.0, fmt="%.0f")
    state.num("Spread rate (USD/day)", "cost", "spread_rate", b, step=10000.0, min_value=0.0, fmt="%.0f")
    state.num("Mobilisation cost (USD)", "cost", "mob_cost", cc, step=100000.0, min_value=0.0, fmt="%.0f")
    state.num("Mobilisation days", "cost", "mob_days", d, step=0.5, min_value=0.0)

    with st.expander("Section plan", expanded=False):
        st.caption("Lengths in metres; ROP and trip/casing speeds in m/hr. Casing cost is per metre of string run (surface to shoe).")
        state.editor("cost_sections", c["sections"], SECTION_FIELDS, {
            "name": CC.TextColumn("Section"), "hole_in": CC.NumberColumn("Hole (in)", format="%.2f"),
            "top_md": CC.NumberColumn("Top (m)"), "bottom_md": CC.NumberColumn("Bottom (m)"), "rop": CC.NumberColumn("ROP (m/hr)"),
            "trip_speed": CC.NumberColumn("Trip (m/hr)"), "casing_speed": CC.NumberColumn("Casing run (m/hr)"), "bits": CC.NumberColumn("Bits", step=1),
            "circ_hr": CC.NumberColumn("Circ (hr)"), "logging_hr": CC.NumberColumn("Logging (hr)"), "cement_hr": CC.NumberColumn("Cement (hr)"),
            "woc_hr": CC.NumberColumn("WOC (hr)"), "bop_hr": CC.NumberColumn("WH/BOP (hr)"), "npt_pct": CC.NumberColumn("NPT (%)"),
            "bit_cost": CC.NumberColumn("Bit cost (USD)", format="%.0f"), "mud_cost_per_len": CC.NumberColumn("Mud (USD/m)", format="%.0f"),
            "casing_cost_per_len": CC.NumberColumn("Casing (USD/m)", format="%.0f"), "cement_cost": CC.NumberColumn("Cement (USD)", format="%.0f"),
            "logging_cost": CC.NumberColumn("Logging (USD)", format="%.0f"), "other_cost": CC.NumberColumn("Other (USD)", format="%.0f")},
            setter=lambda r: c.__setitem__("sections", sorted(({k: (v if v is not None else 0) for k, v in x.items()} | {"name": x["name"] or "Section"}
                                                              for x in r), key=lambda s: s["top_md"])),
            dropna_cols=["top_md", "bottom_md", "rop"])
    if not c["sections"]:
        st.info("Add at least one section.")
        return
    plan = model.cost_plan(p)
    st.markdown(theme.metrics_html([
        ("Planned duration", f"{plan['total_days']:,.1f}", "days incl. mobilisation"),
        ("Planned cost", _musd(plan["total_cost"]), "MUSD"),
        ("Cost per metre", f"{plan['total_cost']/max(c['sections'][-1]['bottom_md'],1):,.0f}", "USD/m"),
        ("Drilling share of time", f"{100*sum(s['drilling_days'] for s in plan['sections'])/max(plan['total_days'],1e-6):.0f}", "% on bottom"),
    ]), unsafe_allow_html=True)

    c1, c2 = st.columns([1.6, 1])
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plan["curve_days"], y=plan["curve_depth"], name="Depth", line=dict(color=theme.NAVY, width=2)))
        fig.add_trace(go.Scatter(x=plan["curve_days"], y=plan["curve_cost"] / 1e6, name="Cumulative cost (MUSD)", xaxis="x", yaxis="y2",
                                 line=dict(color=theme.MOSS, dash="dot")))
        theme.plotly_layout(fig, 420, title="Time vs depth")
        fig.update_layout(yaxis=dict(title="Depth (m MD)", autorange="reversed"), xaxis=dict(title="Days"),
                          yaxis2=dict(title="MUSD", overlaying="y", side="right", showgrid=False))
        st.plotly_chart(fig, use_container_width=True, key=state.key("cost", "tvd"))
    with c2:
        afe = {k: v for k, v in plan["afe"].items() if v > 0}
        fig = go.Figure(go.Bar(x=[v / 1e6 for v in afe.values()], y=list(afe.keys()), orientation="h", marker_color=theme.MOSS,
                               text=[f"{v/1e6:,.1f}" for v in afe.values()], textposition="outside"))
        theme.plotly_layout(fig, 420, title="AFE build-up (MUSD)", legend=False)
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, key=state.key("cost", "afe"))
    st.dataframe(pd.DataFrame([{"Section": s["section"], "Days": round(s["days"], 1), "On-bottom days": round(s["drilling_days"], 1),
                                "Cost (MUSD)": round(s["cost"] / 1e6, 2)} for s in plan["sections"]]), hide_index=True, use_container_width=True)
    with st.expander("Activity breakdown"):
        df = pd.DataFrame(plan["activities"]).rename(columns={"section": "Section", "activity": "Activity", "hours": "Hours", "end_day": "End day", "depth": "Depth (m)"})
        st.dataframe(df.round(1), hide_index=True, use_container_width=True, height=320)
        st.download_button("Download activity plan (CSV)", df.to_csv(index=False).encode(), "activity_plan.csv", "text/csv", key=state.key("cost", "csv"))

    st.subheader("Uncertainty (Monte Carlo)")
    st.caption("Triangular multipliers (low, mode, high) applied to ROP, NPT allowance and daily rates.")
    a, b, cc, d = st.columns(4)
    for col, field, label in [(a, "mc_rop", "ROP multiplier"), (b, "mc_npt", "NPT multiplier"), (cc, "mc_rate", "Rate multiplier")]:
        lo, hi = col.slider(label + " (low, high)", 0.1, 4.0, (float(c[field][0]), float(c[field][2])), 0.05, key=state.key("cost", field))
        c[field] = [lo, float(np.clip(c[field][1], lo, hi)), hi]
    state.num("Iterations", "cost", "mc_n", d, step=500, min_value=200, max_value=20000, integer=True)
    mc = cost_mc(p)
    ds, cs = mc["days_stats"], mc["cost_stats"]
    st.markdown(theme.metrics_html([
        ("P10 / P50 / P90 days", f"{ds['P10']:.0f} / {ds['P50']:.0f} / {ds['P90']:.0f}", "days"),
        ("P10 cost", _musd(cs["P10"]), "MUSD"),
        ("P50 cost", _musd(cs["P50"]), "MUSD"),
        ("P90 cost", _musd(cs["P90"]), "MUSD"),
    ]), unsafe_allow_html=True)
    srt = np.sort(mc["cost"]) / 1e6
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=srt, nbinsx=40, marker_color=theme.MOSS_LIGHT, name="Frequency"))
    fig.add_trace(go.Scatter(x=srt, y=np.linspace(0, 1, len(srt)), yaxis="y2", line=dict(color=theme.NAVY), name="Cumulative"))
    for k_, col in (("P10", theme.PISTACHIO), ("P50", theme.NAVY), ("P90", theme.RED)):
        fig.add_vline(x=cs[k_] / 1e6, line=dict(color=col, dash="dash"), annotation_text=k_)
    theme.plotly_layout(fig, 340)
    fig.update_layout(xaxis=dict(title="Well cost (MUSD)"), yaxis=dict(title="Count"),
                      yaxis2=dict(overlaying="y", side="right", range=[0, 1], tickformat=".0%", showgrid=False))
    st.plotly_chart(fig, use_container_width=True, key=state.key("cost", "mc"))
