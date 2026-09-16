"""Headless smoke test: executes every page's render() against the default
project (and a round-tripped JSON copy) using stubbed Streamlit/Plotly, plus
the HTML report and kill sheet. Catches wiring, key and data-shape errors."""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "stubs"))

import _fake  # noqa: E402

STUBBED = _fake.install()

import streamlit as st  # noqa: E402

from ks_ui import model, report, state  # noqa: E402
from ks_ui.views import (bha_page, casing_page, cost_page, geomech_page, hydraulics_page, schematic, studio,  # noqa: E402
                         td_page, trajectory_page, well_data, wellcontrol_page)

PAGES = [studio, schematic, well_data, trajectory_page, td_page, hydraulics_page, casing_page, geomech_page,
         wellcontrol_page, bha_page, cost_page]


def run(label, project):
    st.session_state.clear()
    state.init()
    state.replace_project(project)
    fails = []
    for mod in PAGES:
        try:
            mod.render()
        except Exception:
            fails.append((mod.__name__, traceback.format_exc()))
    try:
        html = report.build(state.project())
        assert "<table>" in html and "Engineering checks" in html
    except Exception:
        fails.append(("report", traceback.format_exc()))
    return fails


def scenarios():
    base = model.new_project()
    yield "default", base
    yield "json round-trip", model.project_from_json(model.project_to_json(base))
    for plan_type in ["Vertical", "S-type", "Horizontal"]:
        p = model.new_project()
        p["plan"]["type"] = plan_type
        yield f"plan {plan_type}", p
    p = model.new_project()
    p["fluid"]["model"] = "bingham"
    p["bit"]["type"] = "Roller cone"
    p["opcase"]["operation"] = "trip_out"
    yield "bingham / roller cone / trip out", p
    p = model.new_project()
    p["opcase"]["bit_md_m"] = 900.0
    yield "shallow bit", p


def test_pages_render():
    if not STUBBED:
        return  # real Streamlit present: use `streamlit run app.py` instead
    all_fail = []
    for label, p in scenarios():
        all_fail += [(label, *f) for f in run(label, p)]
    assert not all_fail, "\n".join(f"[{a}] {b}\n{c}" for a, b, c in all_fail)


if __name__ == "__main__":
    if not STUBBED:
        print("Real Streamlit found; run `streamlit run app.py` for UI checks.")
        sys.exit(0)
    total = 0
    for label, p in scenarios():
        f = run(label, p)
        total += len(f)
        print(("OK   " if not f else "FAIL ") + label)
        for name, tb in f:
            print(f"  -- {name}\n{tb}")
    sys.exit(1 if total else 0)
