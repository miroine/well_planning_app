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


def test_project_input_validation():
    p = model.new_project()
    assert model.project_from_json(model.project_to_json(p))["header"] == p["header"]
    for text in (
        '{"header": [], "fluid": {}}',
        '{"header": {}, "fluid": {"mud_ppg": NaN}}',
        '{"header": {}, "offset_wells": ["not an object"]}',
    ):
        try:
            model.project_from_json(text)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid project data accepted: {text}")


def test_nozzle_validation():
    p = model.new_project()
    for value in ("14,broken,14", "", "0,14", "NaN,14"):
        p["bit"]["nozzles"] = value
        try:
            model.nozzles(p)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid nozzle string accepted: {value!r}")


def test_operation_summary_clamps_bit_depth():
    p = model.new_project()
    p["opcase"]["bit_md_m"] = 100000.0
    result = model.operation_summary(p)
    assert result["bit_md"] == result["traj"]["md"][-1]
    assert result["td"]["md"][0] == result["bit_md"] * 3.280839895
    assert max(segment["md_bot"] for segment in result["hyd"]["segments"]) <= result["bit_md"] * 3.280839895


def test_invalid_offsets_are_reported():
    p = model.new_project()
    p["offset_wells"].append({"name": "Bad offset", "hold_inc": "invalid"})
    errors = []
    model.anticollision(p, model.trajectory_m(p)[0], errors)
    assert errors and "Bad offset" in errors[0]


def test_report_can_reuse_summary(monkeypatch):
    monkeypatch.setattr(model, "operation_summary", lambda _p: (_ for _ in ()).throw(AssertionError("recomputed")))
    html = report.build(model.new_project(), {"error": "test"})
    assert "Trajectory not feasible: test" in html


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
