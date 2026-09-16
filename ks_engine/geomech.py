"""1D geomechanics: overburden, pore pressure (direct or Eaton sonic),
fracture gradient (Eaton 1969), and vertical-well stability window
(Kirsch + Mohr-Coulomb).

Stability assumptions (stated in UI): vertical, impermeable wellbore wall;
sigma_theta is the maximum principal stress for shear breakout and
sigma_z is intermediate; horizontal stresses from Eaton Shmin and a user
SHmax/Shmin ratio. For deviated wells use a full 3D stress transformation
tool - this screening is conservative only for near-vertical sections.

Pressures in psi, depths ft TVD, gradients ppg EMW.
"""
from __future__ import annotations

import numpy as np

from .units import GCC_TO_PPG, PSI_PER_FT_PER_PPG


def overburden(tvd, layers_top, layers_rho_gcc, water_depth=0.0, air_gap=0.0, rho_sw=1.03):
    """Vertical stress (psi) by integrating bulk density.
    tvd measured from RKB; seabed at air_gap + water_depth."""
    tvd = np.asarray(tvd, float)
    grid = np.linspace(0.0, float(tvd.max()), 4000)
    rho = np.zeros_like(grid)
    seabed = air_gap + water_depth
    rho[(grid > air_gap) & (grid <= seabed)] = rho_sw
    tops = np.asarray(layers_top, float)
    dens = np.asarray(layers_rho_gcc, float)
    order = np.argsort(tops)
    tops, dens = tops[order], dens[order]
    below = grid > seabed
    idx = np.clip(np.searchsorted(tops, grid, side="right") - 1, 0, len(tops) - 1)
    rho[below] = dens[idx[below]]
    sv = np.concatenate([[0.0], np.cumsum(0.4335 * 0.5 * (rho[1:] + rho[:-1]) * np.diff(grid))])
    return np.interp(tvd, grid, sv)


def eaton_pore_sonic(obg_ppg, normal_ppg, dt_normal, dt_observed, exponent=3.0):
    return obg_ppg - (obg_ppg - normal_ppg) * (np.asarray(dt_normal) / np.asarray(dt_observed)) ** exponent


def eaton_frac(obg_ppg, pp_ppg, poisson):
    k = np.asarray(poisson) / (1.0 - np.asarray(poisson))
    return k * (np.asarray(obg_ppg) - np.asarray(pp_ppg)) + np.asarray(pp_ppg)


def mc_q(friction_angle_deg):
    s = np.sin(np.radians(friction_angle_deg))
    return (1 + s) / (1 - s)


def breakout_pressure(sH, sh, pp, ucs, friction_angle_deg):
    """Minimum wellbore pressure (psi) to avoid shear breakout, vertical well."""
    q = mc_q(friction_angle_deg)
    return (3.0 * np.asarray(sH) - np.asarray(sh) - np.asarray(ucs) + (q - 1.0) * np.asarray(pp)) / (1.0 + q)


def tensile_frac_pressure(sH, sh, pp, tensile=0.0):
    """Wellbore pressure (psi) initiating tensile fracture, vertical well."""
    return 3.0 * np.asarray(sh) - np.asarray(sH) - np.asarray(pp) + tensile


def mud_weight_window(tvd, layers, water_depth=0.0, air_gap=0.0, shmax_ratio=1.1,
                      use_eaton_sonic=False, normal_ppg=8.6):
    """Compute the window on a TVD grid.

    layers: list of dicts with top (ft TVD), rho (g/cc), pp (ppg), nu,
    ucs (psi), phi (deg), and optionally dt, dt_n for Eaton sonic.
    Returns dict of ppg arrays: obg, pp, fg, shmin, collapse, tensile.
    """
    tvd = np.asarray(tvd, float)
    tops = np.array([l["top"] for l in layers], float)
    order = np.argsort(tops)
    L = [layers[i] for i in order]
    tops = tops[order]
    sv = overburden(tvd, tops, [l["rho"] for l in L], water_depth, air_gap)
    obg = sv / (PSI_PER_FT_PER_PPG * np.maximum(tvd, 1.0))
    idx = np.clip(np.searchsorted(tops, tvd, side="right") - 1, 0, len(L) - 1)
    col = lambda key, default=0.0: np.array([float(L[i].get(key, default)) for i in idx])
    if use_eaton_sonic:
        pp = eaton_pore_sonic(obg, normal_ppg, col("dt_n", 100), col("dt", 100))
    else:
        pp = col("pp", normal_ppg)
    pp = np.maximum(pp, normal_ppg if water_depth == 0 else 8.4)
    nu = col("nu", 0.3)
    fg = eaton_frac(obg, pp, nu)
    p = lambda g: PSI_PER_FT_PER_PPG * g * np.maximum(tvd, 1.0)
    sh = p(fg)
    sH = shmax_ratio * sh
    pw_bo = breakout_pressure(sH, sh, p(pp), col("ucs", 5000), col("phi", 30))
    pw_t = tensile_frac_pressure(sH, sh, p(pp))
    to_ppg = lambda x: x / (PSI_PER_FT_PER_PPG * np.maximum(tvd, 1.0))
    collapse = np.maximum(to_ppg(pw_bo), pp)
    return {"tvd": tvd, "obg": obg, "pp": pp, "fg": fg, "shmin": fg,
            "collapse": collapse, "tensile": to_ppg(pw_t),
            "min_mw": np.maximum(pp, collapse), "max_mw": np.minimum(fg, np.maximum(to_ppg(pw_t), pp))}


def rho_gcc_to_ppg(rho):
    return rho * GCC_TO_PPG
