"""07 BHA & vibration: weight on bit design, neutral point, critical speeds."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ks_engine import bha as bha_eng
from ks_engine.units import FT2M, M2FT

from .. import model, state, theme


def render():
    p = state.project()
    st.markdown(theme.header_html("BHA & vibration", "Available weight on bit, neutral point and critical rotary speeds"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(plan.message)
        return
    oc = p["opcase"]
    a, b, c, d = st.columns(4)
    state.num("WOB (lb)", "opcase", "wob_lb", a, step=1000.0, min_value=0.0)
    state.num("Rotary speed (RPM)", "opcase", "rpm", b, step=10.0, min_value=0.0)
    state.num("WOB design factor", "limits", "wob_df", c, step=0.05, min_value=1.0)
    state.select("Bit type", "bit", "type", ["PDC", "Roller cone", "Impregnated"], d,
                 help="Roller cone excites axial vibration at 3x RPM; PDC and impregnated at 1x.")
    inc = model.inc_at_md(traj, oc["bit_md_m"])
    comps = model.string_components_ft(p)
    bha = [x for x in comps if x["in_bha"]]
    rows, cum = bha_eng.bha_weight(bha, p["fluid"]["mud_ppg"], inc)
    wob_max = cum / p["limits"]["wob_df"]
    np_ft, np_comp = bha_eng.neutral_point(comps, p["fluid"]["mud_ppg"], oc["wob_lb"], inc)
    bha_len_ft = sum(x["length"] for x in bha)
    st.markdown(theme.metrics_html([
        ("Buoyed BHA weight (axial)", f"{cum/1000:,.1f}", f"klbf at {inc:.1f}° inclination"),
        ("Max WOB with design factor", f"{wob_max/1000:,.1f}", "klbf"),
        ("Neutral point above bit", f"{np_ft*FT2M:,.0f}" if np_ft is not None else "n/a", "m" if np_ft is not None else "outside string"),
        ("Neutral point in", np_comp.split(" ")[0] if np_ft is not None else "n/a", np_comp if np_ft is not None else ""),
    ]), unsafe_allow_html=True)
    in_bha = np_ft is not None and np_ft <= bha_len_ft
    st.markdown(theme.check_html({"check": "Neutral point inside the BHA", "status": "pass" if in_bha and oc["wob_lb"] <= wob_max else "fail",
                                  "value": f"{oc['wob_lb']:,.0f} lb WOB", "limit": f"{wob_max:,.0f} lb",
                                  "note": "Keeps drill pipe in tension; high-angle wells may run DP in compression if buckling is checked on Torque & drag"}),
                unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{"Component": r["name"], "Length (m)": round(r["length"] * FT2M, 1), "Air weight (klbf)": round(r["air_lbf"] / 1000, 2),
                                "Buoyed (klbf)": round(r["buoyed_lbf"] / 1000, 2), "Cumulative axial (klbf)": round(r["cum_axial_lbf"] / 1000, 2)}
                               for r in rows]), hide_index=True, use_container_width=True)

    st.subheader("Stabiliser placement")
    st.caption("Distance of each stabiliser centre above the bit. Spans between stabilisers set the lateral critical speeds.")
    stabs = [{"distance_m": x} for x in p.get("stabilizers_m", [])]
    state.editor("stabs", stabs, ["distance_m"], {"distance_m": st.column_config.NumberColumn("Distance above bit (m)", min_value=0.0, format="%.1f")},
                 setter=lambda r: p.__setitem__("stabilizers_m", sorted(float(x["distance_m"]) for x in r if x.get("distance_m") is not None)),
                 dropna_cols=["distance_m"])

    st.subheader("Critical speeds")
    k = 3.0 if p["bit"]["type"] == "Roller cone" else 1.0
    string_ft = oc["bit_md_m"] * M2FT
    f_ax, rpm_ax = bha_eng.axial_critical_rpm(string_ft, k)
    f_tor = bha_eng.torsional_natural_frequency(string_ft)
    crit = [(float(r), f"Axial mode {i+1}") for i, r in enumerate(rpm_ax)]
    span_rows = []
    for span, od, id_, w in model.stabilizer_spans(p):
        _, lat = bha_eng.lateral_critical_rpm(span * M2FT, od, id_, w, p["fluid"]["mud_ppg"])
        crit.append((float(lat[0]), f"Lateral {span:.1f} m span"))
        span_rows.append({"Span (m)": round(span, 1), "OD (in)": od, "Mode 1 (RPM)": round(float(lat[0]), 0), "Mode 2 (RPM)": round(float(lat[1]), 0)})
    fig = go.Figure()
    rpm_max = max(300.0, oc["rpm"] * 1.5)
    for rpm_c, label in crit:
        if rpm_c <= rpm_max * 1.2:
            fig.add_shape(type="rect", x0=rpm_c * 0.85, x1=rpm_c * 1.15, y0=0, y1=1, yref="paper", fillcolor="rgba(235,0,55,0.10)", line_width=0)
            fig.add_vline(x=rpm_c, line=dict(color=theme.RED, width=1), annotation_text=label, annotation_textangle=-90,
                          annotation_font_size=10)
    fig.add_vline(x=oc["rpm"], line=dict(color=theme.MOSS, width=3), annotation_text="Operating", annotation_position="top left")
    theme.plotly_layout(fig, 280, legend=False)
    fig.update_xaxes(range=[0, rpm_max], title="Rotary speed (RPM)")
    fig.update_yaxes(visible=False)
    st.plotly_chart(fig, use_container_width=True, key=state.key("bha", "crit"))
    hits = bha_eng.rpm_risk(oc["rpm"], crit)
    st.markdown(theme.check_html({"check": "Operating RPM clear of critical bands", "status": "warn" if hits else "pass", "value": f"{oc['rpm']:.0f} RPM",
                                  "limit": "±15% of each critical", "note": ", ".join(f"{h[1]} at {h[0]:.0f} RPM" for h in hits) or "No screened critical in band"}),
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.dataframe(pd.DataFrame({"Mode": [1, 2, 3], "Axial (Hz)": f_ax.round(2), "Axial critical (RPM)": rpm_ax.round(0), "Torsional (Hz)": f_tor.round(2)}),
                 hide_index=True, use_container_width=True)
    if span_rows:
        c2.dataframe(pd.DataFrame(span_rows), hide_index=True, use_container_width=True)
    else:
        c2.info("Enter at least two stabilisers to screen lateral critical speeds.")
    st.markdown(theme.note_html("Screening only: axial and torsional modes treat the string as a uniform fixed-free steel bar; lateral modes treat each stabiliser span as a pinned-pinned beam with mud added mass. Stick-slip and whirl severity need a dynamics model or downhole data."), unsafe_allow_html=True)
