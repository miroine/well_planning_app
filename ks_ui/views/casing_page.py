"""04 Casing & cementing: program editor with API 5C3 ratings, burst /
collapse / tension design per string, cement volumes and placement ECD."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ks_engine import casing as cas
from ks_engine.units import FT2M, M2FT

from .. import model, state, theme

CC = st.column_config


def render():
    p = state.project()
    st.markdown(theme.header_html("Casing & cementing", "API TR 5C3 ratings, screening load cases, cement job design"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(plan.message)
        return
    st.subheader("Casing program")
    state.editor("casing", p["casing"],
                 ["name", "od", "wall", "grade", "top_md", "shoe_md", "hole_in", "toc_md", "lot_emw", "mud_ppg", "next_pore_ppg"],
                 {"name": CC.TextColumn("String"), "od": CC.NumberColumn("OD (in)", min_value=2.0, format="%.3f"),
                  "wall": CC.NumberColumn("Wall (in)", min_value=0.1, format="%.3f"),
                  "grade": CC.SelectboxColumn("Grade", options=list(cas.GRADES)),
                  "top_md": CC.NumberColumn("Top (mMD)", min_value=0.0), "shoe_md": CC.NumberColumn("Shoe (mMD)", min_value=1.0),
                  "hole_in": CC.NumberColumn("Hole (in)", min_value=2.0, format="%.3f"), "toc_md": CC.NumberColumn("TOC (mMD)", min_value=0.0),
                  "lot_emw": CC.NumberColumn("LOT/FIT (ppg)", format="%.2f"), "mud_ppg": CC.NumberColumn("Mud when run (ppg)", format="%.2f"),
                  "next_pore_ppg": CC.NumberColumn("Max pore next section (ppg)", format="%.2f")},
                 setter=lambda r: p.__setitem__("casing", sorted(r, key=lambda x: x["shoe_md"])),
                 dropna_cols=["od", "wall", "grade", "top_md", "shoe_md", "hole_in"])
    rows = model.casing_rows(p)
    if not rows:
        st.info("Add at least one casing string to run the design checks.")
        return
    st.dataframe(pd.DataFrame([{"String": r["name"], "ID (in)": round(r["id"], 3), "Plain-end weight (ppf)": round(r["weight_ppf"], 1),
                                "Burst (psi)": round(r["burst"], -1), "Collapse (psi)": round(r["collapse"], -1),
                                "Collapse regime": r["collapse_regime"], "Body yield (klbf)": round(r["body_yield"] / 1000, 0)} for r in rows]),
                 hide_index=True, use_container_width=True)

    a, b, c, d = st.columns(4)
    state.num("Burst design factor", "limits", "burst_df", a, step=0.05, min_value=1.0)
    state.num("Collapse design factor", "limits", "collapse_df", b, step=0.05, min_value=0.8)
    state.num("Tension design factor", "limits", "tension_df_casing", c, step=0.05, min_value=1.0)
    names = [r["name"] for r in rows]
    sel = d.selectbox("String to design", names, index=len(names) - 1, key=state.key("cas", "sel"))
    cs = rows[names.index(sel)]
    evac = a.slider("Collapse evacuation fraction", 0.0, 1.0, 1.0, 0.05, key=state.key("cas", "evac"),
                    help="1.0 = full evacuation; lower values model partial losses")
    gas_grad = b.number_input("Gas gradient (psi/ft)", value=0.1, min_value=0.0, step=0.01, key=state.key("cas", "gas"))
    backup = c.number_input("Burst backup gradient (ppg)", value=8.6, min_value=0.0, step=0.1, key=state.key("cas", "bk"))
    overpull = d.number_input("Overpull (klbf)", value=100.0, min_value=0.0, step=10.0, key=state.key("cas", "op"))

    shoe_tvd = model.tvd_at_md_m(traj, cs["shoe_md"]) * M2FT
    top_tvd = model.tvd_at_md_m(traj, cs["top_md"]) * M2FT
    deeper = [r for r in rows if r["shoe_md"] > cs["shoe_md"]]
    next_td_md = deeper[0]["shoe_md"] if deeper else float(traj["md"][-1])
    next_td_tvd = model.tvd_at_md_m(traj, next_td_md) * M2FT
    loads = cas.design_loads(shoe_tvd, top_tvd, cs["mud_ppg"], cs["next_pore_ppg"], next_td_tvd, gas_grad, backup, evac, cs["lot_emw"])
    ten = cas.tension_check(cs["weight_ppf"], (cs["shoe_md"] - cs["top_md"]) * M2FT, shoe_tvd - top_tvd, cs["mud_ppg"],
                            cs["body_yield"], overpull * 1000, 1.0, p["limits"]["tension_df_casing"])
    b_sf = cs["burst"] / max(loads["burst"].max(), 1)
    c_sf = cs["collapse"] / max(loads["collapse"].max(), 1)
    st.markdown(theme.metrics_html([
        ("Burst safety factor", f"{b_sf:.2f}", f"required {p['limits']['burst_df']:.2f}"),
        ("Collapse safety factor", f"{c_sf:.2f}", f"required {p['limits']['collapse_df']:.2f}"),
        ("Tension safety factor", f"{ten['sf']:.2f}", f"required {p['limits']['tension_df_casing']:.2f}"),
        ("Hanging load", f"{ten['load']/1000:,.0f}", "klbf incl. overpull"),
    ]), unsafe_allow_html=True)
    verdict = [("Burst", b_sf >= p["limits"]["burst_df"]), ("Collapse", c_sf >= p["limits"]["collapse_df"]), ("Tension", ten["sf"] >= p["limits"]["tension_df_casing"])]
    fails = [n for n, ok in verdict if not ok]
    if fails:
        st.error(f"{sel} does not meet the design factor for: {', '.join(fails)}. Increase wall thickness or grade.")
    else:
        st.success(f"{sel} meets all three design factors for the screening load cases.")

    fig = go.Figure()
    tvd_m = loads["tvd"] * FT2M
    fig.add_trace(go.Scatter(x=loads["burst"], y=tvd_m, name="Net burst load", line=dict(color=theme.RED)))
    fig.add_trace(go.Scatter(x=loads["collapse"], y=tvd_m, name="Net collapse load", line=dict(color="#3D7CC9")))
    fig.add_vline(x=cs["burst"] / p["limits"]["burst_df"], line=dict(color=theme.RED, dash="dash"), annotation_text="Burst rating / DF")
    fig.add_vline(x=cs["collapse"] / p["limits"]["collapse_df"], line=dict(color="#3D7CC9", dash="dash"), annotation_text="Collapse rating / DF", annotation_position="bottom right")
    theme.plotly_layout(fig, 400)
    fig.update_yaxes(autorange="reversed", title="TVD (m)")
    fig.update_xaxes(title="Pressure (psi)")
    st.plotly_chart(fig, use_container_width=True, key=state.key("cas", "load"))
    st.caption("Burst: gas to surface from next-section pore pressure, capped by shoe fracture pressure, external backup gradient. "
               "Collapse: internal evacuation with mud outside. Tension: buoyed weight + overpull. No biaxial or temperature derating.")

    st.subheader("Cement job")
    cm = p["cementing"]
    a, b, c, d = st.columns(4)
    state.num("Open-hole excess (fraction)", "cementing", "excess_oh", a, step=0.05, min_value=0.0)
    state.num("Shoe track (m)", "cementing", "shoe_track_m", b, step=1.0, min_value=0.0)
    state.num("Tail length (m)", "cementing", "tail_length_m", c, step=10.0, min_value=0.0)
    state.num("Spacer density (ppg)", "cementing", "spacer_ppg", d, step=0.1)
    state.num("Lead density (ppg)", "cementing", "lead_ppg", a, step=0.1)
    state.num("Tail density (ppg)", "cementing", "tail_ppg", b, step=0.1)
    state.num("Lead yield (ft³/sk)", "cementing", "lead_yield", c, step=0.05, min_value=0.5)
    state.num("Tail yield (ft³/sk)", "cementing", "tail_yield", d, step=0.05, min_value=0.5)
    shallower = [r for r in rows if r["shoe_md"] < cs["shoe_md"]]
    prev = shallower[-1] if shallower else None
    try:
        job = cas.cement_job(cs["hole_in"], cs["od"], cs["id"], cs["shoe_md"] * M2FT, (cs.get("toc_md") or cs["top_md"]) * M2FT,
                             prev["id"] if prev else cs["hole_in"], (prev["shoe_md"] if prev else 0.0) * M2FT,
                             cm["shoe_track_m"] * M2FT, cm["excess_oh"], cm["tail_length_m"] * M2FT, cm["lead_yield"], cm["tail_yield"],
                             cm["lead_water"], cm["tail_water"])
    except ValueError as exc:
        st.error(str(exc))
        return
    place = cas.cement_placement_ecd(shoe_tvd, model.tvd_at_md_m(traj, cs.get("toc_md") or cs["top_md"]) * M2FT,
                                     model.tvd_at_md_m(traj, job["tail_top_md"] * FT2M) * M2FT, cs["mud_ppg"], cm["spacer_ppg"],
                                     cm["lead_ppg"], cm["tail_ppg"])
    st.markdown(theme.metrics_html([
        ("Lead slurry", f"{job['lead_bbl']:,.0f}", f"bbl, {job['lead_sx']:,.0f} sx"),
        ("Tail slurry", f"{job['tail_bbl']:,.0f}", f"bbl, {job['tail_sx']:,.0f} sx"),
        ("Displacement", f"{job['displacement_bbl']:,.0f}", f"bbl, {job['displacement_bbl']/p['rig']['pump_output_bbl_stk']:,.0f} strokes"),
        ("Static EMW at shoe", f"{place['emw']:.2f}", f"ppg vs LOT above {prev['lot_emw'] if prev else float('nan'):.2f}" if prev else "ppg"),
    ]), unsafe_allow_html=True)
    st.caption(f"Mix water {job['mix_water_bbl']:,.0f} bbl. Lift pressure at plug bump ≈ {place['lift_pressure']:,.0f} psi (hydrostatic only, add circulating friction).")
    if prev:
        st.markdown(theme.note_html(f"Compare the end-of-job static EMW ({place['emw']:.2f} ppg) against the fracture gradient of the weakest open-hole zone below the {prev['name']} shoe."), unsafe_allow_html=True)
