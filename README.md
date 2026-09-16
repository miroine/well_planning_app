# Kestrel: well engineering workbench

A Streamlit application for screening-level well design: trajectory planning, torque & drag, hydraulics, casing and cementing, geomechanics, well control, BHA dynamics and time & cost, all driven from one project file with live engineering checks.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens on an anonymised example offshore well (J-type, five casing strings, 8-1/2" PDC section) so every page has data from the first click. Save the project as JSON from the sidebar, edit it, and reload it later.

## Modules

| Page | What it does | Method |
|---|---|---|
| Well design studio | 3D / plan / section viewer with EOU cones and offset wells, operation case, live KPIs and all checks | Combines every module for the active case |
| Well schematic | Casing, cement, hole and string drawn to depth | |
| Well data | Header, formations, targets, actual survey import (CSV), offsets, drillstring, fluid, rig | |
| Trajectory & survey | J, S, horizontal, vertical or survey-table plans; DLS; target hit; anti-collision | Minimum curvature; scalar-cone separation factor |
| Torque & drag | Tension/torque for trip in/out, rotate, slide, ream; broomstick plots; buckling; friction calibration | Johancsik soft-string (SPE 11380); Dawson–Paslay / Wu–Juvkam-Wold buckling |
| Hydraulics & tripping | SPP breakdown, ECD vs window, flow-rate sweep, bit optimisation, hole cleaning, surge & swab | API RP 13D power law or Bingham; Burkhardt clinging constant |
| Casing & cementing | API ratings from OD/wall/grade, burst/collapse/tension design, cement volumes and placement EMW | API TR 5C3 (all four collapse regimes, validated against tables) |
| Geomechanics | Overburden, pore (direct or Eaton sonic), fracture, shear collapse and window per formation | Eaton 1969; Kirsch + Mohr-Coulomb, vertical well |
| Well control | Kill sheet (printable), influx type, MAASP, kick tolerance, gas migration, volumetric method | Wait & weight with deviated-well correction |
| BHA & vibration | Available WOB, neutral point, axial/torsional/lateral critical RPM against operating speed | Wave equation (fixed-free); pinned-pinned span with added mass |
| Time & cost | Section activity plan, time-depth curve, AFE build-up, P10/P50/P90 | Triangular Monte Carlo on ROP, NPT and rates |

The sidebar also exports a printable HTML engineering report (open it in a browser and print to PDF).

## Structure

```
app.py                 navigation, project save/load/reset, report download
ks_engine/             pure NumPy physics, field units internally, no Streamlit
ks_ui/model.py         default project, unit conversion, cross-module checks (no Streamlit)
ks_ui/state.py         session state, revision-keyed widgets, snapshot data editors
ks_ui/views/           one module per page
ks_ui/report.py        HTML report
tests/test_engine.py   66 analytic and published-table checks
tests/test_ui_smoke.py renders every page headless across 7 project scenarios
```

Run the tests with `python tests/test_engine.py` and `python tests/test_ui_smoke.py`, or `pytest tests/`. The UI smoke test uses built-in Streamlit/Plotly stand-ins when those packages are not installed; with them installed, check the UI with `streamlit run app.py`.

Widget state follows one rule: every widget key carries a project revision number, so opening or resetting a project rebuilds all inputs from the file instead of showing stale values.

## Deploy

Push the folder to a GitHub repository and deploy on Streamlit Community Cloud (share.streamlit.io) with `app.py` as the entry point.

## Limits

Screening tool. Soft-string T&D ignores string stiffness; stability assumes a vertical wellbore; casing loads are simplified single cases; vibration is linear screening, not BHA finite-element dynamics. Verify any operational decision with qualified engineers and approved software. Not affiliated with any operator or software vendor. MIT licence.
