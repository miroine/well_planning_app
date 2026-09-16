"""Casing ratings (API TR 5C3 / Bull 5C3), design load cases and cementing.

Ratings computed from OD, wall thickness and minimum yield:
* Burst  : Barlow with 87.5% wall tolerance  P = 0.875 * 2 Yp t / D
* Collapse: API four-regime formula (yield / plastic / transition / elastic)
* Pipe body yield: Yp * pi/4 (D^2 - d^2)

Load cases are simplified screening cases (stated in UI):
* Burst  - gas kick to surface: internal = pore pressure at next-section TD
  minus gas gradient; external backup = pore gradient (or seawater/normal).
* Collapse - full/partial evacuation: internal = mud drop to evacuation
  level; external = mud gradient at time of running.
* Tension - buoyed hanging weight + overpull, and air weight x shock factor.
"""
from __future__ import annotations

import numpy as np

from .units import PSI_PER_FT_PER_PPG, STEEL_PPG

GRADES = {  # minimum yield strength, psi
    "H-40": 40000, "J-55": 55000, "K-55": 55000, "N-80": 80000, "L-80": 80000,
    "C-90": 90000, "T-95": 95000, "P-110": 110000, "Q-125": 125000,
}


def collapse_coefficients(yp):
    A = 2.8762 + 0.10679e-5 * yp + 0.21301e-10 * yp ** 2 - 0.53132e-16 * yp ** 3
    B = 0.026233 + 0.50609e-6 * yp
    C = -465.93 + 0.030867 * yp - 0.10483e-7 * yp ** 2 + 0.36989e-13 * yp ** 3
    ba = B / A
    x = 3.0 * ba / (2.0 + ba)
    F = 46.95e6 * x ** 3 / (yp * (x - ba) * (1.0 - x) ** 2)
    G = F * B / A
    return A, B, C, F, G


def api_collapse(od, wall, yp):
    A, B, C, F, G = collapse_coefficients(yp)
    dt = od / wall
    dt_yp = (np.sqrt((A - 2.0) ** 2 + 8.0 * (B + C / yp)) + (A - 2.0)) / (2.0 * (B + C / yp))
    dt_pt = yp * (A - F) / (C + yp * (B - G))
    dt_te = (2.0 + B / A) / (3.0 * B / A)
    if dt <= dt_yp:
        p = 2.0 * yp * ((dt - 1.0) / dt ** 2)
        regime = "yield"
    elif dt <= dt_pt:
        p = yp * (A / dt - B) - C
        regime = "plastic"
    elif dt <= dt_te:
        p = yp * (F / dt - G)
        regime = "transition"
    else:
        p = 46.95e6 / (dt * (dt - 1.0) ** 2)
        regime = "elastic"
    return float(p), regime


def api_burst(od, wall, yp, tolerance=0.875):
    return float(tolerance * 2.0 * yp * wall / od)


def body_yield(od, wall, yp):
    return float(yp * np.pi / 4.0 * (od ** 2 - (od - 2 * wall) ** 2))


def ratings(od, wall, grade):
    yp = GRADES[grade]
    col, regime = api_collapse(od, wall, yp)
    return {"burst": api_burst(od, wall, yp), "collapse": col, "collapse_regime": regime,
            "body_yield": body_yield(od, wall, yp), "id": od - 2 * wall, "yield": yp}


def nominal_weight_ppf(od, wall):
    """Plain-end weight (lb/ft) = 10.68 (D - t) t."""
    return 10.68 * (od - wall) * wall


def design_loads(shoe_tvd, top_tvd, mud_ppg, next_pore_ppg, next_td_tvd, gas_grad=0.1,
                 backup_ppg=8.6, evacuation_frac=1.0, frac_ppg_shoe=None, n=40):
    """Pressure profiles (psi) vs TVD for burst and collapse (net = in - out)."""
    tvd = np.linspace(top_tvd, shoe_tvd, n)
    p_res = PSI_PER_FT_PER_PPG * next_pore_ppg * next_td_tvd
    p_int_burst = p_res - gas_grad * (next_td_tvd - tvd)
    if frac_ppg_shoe:
        # internal pressure cannot exceed shoe fracture pressure (+ gas above)
        p_frac = PSI_PER_FT_PER_PPG * frac_ppg_shoe * shoe_tvd
        p_int_burst = np.minimum(p_int_burst, p_frac - gas_grad * (shoe_tvd - tvd))
    p_ext_burst = PSI_PER_FT_PER_PPG * backup_ppg * tvd
    burst = p_int_burst - p_ext_burst
    evac_level = top_tvd + evacuation_frac * (shoe_tvd - top_tvd)
    p_int_col = PSI_PER_FT_PER_PPG * mud_ppg * np.maximum(tvd - evac_level, 0.0)
    p_ext_col = PSI_PER_FT_PER_PPG * mud_ppg * tvd
    collapse = p_ext_col - p_int_col
    return {"tvd": tvd, "burst": burst, "collapse": collapse,
            "p_int_burst": p_int_burst, "p_ext_burst": p_ext_burst}


