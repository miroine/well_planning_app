"""Well design studio: live KPIs, 3D/plan/section viewer, operation case and
engineering checks for the active case."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ks_engine.torque_drag import OPERATIONS
from ks_engine.units import FT2M

from .. import model, plots, state, theme
from ..compute import summary


def render():
    p = state.project()
    h = p["header"]
    st.markdown(theme.header_html("Well design studio", f"{h['well_name']}, {h['field']}, {h['rig']}"), unsafe_allow_html=True)
    res = summary(p)
    if "error" in res:
        st.error(f"Trajectory plan is not feasible: {res['error']}. Adjust it under Trajectory & survey.")
        return
    traj = res["traj"]
    st.markdown(theme.metrics_html([
        ("Hookload incl. blocks", f"{res['hookload']/1000:,.1f}", "klbf"),
        ("Surface torque", f"{res['surface_torque']/1000:,.1f}", "kft-lbf"),
        ("Standpipe pressure", f"{res['spp']:,.0f}" if res["spp"] is not None else "n/a", "psi"),
        ("Bit circulating ECD", f"{res['ecd_bit']:.2f}" if res["ecd_bit"] is not None else "n/a", "ppg"),
    ]), unsafe_allow_html=True)

    left, right = st.columns([2.1, 1], gap="medium")
    with left:
        view = st.radio("View", ["3D", "Plan view", "Vertical section"], horizontal=True,
                        key=state.key("studio", "view"), label_visibility="collapsed")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.4])
        show_eou = c1.checkbox("EOU", value=True, key=state.key("studio", "eou"))
        show_off = c2.checkbox("Offset wells", value=True, key=state.key("studio", "off"))
        show_act = c3.checkbox("Actual survey", value=True, key=state.key("studio", "act"))
        c4.caption("Imported or existing survey is drawn in amber")
        if view == "3D":
            fig = plots.well_3d(p, traj, res["bit_md"], show_eou, show_off, show_act, height=560)
            st.plotly_chart(fig, use_container_width=True, key=state.key("studio", "fig3d"))
            st.caption("Local N/E/TVD in metres from the slot; drag to rotate. EOU cone radius exaggerated 3x for visibility.")
        elif view == "Plan view":
            st.plotly_chart(plots.plan_view(p, traj, res["bit_md"], 560), use_container_width=True, key=state.key("studio", "plan"))
        else:
            st.plotly_chart(plots.section_view(p, traj, res["bit_md"], 560), use_container_width=True, key=state.key("studio", "vs"))

        st.subheader("Assembly position")
        st.caption(f"Bit at {res['bit_md']:,.0f} mMD, {res['bit_tvd']:,.0f} mTVD, {res['inc_bit']:.1f}° inclination")
        rows, bot = [], res["bit_md"]
        for k, c in enumerate(p["drillstring"]):
            top = max(bot - float(c["length_m"]), 0.0) if k < len(p["drillstring"]) - 1 else 0.0
            rows.append({"Component": c["name"], "Top (mMD)": round(top, 1), "Bottom (mMD)": round(bot, 1),
                         "Length (m)": round(bot - top, 1), "OD (in)": c["od"]})
            bot = top
            if bot <= 0:
                break
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with right:
        with st.form(key=state.key("opcase_form")):
            st.markdown("**Operation case**")
            oc = p["opcase"]
            ops = list(OPERATIONS.keys())
            a, b = st.columns(2)
            op = a.selectbox("Operation", ops, index=ops.index(oc["operation"]), format_func=lambda k: OPERATIONS[k])
            bit_md = b.number_input("Bit / shoe MD (m)", value=float(oc["bit_md_m"]), min_value=1.0, step=10.0)
            wob = a.number_input("WOB (lb)", value=float(oc["wob_lb"]), min_value=0.0, step=1000.0)
            btq = b.number_input("Bit torque (ft-lb)", value=float(oc["bit_torque"]), min_value=0.0, step=500.0)
            rpm = a.number_input("Rotation (RPM)", value=float(oc["rpm"]), min_value=0.0, step=10.0)
            trip = b.number_input("Tripping speed (m/min)", value=float(oc["trip_speed_mmin"]), min_value=0.0, step=1.0)
            q = a.number_input("Flow rate (gpm)", value=float(oc["flow_gpm"]), min_value=0.0, step=25.0)
            rop = b.number_input("ROP (m/hr)", value=float(oc["rop_mhr"]), min_value=0.0, step=1.0)
            ffc = a.number_input("FF cased", value=float(oc["ff_cased"]), min_value=0.0, max_value=1.0, step=0.01)
            ffo = b.number_input("FF open hole", value=float(oc["ff_open"]), min_value=0.0, max_value=1.0, step=0.01)
            st.caption("Inputs are saved with the project.")
            if st.form_submit_button("Apply operation case", type="primary", use_container_width=True):
                oc.update({"operation": op, "bit_md_m": bit_md, "wob_lb": wob, "bit_torque": btq, "rpm": rpm,
                           "trip_speed_mmin": trip, "flow_gpm": q, "rop_mhr": rop, "ff_cased": ffc, "ff_open": ffo})
                st.rerun()

        st.markdown("**Engineering checks**")
        cnt = model.status_counts(res["checks"])
        st.markdown(theme.note_html(f"Limits checked on the active case: {cnt['pass']} pass, {cnt['warn']} to review, {cnt['fail']} failing."),
                    unsafe_allow_html=True)
        order = {"fail": 0, "warn": 1, "pass": 2}
        for c in sorted(res["checks"], key=lambda c: order[c["status"]]):
            st.markdown(theme.check_html(c), unsafe_allow_html=True)

    td = res["td"]
    st.subheader("String loads along depth (active case)")
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, subplot_titles=("Effective tension (klbf)", "Torque (kft-lbf)"))
    md_m = td["md"] * FT2M
    fig.add_trace(go.Scatter(x=td["tension"] / 1000, y=md_m, line=dict(color=theme.MOSS), name="Tension"), 1, 1)
    fig.add_trace(go.Scatter(x=-td["f_sin"] / 1000, y=td["element_md"] * FT2M, line=dict(color=theme.AMBER, dash="dot"), name="Sinusoidal buckling limit"), 1, 1)
    fig.add_trace(go.Scatter(x=td["torque"] / 1000, y=md_m, line=dict(color=theme.NAVY), name="Torque"), 1, 2)
    theme.plotly_layout(fig, height=380)
    fig.update_yaxes(autorange="reversed", title="MD (m)", row=1, col=1)
    st.plotly_chart(fig, use_container_width=True, key=state.key("studio", "loads"))
