"""Well control: kill sheet (wait & weight, deviated-well corrected),
influx identification, MAASP, kick tolerance and volumetric method.

Field units: psi, ppg, ft, bbl, strokes. Gas behaviour for kick tolerance
uses Boyle's law (isothermal, Z=1) - a screening simplification (IADC).
"""
from __future__ import annotations

import numpy as np

from .units import PSI_PER_FT_PER_PPG


def kill_mud_weight(omw, sidpp, tvd, margin_ppg=0.0):
    return omw + sidpp / (PSI_PER_FT_PER_PPG * tvd) + margin_ppg


def icp_fcp(scr_psi, sidpp, omw, kmw):
    return scr_psi + sidpp, scr_psi * kmw / omw


def influx_gradient(omw, sidpp, sicp, pit_gain_bbl, ann_cap_bha_bbl_ft, bha_len_ft,
                    ann_cap_dp_bbl_ft):
    """Influx density (ppg) from SICP-SIDPP and influx height."""
    v_bha = ann_cap_bha_bbl_ft * bha_len_ft
    if pit_gain_bbl <= v_bha:
        h = pit_gain_bbl / ann_cap_bha_bbl_ft
    else:
        h = bha_len_ft + (pit_gain_bbl - v_bha) / ann_cap_dp_bbl_ft
    rho = omw - (sicp - sidpp) / (PSI_PER_FT_PER_PPG * max(h, 1e-6))
    if rho < 3.0:
        kind = "gas"
    elif rho < 7.0:
        kind = "oil / gas-oil mixture"
    else:
        kind = "water / brine"
    return {"height_ft": h, "density_ppg": rho, "type": kind}


def maasp(lot_emw, mw, shoe_tvd):
    return (lot_emw - mw) * PSI_PER_FT_PER_PPG * shoe_tvd


def kill_schedule(scr_psi, sidpp, omw, kmw, string_md, string_cap_bbl, tvd_func,
                  pump_output_bbl_stk, n=25):
    """Drill-pipe pressure schedule vs strokes while KMW fills the string.

    string_md: array of MD (ft) along the string; string_cap_bbl: cumulative
    internal volume (bbl) from surface to each MD. Deviated-well correction:
    P(md) = SCR + (FCP - SCR) * V/Vbit + SIDPP - 0.052 (KMW - OMW) TVD(md)
    (friction term uses volume fraction, hydrostatic uses TVD).
    """
    icp, fcp = icp_fcp(scr_psi, sidpp, omw, kmw)
    md = np.linspace(0.0, string_md[-1], n)
    vol = np.interp(md, string_md, string_cap_bbl)
    vbit = string_cap_bbl[-1]
    tvd = np.array([tvd_func(m) for m in md])
    frac = vol / max(vbit, 1e-9)
    p = scr_psi + (fcp - scr_psi) * frac + sidpp - PSI_PER_FT_PER_PPG * (kmw - omw) * tvd
    p = np.maximum(p, fcp)
    strokes = vol / pump_output_bbl_stk
    p[-1] = fcp
    return {"md": md, "strokes": strokes, "pressure": p, "icp": icp, "fcp": fcp,
            "strokes_to_bit": vbit / pump_output_bbl_stk}


def kick_tolerance(mw, pore_ppg_td, td_tvd, lot_emw_shoe, shoe_tvd, ann_cap_bha, bha_len,
                   ann_cap_dp_oh, ann_cap_shoe, gas_grad=0.1, safety_psi=0.0,
                   kick_intensity_ppg=0.0):
    """Maximum influx volume (bbl at bottomhole) that can be circulated out
    without breaking down the shoe (IADC single-bubble method).

    Two limits: (A) influx height at bottom when shut in; (B) bubble at shoe.
    """
    g_mud = PSI_PER_FT_PER_PPG * mw
    pp = PSI_PER_FT_PER_PPG * (pore_ppg_td + kick_intensity_ppg) * td_tvd
    maasp_psi = maasp(lot_emw_shoe, mw, shoe_tvd) - safety_psi
    underbalance = pp - g_mud * td_tvd
    h_max = (maasp_psi - underbalance) / max(g_mud - gas_grad, 1e-6)
    if h_max <= 0:
        return {"volume_bbl": 0.0, "h_max_ft": h_max, "maasp": maasp_psi,
                "limit": "no tolerance - underbalance exceeds MAASP"}

    def vol_from_height(h):
        if h <= bha_len:
            return h * ann_cap_bha
        return bha_len * ann_cap_bha + (h - bha_len) * ann_cap_dp_oh

    v_bottom = vol_from_height(h_max)
    # bubble at shoe (top at shoe at frac pressure); Boyle back to bottom
    p_frac_shoe = PSI_PER_FT_PER_PPG * lot_emw_shoe * shoe_tvd - safety_psi
    v_shoe = h_max * ann_cap_shoe
    v_bottom_from_shoe = v_shoe * p_frac_shoe / max(pp, 1e-6)
    vol = min(v_bottom, v_bottom_from_shoe)
    limit = "bottom-hole shut-in" if v_bottom <= v_bottom_from_shoe else "bubble at shoe"
    return {"volume_bbl": max(vol, 0.0), "h_max_ft": h_max, "maasp": maasp_psi,
            "v_bottom": v_bottom, "v_shoe_limit": v_bottom_from_shoe, "limit": limit}


def gas_migration(pressure_rise_psi, hours, mw):
    """Migration velocity (ft/hr) from shut-in pressure build-up."""
    return pressure_rise_psi / max(hours, 1e-6) / (PSI_PER_FT_PER_PPG * mw)


def volumetric_steps(sicp, mw, ann_cap_top_bbl_ft, safety_psi=100.0, working_psi=100.0,
                     maasp_psi=None, n_steps=10):
    """Volumetric method bleed schedule: allow casing pressure to rise by
    safety + working, then bleed dV = working * Ca / (0.052 MW) per cycle."""
    dv = working_psi * ann_cap_top_bbl_ft / (PSI_PER_FT_PER_PPG * mw)
    rows = []
    p_hold = sicp + safety_psi + working_psi
    for k in range(n_steps):
        if maasp_psi is not None and p_hold > maasp_psi:
            break
        rows.append({"cycle": k + 1, "casing_pressure_hold_psi": p_hold,
                     "bleed_bbl": dv, "cumulative_bbl": dv * (k + 1)})
        p_hold += working_psi
    return rows
