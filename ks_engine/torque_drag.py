"""Soft-string torque & drag (Johancsik, Friesen & Dawson, SPE 11380, 1984)
with buckling screening (Dawson & Paslay 1984; Wu & Juvkam-Wold 1993).

All inputs in field units: depths ft, diameters in, weights lb/ft, forces lbf,
torque ft-lbf, mud ppg. Tension positive, compression negative.

Assumptions (stated in the UI):
* soft string - no bending stiffness contribution to side force;
* buckling is screened against critical loads, but post-buckling contact
  forces (helical lock-up) are not added to drag;
* same mud density inside and outside the string (static buoyancy factor).
"""
from __future__ import annotations

import numpy as np

from .trajectory import interpolate_at_md
from .units import E_STEEL_PSI, STEEL_PPG

OPERATIONS = {
    "drill_rotate": "Drilling - rotating on bottom",
    "slide": "Drilling - sliding on bottom",
    "rotate_off": "Rotating off bottom",
    "trip_out": "Tripping out (pick-up)",
    "trip_in": "Tripping in (slack-off)",
    "ream_out": "Back-reaming (POOH + rotation)",
    "ream_in": "Reaming in (RIH + rotation)",
}


def buoyancy_factor(mud_ppg, steel_ppg=STEEL_PPG):
    return 1.0 - mud_ppg / steel_ppg


def build_elements(components, bit_md, dl=30.0):
    """Discretise the string from bit (bottom) to surface.

    components: list of dicts ordered bit-upward with keys
      name, od, id, tj_od, weight (lb/ft air), length (ft; last one fills to
      surface), tensile_yield (lbf), mu_torque (make-up torque, ft-lbf).
    Returns dict of arrays per element, ordered bottom -> top.
    """
    if bit_md <= 0:
        raise ValueError("Bit depth must be positive")
    if not components:
        raise ValueError("Drillstring has no components")
    tops = []
    md_cursor = bit_md
    for k, c in enumerate(components):
        length = float(c.get("length", 0) or 0)
        last = k == len(components) - 1
        top = 0.0 if last else max(md_cursor - length, 0.0)
        tops.append((md_cursor, top, c))
        md_cursor = top
        if md_cursor <= 0:
            break
    rows = []
    for bot, top, c in tops:
        if bot - top <= 1e-9:
            continue
        n = max(int(np.ceil((bot - top) / dl)), 1)
        edges = np.linspace(bot, top, n + 1)
        for lo, hi in zip(edges[:-1], edges[1:]):
            rows.append((lo, hi, c))
    out = {
        "md_bot": np.array([r[0] for r in rows]),
        "md_top": np.array([r[1] for r in rows]),
        "od": np.array([float(r[2]["od"]) for r in rows]),
        "id": np.array([float(r[2]["id"]) for r in rows]),
        "tj_od": np.array([float(r[2].get("tj_od") or r[2]["od"]) for r in rows]),
        "w_air": np.array([float(r[2]["weight"]) for r in rows]),
        "yield": np.array([float(r[2].get("tensile_yield") or 0) for r in rows]),
        "mut": np.array([float(r[2].get("mu_torque") or 0) for r in rows]),
        "name": [r[2].get("name", "") for r in rows],
    }
    return out


def critical_buckling(od, id_, w_buoyed, inc_deg, hole_id):
    """Sinusoidal & helical critical compressive loads (lbf).

    Inclined (> ~5 deg): Dawson-Paslay F_sin = 2*sqrt(E I w sin(I) / r).
    Near-vertical: Wu & Juvkam-Wold F_sin = 2.55 (E I w^2)^(1/3).
    Helical taken as sqrt(2) x sinusoidal (Wu & Juvkam-Wold, inclined).
    """
    od = np.asarray(od, float)
    id_ = np.asarray(id_, float)
    I = np.pi / 64.0 * (od ** 4 - id_ ** 4)
    w_in = np.maximum(np.asarray(w_buoyed, float), 1e-6) / 12.0
    r = np.maximum((np.asarray(hole_id, float) - od) / 2.0, 0.05)
    s = np.sin(np.radians(np.asarray(inc_deg, float)))
    f_incl = 2.0 * np.sqrt(E_STEEL_PSI * I * w_in * np.maximum(s, 1e-6) / r)
    f_vert = 2.55 * np.cbrt(E_STEEL_PSI * I * w_in ** 2)
    f_sin = np.where(np.asarray(inc_deg) > 5.0, np.maximum(f_incl, f_vert), f_vert)
    return f_sin, np.sqrt(2.0) * f_sin


