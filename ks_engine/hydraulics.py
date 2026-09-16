"""Circulating hydraulics, ECD, bit hydraulics, hole cleaning and surge/swab.

Rheology models
* Power law per API RP 13D: n/K from Fann 600/300 (pipe) and 100/3
  (annulus); V in ft/min; Fanning f = 16/Re (pipe) or 24/Re (annulus, slot)
  laminar, a/Re^b turbulent, linear interpolation across the transition band.
* Bingham plastic per Bourgoyne et al. (1986), Applied Drilling Engineering,
  ch. 4 (laminar slot/pipe equations, Blasius turbulent).

Surge/swab: Burkhardt (1961) clinging-constant equivalent velocity.
Field units: Q gpm, D in, L ft, rho ppg, V ft/min (power law), psi.
"""
from __future__ import annotations

import numpy as np

from .units import PSI_PER_FT_PER_PPG


# --------------------------------------------------------------------------
# Rheology
# --------------------------------------------------------------------------
def power_law_params(r600, r300, r100, r3):
    if min(r600, r300, r100, r3) <= 0 or r600 <= r300 or r100 <= r3:
        raise ValueError("Fann readings must be positive and increasing with RPM")
    n_p = 3.32 * np.log10(r600 / r300)
    k_p = 5.11 * r300 / 511.0 ** n_p
    n_a = 0.657 * np.log10(r100 / r3)
    k_a = 5.11 * r100 / 170.2 ** n_a
    return {"n_p": n_p, "K_p": k_p, "n_a": n_a, "K_a": k_a,
            "PV": r600 - r300, "YP": 2 * r300 - r600}


def _fanning(re, n, laminar_c=16.0):
    """Fanning friction factor (API RP 13D): laminar C/Re (16 pipe, 24 slot/
    annulus), turbulent a/Re^b, linear interpolation in the transition band."""
    a = (np.log10(n) + 3.93) / 50.0
    b = (1.75 - np.log10(n)) / 7.0
    re_lam = 3470.0 - 1370.0 * n
    re_turb = 4270.0 - 1370.0 * n
    if re <= re_lam:
        return laminar_c / max(re, 1e-9), "laminar"
    f_turb = a / re ** b
    if re >= re_turb:
        return max(f_turb, laminar_c / re), "turbulent"
    f_l = laminar_c / re_lam
    f_t = a / re_turb ** b
    x = (re - re_lam) / (re_turb - re_lam)
    return f_l + x * (f_t - f_l), "transitional"


def pipe_loss_power_law(q_gpm, d_in, length_ft, rho, n, K):
    if q_gpm <= 0 or length_ft <= 0:
        return {"dp": 0.0, "v": 0.0, "re": 0.0, "regime": "static"}
    v = 24.51 * q_gpm / d_in ** 2
    mu = 100.0 * K * (1.6 * v / d_in) ** (n - 1.0) * ((3.0 * n + 1.0) / (4.0 * n)) ** n
    re = 15.467 * v * d_in * rho / mu
    f, regime = _fanning(re, n, 16.0)
    dp = f * v ** 2 * rho * length_ft / (92916.0 * d_in)
    return {"dp": dp, "v": v, "re": re, "regime": regime}


def annulus_loss_power_law(q_gpm, d_hole, d_pipe, length_ft, rho, n, K, v_override=None):
    dh = d_hole - d_pipe
    if length_ft <= 0 or dh <= 0:
        return {"dp": 0.0, "v": 0.0, "re": 0.0, "regime": "static"}
    v = v_override if v_override is not None else 24.51 * q_gpm / (d_hole ** 2 - d_pipe ** 2)
    if v <= 0:
        return {"dp": 0.0, "v": 0.0, "re": 0.0, "regime": "static"}
    mu = 100.0 * K * (2.4 * v / dh) ** (n - 1.0) * ((2.0 * n + 1.0) / (3.0 * n)) ** n
    re = 15.467 * v * dh * rho / mu
    f, regime = _fanning(re, n, 24.0)
    dp = f * v ** 2 * rho * length_ft / (92916.0 * dh)
    return {"dp": dp, "v": v, "re": re, "regime": regime}


def pipe_loss_bingham(q_gpm, d_in, length_ft, rho, pv, yp):
    if q_gpm <= 0 or length_ft <= 0:
        return {"dp": 0.0, "v": 0.0, "re": 0.0, "regime": "static"}
    v = q_gpm / (2.448 * d_in ** 2)  # ft/s
    mu_a = pv + 6.66 * yp * d_in / v
    re = 928.0 * rho * v * d_in / mu_a
    if re < 2100:
        g = pv * v / (1500.0 * d_in ** 2) + yp / (225.0 * d_in)
        regime = "laminar"
    else:
        g = rho ** 0.75 * v ** 1.75 * pv ** 0.25 / (1800.0 * d_in ** 1.25)
        regime = "turbulent"
    return {"dp": g * length_ft, "v": v * 60.0, "re": re, "regime": regime}


