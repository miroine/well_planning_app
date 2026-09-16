"""Engine validation suite: analytic limits and published reference values.

Run:  python tests/test_engine.py   (or pytest tests/)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ks_engine import bha, casing, cost, geomech, hydraulics as hy, torque_drag as td  # noqa: E402
from ks_engine import trajectory as tj, well_control as wc  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def close(a, b, rel=1e-3, abs_=1e-6):
    return abs(a - b) <= max(rel * abs(b), abs_)


# ---------------------------------------------------------------- trajectory
def test_trajectory():
    p = tj.plan_build_hold(500, 3, 2500, 800, 45)
    t = tj.minimum_curvature(p.md, p.inc, p.azi)
    x = tj.interpolate_at_md(t, [p.key_points["Target"]])
    check("J-type hits target TVD", close(x["tvd"][0], 2500, 1e-9, 1e-6))
    check("J-type hits target departure", close(np.hypot(x["north"][0], x["east"][0]), 800, 1e-9, 1e-6))
    check("J-type closure azimuth", close(tj.closure(x["north"][0], x["east"][0])[1], 45, 1e-9, 1e-6))
    R = 180 / np.pi * 30 / 3
    i = np.radians(p.key_points["hold_inc"])
    e = tj.interpolate_at_md(t, [p.key_points["EOB"]])
    check("Min curvature exact on circular arc (TVD)", abs(e["tvd"][0] - (500 + R * np.sin(i))) < 1e-6)
    check("Min curvature exact on circular arc (disp)", abs(np.hypot(e["north"][0], e["east"][0]) - R * (1 - np.cos(i))) < 1e-6)
    check("DLS in build = BUR", close(t["dls"][(t["md"] > 520) & (t["md"] < 720)].max(), 3.0, 1e-6))
    s = tj.plan_s_type(500, 2.5, 2, 3000, 900, 120)
    ts = tj.minimum_curvature(s.md, s.inc, s.azi)
    y = tj.interpolate_at_md(ts, [s.key_points["Target"]])
    check("S-type departure at target", abs(np.hypot(y["north"][0], y["east"][0]) - 900) < 0.05)
    check("S-type ends vertical", abs(ts["inc"][-1]) < 1e-6)
    h = tj.plan_horizontal(2500, 4, 1000, 90)
    th = tj.minimum_curvature(h.md, h.inc, h.azi)
    z = tj.interpolate_at_md(th, [h.key_points["Landing"]])
    check("Horizontal lands at TVD", abs(z["tvd"][0] - 2500) < 1e-6 and abs(z["inc"][0] - 90) < 1e-6)
    check("Unreachable J-target flagged", not tj.plan_build_hold(2400, 1, 2500, 3000, 0).feasible)
    # interpolation mid-arc reproduces a denser survey
    dense = tj.plan_build_hold(500, 3, 2500, 800, 45, step=1.0)
    td_ = tj.minimum_curvature(dense.md, dense.inc, dense.azi)
    q = tj.interpolate_at_md(t, [611.3])
    r = tj.interpolate_at_md(td_, [611.3])
    check("Arc interpolation matches dense survey", abs(q["tvd"][0] - r["tvd"][0]) < 1e-3 and abs(q["inc"][0] - r["inc"][0]) < 1e-6)
    off = {k: v + (50 if k == "east" else 0) for k, v in tj.minimum_curvature([0, 3000], [0, 0], [0, 0]).items()}
    off["md"] = np.array([0.0, 3000.0])
    ref = tj.minimum_curvature(tj.plan_vertical(3000).md, tj.plan_vertical(3000).inc, tj.plan_vertical(3000).azi)
    sep = tj.separation_to_offset(ref, off, r0=0, growth_per_1000=5)
    check("Parallel offset CtC = 50", np.allclose(sep["ctc"], 50, atol=1e-6))


# ----------------------------------------------------------- torque & drag
def _straight(inc, L=10000):
    return tj.minimum_curvature([0, L], [inc, inc], [0, 0])


DP = [{"name": "DP", "od": 5.0, "id": 4.276, "tj_od": 6.625, "weight": 21.9, "length": 1e9,
       "tensile_yield": 554000, "mu_torque": 30000}]


def test_torque_drag():
    t = _straight(0.0)
    bf = td.buoyancy_factor(10.0)
    for op in ("trip_out", "trip_in", "rotate_off"):
        r = td.torque_drag(t, DP, 10000, op, 10.0, 0.3, 0.3, 0, block_weight=50000)
        check(f"Vertical {op}: hookload = buoyed weight + blocks", close(r["hookload"], 21.9 * bf * 10000 + 50000, 1e-9))
    inc, mu, L = 60.0, 0.25, 10000
    t = _straight(inc, L)
    w = 21.9 * bf
    po = td.torque_drag(t, DP, L, "trip_out", 10.0, mu, mu, 0)["hookload"]
    so = td.torque_drag(t, DP, L, "trip_in", 10.0, mu, mu, 0)["hookload"]
    ro = td.torque_drag(t, DP, L, "rotate_off", 10.0, mu, mu, 0)
    s, c = np.sin(np.radians(inc)), np.cos(np.radians(inc))
    check("Straight inclined pick-up analytic", close(po, w * L * (c + mu * s), 1e-9))
    check("Straight inclined slack-off analytic", close(so, w * L * (c - mu * s), 1e-9))
    check("Straight inclined rotating torque analytic", close(ro["surface_torque"], mu * w * L * s * 6.625 / 24, 1e-9))
    dr = td.torque_drag(t, DP, L, "drill_rotate", 10.0, mu, mu, 0, wob=20000, bit_torque=5000)
    check("On-bottom: hookload drops by WOB", close(dr["hookload"], w * L * c - 20000, 1e-9))
    check("On-bottom: torque adds bit torque", dr["surface_torque"] > ro["surface_torque"] + 4999)
    ream = td.torque_drag(t, DP, L, "ream_out", 10.0, mu, mu, 0, rpm=120, trip_speed_ftmin=30)
    check("Back-reaming drag between rotate & pick-up", ro["hookload"] < ream["hookload"] < po)
    ff = td.calibrate_friction(t, DP, L, 10.0, 0, po, "trip_out", mu)
    check("Friction calibration recovers FF", ff is not None and abs(ff - mu) < 1e-3)
    fs, fh = td.critical_buckling(5.0, 4.276, w, 60.0, 8.5)
    I = np.pi / 64 * (5 ** 4 - 4.276 ** 4)
    ref = 2 * np.sqrt(30e6 * I * (w / 12) * s / 1.75)
    check("Dawson-Paslay critical load", close(float(fs), ref, 1e-9) and close(float(fh), ref * np.sqrt(2), 1e-9))


# ---------------------------------------------------------------- hydraulics
def test_hydraulics():
    b = hy.bit_hydraulics(400, 12.0, hy.tfa_from_nozzles([12, 12, 12]))
    check("TFA 3x12/32", close(hy.tfa_from_nozzles([12, 12, 12]), 0.3313, 1e-3))
    check("Bit dP 12 ppg 400 gpm 3x12 (~1611 psi)", abs(b["dp"] - 1611) < 5, f"{b['dp']:.0f}")
    rh = hy.power_law_params(60, 30, 10, 0.3)
    check("Newtonian readings give n=1", abs(rh["n_p"] - 1) < 1e-3)
    pl = hy.pipe_loss_power_law(50, 4.276, 1000, 10, rh["n_p"], rh["K_p"])
    bg = hy.pipe_loss_bingham(50, 4.276, 1000, 10, 30, 0)
    check("Power-law n=1 laminar == Newtonian Bingham", pl["regime"] == "laminar" and close(pl["dp"], bg["dp"], 1e-2), f"{pl['dp']:.3f} vs {bg['dp']:.3f}")
    pt = hy.pipe_loss_power_law(600, 4.276, 1000, 10, rh["n_p"], rh["K_p"])
    bt = hy.pipe_loss_bingham(600, 4.276, 1000, 10, 30, 0)
    check("Power-law n=1 turbulent ~ Blasius", pt["regime"] == "turbulent" and close(pt["dp"], bt["dp"], 3e-2), f"{pt['dp']:.1f} vs {bt['dp']:.1f}")
    al = hy.annulus_loss_power_law(50, 8.5, 5, 1000, 10, 1.0, 0.3)
    ab = hy.annulus_loss_bingham(50, 8.5, 5, 1000, 10, 30, 0)
    check("Annular power-law n=1 == slot Newtonian", close(al["dp"], ab["dp"], 1e-2), f"{al['dp']:.4f} vs {ab['dp']:.4f}")
    rh2 = hy.power_law_params(55, 35, 25, 6)
    tvd = lambda md: md
    ss = [(0, 9500, 5.0, 4.276), (9500, 10000, 6.5, 2.8125)]
    aa = [(0, 6000, 8.835), (6000, 10000, 8.5)]
    sys_ = hy.circulating_system(500, 10.0, rh2, ss, aa, 10000, tvd, [16, 16, 16], shoe_md=6000)
    check("ECD at bit > MW", sys_["ecd_bit"] > 10.0)
    check("ECD shoe < ECD bit", sys_["ecd_shoe"] < sys_["ecd_bit"])
    check("SPP = sum of components", close(sys_["spp"], sys_["string_dp"] + sys_["bit"]["dp"] + sys_["annulus_dp"], 1e-9))
    sw = hy.surge_swab(60, 10.0, rh2, ss, aa, 10000, tvd)
    check("Surge/swab symmetric about MW", close(sw["surge_emw"] - 10, 10 - sw["swab_emw"], 1e-9))
    vmax = hy.max_trip_speed(10.3, "surge", 10.0, rh2, ss, aa, 10000, tvd)
    check("Max trip speed reproduces limit", abs(hy.surge_swab(vmax, 10.0, rh2, ss, aa, 10000, tvd)["surge_emw"] - 10.3) < 1e-3)


# ------------------------------------------------------------------- casing
def test_casing():
    refs = [(9.625, 0.472, "P-110", 5300, 9440), (7.0, 0.408, "N-80", 7020, 8160),
            (13.375, 0.480, "K-55", 1950, 3450), (9.625, 0.395, "N-80", 3090, 5750),
            (5.5, 0.304, "N-80", 6280, 7740), (20.0, 0.438, "K-55", 520, 2110)]
    for od, t, g, c_ref, b_ref in refs:
        r = casing.ratings(od, t, g)
        check(f"API 5C3 collapse {od} {g} ({r['collapse_regime']})", abs(r["collapse"] - c_ref) <= 0.01 * c_ref, f"{r['collapse']:.0f}/{c_ref}")
        check(f"API 5C3 burst {od} {g}", abs(r["burst"] - b_ref) <= 0.005 * b_ref, f"{r['burst']:.0f}/{b_ref}")
    check("9-5/8 47# P-110 body yield 1,493 klbf", abs(casing.ratings(9.625, 0.472, "P-110")["body_yield"] / 1000 - 1493) < 3)
    cj = casing.cement_job(12.25, 9.625, 8.681, 8000, 6000, 12.415, 5000, shoe_track_ft=0,
                           excess_oh=0.0, tail_length_ft=0)
    ref = 2000 * (12.25 ** 2 - 9.625 ** 2) / 1029.4
    check("Cement annular volume (no excess)", close(cj["total_bbl"], ref, 1e-9))
    check("Displacement = casing capacity", close(cj["displacement_bbl"], 8000 * 8.681 ** 2 / 1029.4, 1e-9))


# ---------------------------------------------------------------- geomech
def test_geomech():
    sv = geomech.overburden([10000], [0], [2.3])
    check("Overburden constant density", close(sv[0], 0.4335 * 2.3 * 10000, 1e-3))
    check("Eaton frac nu=0.25", close(float(geomech.eaton_frac(19.0, 9.0, 0.25)), 9 + (10 / 3), 1e-9))
    check("Breakout: frictionless cohesionless isotropic => Pw = sigma", close(float(geomech.breakout_pressure(5000, 5000, 0, 0, 0)), 5000, 1e-9))
    check("Eaton sonic normal trend => normal PP", close(float(geomech.eaton_pore_sonic(19, 8.6, 100, 100)), 8.6, 1e-9))
    w = geomech.mud_weight_window(np.linspace(1000, 10000, 10), [
        {"top": 0, "rho": 2.2, "pp": 9.0, "nu": 0.3, "ucs": 3000, "phi": 30}])
    check("Window ordered pp <= fg <= obg", np.all(w["pp"] <= w["fg"]) and np.all(w["fg"] <= w["obg"]))


# ------------------------------------------------------------ well control
def test_well_control():
    kmw = wc.kill_mud_weight(10.0, 500, 10000)
    check("Kill mud weight", close(kmw, 10 + 500 / (0.051948 * 10000), 1e-9))
    icp, fcp = wc.icp_fcp(800, 500, 10, kmw)
    check("ICP/FCP", icp == 1300 and close(fcp, 800 * kmw / 10, 1e-9))
    md = np.linspace(0, 10000, 50)
    ks = wc.kill_schedule(800, 500, 10, kmw, md, md * 0.0178, lambda m: m, 0.1)
    check("Kill schedule starts at ICP, ends at FCP", close(ks["pressure"][0], icp, 1e-9) and close(ks["pressure"][-1], fcp, 1e-9))
    inf = wc.influx_gradient(10, 500, 700, 20, 0.0459, 600, 0.0459)
    check("Influx classified gas", inf["type"] == "gas", f"{inf['density_ppg']:.2f}")
    kt = wc.kick_tolerance(10, 10.2, 12000, 14.5, 8000, 0.0291, 600, 0.0459, 0.0505)
    check("Kick tolerance positive & finite", 0 < kt["volume_bbl"] < 1000, f"{kt['volume_bbl']:.1f}")
    check("MAASP", close(wc.maasp(14.5, 10, 8000), 4.5 * 0.051948 * 8000, 1e-9))


# --------------------------------------------------------------------- BHA
def test_bha():
    check("Axial wave speed ~16,840 ft/s", abs(bha.C_AXIAL - 16840) < 60, f"{bha.C_AXIAL:.0f}")
    comps = [{"name": "DC", "length": 600, "weight": 100.0}]
    np_, name = bha.neutral_point(comps, 10.0, 30000)
    check("Neutral point within collars", name == "DC" and close(np_, 30000 / (100 * td.buoyancy_factor(10)), 1e-9))
    f, rpm = bha.lateral_critical_rpm(60, 8, 2.8125, 150, 10)
    check("Lateral critical RPM physical range", 50 < rpm[0] < 2000, f"{rpm[0]:.0f}")


# -------------------------------------------------------------------- cost
def test_cost():
    sec = [{"name": "A", "hole_in": 12.25, "top_md": 0, "bottom_md": 1000, "rop": 10, "trip_speed": 500,
            "casing_speed": 250, "bits": 1, "circ_hr": 2, "logging_hr": 0, "cement_hr": 6, "woc_hr": 6,
            "bop_hr": 6, "npt_pct": 0, "bit_cost": 1000, "mud_cost_per_len": 10, "casing_cost_per_len": 100,
            "cement_cost": 5000, "logging_cost": 0, "other_cost": 0}]
    r = cost.plan_well(sec, 24000, 24000)
    hrs = 100 + 2 + 2 + 4 + 6 + 6 + 6
    check("Section hours", close(r["total_days"] * 24, hrs, 1e-9))
    check("AFE total", close(r["total_cost"], hrs / 24 * 48000 + 1000 + 10000 + 100000 + 5000, 1e-9))
    mc = cost.monte_carlo(sec, 24000, 24000, n=500)
    check("Monte Carlo P10<P50<P90", mc["cost_stats"]["P10"] < mc["cost_stats"]["P50"] < mc["cost_stats"]["P90"])


ALL = [test_trajectory, test_torque_drag, test_hydraulics, test_casing, test_geomech,
       test_well_control, test_bha, test_cost]


def test_all_pass():
    RESULTS.clear()
    for f in ALL:
        f()
    failed = [r for r in RESULTS if not r[1]]
    assert not failed, failed


if __name__ == "__main__":
    for f in ALL:
        f()
    for name, ok, detail in RESULTS:
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    n_fail = sum(1 for r in RESULTS if not r[1])
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} passed")
    sys.exit(1 if n_fail else 0)
