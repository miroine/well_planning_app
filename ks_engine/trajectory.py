"""Wellbore trajectory: minimum curvature, well planners, interpolation,
vertical section and scalar-cone anti-collision.

Geometry is unit-agnostic: MD/TVD/N/E share one length unit (the UI uses
metres). Dogleg severity is reported per ``dls_course`` length units
(30 for deg/30 m, 100 for deg/100 ft).

References
----------
* Sawaryn, S.J. & Thorogood, J.L. (2005) SPE 84246 — minimum curvature.
* Adams, N. (1985) Drilling Engineering — build-and-hold planning.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

D2R = np.pi / 180.0


# --------------------------------------------------------------------------
# Core minimum curvature
# --------------------------------------------------------------------------
def _tangent(inc_deg, azi_deg):
    i = np.asarray(inc_deg) * D2R
    a = np.asarray(azi_deg) * D2R
    return np.stack([np.sin(i) * np.cos(a), np.sin(i) * np.sin(a), np.cos(i)], axis=-1)


def dogleg_rad(i1, a1, i2, a2):
    """Dogleg angle (rad) between two survey stations (degrees in)."""
    i1, a1, i2, a2 = (np.asarray(x) * D2R for x in (i1, a1, i2, a2))
    c = np.cos(i2 - i1) - np.sin(i1) * np.sin(i2) * (1.0 - np.cos(a2 - a1))
    return np.arccos(np.clip(c, -1.0, 1.0))


def ratio_factor(beta):
    beta = np.asarray(beta, dtype=float)
    out = np.ones_like(beta)
    m = beta > 1e-9
    out[m] = 2.0 / beta[m] * np.tan(beta[m] / 2.0)
    return out


def minimum_curvature(md, inc, azi, tvd0=0.0, n0=0.0, e0=0.0, dls_course=30.0):
    """Compute positions from MD/inc/azi arrays.

    Returns dict of numpy arrays: md, inc, azi, tvd, north, east, dls.
    """
    md = np.asarray(md, dtype=float)
    inc = np.asarray(inc, dtype=float)
    azi = np.mod(np.asarray(azi, dtype=float), 360.0)
    if md.ndim != 1 or len(md) < 1:
        raise ValueError("Survey needs at least one station")
    if np.any(np.diff(md) <= 0):
        raise ValueError("Measured depth must be strictly increasing")
    if np.any((inc < 0) | (inc > 180)):
        raise ValueError("Inclination must be within 0-180 deg")
    n = len(md)
    tvd = np.full(n, tvd0, dtype=float)
    north = np.full(n, n0, dtype=float)
    east = np.full(n, e0, dtype=float)
    dls = np.zeros(n)
    if n > 1:
        dmd = np.diff(md)
        beta = dogleg_rad(inc[:-1], azi[:-1], inc[1:], azi[1:])
        rf = ratio_factor(beta)
        i1, i2 = inc[:-1] * D2R, inc[1:] * D2R
        a1, a2 = azi[:-1] * D2R, azi[1:] * D2R
        dn = dmd / 2 * (np.sin(i1) * np.cos(a1) + np.sin(i2) * np.cos(a2)) * rf
        de = dmd / 2 * (np.sin(i1) * np.sin(a1) + np.sin(i2) * np.sin(a2)) * rf
        dv = dmd / 2 * (np.cos(i1) + np.cos(i2)) * rf
        tvd[1:] = tvd0 + np.cumsum(dv)
        north[1:] = n0 + np.cumsum(dn)
        east[1:] = e0 + np.cumsum(de)
        dls[1:] = beta / D2R * dls_course / dmd
    return {"md": md, "inc": inc, "azi": azi, "tvd": tvd, "north": north,
            "east": east, "dls": dls}


def interpolate_at_md(traj, md_query):
    """Minimum-curvature interpolation of inc/azi/position at arbitrary MD.

    Values outside the survey are extrapolated along the end tangent.
    """
    mdq = np.atleast_1d(np.asarray(md_query, dtype=float))
    md = traj["md"]
    t = _tangent(traj["inc"], traj["azi"])
    pos = np.stack([traj["north"], traj["east"], traj["tvd"]], axis=-1)
    out = {k: np.zeros(len(mdq)) for k in ("md", "inc", "azi", "tvd", "north", "east")}
    out["md"] = mdq.copy()
    for k, q in enumerate(mdq):
        if len(md) == 1 or q <= md[0]:
            j = 0
            tq = t[0]
            p = pos[0] + tq * (q - md[0])
        elif q >= md[-1]:
            tq = t[-1]
            p = pos[-1] + tq * (q - md[-1])
        else:
            j = int(np.searchsorted(md, q, side="right") - 1)
            L = md[j + 1] - md[j]
            f = (q - md[j]) / L
            beta = float(np.arccos(np.clip(np.dot(t[j], t[j + 1]), -1, 1)))
            if beta < 1e-9:
                tq = t[j]
            else:
                tq = (np.sin((1 - f) * beta) * t[j] + np.sin(f * beta) * t[j + 1]) / np.sin(beta)
            b2 = f * beta
            rf = 1.0 if b2 < 1e-9 else 2.0 / b2 * np.tan(b2 / 2.0)
            p = pos[j] + (q - md[j]) / 2.0 * (t[j] + tq) * rf
        tq = tq / np.linalg.norm(tq)
        out["inc"][k] = np.degrees(np.arccos(np.clip(tq[2], -1, 1)))
        out["azi"][k] = np.mod(np.degrees(np.arctan2(tq[1], tq[0])), 360.0)
        out["north"][k], out["east"][k], out["tvd"][k] = p
    return out


def vertical_section(north, east, vs_azi_deg, n0=0.0, e0=0.0):
    a = vs_azi_deg * D2R
    return (np.asarray(north) - n0) * np.cos(a) + (np.asarray(east) - e0) * np.sin(a)


def closure(north, east):
    dist = float(np.hypot(north, east))
    az = float(np.mod(np.degrees(np.arctan2(east, north)), 360.0))
    return dist, az


# --------------------------------------------------------------------------
# Well planners (return station arrays md/inc/azi)
# --------------------------------------------------------------------------
@dataclass
class PlanResult:
    md: np.ndarray
    inc: np.ndarray
    azi: np.ndarray
    feasible: bool
    message: str
    key_points: dict


def _radius(bur_deg_per_course, course):
    if bur_deg_per_course <= 0:
        raise ValueError("Build/drop rate must be positive")
    return 180.0 / np.pi * course / bur_deg_per_course


def _stations(segments, step):
    """segments: list of (md_start, md_end, inc_start, inc_end) linear-in-MD
    inclination segments (constant curvature in the vertical plane)."""
    mds, incs = [0.0], [segments[0][2] if segments else 0.0]
    for md_s, md_e, i_s, i_e in segments:
        if md_e - md_s <= 1e-9:
            continue
        n = max(int(np.ceil((md_e - md_s) / step)), 1)
        grid = np.linspace(md_s, md_e, n + 1)[1:]
        mds.extend(grid)
        incs.extend(i_s + (i_e - i_s) * (grid - md_s) / (md_e - md_s))
    md = np.asarray(mds)
    inc = np.asarray(incs)
    keep = np.concatenate([[True], np.diff(md) > 1e-9])
    return md[keep], inc[keep]


def plan_vertical(td_md, step=30.0):
    md = np.arange(0.0, td_md + 1e-9, step)
    if md[-1] < td_md:
        md = np.append(md, td_md)
    return PlanResult(md, np.zeros_like(md), np.zeros_like(md), True, "Vertical well", {})


def plan_build_hold(kop, bur, target_tvd, target_disp, azimuth, course=30.0,
                    step=30.0, extend_md=0.0):
    """J-type: vertical to KOP, build at BUR, hold to target (TVD, departure)."""
    R = _radius(bur, course)
    V = target_tvd - kop
    D = target_disp
    if V <= 0:
        return PlanResult(np.array([0.0]), np.array([0.0]), np.array([azimuth]), False,
                          "Target TVD must be below KOP", {})
    rho = np.hypot(V, R - D)
    if rho < R:
        return PlanResult(np.array([0.0]), np.array([0.0]), np.array([azimuth]), False,
                          "Target unreachable: increase build rate or deepen KOP", {})
    phi = np.arctan2(R - D, V)
    inc = np.arcsin(R / rho) - phi
    inc_deg = np.degrees(inc)
    if inc_deg <= 0 or inc_deg >= 90:
        return PlanResult(np.array([0.0]), np.array([0.0]), np.array([azimuth]), False,
                          f"Hold inclination {inc_deg:.1f} deg outside 0-90 deg", {})
    build_len = inc_deg / bur * course
    eob_tvd = kop + R * np.sin(inc)
    hold_len = (target_tvd - eob_tvd) / np.cos(inc)
    md_eob = kop + build_len
    md_tgt = md_eob + hold_len
    segs = [(0.0, kop, 0.0, 0.0), (kop, md_eob, 0.0, inc_deg),
            (md_eob, md_tgt + extend_md, inc_deg, inc_deg)]
    md, incs = _stations(segs, step)
    return PlanResult(md, incs, np.full_like(md, azimuth), True,
                      f"Build-hold: {inc_deg:.1f} deg hold", {
                          "KOP": kop, "EOB": md_eob, "Target": md_tgt,
                          "hold_inc": inc_deg})


def plan_s_type(kop, bur, dor, target_tvd, target_disp, azimuth, end_inc=0.0,
                drop_end_above_target=0.0, course=30.0, step=30.0):
    """Build-hold-drop solved by bisection on hold inclination so that the
    drop finishes ``drop_end_above_target`` above target TVD with the
    required departure at target TVD."""
    Rb, Rd = _radius(bur, course), _radius(dor, course)

    def geometry(hold):
        hi = hold * D2R
        ei = end_inc * D2R
        dv_b, dh_b = Rb * np.sin(hi), Rb * (1 - np.cos(hi))
        dv_d = Rd * (np.sin(hi) - np.sin(ei))
        dh_d = Rd * (np.cos(ei) - np.cos(hi))
        drop_end_tvd = target_tvd - drop_end_above_target
        v_hold = drop_end_tvd - kop - dv_b - dv_d
        if v_hold < 0:
            return None
        dh_hold = v_hold * np.tan(hi)
        dh_tail = drop_end_above_target * np.tan(ei)
        return dh_b + dh_hold + dh_d + dh_tail, v_hold / max(np.cos(hi), 1e-9)

    lo, hi_ = max(end_inc, 0.01), 89.0
    g_lo, g_hi = geometry(lo), None
    # find largest feasible upper bound
    for cand in np.linspace(89.0, lo, 400):
        g_hi = geometry(cand)
        if g_hi is not None:
            hi_ = cand
            break
    if g_lo is None or g_hi is None or not (g_lo[0] <= target_disp <= g_hi[0]):
        return PlanResult(np.array([0.0]), np.array([0.0]), np.array([azimuth]), False,
                          "S-type target unreachable with these rates/KOP", {})
    for _ in range(80):
        mid = 0.5 * (lo + hi_)
        g = geometry(mid)
        if g is None or g[0] > target_disp:
            hi_ = mid
        else:
            lo = mid
    hold = 0.5 * (lo + hi_)
    _, hold_len = geometry(hold)
    md_eob = kop + hold / bur * course
    md_sod = md_eob + hold_len
    md_eod = md_sod + (hold - end_inc) / dor * course
    md_tgt = md_eod + drop_end_above_target / max(np.cos(end_inc * D2R), 1e-9)
    segs = [(0.0, kop, 0, 0), (kop, md_eob, 0, hold), (md_eob, md_sod, hold, hold),
            (md_sod, md_eod, hold, end_inc), (md_eod, md_tgt, end_inc, end_inc)]
    md, incs = _stations(segs, step)
    return PlanResult(md, incs, np.full_like(md, azimuth), True,
                      f"S-type: {hold:.1f} deg hold, drop to {end_inc:.0f} deg",
                      {"KOP": kop, "EOB": md_eob, "SOD": md_sod, "EOD": md_eod,
                       "Target": md_tgt, "hold_inc": hold})


def plan_horizontal(landing_tvd, bur, lateral_length, azimuth, tangent_inc=0.0,
                    tangent_len=0.0, course=30.0, step=30.0):
    """Vertical - build to 90 deg landing at ``landing_tvd`` - lateral.
    Optional tangent (tangent_inc, tangent_len) inside the build."""
    R = _radius(bur, course)
    ti = tangent_inc * D2R
    dv = R * np.sin(ti) + tangent_len * np.cos(ti) + R * (1 - np.sin(ti))
    kop = landing_tvd - dv
    if kop <= 0:
        return PlanResult(np.array([0.0]), np.array([0.0]), np.array([azimuth]), False,
                          "Landing too shallow for this build rate", {})
    md1 = kop + tangent_inc / bur * course
    md2 = md1 + tangent_len
    md3 = md2 + (90.0 - tangent_inc) / bur * course
    md4 = md3 + lateral_length
    segs = [(0, kop, 0, 0), (kop, md1, 0, tangent_inc), (md1, md2, tangent_inc, tangent_inc),
            (md2, md3, tangent_inc, 90.0), (md3, md4, 90.0, 90.0)]
    md, incs = _stations(segs, step)
    return PlanResult(md, incs, np.full_like(md, azimuth), True,
                      f"Horizontal: KOP {kop:.0f}, lands at MD {md3:.0f}",
                      {"KOP": kop, "Landing": md3, "TD": md4})


# --------------------------------------------------------------------------
# Anti-collision (scalar cone of uncertainty)
# --------------------------------------------------------------------------
def uncertainty_radius(md, r0=0.5, growth_per_1000=5.0):
    """Radius of a circular error cone: r0 + growth per 1000 length units.
    Scalar approximation - not an ISCWSA tool-code error model."""
    return r0 + np.asarray(md) * growth_per_1000 / 1000.0


def separation_to_offset(ref, off, r0=0.5, growth_per_1000=5.0, offset_step=5.0):
    """Closest-approach centre-to-centre distance and separation factor
    for each reference station against one offset trajectory (the offset is
    densified by minimum-curvature interpolation every ``offset_step``)."""
    grid = np.arange(off["md"][0], off["md"][-1] + offset_step, offset_step)
    grid = np.clip(grid, off["md"][0], off["md"][-1])
    off = interpolate_at_md(off, np.unique(grid))
    P = np.stack([ref["north"], ref["east"], ref["tvd"]], axis=-1)
    Q = np.stack([off["north"], off["east"], off["tvd"]], axis=-1)
    d = np.linalg.norm(P[:, None, :] - Q[None, :, :], axis=-1)
    j = np.argmin(d, axis=1)
    ctc = d[np.arange(len(P)), j]
    r_ref = uncertainty_radius(ref["md"], r0, growth_per_1000)
    r_off = uncertainty_radius(off["md"][j], r0, growth_per_1000)
    sf = ctc / np.maximum(r_ref + r_off, 1e-9)
    return {"md": ref["md"], "ctc": ctc, "sf": sf, "offset_md": off["md"][j]}