def annulus_loss_bingham(q_gpm, d_hole, d_pipe, length_ft, rho, pv, yp, v_override_ftmin=None):
    dh = d_hole - d_pipe
    if length_ft <= 0 or dh <= 0:
        return {"dp": 0.0, "v": 0.0, "re": 0.0, "regime": "static"}
    v = (v_override_ftmin / 60.0) if v_override_ftmin is not None else q_gpm / (2.448 * (d_hole ** 2 - d_pipe ** 2))
    if v <= 0:
        return {"dp": 0.0, "v": 0.0, "re": 0.0, "regime": "static"}
    mu_a = pv + 5.0 * yp * dh / v
    re = 757.0 * rho * v * dh / mu_a
    if re < 2100:
        g = pv * v / (1000.0 * dh ** 2) + yp / (200.0 * dh)
        regime = "laminar"
    else:
        g = rho ** 0.75 * v ** 1.75 * pv ** 0.25 / (1396.0 * dh ** 1.25)
        regime = "turbulent"
    return {"dp": g * length_ft, "v": v * 60.0, "re": re, "regime": regime}


# --------------------------------------------------------------------------
# Bit
# --------------------------------------------------------------------------
def tfa_from_nozzles(nozzles_32nds):
    return float(sum(np.pi / 4.0 * (n / 32.0) ** 2 for n in nozzles_32nds if n > 0))


def bit_hydraulics(q_gpm, rho, tfa_in2, cd=0.95):
    if tfa_in2 <= 0:
        raise ValueError("Total flow area must be positive")
    dp = 8.311e-5 * rho * q_gpm ** 2 / (cd ** 2 * tfa_in2 ** 2)
    vn = 0.3208 * q_gpm / tfa_in2
    hhp = dp * q_gpm / 1714.0
    impact = 0.01823 * cd * q_gpm * np.sqrt(rho * dp)
    return {"dp": dp, "nozzle_velocity_fts": vn, "hhp": hhp, "impact_force_lbf": impact}


# --------------------------------------------------------------------------
# Full circulating system
# --------------------------------------------------------------------------
def _segments(string_sections, annulus_sections, bit_md):
    """Intersect string component intervals with hole/casing intervals.

    string_sections: list of (md_top, md_bot, od, id)
    annulus_sections: list of (md_top, md_bot, hole_id)
    """
    cuts = {0.0, bit_md}
    for a, b, *_ in string_sections:
        cuts.update([a, b])
    for a, b, _ in annulus_sections:
        cuts.update([a, b])
    cuts = sorted(c for c in cuts if 0.0 <= c <= bit_md)
    segs = []
    for top, bot in zip(cuts[:-1], cuts[1:]):
        if bot - top <= 1e-6:
            continue
        mid = 0.5 * (top + bot)
        s = next((x for x in string_sections if x[0] <= mid <= x[1]), None)
        h = next((x for x in annulus_sections if x[0] <= mid <= x[1]), None)
        if s is None or h is None:
            continue
        segs.append({"md_top": top, "md_bot": bot, "od": s[2], "id": s[3], "hole": h[2]})
    return segs


def circulating_system(q_gpm, rho, rheo, string_sections, annulus_sections, bit_md,
                       tvd_func, nozzles_32nds, model="power_law", surface_loss_psi=0.0,
                       bha_tool_loss_psi=0.0, rop_fthr=0.0, cuttings_sg=2.6,
                       transport_ratio=0.7, shoe_md=None):
    """Pump pressure breakdown, ECD at bit and shoe, annular velocities.

    tvd_func: callable(md) -> TVD (ft).
    Cuttings loading (optional): volume fraction C = ROP*Dh^2/(1471*Q*Rt)
    added to annular density (Rt = transport ratio).
    """
    segs = _segments(string_sections, annulus_sections, bit_md)
    if not segs:
        raise ValueError("No overlapping string/hole geometry down to bit")
    string_dp, ann_rows = 0.0, []
    for sg in segs:
        L = sg["md_bot"] - sg["md_top"]
        if model == "power_law":
            p = pipe_loss_power_law(q_gpm, sg["id"], L, rho, rheo["n_p"], rheo["K_p"])
        else:
            p = pipe_loss_bingham(q_gpm, sg["id"], L, rho, rheo["PV"], rheo["YP"])
        string_dp += p["dp"]
        dh = sg["hole"]
        conc = 0.0
        if rop_fthr > 0 and q_gpm > 0:
            conc = min(rop_fthr * dh ** 2 / (1471.0 * q_gpm * max(transport_ratio, 0.05)), 0.15)
        rho_ann = rho * (1 - conc) + cuttings_sg * 8.3454 * conc
        if model == "power_law":
            a = annulus_loss_power_law(q_gpm, dh, sg["od"], L, rho_ann, rheo["n_a"], rheo["K_a"])
        else:
            a = annulus_loss_bingham(q_gpm, dh, sg["od"], L, rho_ann, rheo["PV"], rheo["YP"])
        ann_rows.append({**sg, "dp": a["dp"], "v_ftmin": a["v"], "re": a["re"],
                         "regime": a["regime"], "cuttings_conc": conc, "rho_ann": rho_ann,
                         "dtvd": tvd_func(sg["md_bot"]) - tvd_func(sg["md_top"])})
    bit = bit_hydraulics(q_gpm, rho, tfa_from_nozzles(nozzles_32nds))
    ann_dp = sum(r["dp"] for r in ann_rows)
    spp = surface_loss_psi + string_dp + bha_tool_loss_psi + bit["dp"] + ann_dp

    def ecd_at(md):
        tvd = tvd_func(md)
        p = 0.0
        for r in ann_rows:
            if r["md_top"] >= md:
                continue
            frac = min(1.0, (md - r["md_top"]) / (r["md_bot"] - r["md_top"]))
            p += r["dp"] * frac + PSI_PER_FT_PER_PPG * (r["rho_ann"] - rho) * r["dtvd"] * frac
        return rho + p / (PSI_PER_FT_PER_PPG * max(tvd, 1e-6))

    return {
        "segments": ann_rows,
        "surface_dp": surface_loss_psi,
        "string_dp": string_dp,
        "tool_dp": bha_tool_loss_psi,
        "bit": bit,
        "annulus_dp": ann_dp,
        "spp": spp,
        "ecd_bit": ecd_at(bit_md),
        "ecd_shoe": ecd_at(shoe_md) if shoe_md and 0 < shoe_md < bit_md else None,
        "ecd_profile": ecd_at,
        "bit_hhp_fraction": bit["dp"] / spp if spp > 0 else 0.0,
        "hhp_pump": spp * q_gpm / 1714.0,
    }


