"""03 Hydraulics & tripping: pressure breakdown, ECD vs window, flow sweep,
bit optimisation, surge & swab."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ks_engine import hydraulics as hy
from ks_engine.units import FT2M, M2FT

from .. import model, state, theme


def render():
    p = state.project()
    st.markdown(theme.header_html("Hydraulics & tripping", "API RP 13D power law or Bingham plastic, ECD, bit hydraulics, surge & swab"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(plan.message)
        return
    a, b, c, d = st.columns(4)
    state.num("Bit depth (m MD)", "opcase", "bit_md_m", a, step=10.0, min_value=1.0)
    state.num("Flow rate (gpm)", "opcase", "flow_gpm", b, step=25.0, min_value=0.0)
    state.num("ROP for cuttings load (m/hr)", "opcase", "rop_mhr", c, step=1.0, min_value=0.0)
    state.num("Mud weight (ppg)", "fluid", "mud_ppg", d, step=0.1, min_value=6.0)
    a, b, c, d = st.columns(4)
    state.select("Rheology model", "fluid", "model", ["power_law", "bingham"], a,
                 format_func=lambda x: {"power_law": "Power law (API RP 13D)", "bingham": "Bingham plastic"}[x])
    state.text("Nozzles (1/32 in)", "bit", "nozzles", b)
    state.num("Cuttings transport ratio", "fluid", "transport_ratio", c, step=0.05, min_value=0.05, max_value=1.0)
    state.num("Tool pressure drop (psi)", "rig", "tool_loss_psi", d, step=25.0, min_value=0.0)

    try:
        rh = model.rheology(p)
        res = model.run_hydraulics(p, traj)
    except ValueError as exc:
        st.error(f"Hydraulics cannot run: {exc}")
        return
    bit = res["bit"]
    st.markdown(theme.metrics_html([
        ("Standpipe pressure", f"{res['spp']:,.0f}", f"psi of {p['rig']['pump_rating_psi']:,.0f} rated"),
        ("ECD at bit", f"{res['ecd_bit']:.2f}", "ppg"),
        ("Bit hydraulic power", f"{bit['hhp']:,.0f}", f"hp, {res['bit_hhp_fraction']*100:.0f}% of pump pressure"),
        ("Jet impact force", f"{bit['impact_force_lbf']:,.0f}", f"lbf, nozzle velocity {bit['nozzle_velocity_fts']:.0f} ft/s"),
    ]), unsafe_allow_html=True)
    st.caption(f"Power-law parameters: pipe n={rh['n_p']:.3f}, K={rh['K_p']:.3f} dyne·sⁿ/cm²; annulus n={rh['n_a']:.3f}, K={rh['K_a']:.3f}. PV {rh['PV']:.0f} cP, YP {rh['YP']:.0f} lbf/100ft².")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pressure breakdown")
        parts = [("Surface", res["surface_dp"]), ("Drillstring", res["string_dp"]), ("Tools", res["tool_dp"]),
                 ("Bit", bit["dp"]), ("Annulus", res["annulus_dp"])]
        fig = go.Figure(go.Waterfall(x=[x[0] for x in parts] + ["SPP"], y=[x[1] for x in parts] + [0],
                                     measure=["relative"] * len(parts) + ["total"], connector=dict(line=dict(color=theme.LINE)),
                                     increasing=dict(marker=dict(color=theme.MOSS)), totals=dict(marker=dict(color=theme.NAVY))))
        fig.add_hline(y=p["rig"]["pump_rating_psi"], line=dict(color=theme.RED, dash="dash"), annotation_text="Pump rating")
        theme.plotly_layout(fig, 360, legend=False)
        fig.update_yaxes(title="psi")
        st.plotly_chart(fig, use_container_width=True, key=state.key("hy", "wf"))
    with c2:
        st.subheader("ECD vs mud-weight window")
        md = np.linspace(max(p["header"]["rkb_elev_m"] + p["header"]["water_depth_m"], 50.0), p["opcase"]["bit_md_m"], 60)
        tvd = np.array([model.tvd_at_md_m(traj, m) for m in md])
        w = model.geomech_window(p, tvd)
        full = res
        ecd = np.array([full["ecd_profile"](m * M2FT) for m in md])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=w["pp"], y=tvd, name="Pore", line=dict(color="#3D7CC9")))
        fig.add_trace(go.Scatter(x=w["collapse"], y=tvd, name="Collapse", line=dict(color="#3D7CC9", dash="dot")))
        fig.add_trace(go.Scatter(x=w["max_mw"], y=tvd, name="Fracture", line=dict(color=theme.RED)))
        fig.add_trace(go.Scatter(x=ecd, y=tvd, name="ECD", line=dict(color=theme.MOSS, width=3)))
        fig.add_vline(x=p["fluid"]["mud_ppg"], line=dict(color=theme.NAVY, dash="dash"), annotation_text="MW")
        for cs in model.casing_rows(p):
            if cs["shoe_md"] <= p["opcase"]["bit_md_m"]:
                fig.add_trace(go.Scatter(x=[cs["lot_emw"]], y=[model.tvd_at_md_m(traj, cs["shoe_md"])], mode="markers",
                                         marker=dict(symbol="triangle-left", size=11, color=theme.NAVY), name=f"LOT {cs['name']}", showlegend=False))
        theme.plotly_layout(fig, 360)
        fig.update_yaxes(autorange="reversed", title="TVD (m)")
        fig.update_xaxes(title="ppg EMW")
        st.plotly_chart(fig, use_container_width=True, key=state.key("hy", "ecd"))

    st.subheader("Annular sections")
    seg = pd.DataFrame([{"Top (mMD)": round(s["md_top"] * FT2M, 0), "Bottom (mMD)": round(s["md_bot"] * FT2M, 0), "Hole/csg ID (in)": s["hole"],
                         "Pipe OD (in)": s["od"], "AV (ft/min)": round(s["v_ftmin"], 0), "Regime": s["regime"],
                         "Re": round(s["re"], 0), "ΔP (psi)": round(s["dp"], 1), "Cuttings conc. (%)": round(s["cuttings_conc"] * 100, 2)}
                        for s in res["segments"] if s["hole"] > s["od"]])
    st.dataframe(seg, hide_index=True, use_container_width=True)

    st.subheader("Flow rate sweep and bit optimisation")
    a, b = st.columns([1, 3])
    q_lo = a.number_input("Min flow (gpm)", value=200.0, min_value=10.0, step=25.0, key=state.key("hy", "qlo"))
    q_hi = a.number_input("Max flow (gpm)", value=float(p["rig"]["max_flow_gpm"]), min_value=q_lo + 10, step=25.0, key=state.key("hy", "qhi"))
    qs = np.linspace(q_lo, q_hi, 30)
    sweep = [model.run_hydraulics(p, traj, flow_gpm=q) for q in qs]
    spp = np.array([s["spp"] for s in sweep])
    ecd = np.array([s["ecd_bit"] for s in sweep])
    hhp = np.array([s["bit"]["hhp"] for s in sweep])
    imp = np.array([s["bit"]["impact_force_lbf"] for s in sweep])
    ok = spp <= p["rig"]["pump_rating_psi"]
    if ok.any():
        i_h = int(np.argmax(np.where(ok, hhp, -1)))
        i_i = int(np.argmax(np.where(ok, imp, -1)))
        a.markdown(f"Max bit HHP within pump rating: **{qs[i_h]:.0f} gpm** ({hhp[i_h]:,.0f} hp)")
        a.markdown(f"Max jet impact within pump rating: **{qs[i_i]:.0f} gpm** ({imp[i_i]:,.0f} lbf)")
    else:
        a.warning("Every flow rate in the range exceeds the pump rating.")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=qs, y=spp, name="SPP (psi)", line=dict(color=theme.NAVY)))
    fig.add_trace(go.Scatter(x=qs, y=hhp, name="Bit HHP", line=dict(color=theme.MOSS), yaxis="y2"))
    fig.add_trace(go.Scatter(x=qs, y=ecd, name="ECD at bit (ppg)", line=dict(color=theme.AMBER), yaxis="y3"))
    fig.add_hline(y=p["rig"]["pump_rating_psi"], line=dict(color=theme.RED, dash="dash"))
    theme.plotly_layout(fig, 380)
    fig.update_layout(xaxis=dict(title="Flow rate (gpm)", domain=[0, 0.88]), yaxis=dict(title="SPP (psi)"),
                      yaxis2=dict(title="HHP", overlaying="y", side="right", showgrid=False),
                      yaxis3=dict(title="ECD", overlaying="y", side="right", position=0.97, anchor="free", showgrid=False))
    b.plotly_chart(fig, use_container_width=True, key=state.key("hy", "sweep"))

    st.subheader("Surge & swab")
    a, b, c = st.columns(3)
    state.num("Tripping speed (m/min)", "opcase", "trip_speed_mmin", a, step=1.0, min_value=0.0)
    state.toggle("Closed-end pipe (float / bit plugged)", "opcase", "closed_end", b)
    state.num("Surge/swab margin (ppg)", "limits", "surge_margin_ppg", c, step=0.05, min_value=0.0)
    sw = model.run_surge_swab(p, traj)
    win = model.window_at_tvd(p, model.tvd_at_md_m(traj, p["opcase"]["bit_md_m"]))
    tvd_fn = lambda md_ft: model.tvd_at_md_m(traj, md_ft * FT2M) * M2FT
    ss_args = (p["fluid"]["mud_ppg"], rh, model.string_sections_ft(p, p["opcase"]["bit_md_m"]),
               model.annulus_sections_ft(p, p["opcase"]["bit_md_m"]), p["opcase"]["bit_md_m"] * M2FT, tvd_fn)
    v_surge = hy.max_trip_speed(win["max_mw"] - p["limits"]["surge_margin_ppg"], "surge", *ss_args, closed_end=p["opcase"]["closed_end"]) * FT2M
    v_swab = hy.max_trip_speed(win["pp"] + p["limits"]["surge_margin_ppg"], "swab", *ss_args, closed_end=p["opcase"]["closed_end"]) * FT2M
    st.markdown(theme.metrics_html([
        ("Surge EMW at bit", f"{sw['surge_emw']:.2f}", f"ppg, fracture {win['max_mw']:.2f}"),
        ("Swab EMW at bit", f"{sw['swab_emw']:.2f}", f"ppg, pore {win['pp']:.2f}"),
        ("Max running speed", f"{v_surge:.1f}", "m/min within surge margin"),
        ("Max pulling speed", f"{v_swab:.1f}", "m/min within swab margin"),
    ]), unsafe_allow_html=True)
    speeds = np.linspace(1, max(60.0, p["opcase"]["trip_speed_mmin"] * 1.5), 30)
    surge = [model.run_surge_swab(p, traj, speed_mmin=v) for v in speeds]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=speeds, y=[s["surge_emw"] for s in surge], name="Surge EMW", line=dict(color=theme.RED)))
    fig.add_trace(go.Scatter(x=speeds, y=[s["swab_emw"] for s in surge], name="Swab EMW", line=dict(color="#3D7CC9")))
    fig.add_hline(y=win["max_mw"], line=dict(color=theme.RED, dash="dash"), annotation_text="Fracture")
    fig.add_hline(y=win["pp"], line=dict(color="#3D7CC9", dash="dash"), annotation_text="Pore")
    fig.add_vline(x=p["opcase"]["trip_speed_mmin"], line=dict(color=theme.MUTED, dash="dot"))
    theme.plotly_layout(fig, 340)
    fig.update_xaxes(title="Pipe speed (m/min)")
    fig.update_yaxes(title="EMW at bit (ppg)")
    st.plotly_chart(fig, use_container_width=True, key=state.key("hy", "ss"))
    st.caption("Burkhardt clinging constant 0.45; steady-state (no inertia or gel breaking). Hole-cleaning AV guide is a rule of thumb, not a cuttings-transport model.")
