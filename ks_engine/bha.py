"""BHA weight design (API RP 7G style neutral-point method) and vibration
screening: axial / torsional natural frequencies of the string (1D wave
equation, fixed-free) and lateral critical speeds of stabiliser spans
(pinned-pinned Euler-Bernoulli beam with mud added-mass).

Screening only - does not replace a finite-element BHA dynamics model.
"""
from __future__ import annotations

import numpy as np

from .units import E_STEEL_PSI, G_STEEL_PSI, STEEL_PPG

G_ACC = 32.174
STEEL_LB_FT3 = 490.0
C_AXIAL = np.sqrt(E_STEEL_PSI * 144.0 / (STEEL_LB_FT3 / G_ACC))   # ~16,840 ft/s
C_TORS = np.sqrt(G_STEEL_PSI * 144.0 / (STEEL_LB_FT3 / G_ACC))    # ~10,440 ft/s


def bha_weight(components, mud_ppg, inc_deg=0.0):
    """components bit-upward: dicts with name, length (ft), weight (lb/ft air),
    in_bha (bool). Returns per-component table and cumulative buoyed weight."""
    bf = 1.0 - mud_ppg / STEEL_PPG
    rows, cum = [], 0.0
    cos_i = np.cos(np.radians(inc_deg))
    for c in components:
        if not c.get("in_bha", True):
            continue
        L = float(c["length"])
        w_b = float(c["weight"]) * L * bf
        cum += w_b * cos_i
        rows.append({"name": c["name"], "length": L, "air_lbf": float(c["weight"]) * L,
                     "buoyed_lbf": w_b, "cum_axial_lbf": cum})
    return rows, cum


def max_wob(components, mud_ppg, inc_deg=0.0, design_factor=1.15):
    _, cum = bha_weight(components, mud_ppg, inc_deg)
    return cum / design_factor


def neutral_point(components, mud_ppg, wob, inc_deg=0.0):
    """Distance from bit (ft) to the axial neutral point and the component."""
    bf = 1.0 - mud_ppg / STEEL_PPG
    cos_i = np.cos(np.radians(inc_deg))
    dist, remaining = 0.0, wob
    for c in components:
        w = float(c["weight"]) * bf * cos_i
        L = float(c["length"])
        if w * L >= remaining:
            return dist + remaining / max(w, 1e-9), c["name"]
        remaining -= w * L
        dist += L
    return None, "above defined string - WOB exceeds buoyed weight"


def axial_critical_rpm(string_length_ft, excitation_per_rev=3.0, modes=3):
    """Fixed-free axial natural frequencies f_n=(2n-1)c/4L -> RPM = 60 f / k.
    k = 3 for roller-cone (three-lobe bottom pattern), ~1 for PDC."""
    f = np.array([(2 * n - 1) * C_AXIAL / (4.0 * string_length_ft) for n in range(1, modes + 1)])
    return f, 60.0 * f / excitation_per_rev


def torsional_natural_frequency(string_length_ft, modes=3):
    return np.array([(2 * n - 1) * C_TORS / (4.0 * string_length_ft) for n in range(1, modes + 1)])


def lateral_critical_rpm(span_ft, od_in, id_in, weight_ppf, mud_ppg, added_mass_coeff=1.0,
                         modes=2):
    """Pinned-pinned span: f_n = (n^2 pi / 2 L^2) sqrt(EI/m), RPM = 60 f
    (forward synchronous whirl). m includes internal mud and added mass."""
    I_ft4 = np.pi / 64.0 * (od_in ** 4 - id_in ** 4) / 20736.0
    EI = E_STEEL_PSI * 144.0 * I_ft4
    mud_lb_ft3 = mud_ppg * 7.48052
    a_in = np.pi / 4 * id_in ** 2 / 144.0
    a_out = np.pi / 4 * od_in ** 2 / 144.0
    m = (weight_ppf + mud_lb_ft3 * (a_in + added_mass_coeff * a_out)) / G_ACC
    f = np.array([n ** 2 * np.pi / (2.0 * span_ft ** 2) * np.sqrt(EI / m) for n in range(1, modes + 1)])
    return f, 60.0 * f


def rpm_risk(rpm, criticals, band=0.15):
    """Return list of (critical_rpm, label) within +/- band of operating RPM."""
    hits = []
    for crit, label in criticals:
        if crit > 0 and abs(rpm - crit) / crit <= band:
            hits.append((crit, label))
    return hits