def tension_check(weight_ppf, length_md_ft, shoe_tvd_ft, mud_ppg, body_yield_lbf,
                  overpull=100000.0, shock_factor=1.0, design_factor=1.6):
    bf = 1.0 - mud_ppg / STEEL_PPG
    air = weight_ppf * length_md_ft
    buoyed_vertical = weight_ppf * shoe_tvd_ft * bf  # conservative using TVD for axial
    load = max(buoyed_vertical + overpull, air * shock_factor)
    allowable = body_yield_lbf / design_factor
    return {"air_weight": air, "buoyed_weight": buoyed_vertical, "load": load,
            "allowable": allowable, "sf": body_yield_lbf / max(load, 1.0)}


def cement_job(hole_in, casing_od, casing_id, shoe_md, toc_md, prev_casing_id, prev_shoe_md,
               shoe_track_ft=80.0, excess_oh=0.3, tail_length_ft=500.0,
               lead_yield=2.1, tail_yield=1.18, lead_water=11.5, tail_water=5.2,
               rathole_ft=0.0):
    """Cement volumes (bbl), sacks and displacement.

    Open-hole annulus below previous shoe gets ``excess_oh``; cased overlap
    none. Tail placed from shoe upward for ``tail_length_ft``.
    Yields ft3/sk, water gal/sk.
    """
    if toc_md >= shoe_md:
        raise ValueError("Top of cement must be above the shoe")

    def ann_vol(top, bot):
        if bot <= top:
            return 0.0
        oh_top = max(top, prev_shoe_md)
        oh = max(bot - oh_top, 0.0) * (hole_in ** 2 - casing_od ** 2) / 1029.4 * (1 + excess_oh)
        ch = max(min(bot, prev_shoe_md) - top, 0.0) * (prev_casing_id ** 2 - casing_od ** 2) / 1029.4
        return oh + ch

    tail_top = max(shoe_md - tail_length_ft, toc_md)
    tail_ann = ann_vol(tail_top, shoe_md)
    lead_ann = ann_vol(toc_md, tail_top)
    shoe_track = shoe_track_ft * casing_id ** 2 / 1029.4
    rathole = rathole_ft * hole_in ** 2 / 1029.4 * (1 + excess_oh)
    tail_bbl = tail_ann + shoe_track + rathole
    lead_bbl = lead_ann
    lead_sx = lead_bbl * 5.6146 / lead_yield
    tail_sx = tail_bbl * 5.6146 / tail_yield
    displacement = (shoe_md - shoe_track_ft) * casing_id ** 2 / 1029.4
    return {"lead_bbl": lead_bbl, "tail_bbl": tail_bbl, "total_bbl": lead_bbl + tail_bbl,
            "lead_sx": lead_sx, "tail_sx": tail_sx,
            "mix_water_bbl": (lead_sx * lead_water + tail_sx * tail_water) / 42.0,
            "displacement_bbl": displacement, "shoe_track_bbl": shoe_track,
            "tail_top_md": tail_top}


def cement_placement_ecd(shoe_tvd, toc_tvd, tail_top_tvd, mud_ppg, spacer_ppg, lead_ppg,
                         tail_ppg, spacer_len_tvd=500.0, friction_psi=0.0):
    """Static bottom-hole pressure at end of displacement (annulus column),
    expressed as EMW at shoe, plus circulating friction allowance."""
    tail_h = max(shoe_tvd - tail_top_tvd, 0.0)
    lead_h = max(tail_top_tvd - toc_tvd, 0.0)
    spacer_h = min(spacer_len_tvd, toc_tvd)
    mud_h = max(toc_tvd - spacer_h, 0.0)
    p = PSI_PER_FT_PER_PPG * (tail_ppg * tail_h + lead_ppg * lead_h + spacer_ppg * spacer_h + mud_ppg * mud_h)
    p += friction_psi
    # U-tube differential at plug bump: annulus column vs displacement fluid inside
    p_inside = PSI_PER_FT_PER_PPG * mud_ppg * shoe_tvd
    return {"bhp": p, "emw": p / (PSI_PER_FT_PER_PPG * shoe_tvd), "lift_pressure": p - p_inside}