def torque_drag(traj, components, bit_md, operation, mud_ppg, ff_cased, ff_open,
                shoe_md, wob=0.0, bit_torque=0.0, rpm=0.0, trip_speed_ftmin=0.0,
                block_weight=0.0, hole_id_func=None, dl=30.0):
    """Run one soft-string case.

    traj: trajectory dict (md/inc/azi/tvd/north/east) in FEET.
    hole_id_func: callable(md_array) -> hole/casing ID (in) for buckling.
    Returns dict with node profiles (bottom -> top) and summary values.
    """
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown operation {operation}")
    el = build_elements(components, bit_md, dl)
    bf = buoyancy_factor(mud_ppg)
    w = el["w_air"] * bf
    nodes_md = np.concatenate([[el["md_bot"][0]], el["md_top"]])
    s = interpolate_at_md(traj, nodes_md)
    inc = np.radians(s["inc"])
    azi = np.radians(s["azi"])

    on_bottom = operation in ("drill_rotate", "slide")
    rotating = operation in ("drill_rotate", "rotate_off", "ream_out", "ream_in")
    axial_sign = {"trip_out": 1, "ream_out": 1, "trip_in": -1, "ream_in": -1,
                  "slide": -1}.get(operation, 0)

    n_el = len(w)
    F = np.zeros(n_el + 1)
    T = np.zeros(n_el + 1)
    Nf = np.zeros(n_el)
    F[0] = -wob if on_bottom else 0.0
    T[0] = bit_torque if (on_bottom and rotating) else 0.0

    for k in range(n_el):
        dL = el["md_bot"][k] - el["md_top"][k]
        i_lo, i_hi = inc[k], inc[k + 1]
        a_lo, a_hi = azi[k], azi[k + 1]
        ibar = 0.5 * (i_lo + i_hi)
        d_inc = i_hi - i_lo
        d_azi = (a_hi - a_lo + np.pi) % (2 * np.pi) - np.pi
        md_mid = 0.5 * (el["md_bot"][k] + el["md_top"][k])
        mu = ff_cased if md_mid <= shoe_md else ff_open
        Fb = F[k]
        N = np.hypot(Fb * d_azi * np.sin(ibar), Fb * d_inc + w[k] * dL * np.sin(ibar))
        Nf[k] = N / dL
        r_ft = el["tj_od"][k] / 24.0
        if operation in ("ream_out", "ream_in") and rpm > 0 and trip_speed_ftmin > 0:
            v_rot = rpm * np.pi * el["tj_od"][k] / 12.0  # ft/min at contact
            ax_frac = trip_speed_ftmin / np.hypot(trip_speed_ftmin, v_rot)
            rot_frac = v_rot / np.hypot(trip_speed_ftmin, v_rot)
        else:
            ax_frac = 1.0 if axial_sign != 0 else 0.0
            rot_frac = 1.0 if rotating else 0.0
        F[k + 1] = Fb + w[k] * dL * np.cos(ibar) + axial_sign * mu * N * ax_frac
        T[k + 1] = T[k] + mu * N * r_ft * rot_frac

    # buckling screen on elements (use lower-node force)
    hole_id = hole_id_func(0.5 * (el["md_bot"] + el["md_top"])) if hole_id_func else el["od"] + 2.0
    f_sin, f_hel = critical_buckling(el["od"], el["id"], w, np.degrees(0.5 * (inc[:-1] + inc[1:])), hole_id)
    comp = -F[:-1]
    buckling = np.where(comp > f_hel, "helical", np.where(comp > f_sin, "sinusoidal", "none"))

    area = np.pi / 4.0 * (el["od"] ** 2 - el["id"] ** 2)
    ten_util = np.where(el["yield"] > 0, np.abs(F[1:]) / np.maximum(el["yield"], 1), 0.0)
    tq_util = np.where(el["mut"] > 0, T[1:] / np.maximum(el["mut"], 1), 0.0)
    return {
        "md": nodes_md,
        "tvd": s["tvd"],
        "tension": F,
        "torque": T,
        "side_force_per_ft": np.concatenate([[Nf[0]], Nf]),
        "element_md": 0.5 * (el["md_bot"] + el["md_top"]),
        "element_name": el["name"],
        "f_sin": f_sin,
        "f_hel": f_hel,
        "buckling": buckling,
        "axial_stress": F[1:] / np.maximum(area, 1e-6),
        "tension_utilisation": ten_util,
        "torque_utilisation": tq_util,
        "surface_tension": float(F[-1]),
        "hookload": float(F[-1] + block_weight),
        "surface_torque": float(T[-1]),
        "buoyancy_factor": bf,
        "string_weight_air": float(np.sum(el["w_air"] * (el["md_bot"] - el["md_top"]))),
        "string_weight_buoyed": float(np.sum(w * (el["md_bot"] - el["md_top"]))),
    }


def broomstick(traj, components, depths, mud_ppg, ff_list, shoe_md, block_weight=0.0,
               ops=("trip_out", "rotate_off", "trip_in"), dl=100.0):
    """Hookload vs bit depth for several friction factors (cased=open=FF)."""
    out = {}
    for ff in ff_list:
        for op in ops:
            hl = []
            for d in depths:
                r = torque_drag(traj, components, d, op, mud_ppg, ff, ff, shoe_md,
                                block_weight=block_weight, dl=dl)
                hl.append(r["hookload"])
            out[(ff, op)] = np.array(hl)
    return out


def calibrate_friction(traj, components, bit_md, mud_ppg, shoe_md, measured_hookload,
                       operation, ff_cased, block_weight=0.0, lo=0.0, hi=0.8):
    """Back-calculate open-hole FF matching a measured hookload (bisection)."""
    def f(ff):
        return torque_drag(traj, components, bit_md, operation, mud_ppg, ff_cased, ff,
                           shoe_md, block_weight=block_weight, dl=100.0)["hookload"] - measured_hookload
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)
