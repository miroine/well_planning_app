"""Well schematic view."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import model, plots, state, theme


def render():
    p = state.project()
    st.markdown(theme.header_html("Well schematic", "Casing program, cement, open hole, formations and the string at bit depth"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(f"Trajectory plan is not feasible: {plan.message}")
        return
    a, b = st.columns([1, 3])
    ref = a.radio("Depth reference", ["MD", "TVD"], horizontal=True, key=state.key("sch", "ref"))
    show_string = a.checkbox("Show string at bit depth", value=True, key=state.key("sch", "str"))
    a.caption("Grey fill is cement from TOC to shoe. Amber is BHA, blue-grey is drill pipe. Horizontal scale is radius in inches, not to depth scale.")
    rows = model.casing_rows(p)
    a.dataframe(pd.DataFrame([{"String": r["name"], "Shoe (mMD)": r["shoe_md"], "TVD (m)": round(model.tvd_at_md_m(traj, r["shoe_md"]), 0),
                               "LOT (ppg)": r["lot_emw"]} for r in rows]), hide_index=True, use_container_width=True)
    fig = plots.schematic(p, traj, p["opcase"]["bit_md_m"] if show_string else None, height=760, depth_ref=ref)
    b.plotly_chart(fig, use_container_width=True, key=state.key("sch", "fig"))
