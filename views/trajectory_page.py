"""01 Trajectory & survey: planner, survey listing, target check,
anti-collision."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ks_engine import trajectory as tj

from .. import model, plots, state, theme

CC = st.column_config


def render():
    p = state.project()
    st.markdown(theme.header_html("Trajectory & survey", "Minimum curvature planning, target check and anti-collision"), unsafe_allow_html=True)
    left, right = st.columns([1, 2.2], gap="medium")
    with left:
        st.markdown("**Well plan**")
        t = state.select("Profile", "plan", "type", model.PLAN_TYPES)
        a, b = st.columns(2)
        if t in ("Build & hold (J)", "S-type"):
            state.num("KOP (m MD)", "plan", "kop_m", a, step=10.0, min_value=0.0)
            state.num("Build rate (°/30 m)", "plan", "bur", b, step=0.1, min_value=0.1)
            state.num("Target TVD (m)", "plan", "target_tvd_m", a, step=10.0, min_value=1.0)
            state.num("Target departure (m)", "plan", "target_disp_m", b, step=10.0, min_value=0.0)
            state.num("Azimuth (°)", "plan", "azimuth", a, step=1.0, min_value=0.0, max_value=360.0)
            if t == "S-type":
                state.num("Drop rate (°/30 m)", "plan", "dor", b, step=0.1, min_value=0.1)
                state.num("Final inclination (°)", "plan", "end_inc", a, step=1.0, min_value=0.0, max_value=80.0)
            else:
                state.num("Extend past target (m MD)", "plan", "extend_m", b, step=10.0, min_value=0.0)
        elif t == "Horizontal":
            state.num("Landing TVD (m)", "plan", "landing_tvd_m", a, step=10.0, min_value=1.0)
            state.num("Build rate (°/30 m)", "plan", "bur", b, step=0.1, min_value=0.1)
            state.num("Lateral length (m)", "plan", "lateral_m", a, step=25.0, min_value=0.0)
            state.num("Azimuth (°)", "plan", "azimuth", b, step=1.0, min_value=0.0, max_value=360.0)
        elif t == "Vertical":
            state.num("TD TVD (m)", "plan", "target_tvd_m", a, step=10.0, min_value=1.0)
        else:
            st.caption("Planned stations (MD m, inc °, azi °). Minimum curvature is applied between stations.")
            state.editor("survey_table", p["survey_table"], ["md", "inc", "azi"],
                         {"md": CC.NumberColumn("MD (m)", min_value=0.0), "inc": CC.NumberColumn("Inc (°)", min_value=0.0, max_value=180.0),
                          "azi": CC.NumberColumn("Azi (°)", min_value=0.0, max_value=360.0)},
                         setter=lambda r: p.__setitem__("survey_table", r), dropna_cols=["md", "inc", "azi"])
        if t != "Survey table":
            state.num("Station spacing (m)", "plan", "step_m", a, step=5.0, min_value=1.0)
        a2, b2 = st.columns(2)
        state.num("DLS limit (°/30 m)", "limits", "max_dls", a2, step=0.5, min_value=0.1)
        state.num("Minimum separation factor", "limits", "min_sf", b2, step=0.1, min_value=0.5)
        state.num("EOU radius at surface (m)", "limits", "anticol_r0", a2, step=0.1, min_value=0.0)
        state.num("EOU growth (m per 1000 m MD)", "limits", "anticol_growth", b2, step=0.5, min_value=0.0)

    try:
        traj, plan = model.trajectory_m(p)
    except ValueError as exc:
        right.error(f"Survey table is invalid: {exc}")
        return
    if traj is None:
        right.error(f"Plan is not feasible: {plan.message}")
        return
    with right:
        td_md = traj["md"][-1]
        dist, az = tj.closure(traj["north"][-1] - p["header"]["surface_n"], traj["east"][-1] - p["header"]["surface_e"])
        st.markdown(theme.metrics_html([
            ("TD measured depth", f"{td_md:,.0f}", "m MD"), ("TD vertical depth", f"{traj['tvd'][-1]:,.0f}", "m TVD"),
            ("Closure", f"{dist:,.0f}", f"m at {az:.1f}°"), ("Max dogleg", f"{traj['dls'].max():.2f}", "°/30 m")]),
            unsafe_allow_html=True)
        st.caption(plan.message + ("; key points: " + ", ".join(f"{k} {v:,.0f} m" for k, v in plan.key_points.items() if k != "hold_inc") if plan.key_points else ""))
        v1, v2, v3 = st.tabs(["3D", "Plan view", "Vertical section"])
        with v1:
            st.plotly_chart(plots.well_3d(p, traj, None, True, True, True, 500), use_container_width=True, key=state.key("tj", "3d"))
        with v2:
            st.plotly_chart(plots.plan_view(p, traj, None, 500), use_container_width=True, key=state.key("tj", "pv"))
        with v3:
            st.plotly_chart(plots.section_view(p, traj, None, 500), use_container_width=True, key=state.key("tj", "vs"))

    st.subheader("Target check")
    rows = []
    for tg in p.get("targets", []):
        try:
            md_grid = np.linspace(0, td_md, 2000)
            s = tj.interpolate_at_md(traj, md_grid)
            k = int(np.argmin(np.abs(s["tvd"] - float(tg["tvd"]))))
            miss = float(np.hypot(s["north"][k] - float(tg["north"]), s["east"][k] - float(tg["east"])))
            rows.append({"Target": tg["name"], "MD at target TVD (m)": round(float(md_grid[k]), 1), "Horizontal miss (m)": round(miss, 1),
                         "Radius (m)": tg["radius"], "Status": "Inside" if miss <= float(tg["radius"] or 0) else "Outside"})
        except (KeyError, TypeError, ValueError):
            continue
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("Add targets under Well data to check the plan against them.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Dogleg severity")
        fig = go.Figure(go.Scatter(x=traj["md"], y=traj["dls"], mode="lines", line=dict(color=theme.MOSS), name="DLS"))
        fig.add_hline(y=p["limits"]["max_dls"], line=dict(color=theme.RED, dash="dash"), annotation_text="Limit")
        act = model.actual_trajectory_m(p)
        if act is not None:
            fig.add_trace(go.Scatter(x=act["md"], y=act["dls"], mode="lines+markers", line=dict(color=theme.AMBER), name="Actual"))
        theme.plotly_layout(fig, 320)
        fig.update_xaxes(title="MD (m)")
        fig.update_yaxes(title="°/30 m")
        st.plotly_chart(fig, use_container_width=True, key=state.key("tj", "dls"))
    with c2:
        st.subheader("Anti-collision")
        ac = model.anticollision(p, traj)
        if not ac:
            st.caption("No offset wells defined.")
        else:
            fig = go.Figure()
            for a in ac:
                fig.add_trace(go.Scatter(x=a["sep"]["md"], y=a["sep"]["sf"], mode="lines", name=a["name"]))
            fig.add_hline(y=p["limits"]["min_sf"], line=dict(color=theme.RED, dash="dash"), annotation_text="Minimum SF")
            theme.plotly_layout(fig, 320)
            fig.update_xaxes(title="Reference MD (m)")
            fig.update_yaxes(title="Separation factor", type="log")
            st.plotly_chart(fig, use_container_width=True, key=state.key("tj", "ac"))
            st.dataframe(pd.DataFrame([{"Offset": a["name"], "Min SF": round(a["min_sf"], 2), "At MD (m)": round(a["at_md"], 0),
                                        "Min centre-to-centre (m)": round(a["min_ctc"], 1)} for a in ac]), hide_index=True, use_container_width=True)
            st.caption("Scalar cone of uncertainty (radius = r0 + growth × MD). Screening only; use an ISCWSA error model for final anti-collision.")

    st.subheader("Survey listing")
    df = pd.DataFrame({"MD (m)": traj["md"], "Inc (°)": traj["inc"], "Azi (°)": traj["azi"], "TVD (m)": traj["tvd"],
                       "North (m)": traj["north"], "East (m)": traj["east"], "VS (m)": traj["vs"], "DLS (°/30 m)": traj["dls"]}).round(2)
    st.dataframe(df, hide_index=True, use_container_width=True, height=300)
    d1, d2 = st.columns(2)
    d1.download_button("Download survey CSV", df.to_csv(index=False).encode(), f"{p['header']['well_name']}_plan.csv",
                       "text/csv", key=state.key("tj", "dl"))
    if d2.button("Copy plan into survey table (for manual editing)", key=state.key("tj", "copy")):
        state.set_table("survey_table", ["survey_table"], [{"md": float(m), "inc": float(i), "azi": float(z)} for m, i, z in zip(traj["md"], traj["inc"], traj["azi"])])
        p["plan"]["type"] = "Survey table"
        state.bump()
        st.rerun()