def optimum_flow_for_max(criterion, q_min, q_max, evaluate, n=60):
    """Scan flow rate for max bit HHP or impact force under a pump pressure cap.
    evaluate(q) -> (value, spp, within_limits)."""
    best = None
    for q in np.linspace(q_min, q_max, n):
        val, spp, ok = evaluate(q)
        if ok and (best is None or val > best[1]):
            best = (q, val, spp)
    return best


# --------------------------------------------------------------------------
# Hole cleaning
# --------------------------------------------------------------------------
def min_annular_velocity_ftmin(inc_deg):
    """Rule-of-thumb minimum AV by inclination band (industry guideline, not a
    transport model): 0-30 deg 120, 30-60 deg 150, >60 deg 180 ft/min."""
    if inc_deg < 30:
        return 120.0
    if inc_deg < 60:
        return 150.0
    return 180.0


# --------------------------------------------------------------------------
# Surge & swab
# --------------------------------------------------------------------------
def surge_swab(trip_speed_ftmin, rho, rheo, string_sections, annulus_sections, bit_md,
               tvd_func, closed_end=True, clinging=0.45, model="power_law"):
    """Surge (RIH) = +dp, swab (POOH) = -dp in annulus, Burkhardt equivalent
    velocity: V_eq = Vp*(Kc + d^2/(D^2-d^2)) closed end,
    V_eq = Vp*(Kc + (d^2-di^2)/(D^2-d^2)) open end."""
    segs = _segments(string_sections, annulus_sections, bit_md)
    dp_tot = 0.0
    rows = []
    for sg in segs:
        D, d, di = sg["hole"], sg["od"], sg["id"]
        L = sg["md_bot"] - sg["md_top"]
        disp = d ** 2 if closed_end else (d ** 2 - di ** 2)
        v_eq = trip_speed_ftmin * (clinging + disp / max(D ** 2 - d ** 2, 1e-6))
        if model == "power_law":
            a = annulus_loss_power_law(0.0, D, d, L, rho, rheo["n_a"], rheo["K_a"], v_override=v_eq)
        else:
            a = annulus_loss_bingham(0.0, D, d, L, rho, rheo["PV"], rheo["YP"], v_override_ftmin=v_eq)
        dp_tot += a["dp"]
        rows.append({**sg, "v_eq": v_eq, "dp": a["dp"]})
    tvd = tvd_func(bit_md)
    delta = dp_tot / (PSI_PER_FT_PER_PPG * max(tvd, 1e-6))
    return {"dp": dp_tot, "surge_emw": rho + delta, "swab_emw": rho - delta, "segments": rows}


def max_trip_speed(limit_emw, mode, rho, rheo, string_sections, annulus_sections, bit_md,
                   tvd_func, closed_end=True, clinging=0.45, v_hi=300.0):
    """Largest trip speed (ft/min) keeping surge <= limit (mode='surge') or
    swab >= limit (mode='swab')."""
    def ok(v):
        r = surge_swab(v, rho, rheo, string_sections, annulus_sections, bit_md, tvd_func,
                       closed_end, clinging)
        return r["surge_emw"] <= limit_emw if mode == "surge" else r["swab_emw"] >= limit_emw
    if not ok(1e-3):
        return 0.0
    if ok(v_hi):
        return v_hi
    lo, hi = 1e-3, v_hi
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo
