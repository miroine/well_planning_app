"""Project model: default (anonymised) project, conversion of project data
into engine inputs, cross-module calculations and engineering checks.

Streamlit-free so it can be tested headless. Project depths are stored in
metres (MD/TVD from RKB), everything else in field units + USD; conversion
to feet happens here, at the engine boundary.
"""
from __future__ import annotations

import copy
import json

import numpy as np

from ks_engine import bha as bha_eng
from ks_engine import casing as cas_eng
from ks_engine import cost as cost_eng
from ks_engine import geomech as geo_eng
from ks_engine import hydraulics as hy_eng
from ks_engine import torque_drag as td_eng
from ks_engine import trajectory as tj
from ks_engine import well_control as wc_eng
from ks_engine.units import FT2M, M2FT, PSI_PER_FT_PER_PPG

APP_NAME = "Kestrel"
SCHEMA_VERSION = 1

PLAN_TYPES = ["Build & hold (J)", "S-type", "Horizontal", "Vertical", "Survey table"]

# ---------------------------------------------------------------------------
# Default project (anonymised example: "Well A-1", offshore, Field A)
# ---------------------------------------------------------------------------
DEFAULT_PROJECT = {
    "schema": SCHEMA_VERSION,
    "header": {"well_name": "Well A-1", "field": "Field A", "rig": "Rig 1", "operator": "Operator",
               "rkb_elev_m": 25.0, "water_depth_m": 110.0, "surface_n": 0.0, "surface_e": 0.0,
               "vs_azimuth": 45.0, "spud_date": "2026-11-01"},
    "plan": {"type": "Build & hold (J)", "kop_m": 500.0, "bur": 2.5, "dor": 2.0, "target_tvd_m": 2700.0,
             "target_disp_m": 1100.0, "azimuth": 45.0, "end_inc": 0.0, "landing_tvd_m": 2600.0,
             "lateral_m": 800.0, "step_m": 30.0, "extend_m": 150.0},
    "survey_table": [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 500.0, "inc": 0.0, "azi": 45.0},
                     {"md": 1000.0, "inc": 20.0, "azi": 45.0}, {"md": 3000.0, "inc": 30.0, "azi": 45.0}],
    "actual_survey": [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.3, "azi": 110.0},
                      {"md": 600.0, "inc": 5.1, "azi": 47.0}, {"md": 900.0, "inc": 13.6, "azi": 44.0},
                      {"md": 1200.0, "inc": 22.4, "azi": 45.5}, {"md": 1500.0, "inc": 25.9, "azi": 46.0}],
    "targets": [{"name": "Reservoir target", "tvd": 2700.0, "north": 777.8, "east": 777.8, "radius": 50.0}],
    "offset_wells": [
        {"name": "Well A-2", "surface_n": 15.0, "surface_e": -10.0, "kop": 400.0, "bur": 2.0, "hold_inc": 35.0, "azimuth": 20.0, "td": 3000.0},
        {"name": "Well A-3", "surface_n": -12.0, "surface_e": 18.0, "kop": 700.0, "bur": 3.0, "hold_inc": 25.0, "azimuth": 70.0, "td": 2800.0},
    ],
    "formations": [
        {"name": "Nordland", "top_tvd": 135.0, "lithology": "Clay", "rho": 1.95, "pp": 8.7, "nu": 0.40, "ucs": 800.0, "phi": 20.0, "dt": 150.0, "dt_n": 150.0},
        {"name": "Hordaland", "top_tvd": 800.0, "lithology": "Claystone", "rho": 2.15, "pp": 9.0, "nu": 0.35, "ucs": 2500.0, "phi": 24.0, "dt": 118.0, "dt_n": 120.0},
        {"name": "Rogaland", "top_tvd": 1700.0, "lithology": "Shale", "rho": 2.30, "pp": 10.6, "nu": 0.30, "ucs": 5000.0, "phi": 28.0, "dt": 102.0, "dt_n": 95.0},
        {"name": "Shetland", "top_tvd": 2250.0, "lithology": "Chalk / marl", "rho": 2.40, "pp": 11.2, "nu": 0.27, "ucs": 7000.0, "phi": 30.0, "dt": 88.0, "dt_n": 85.0},
        {"name": "Reservoir", "top_tvd": 2650.0, "lithology": "Sandstone", "rho": 2.35, "pp": 10.4, "nu": 0.25, "ucs": 6000.0, "phi": 32.0, "dt": 85.0, "dt_n": 82.0},
    ],
    "casing": [
        {"name": "Conductor 30\"", "od": 30.0, "wall": 1.0, "grade": "K-55", "top_md": 135.0, "shoe_md": 200.0, "hole_in": 36.0, "toc_md": 135.0, "lot_emw": 9.5, "mud_ppg": 8.6, "next_pore_ppg": 8.8},
        {"name": "Surface 20\"", "od": 20.0, "wall": 0.635, "grade": "K-55", "top_md": 135.0, "shoe_md": 800.0, "hole_in": 26.0, "toc_md": 135.0, "lot_emw": 12.5, "mud_ppg": 9.5, "next_pore_ppg": 9.2},
        {"name": "Intermediate 13-3/8\"", "od": 13.375, "wall": 0.480, "grade": "N-80", "top_md": 135.0, "shoe_md": 1700.0, "hole_in": 17.5, "toc_md": 1000.0, "lot_emw": 14.8, "mud_ppg": 11.0, "next_pore_ppg": 11.2},
        {"name": "Production 9-5/8\"", "od": 9.625, "wall": 0.472, "grade": "P-110", "top_md": 135.0, "shoe_md": 2600.0, "hole_in": 12.25, "toc_md": 1900.0, "lot_emw": 15.2, "mud_ppg": 11.6, "next_pore_ppg": 11.2},
    ],
    "bit": {"size_in": 8.5, "type": "PDC", "nozzles": "14,14,14,14,14"},
    "drillstring": [
        {"name": "Bit 8-1/2\" PDC", "od": 8.5, "id": 2.0, "tj_od": 8.5, "weight": 120.0, "length_m": 0.3, "tensile_yield": 0.0, "mu_torque": 0.0, "in_bha": True},
        {"name": "RSS 6-3/4\"", "od": 6.75, "id": 2.25, "tj_od": 6.75, "weight": 105.0, "length_m": 8.0, "tensile_yield": 1000000.0, "mu_torque": 35000.0, "in_bha": True},
        {"name": "MWD/LWD 6-3/4\"", "od": 6.75, "id": 2.25, "tj_od": 6.75, "weight": 100.0, "length_m": 18.0, "tensile_yield": 1000000.0, "mu_torque": 35000.0, "in_bha": True},
        {"name": "Drill collars 6-1/2\"", "od": 6.5, "id": 2.8125, "tj_od": 6.5, "weight": 91.0, "length_m": 56.0, "tensile_yield": 1000000.0, "mu_torque": 30000.0, "in_bha": True},
        {"name": "Hydraulic jar 6-1/2\"", "od": 6.5, "id": 2.75, "tj_od": 6.5, "weight": 90.0, "length_m": 10.0, "tensile_yield": 800000.0, "mu_torque": 30000.0, "in_bha": True},
        {"name": "HWDP 5\"", "od": 5.0, "id": 3.0, "tj_od": 6.5, "weight": 49.3, "length_m": 140.0, "tensile_yield": 691000.0, "mu_torque": 29400.0, "in_bha": True},
        {"name": "Drill pipe 5\" 19.5# G-105", "od": 5.0, "id": 4.276, "tj_od": 6.625, "weight": 22.6, "length_m": 5000.0, "tensile_yield": 553800.0, "mu_torque": 29400.0, "in_bha": False},
    ],
    "stabilizers_m": [1.5, 12.0, 30.0],
    "fluid": {"mud_ppg": 11.6, "r600": 62.0, "r300": 40.0, "r200": 31.0, "r100": 22.0, "r6": 8.0, "r3": 6.0,
              "model": "power_law", "cuttings_sg": 2.6, "transport_ratio": 0.7},
    "rig": {"block_weight_klbf": 60.0, "hookload_capacity_klbf": 750.0, "top_drive_torque": 45000.0,
            "pump_rating_psi": 5000.0, "max_flow_gpm": 1200.0, "pump_output_bbl_stk": 0.1,
            "surface_loss_psi": 120.0, "tool_loss_psi": 450.0},
    "opcase": {"operation": "drill_rotate", "bit_md_m": 3000.0, "wob_lb": 15000.0, "bit_torque": 8000.0,
               "rpm": 120.0, "trip_speed_mmin": 15.0, "flow_gpm": 550.0, "rop_mhr": 20.0,
               "ff_cased": 0.20, "ff_open": 0.30, "closed_end": True},
    "limits": {"max_dls": 4.0, "min_sf": 1.5, "tension_df": 1.1, "hookload_derate": 0.9,
               "anticol_r0": 0.5, "anticol_growth": 5.0, "burst_df": 1.1, "collapse_df": 1.0,
               "tension_df_casing": 1.6, "surge_margin_ppg": 0.2, "trip_margin_ppg": 0.2,
               "wob_df": 1.15},
    "geomech": {"shmax_ratio": 1.05, "use_eaton_sonic": False, "normal_ppg": 8.7},
    "well_control": {"sidpp": 350.0, "sicp": 520.0, "pit_gain": 15.0, "scr_psi": 650.0, "scr_spm": 30.0,
                     "margin_ppg": 0.0, "kick_intensity_ppg": 0.5, "safety_psi": 0.0,
                     "migration_psi": 120.0, "migration_hr": 0.5, "working_psi": 100.0},
    "cementing": {"shoe_track_m": 25.0, "excess_oh": 0.3, "tail_length_m": 150.0, "lead_yield": 2.1,
                  "tail_yield": 1.18, "lead_ppg": 13.5, "tail_ppg": 15.8, "spacer_ppg": 12.8,
                  "lead_water": 11.5, "tail_water": 5.2},
    "cost": {
        "rig_rate": 320000.0, "spread_rate": 180000.0, "mob_cost": 1500000.0, "mob_days": 3.0,
        "sections": [
            {"name": "36\" conductor", "hole_in": 36.0, "top_md": 135.0, "bottom_md": 200.0, "rop": 15.0, "trip_speed": 400.0, "casing_speed": 100.0, "bits": 1, "circ_hr": 2.0, "logging_hr": 0.0, "cement_hr": 6.0, "woc_hr": 8.0, "bop_hr": 0.0, "npt_pct": 8.0, "bit_cost": 25000.0, "mud_cost_per_len": 150.0, "casing_cost_per_len": 2800.0, "cement_cost": 60000.0, "logging_cost": 0.0, "other_cost": 50000.0},
            {"name": "26\" surface", "hole_in": 26.0, "top_md": 200.0, "bottom_md": 800.0, "rop": 40.0, "trip_speed": 400.0, "casing_speed": 150.0, "bits": 1, "circ_hr": 3.0, "logging_hr": 0.0, "cement_hr": 8.0, "woc_hr": 8.0, "bop_hr": 24.0, "npt_pct": 8.0, "bit_cost": 40000.0, "mud_cost_per_len": 180.0, "casing_cost_per_len": 950.0, "cement_cost": 90000.0, "logging_cost": 0.0, "other_cost": 120000.0},
            {"name": "17-1/2\" intermediate", "hole_in": 17.5, "top_md": 800.0, "bottom_md": 1700.0, "rop": 30.0, "trip_speed": 350.0, "casing_speed": 200.0, "bits": 1, "circ_hr": 4.0, "logging_hr": 12.0, "cement_hr": 8.0, "woc_hr": 12.0, "bop_hr": 12.0, "npt_pct": 10.0, "bit_cost": 60000.0, "mud_cost_per_len": 250.0, "casing_cost_per_len": 420.0, "cement_cost": 120000.0, "logging_cost": 250000.0, "other_cost": 150000.0},
            {"name": "12-1/4\" production", "hole_in": 12.25, "top_md": 1700.0, "bottom_md": 2600.0, "rop": 22.0, "trip_speed": 300.0, "casing_speed": 220.0, "bits": 2, "circ_hr": 6.0, "logging_hr": 18.0, "cement_hr": 10.0, "woc_hr": 12.0, "bop_hr": 12.0, "npt_pct": 12.0, "bit_cost": 90000.0, "mud_cost_per_len": 320.0, "casing_cost_per_len": 260.0, "cement_cost": 140000.0, "logging_cost": 400000.0, "other_cost": 200000.0},
            {"name": "8-1/2\" reservoir", "hole_in": 8.5, "top_md": 2600.0, "bottom_md": 3150.0, "rop": 18.0, "trip_speed": 300.0, "casing_speed": 250.0, "bits": 1, "circ_hr": 6.0, "logging_hr": 30.0, "cement_hr": 10.0, "woc_hr": 12.0, "bop_hr": 0.0, "npt_pct": 12.0, "bit_cost": 110000.0, "mud_cost_per_len": 380.0, "casing_cost_per_len": 180.0, "cement_cost": 110000.0, "logging_cost": 900000.0, "other_cost": 250000.0},
        ],
        "mc_rop": [0.7, 1.0, 1.25], "mc_npt": [0.5, 1.0, 2.5], "mc_rate": [0.95, 1.0, 1.1], "mc_n": 2000,
    },
}


def new_project():
    return copy.deepcopy(DEFAULT_PROJECT)


def project_to_json(p):
    return json.dumps(p, indent=2, default=float)


def project_from_json(text):
    data = json.loads(text)
    if not isinstance(data, dict) or "header" not in data:
        raise ValueError("File is not a Kestrel project (missing header)")
    base = new_project()
    # forward-compatible merge: keep defaults for any missing keys
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def section_key(p, *keys):
    """Deterministic cache key (md5 of JSON) for a subset of the project."""
    import hashlib
    blob = json.dumps({k: p.get(k) for k in keys}, sort_keys=True, default=float)
    return hashlib.md5(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Trajectory
# ---------------------------------------------------------------------------
def build_plan(p):
    pl = p["plan"]
    t = pl["type"]
    step = max(float(pl.get("step_m", 30.0)), 1.0)
    if t == "Build & hold (J)":
        r = tj.plan_build_hold(pl["kop_m"], pl["bur"], pl["target_tvd_m"], pl["target_disp_m"],
                               pl["azimuth"], 30.0, step, pl.get("extend_m", 0.0))
    elif t == "S-type":
        r = tj.plan_s_type(pl["kop_m"], pl["bur"], pl["dor"], pl["target_tvd_m"], pl["target_disp_m"],
                           pl["azimuth"], pl.get("end_inc", 0.0), 0.0, 30.0, step)
    elif t == "Horizontal":
        r = tj.plan_horizontal(pl["landing_tvd_m"], pl["bur"], pl["lateral_m"], pl["azimuth"], course=30.0, step=step)
    elif t == "Vertical":
        r = tj.plan_vertical(pl["target_tvd_m"] + pl.get("extend_m", 0.0), step)
    else:
        rows = sorted(p["survey_table"], key=lambda x: x["md"])
        md = np.array([float(x["md"]) for x in rows])
        if len(md) == 0 or md[0] > 0:
            md = np.concatenate([[0.0], md])
            rows = [{"md": 0.0, "inc": 0.0, "azi": 0.0}] + rows
        r = tj.PlanResult(md, np.array([float(x["inc"]) for x in rows]),
                          np.array([float(x["azi"]) for x in rows]), True, "Survey table", {})
    return r


def trajectory_m(p):
    """Planned trajectory in metres (from RKB, local N/E relative to slot)."""
    plan = build_plan(p)
    if not plan.feasible:
        return None, plan
    h = p["header"]
    t = tj.minimum_curvature(plan.md, plan.inc, plan.azi, 0.0, h["surface_n"], h["surface_e"], 30.0)
    t["vs"] = tj.vertical_section(t["north"], t["east"], h["vs_azimuth"], h["surface_n"], h["surface_e"])
    return t, plan


def actual_trajectory_m(p):
    rows = sorted([r for r in p.get("actual_survey", []) if r.get("md") is not None], key=lambda x: x["md"])
    if len(rows) < 2:
        return None
    md = [float(r["md"]) for r in rows]
    if len(set(md)) != len(md):
        return None
    h = p["header"]
    t = tj.minimum_curvature(md, [float(r["inc"]) for r in rows], [float(r["azi"]) for r in rows],
                             0.0, h["surface_n"], h["surface_e"], 30.0)
    t["vs"] = tj.vertical_section(t["north"], t["east"], h["vs_azimuth"], h["surface_n"], h["surface_e"])
    return t


def offset_trajectories_m(p):
    out = []
    for o in p.get("offset_wells", []):
        try:
            disp = 0.0
            r = tj.plan_vertical(float(o["td"]), 30.0) if float(o.get("hold_inc", 0)) <= 0 else None
            if r is None:
                kop, bur, inc = float(o["kop"]), max(float(o["bur"]), 0.1), float(o["hold_inc"])
                md_eob = kop + inc / bur * 30.0
                segs = [(0, kop, 0, 0), (kop, md_eob, 0, inc), (md_eob, max(float(o["td"]), md_eob + 1), inc, inc)]
                md, incs = tj._stations(segs, 30.0)
                r = tj.PlanResult(md, incs, np.full_like(md, float(o["azimuth"])), True, "", {})
            t = tj.minimum_curvature(r.md, r.inc, r.azi, 0.0, float(o["surface_n"]), float(o["surface_e"]))
            t["name"] = o["name"]
            out.append(t)
        except (ValueError, KeyError, TypeError):
            continue
        del disp
    return out


def anticollision(p, traj):
    lim = p["limits"]
    res = []
    for o in offset_trajectories_m(p):
        s = tj.separation_to_offset(traj, o, lim["anticol_r0"], lim["anticol_growth"])
        k = int(np.argmin(s["sf"]))
        res.append({"name": o["name"], "sep": s, "min_sf": float(s["sf"][k]), "at_md": float(s["md"][k]),
                    "min_ctc": float(np.min(s["ctc"]))})
    return res


def traj_ft(traj_m):
    return {k: (np.asarray(v) * M2FT if k in ("md", "tvd", "north", "east") else v)
            for k, v in traj_m.items() if k in ("md", "inc", "azi", "tvd", "north", "east", "dls")}


def tvd_at_md_m(traj, md_m):
    return float(tj.interpolate_at_md(traj, [md_m])["tvd"][0])


def inc_at_md(traj, md_m):
    return float(tj.interpolate_at_md(traj, [md_m])["inc"][0])


# ---------------------------------------------------------------------------
# Geometry: casing / hole / string
# ---------------------------------------------------------------------------
def casing_rows(p):
    rows = []
    for c in p.get("casing", []):
        try:
            r = cas_eng.ratings(float(c["od"]), float(c["wall"]), c["grade"])
        except (KeyError, ValueError, ZeroDivisionError, TypeError):
            continue
        rows.append({**c, **r, "weight_ppf": cas_eng.nominal_weight_ppf(float(c["od"]), float(c["wall"]))})
    return sorted(rows, key=lambda x: x["shoe_md"])


def deepest_shoe_above(p, md_m):
    shoes = [c for c in casing_rows(p) if c["shoe_md"] <= md_m + 1e-6]
    return max(shoes, key=lambda c: c["shoe_md"]) if shoes else None


def hole_id_at(p, md_m):
    """Innermost ID of casing covering md, else open-hole diameter."""
    cover = [c for c in casing_rows(p) if c["top_md"] - 1e-6 <= md_m <= c["shoe_md"] + 1e-6]
    if cover:
        return min(c["id"] for c in cover)
    deeper = [c for c in casing_rows(p) if c["shoe_md"] > md_m]
    if deeper:
        return min(deeper, key=lambda c: c["shoe_md"])["hole_in"]
    return float(p["bit"]["size_in"])


def annulus_sections_ft(p, bit_md_m):
    """(top_ft, bot_ft, hole_id) intervals from surface to bit.
    Above the shallowest casing top (riser/wellhead) use the first casing's ID."""
    cuts = {0.0, bit_md_m}
    for c in casing_rows(p):
        cuts.update([c["top_md"], c["shoe_md"]])
    cuts = sorted(x for x in cuts if 0 <= x <= bit_md_m)
    rows = casing_rows(p)
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        mid = 0.5 * (a + b)
        if rows and mid < min(c["top_md"] for c in rows):
            d = 19.5  # marine riser / wellhead housing above casing hangers
        else:
            d = hole_id_at(p, mid)
        out.append((a * M2FT, b * M2FT, d))
    return out


def string_components_ft(p):
    comps = []
    for c in p["drillstring"]:
        comps.append({"name": c["name"], "od": float(c["od"]), "id": float(c["id"]),
                      "tj_od": float(c.get("tj_od") or c["od"]), "weight": float(c["weight"]),
                      "length": float(c["length_m"]) * M2FT, "tensile_yield": float(c.get("tensile_yield") or 0),
                      "mu_torque": float(c.get("mu_torque") or 0), "in_bha": bool(c.get("in_bha", True))})
    return comps


def string_sections_ft(p, bit_md_m):
    """(top_ft, bot_ft, od, id) from surface to bit."""
    comps = string_components_ft(p)
    bit_ft = bit_md_m * M2FT
    out, bot = [], bit_ft
    for k, c in enumerate(comps):
        top = 0.0 if k == len(comps) - 1 else max(bot - c["length"], 0.0)
        if bot > top:
            out.append((top, bot, c["od"], c["id"]))
        bot = top
        if bot <= 0:
            break
    return sorted(out)


def bha_length_m(p):
    return sum(float(c["length_m"]) for c in p["drillstring"] if c.get("in_bha", True))


# ---------------------------------------------------------------------------
# Engine runs
# ---------------------------------------------------------------------------
def rheology(p):
    f = p["fluid"]
    return hy_eng.power_law_params(f["r600"], f["r300"], f["r100"], f["r3"])


def run_torque_drag(p, traj, operation=None, bit_md_m=None, ff_cased=None, ff_open=None, dl=30.0):
    oc = p["opcase"]
    op = operation or oc["operation"]
    bit_md = (bit_md_m if bit_md_m is not None else oc["bit_md_m"])
    shoe = deepest_shoe_above(p, bit_md)
    tf = traj_ft(traj)
    return td_eng.torque_drag(
        tf, string_components_ft(p), bit_md * M2FT, op, p["fluid"]["mud_ppg"],
        oc["ff_cased"] if ff_cased is None else ff_cased, oc["ff_open"] if ff_open is None else ff_open,
        (shoe["shoe_md"] if shoe else 0.0) * M2FT,
        wob=oc["wob_lb"], bit_torque=oc["bit_torque"], rpm=oc["rpm"],
        trip_speed_ftmin=oc["trip_speed_mmin"] * M2FT,
        block_weight=p["rig"]["block_weight_klbf"] * 1000.0,
        hole_id_func=lambda md_ft: np.array([hole_id_at(p, m * FT2M) for m in np.atleast_1d(md_ft)]),
        dl=dl)


def run_hydraulics(p, traj, flow_gpm=None, bit_md_m=None, rop_mhr=None, model=None):
    oc = p["opcase"]
    bit_md = oc["bit_md_m"] if bit_md_m is None else bit_md_m
    q = oc["flow_gpm"] if flow_gpm is None else flow_gpm
    rop = (oc["rop_mhr"] if rop_mhr is None else rop_mhr) * M2FT
    tvd_ft = lambda md_ft: tvd_at_md_m(traj, md_ft * FT2M) * M2FT
    shoe = deepest_shoe_above(p, bit_md)
    rh = rheology(p)
    return hy_eng.circulating_system(
        q, p["fluid"]["mud_ppg"], rh, string_sections_ft(p, bit_md), annulus_sections_ft(p, bit_md),
        bit_md * M2FT, tvd_ft, nozzles(p), model or p["fluid"]["model"], p["rig"]["surface_loss_psi"],
        p["rig"]["tool_loss_psi"], rop, p["fluid"]["cuttings_sg"], p["fluid"]["transport_ratio"],
        shoe["shoe_md"] * M2FT if shoe else None)


def run_surge_swab(p, traj, speed_mmin=None, bit_md_m=None):
    oc = p["opcase"]
    bit_md = oc["bit_md_m"] if bit_md_m is None else bit_md_m
    v = (oc["trip_speed_mmin"] if speed_mmin is None else speed_mmin) * M2FT
    tvd_ft = lambda md_ft: tvd_at_md_m(traj, md_ft * FT2M) * M2FT
    return hy_eng.surge_swab(v, p["fluid"]["mud_ppg"], rheology(p), string_sections_ft(p, bit_md),
                             annulus_sections_ft(p, bit_md), bit_md * M2FT, tvd_ft,
                             bool(oc.get("closed_end", True)), 0.45, p["fluid"]["model"])


def nozzles(p):
    out = []
    for tok in str(p["bit"]["nozzles"]).replace(";", ",").split(","):
        tok = tok.strip()
        if tok:
            try:
                out.append(float(tok))
            except ValueError:
                continue
    return out or [16.0]


def geomech_window(p, tvd_m_grid):
    layers = [{"top": float(f["top_tvd"]) * M2FT, "rho": float(f["rho"]), "pp": float(f["pp"]),
               "nu": float(f["nu"]), "ucs": float(f["ucs"]), "phi": float(f["phi"]),
               "dt": float(f.get("dt") or 100), "dt_n": float(f.get("dt_n") or 100)} for f in p["formations"]]
    if not layers:
        layers = [{"top": 0.0, "rho": 2.2, "pp": 8.7, "nu": 0.3, "ucs": 3000, "phi": 30}]
    g = p["geomech"]
    h = p["header"]
    w = geo_eng.mud_weight_window(np.asarray(tvd_m_grid) * M2FT, layers, h["water_depth_m"] * M2FT,
                                  h["rkb_elev_m"] * M2FT, g["shmax_ratio"], g["use_eaton_sonic"], g["normal_ppg"])
    w["tvd_m"] = np.asarray(tvd_m_grid)
    return w


def window_at_tvd(p, tvd_m):
    w = geomech_window(p, [max(tvd_m, 1.0)])
    return {k: float(v[0]) for k, v in w.items() if isinstance(v, np.ndarray)}


def formation_at_tvd(p, tvd_m):
    fs = sorted(p["formations"], key=lambda f: f["top_tvd"])
    cur = None
    for f in fs:
        if f["top_tvd"] <= tvd_m:
            cur = f
    return cur


# ---------------------------------------------------------------------------
# Engineering checks for the active operation case
# ---------------------------------------------------------------------------
def _chk(group, name, status, value, limit, note):
    return {"group": group, "check": name, "status": status, "value": value, "limit": limit, "note": note}


def operation_summary(p):
    """Run the active operation case across modules; returns metrics + checks."""
    traj, plan = trajectory_m(p)
    if traj is None:
        return {"error": plan.message}
    oc, rig, lim = p["opcase"], p["rig"], p["limits"]
    td_md = float(traj["md"][-1])
    bit_md = float(np.clip(oc["bit_md_m"], 1.0, td_md + p["plan"].get("extend_m", 0)))
    bit_tvd = tvd_at_md_m(traj, bit_md)
    inc_bit = inc_at_md(traj, bit_md)
    checks = []
    out = {"traj": traj, "plan": plan, "bit_md": bit_md, "bit_tvd": bit_tvd, "inc_bit": inc_bit}

    tdr = run_torque_drag(p, traj)
    out["td"] = tdr
    hook_cap = rig["hookload_capacity_klbf"] * 1000 * lim["hookload_derate"]
    po = run_torque_drag(p, traj, operation="trip_out")
    out["pickup"] = po
    checks.append(_chk("Torque & drag", "Hookload (active case)", "pass" if tdr["hookload"] <= hook_cap else "fail",
                       f"{tdr['hookload']/1000:,.1f} klbf", f"{hook_cap/1000:,.0f} klbf",
                       "Derated rig hookload capacity"))
    checks.append(_chk("Torque & drag", "Pick-up hookload at bit depth", "pass" if po["hookload"] <= hook_cap else "fail",
                       f"{po['hookload']/1000:,.1f} klbf", f"{hook_cap/1000:,.0f} klbf", "Tripping out, same friction factors"))
    tq_lim = min(rig["top_drive_torque"], min((c["mu_torque"] for c in p["drillstring"] if c.get("mu_torque")), default=1e12))
    s_tq = tdr["surface_torque"]
    checks.append(_chk("Torque & drag", "Surface torque", "pass" if s_tq <= 0.8 * tq_lim else ("warn" if s_tq <= tq_lim else "fail"),
                       f"{s_tq:,.0f} ft-lbf", f"{tq_lim:,.0f} ft-lbf", "Lower of top-drive limit and connection make-up torque (warn > 80%)"))
    tu = float(np.max(po["tension_utilisation"])) if len(po["tension_utilisation"]) else 0.0
    checks.append(_chk("Torque & drag", "String tension utilisation (pick-up)",
                       "pass" if tu * lim["tension_df"] <= 1.0 else "fail", f"{tu*100:.0f}% of yield",
                       f"{100/lim['tension_df']:.0f}%", f"Design factor {lim['tension_df']:.2f} on tensile yield"))
    bk = tdr["buckling"]
    status = "fail" if np.any(bk == "helical") else ("warn" if np.any(bk == "sinusoidal") else "pass")
    checks.append(_chk("Torque & drag", "Buckling", status,
                       "helical" if status == "fail" else ("sinusoidal" if status == "warn" else "none"),
                       "no helical", "Dawson-Paslay / Wu & Juvkam-Wold screening"))

    win_bit = window_at_tvd(p, bit_tvd)
    out["window_bit"] = win_bit
    shoe = deepest_shoe_above(p, bit_md)
    try:
        hyd = run_hydraulics(p, traj)
        out["hyd"] = hyd
        checks.append(_chk("Hydraulics", "Standpipe pressure", "pass" if hyd["spp"] <= 0.9 * rig["pump_rating_psi"] else ("warn" if hyd["spp"] <= rig["pump_rating_psi"] else "fail"),
                           f"{hyd['spp']:,.0f} psi", f"{rig['pump_rating_psi']:,.0f} psi", "Pump/manifold rating (warn > 90%)"))
        oh_top = shoe["shoe_md"] if shoe else 0.0
        oh = open_hole_window(p, traj, hyd, oh_top, bit_md)
        out["open_hole_window"] = oh
        checks.append(_chk("Hydraulics", "ECD vs fracture gradient (open hole)",
                           "pass" if oh["ecd_margin_min"] >= lim["surge_margin_ppg"] else ("warn" if oh["ecd_margin_min"] >= 0 else "fail"),
                           f"{oh['ecd_at_worst']:.2f} ppg", f"{oh['fg_at_worst']:.2f} ppg",
                           f"Tightest at {oh['worst_md']:.0f} mMD; margin {lim['surge_margin_ppg']} ppg"))
        if shoe and hyd.get("ecd_shoe"):
            checks.append(_chk("Hydraulics", "ECD at shoe vs LOT", "pass" if hyd["ecd_shoe"] <= shoe["lot_emw"] - lim["surge_margin_ppg"] else ("warn" if hyd["ecd_shoe"] <= shoe["lot_emw"] else "fail"),
                               f"{hyd['ecd_shoe']:.2f} ppg", f"{shoe['lot_emw']:.2f} ppg", shoe["name"]))
        mw = p["fluid"]["mud_ppg"]
        mw_min = oh["min_mw_max"]
        checks.append(_chk("Hydraulics", "Static MW vs pore / collapse (open hole)", "pass" if mw >= mw_min + lim["trip_margin_ppg"] else ("warn" if mw >= mw_min else "fail"),
                           f"{mw:.2f} ppg", f"{mw_min:.2f} ppg", f"Highest requirement at {oh['min_mw_md']:.0f} mMD; trip margin {lim['trip_margin_ppg']} ppg"))
        open_hole = [s for s in hyd["segments"] if s["md_bot"] * FT2M > (shoe["shoe_md"] if shoe else 0) and s["hole"] > s["od"] + 1e-6 and s["v_ftmin"] > 0]
        if open_hole and oc["flow_gpm"] > 0:
            av = min(s["v_ftmin"] for s in open_hole)
            need = hy_eng.min_annular_velocity_ftmin(inc_bit)
            checks.append(_chk("Hydraulics", "Hole cleaning (min open-hole AV)", "pass" if av >= need else "warn",
                               f"{av:.0f} ft/min", f"{need:.0f} ft/min", "Rule-of-thumb by inclination band"))
    except ValueError as exc:
        checks.append(_chk("Hydraulics", "Hydraulics model", "fail", "error", "-", str(exc)))

    try:
        sw = run_surge_swab(p, traj)
        out["surge"] = sw
        if oc["operation"] in ("trip_in", "ream_in"):
            checks.append(_chk("Tripping", "Surge EMW at bit", "pass" if sw["surge_emw"] <= win_bit["max_mw"] - lim["surge_margin_ppg"] else "fail",
                               f"{sw['surge_emw']:.2f} ppg", f"{win_bit['max_mw']:.2f} ppg", f"{oc['trip_speed_mmin']:.0f} m/min"))
        if oc["operation"] in ("trip_out", "ream_out"):
            checks.append(_chk("Tripping", "Swab EMW at bit", "pass" if sw["swab_emw"] >= win_bit["pp"] else "fail",
                               f"{sw['swab_emw']:.2f} ppg", f"{win_bit['pp']:.2f} ppg", f"{oc['trip_speed_mmin']:.0f} m/min"))
    except ValueError:
        pass

    max_dls = float(np.max(traj["dls"][traj["md"] <= bit_md])) if np.any(traj["md"] <= bit_md) else 0.0
    checks.append(_chk("Trajectory", "Max dogleg to bit", "pass" if max_dls <= lim["max_dls"] else "warn",
                       f"{max_dls:.2f} deg/30 m", f"{lim['max_dls']:.1f} deg/30 m", "Planned trajectory"))
    ac = anticollision(p, traj)
    out["anticollision"] = ac
    if ac:
        worst = min(ac, key=lambda a: a["min_sf"])
        checks.append(_chk("Trajectory", "Anti-collision separation factor",
                           "pass" if worst["min_sf"] >= lim["min_sf"] else ("warn" if worst["min_sf"] >= 1.0 else "fail"),
                           f"{worst['min_sf']:.2f} ({worst['name']})", f">= {lim['min_sf']:.2f}",
                           f"At {worst['at_md']:.0f} mMD; scalar cone model"))

    comps_ft = string_components_ft(p)
    wob_max = bha_eng.max_wob([c for c in comps_ft if c["in_bha"]], p["fluid"]["mud_ppg"], inc_bit, lim["wob_df"])
    out["wob_max"] = wob_max
    if oc["operation"] in ("drill_rotate", "slide"):
        checks.append(_chk("BHA", "WOB vs available BHA weight", "pass" if oc["wob_lb"] <= wob_max else "warn",
                           f"{oc['wob_lb']:,.0f} lb", f"{wob_max:,.0f} lb", "Neutral point in BHA, design factor applied"))
    string_len_ft = bit_md * M2FT
    k = 3.0 if p["bit"]["type"] == "Roller cone" else 1.0
    _, ax_rpm = bha_eng.axial_critical_rpm(string_len_ft, k)
    crit = [(float(r), f"axial mode {i+1}") for i, r in enumerate(ax_rpm)]
    for span, od, id_, w in stabilizer_spans(p):
        _, lat = bha_eng.lateral_critical_rpm(span * M2FT, od, id_, w, p["fluid"]["mud_ppg"])
        crit.append((float(lat[0]), f"lateral {span:.0f} m span"))
    out["critical_rpm"] = crit
    if oc["rpm"] > 0 and oc["operation"] in ("drill_rotate", "rotate_off", "ream_out", "ream_in"):
        hits = bha_eng.rpm_risk(oc["rpm"], crit)
        checks.append(_chk("BHA", "RPM vs critical speeds", "warn" if hits else "pass", f"{oc['rpm']:.0f} rpm",
                           "±15% band", ", ".join(f"{h[1]} {h[0]:.0f}" for h in hits) or "Clear of screened criticals"))

    if out.get("hyd"):
        out["hyd"].pop("ecd_profile", None)  # closures are not cacheable
    out["checks"] = checks
    out["hookload"] = tdr["hookload"]
    out["surface_torque"] = tdr["surface_torque"]
    out["spp"] = out.get("hyd", {}).get("spp") if out.get("hyd") else None
    out["ecd_bit"] = out.get("hyd", {}).get("ecd_bit") if out.get("hyd") else None
    return out


def open_hole_window(p, traj, hyd, top_md, bit_md, n=40):
    """ECD profile vs mud-weight window across the open-hole interval."""
    md = np.linspace(max(top_md, 1.0), bit_md, n)
    tvd = np.array([tvd_at_md_m(traj, m) for m in md])
    w = geomech_window(p, tvd)
    ecd = np.array([hyd["ecd_profile"](m * M2FT) for m in md])
    margin = w["max_mw"] - ecd
    k = int(np.argmin(margin))
    j = int(np.argmax(w["min_mw"]))
    return {"md": md, "tvd": tvd, "ecd": ecd, "window": w, "ecd_margin_min": float(margin[k]),
            "worst_md": float(md[k]), "ecd_at_worst": float(ecd[k]), "fg_at_worst": float(w["max_mw"][k]),
            "min_mw_max": float(w["min_mw"][j]), "min_mw_md": float(md[j])}


def stabilizer_spans(p):
    """Spans between stabilisers (m) with the dominant component properties."""
    pos = sorted(float(x) for x in p.get("stabilizers_m", []) if x is not None)
    if len(pos) < 2:
        return []
    spans = []
    for a, b in zip(pos[:-1], pos[1:]):
        mid = 0.5 * (a + b)
        cum = 0.0
        comp = p["drillstring"][-1]
        for c in p["drillstring"]:
            if cum <= mid < cum + float(c["length_m"]):
                comp = c
                break
            cum += float(c["length_m"])
        spans.append((b - a, float(comp["od"]), float(comp["id"]), float(comp["weight"])))
    return spans


def status_counts(checks):
    return {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "warn", "fail")}


