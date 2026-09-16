"""05 Geomechanics: overburden, pore, fracture and stability window."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import model, state, theme


def render():
    p = state.project()
    st.markdown(theme.header_html("Geomechanics", "Overburden, pore pressure, Eaton fracture gradient and vertical-well stability window"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(plan.message)
        return
    a, b, c, d = st.columns(4)
    state.num("SHmax / Shmin ratio", "geomech", "shmax_ratio", a, step=0.05, min_value=1.0, max_value=3.0)
    state.toggle("Pore pressure from Eaton sonic", "geomech", "use_eaton_sonic", b, help="Uses DT and normal-trend DT per formation, exponent 3")
    state.num("Normal pore gradient (ppg)", "geomech", "normal_ppg", c, step=0.05, min_value=8.3)
    state.num("Mud weight (ppg)", "fluid", "mud_ppg", d, step=0.1, min_value=6.0)
    st.caption("Formation properties are edited under Well data, Formations.")
    seabed = p["header"]["rkb_elev_m"] + p["header"]["water_depth_m"]
    tvd = np.linspace(seabed + 5, float(traj["tvd"][-1]), 150)
    w = model.geomech_window(p, tvd)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=w["pp"], y=tvd, name="Pore pressure", line=dict(color="#3D7CC9", width=2)))
    fig.add_trace(go.Scatter(x=w["collapse"], y=tvd, name="Shear collapse", line=dict(color="#8E6BBF", dash="dot")))
    fig.add_trace(go.Scatter(x=w["max_mw"], y=tvd, name="Fracture (Shmin)", line=dict(color=theme.RED, width=2),
                             fill="tonextx", fillcolor="rgba(157,186,0,0.10)"))
    fig.add_trace(go.Scatter(x=w["tensile"], y=tvd, name="Tensile initiation", line=dict(color=theme.RED, dash="dot")))
    fig.add_trace(go.Scatter(x=w["obg"], y=tvd, name="Overburden", line=dict(color=theme.NAVY)))
    fig.add_vline(x=p["fluid"]["mud_ppg"], line=dict(color=theme.MOSS, dash="dash"), annotation_text="Current MW")
    for cs in model.casing_rows(p):
        st_tvd = model.tvd_at_md_m(traj, cs["shoe_md"])
        fig.add_hline(y=st_tvd, line=dict(color=theme.LINE))
        fig.add_trace(go.Scatter(x=[cs["mud_ppg"], cs["lot_emw"]], y=[st_tvd, st_tvd], mode="markers+text",
                                 marker=dict(symbol=["circle", "triangle-left"], size=10, color=[theme.MOSS, theme.NAVY]),
                                 text=["", cs["name"].split(" ")[-1]], textposition="middle right", showlegend=False))
    for f in p["formations"]:
        fig.add_annotation(x=0.0, xref="paper", y=f["top_tvd"], text=f["name"], showarrow=False, xanchor="left", yshift=7,
                           font=dict(size=10, color=theme.MUTED))
    theme.plotly_layout(fig, 640)
    fig.update_yaxes(autorange="reversed", title="TVD (m RKB)")
    fig.update_xaxes(title="EMW (ppg)", range=[8, float(np.max(w["obg"])) + 0.5])
    st.plotly_chart(fig, use_container_width=True, key=state.key("gm", "win"))

    tops = sorted(p["formations"], key=lambda f: f["top_tvd"])
    rows = []
    for i, f in enumerate(tops):
        t0 = max(float(f["top_tvd"]), seabed + 5)
        t1 = float(tops[i + 1]["top_tvd"]) if i + 1 < len(tops) else float(traj["tvd"][-1])
        if t1 <= t0:
            continue
        g = model.geomech_window(p, np.linspace(t0, t1, 20))
        lo, hi = float(np.max(g["min_mw"])), float(np.min(g["max_mw"]))
        rows.append({"Formation": f["name"], "Top TVD (m)": f["top_tvd"], "Min MW (ppg)": round(lo, 2), "Max MW (ppg)": round(hi, 2),
                     "Window (ppg)": round(hi - lo, 2), "Current MW inside": "yes" if lo <= p["fluid"]["mud_ppg"] <= hi else "no"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.markdown(theme.note_html("Stability uses the Kirsch solution with Mohr-Coulomb for a vertical, impermeable wellbore (σθ max, σz intermediate). It is a screening window: deviated sections need a 3D stress transformation and calibrated stresses (LOT/XLOT, breakouts)."), unsafe_allow_html=True)
