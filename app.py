"""Kestrel well engineering workbench: Streamlit entry point.

Run:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Kestrel well engineering", page_icon="🛢️", layout="wide", initial_sidebar_state="expanded")

from ks_ui import model, report, state, theme  # noqa: E402
from ks_ui.compute import summary  # noqa: E402
from ks_ui.views import (bha_page, casing_page, cost_page, geomech_page, hydraulics_page, schematic,  # noqa: E402
                         studio, td_page, trajectory_page, well_data, wellcontrol_page)

NAV = [
    ("Overview", [("studio", "Well design studio", studio), ("schematic", "Well schematic", schematic), ("data", "Well data", well_data)]),
    ("Engineering", [("traj", "Trajectory & survey", trajectory_page), ("td", "Torque & drag", td_page),
                     ("hyd", "Hydraulics & tripping", hydraulics_page), ("casing", "Casing & cementing", casing_page),
                     ("geo", "Geomechanics", geomech_page), ("wc", "Well control", wellcontrol_page), ("bha", "BHA & vibration", bha_page)]),
    ("Planning", [("cost", "Time & cost", cost_page)]),
]
PAGES = {pid: (label, mod) for _, items in NAV for pid, label, mod in items}


def sidebar():
    with st.sidebar:
        st.markdown(theme.BRAND, unsafe_allow_html=True)
        p = state.project()
        res = summary(p)
        if "checks" in res:
            cnt = model.status_counts(res["checks"])
            st.caption(f"{p['header']['well_name']}: {cnt['pass']} pass · {cnt['warn']} check · {cnt['fail']} fail")
        for group, items in NAV:
            st.markdown(f'<div class="ks-group">{group}</div>', unsafe_allow_html=True)
            for pid, label, _ in items:
                active = st.session_state["ks_page"] == pid
                if st.button(label, key=f"nav_{pid}", type="primary" if active else "secondary", use_container_width=True):
                    st.session_state["ks_page"] = pid
                    st.rerun()
        st.markdown('<div class="ks-group">Project</div>', unsafe_allow_html=True)
        name = p["header"]["well_name"].replace(" ", "_")
        st.download_button("Save project (JSON)", model.project_to_json(p).encode(), f"{name}.kestrel.json", "application/json",
                           use_container_width=True, key="dl_project")
        st.download_button("Engineering report (HTML)", report.build(p).encode(), f"{name}_report.html", "text/html",
                           use_container_width=True, key="dl_report", help="Open in a browser and print to PDF")
        up = st.file_uploader("Open project", type=["json"], key=f"open_project_{state.rev()}", label_visibility="collapsed")
        if up is not None:
            try:
                new = model.project_from_json(up.getvalue().decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                st.error(f"Could not open project: {exc}")
            else:
                if st.button(f"Load {new['header']['well_name']}", key="load_project", use_container_width=True):
                    state.replace_project(new)
                    st.rerun()
        if st.button("Reset to example well", key="reset_project", use_container_width=True):
            state.replace_project(model.new_project())
            st.rerun()


def main():
    state.init()
    st.markdown(theme.CSS, unsafe_allow_html=True)
    sidebar()
    label, mod = PAGES.get(st.session_state["ks_page"], PAGES["studio"])
    mod.render()
    st.markdown(theme.FOOTER, unsafe_allow_html=True)


main()
