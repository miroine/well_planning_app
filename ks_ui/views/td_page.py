"""02 Torque & drag: all-operation profiles, broomstick, buckling, calibration."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ks_engine import torque_drag as td_eng
from ks_engine.units import FT2M, M2FT

from .. import model, state, theme

OP_COLORS = {"trip_out": theme.RED, "rotate_off": theme.MOSS, "trip_in": "#3D7CC9", "drill_rotate": theme.NAVY,
             "slide": theme.AMBER, "ream_out": "#A05195", "ream_in": "#6A8F00"}


@st.cache_data(show_spinner=False, max_entries=8)
def _broomstick(blob, depths, ffs):
    import json
    p = json.loads(blob)
    traj, _ = model.trajectory_m(p)
    out = {}
    for ff in ffs:
        for op in ("trip_out", "rotate_off", "trip_in"):
            out[f"{ff}|{op}"] = [model.run_torque_drag(p, traj, op, d, p["opcase"]["ff_cased"], ff, dl=100.0)["hookload"] for d in depths]
    return out


def render():
    p = state.project()
    st.markdown(theme.header_html("Torque & drag", "Soft-string model (Johancsik et al., 1984) with buckling screening"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(plan.message)
        return
    a, b, c, d = st.columns(4)
    state.num("Bit depth (m MD)", "opcase", "bit_md_m", a, step=10.0, min_value=1.0)
    state.num("FF cased hole", "opcase", "ff_cased", b, step=0.01, min_value=0.0, max_value=1.0)
    state.num("FF open hole", "opcase", "ff_open", c, step=0.01, min_value=0.0, max_value=1.0)
    state.num("Mud weight (ppg)", "fluid", "mud_ppg", d, step=0.1, min_value=6.0)
    a, b, c, d = st.columns(4)
    state.num("WOB (lb)", "opcase", "wob_lb", a, step=1000.0, min_value=0.0)
    state.num("Bit torque (ft-lb)", "opcase", "bit_torque", b, step=500.0, min_value=0.0)
    state.num("RPM (reaming)", "opcase", "rpm", c, step=10.0, min_value=0.0)
    state.num("Trip speed (m/min)", "opcase", "trip_speed_mmin", d, step=1.0, min_value=0.0)

    ops = st.multiselect("Operations to compare", list(td_eng.OPERATIONS), default=["trip_out", "rotate_off", "trip_in", "drill_rotate", "slide"],
                         format_func=lambda k: td_eng.OPERATIONS[k], key=state.key("td", "ops"))
    results = {op: model.run_torque_drag(p, traj, op) for op in ops}
    if results:
        st.dataframe(pd.DataFrame([{"Operation": td_eng.OPERATIONS[op], "Hookload (klbf)": round(r["hookload"] / 1000, 1),
                                    "Surface torque (ft-lb)": round(r["surface_torque"]), "Max side force (lbf/ft)": round(float(np.max(r["side_force_per_ft"])), 0),
                                    "Max tension util.": f"{np.max(r['tension_utilisation'])*100:.0f}%" if len(r["tension_utilisation"]) else "-",
                                    "Buckling": ("helical" if np.any(r["buckling"] == "helical") else "sinusoidal" if np.any(r["buckling"] == "sinusoidal") else "none")}
                                   for op, r in results.items()]), hide_index=True, use_container_width=True)
        r0 = next(iter(results.values()))
        st.caption(f"Buoyancy factor {r0['buoyancy_factor']:.3f}; string weight in air {r0['string_weight_air']/1000:,.1f} klbf, buoyed {r0['string_weight_buoyed']/1000:,.1f} klbf; blocks {p['rig']['block_weight_klbf']:.0f} klbf.")

        fig = make_subplots(rows=1, cols=3, shared_yaxes=True, subplot_titles=("Effective tension (klbf)", "Torque (kft-lb)", "Side force (lbf/ft)"))
        for op, r in results.items():
            md = r["md"] * FT2M
            col = OP_COLORS.get(op, theme.INK)
            fig.add_trace(go.Scatter(x=r["tension"] / 1000, y=md, name=td_eng.OPERATIONS[op], line=dict(color=col), legendgroup=op), 1, 1)
            fig.add_trace(go.Scatter(x=r["torque"] / 1000, y=md, line=dict(color=col), showlegend=False, legendgroup=op), 1, 2)
            fig.add_trace(go.Scatter(x=r["side_force_per_ft"], y=md, line=dict(color=col), showlegend=False, legendgroup=op), 1, 3)
        rb = next(iter(results.values()))
        fig.add_trace(go.Scatter(x=-rb["f_sin"] / 1000, y=rb["element_md"] * FT2M, name="Sinusoidal limit", line=dict(color="#999", dash="dot")), 1, 1)
        fig.add_trace(go.Scatter(x=-rb["f_hel"] / 1000, y=rb["element_md"] * FT2M, name="Helical limit", line=dict(color="#555", dash="dash")), 1, 1)
        shoe = model.deepest_shoe_above(p, p["opcase"]["bit_md_m"])
        if shoe:
            for k in (1, 2, 3):
                fig.add_hline(y=shoe["shoe_md"], line=dict(color=theme.MUTED, dash="dot"), row=1, col=k)
        theme.plotly_layout(fig, 520)
        fig.update_yaxes(autorange="reversed", title="MD (m)", row=1, col=1)
        st.plotly_chart(fig, use_container_width=True, key=state.key("td", "prof"))

    st.subheader("Broomstick: hookload vs bit depth")
    c1, c2 = st.columns([1, 3])
    ff_txt = c1.text_input("Open-hole friction factors", "0.15, 0.25, 0.35", key=state.key("td", "ffs"))
    n_pts = c1.slider("Depth points", 8, 40, 16, key=state.key("td", "npts"))
    try:
        ffs = tuple(sorted({round(float(x), 3) for x in ff_txt.split(",") if x.strip()}))
    except ValueError:
        ffs = (0.25,)
        c1.error("Friction factors must be numbers separated by commas.")
    td_md = float(traj["md"][-1])
    depths = tuple(np.linspace(max(td_md * 0.05, 30.0), td_md, n_pts).round(1))
    data = _broomstick(model.project_to_json(p), depths, ffs)
    fig = go.Figure()
    dash = {"trip_out": "solid", "rotate_off": "dot", "trip_in": "dash"}
    for key_, hl in data.items():
        ff, op = key_.split("|")
        fig.add_trace(go.Scatter(x=np.array(hl) / 1000, y=depths, mode="lines", line=dict(dash=dash[op]),
                                 name=f"{td_eng.OPERATIONS[op].split(' (')[0]} FF {ff}"))
    meas = c1.number_input("Measured hookload to overlay (klbf)", value=0.0, min_value=0.0, step=5.0, key=state.key("td", "meas"))
    if meas > 0:
        fig.add_trace(go.Scatter(x=[meas], y=[p["opcase"]["bit_md_m"]], mode="markers", marker=dict(size=12, color=theme.AMBER, symbol="x"), name="Measured"))
    theme.plotly_layout(fig, 480)
    fig.update_yaxes(autorange="reversed", title="Bit MD (m)")
    fig.update_xaxes(title="Hookload incl. blocks (klbf)")
    c2.plotly_chart(fig, use_container_width=True, key=state.key("td", "broom"))

    st.subheader("Friction factor calibration")
    a, b, c = st.columns(3)
    cal_op = a.selectbox("Measured operation", ["trip_out", "trip_in"], format_func=lambda k: td_eng.OPERATIONS[k], key=state.key("td", "calop"))
    cal_hl = b.number_input("Measured hookload at current bit depth (klbf)", value=0.0, min_value=0.0, step=5.0, key=state.key("td", "calhl"))
    if cal_hl > 0:
        shoe = model.deepest_shoe_above(p, p["opcase"]["bit_md_m"])
        ff = td_eng.calibrate_friction(model.traj_ft(traj), model.string_components_ft(p), p["opcase"]["bit_md_m"] * M2FT,
                                       p["fluid"]["mud_ppg"], (shoe["shoe_md"] if shoe else 0) * M2FT, cal_hl * 1000, cal_op,
                                       p["opcase"]["ff_cased"], p["rig"]["block_weight_klbf"] * 1000)
        if ff is None:
            c.warning("No open-hole friction factor between 0 and 0.8 reproduces that hookload. Check block weight, mud weight and string data.")
        else:
            c.success(f"Back-calculated open-hole FF = {ff:.3f}")
            if c.button("Use this friction factor", key=state.key("td", "useff")):
                p["opcase"]["ff_open"] = round(ff, 3)
                state.bump()
                st.rerun()
    st.markdown(theme.note_html("Soft-string assumptions: no bending stiffness in side force, post-buckling contact forces not added to drag, same mud inside and outside the string."), unsafe_allow_html=True)