# ---------------------------------------------------------------------------
# Convenience wrappers for other modules
# ---------------------------------------------------------------------------
def cost_plan(p):
    c = p["cost"]
    return cost_eng.plan_well(c["sections"], c["rig_rate"], c["spread_rate"], c["mob_cost"], c["mob_days"])


def cost_mc(p):
    c = p["cost"]
    return cost_eng.monte_carlo(c["sections"], c["rig_rate"], c["spread_rate"], c["mob_cost"], c["mob_days"],
                                tuple(c["mc_rop"]), tuple(c["mc_npt"]), tuple(c["mc_rate"]), int(c["mc_n"]))


def well_control_calc(p, traj):
    wcp, oc = p["well_control"], p["opcase"]
    mw = p["fluid"]["mud_ppg"]
    bit_md = oc["bit_md_m"]
    tvd_ft = tvd_at_md_m(traj, bit_md) * M2FT
    kmw = wc_eng.kill_mud_weight(mw, wcp["sidpp"], tvd_ft, wcp["margin_ppg"])
    ss = string_sections_ft(p, bit_md)
    md_nodes = [0.0]
    vol = [0.0]
    for top, bot, od, id_ in ss:
        md_nodes.append(bot)
        vol.append(vol[-1] + (bot - top) * id_ ** 2 / 1029.4)
    sched = wc_eng.kill_schedule(wcp["scr_psi"], wcp["sidpp"], mw, kmw, np.array(md_nodes), np.array(vol),
                                 lambda m: tvd_at_md_m(traj, m * FT2M) * M2FT, p["rig"]["pump_output_bbl_stk"])
    hole = hole_id_at(p, bit_md)
    bha_len_ft = bha_length_m(p) * M2FT
    bha_od = max((float(c["od"]) for c in p["drillstring"][1:] if c.get("in_bha", True)), default=6.5)
    dp_od = float(p["drillstring"][-1]["od"])
    cap_bha = max(hole ** 2 - bha_od ** 2, 1e-3) / 1029.4
    cap_dp = max(hole ** 2 - dp_od ** 2, 1e-3) / 1029.4
    shoe = deepest_shoe_above(p, bit_md)
    shoe_tvd_ft = tvd_at_md_m(traj, shoe["shoe_md"]) * M2FT if shoe else tvd_ft
    lot = shoe["lot_emw"] if shoe else window_at_tvd(p, tvd_ft * FT2M)["fg"]
    cap_shoe = max((shoe["id"] if shoe else hole) ** 2 - dp_od ** 2, 1e-3) / 1029.4
    inf = wc_eng.influx_gradient(mw, wcp["sidpp"], wcp["sicp"], wcp["pit_gain"], cap_bha, bha_len_ft, cap_dp)
    pore_td = window_at_tvd(p, tvd_ft * FT2M)["pp"]
    kt = wc_eng.kick_tolerance(mw, pore_td, tvd_ft, lot, shoe_tvd_ft, cap_bha, bha_len_ft, cap_dp, cap_shoe,
                               0.1, wcp["safety_psi"], wcp["kick_intensity_ppg"])
    maasp = wc_eng.maasp(lot, mw, shoe_tvd_ft)
    mig = wc_eng.gas_migration(wcp["migration_psi"], wcp["migration_hr"], mw)
    vol_steps = wc_eng.volumetric_steps(wcp["sicp"], mw, cap_dp, 100.0, wcp["working_psi"], maasp)
    return {"kmw": kmw, "schedule": sched, "influx": inf, "kick_tolerance": kt, "maasp": maasp,
            "migration_fthr": mig, "volumetric": vol_steps, "tvd_ft": tvd_ft, "shoe_tvd_ft": shoe_tvd_ft,
            "lot": lot, "pore_td": pore_td, "string_volume_bbl": vol[-1]}
