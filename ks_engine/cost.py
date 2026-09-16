"""Operations planning: section-based time-depth curve, AFE cost build-up and
Monte Carlo duration/cost uncertainty. Length unit is whatever the caller
uses consistently (UI: metres); money in USD; time in hours/days.
"""
from __future__ import annotations

import numpy as np

SECTION_FIELDS = [
    "name", "hole_in", "top_md", "bottom_md", "rop", "trip_speed", "casing_speed",
    "bits", "circ_hr", "logging_hr", "cement_hr", "woc_hr", "bop_hr", "npt_pct",
    "bit_cost", "mud_cost_per_len", "casing_cost_per_len", "cement_cost",
    "logging_cost", "other_cost",
]


def section_activities(sec, rop_mult=1.0, npt_mult=1.0):
    top, bot = float(sec["top_md"]), float(sec["bottom_md"])
    length = max(bot - top, 0.0)
    rop = max(float(sec["rop"]) * rop_mult, 1e-6)
    ts = max(float(sec["trip_speed"]), 1e-6)
    cs = max(float(sec["casing_speed"]), 1e-6)
    bits = max(int(sec.get("bits", 1) or 1), 1)
    acts = [("Trip in / drill out", top / ts, top, top)]
    drill_hr = length / rop
    # intermediate bit trips spread evenly through section
    seg = length / bits
    d = top
    for b in range(bits):
        d_next = d + seg
        acts.append((f"Drill {sec['name']}" + (f" (bit {b + 1})" if bits > 1 else ""),
                     seg / rop, d, d_next))
        if b < bits - 1:
            acts.append(("Bit trip", 2.0 * d_next / ts, d_next, d_next))
        d = d_next
    acts += [
        ("Circulate & condition", float(sec.get("circ_hr", 0)), bot, bot),
        ("Trip out", bot / ts, bot, bot),
        ("Logging", float(sec.get("logging_hr", 0)), bot, bot),
        ("Run casing / liner", bot / cs if sec.get("run_casing", True) else 0.0, bot, bot),
        ("Cement", float(sec.get("cement_hr", 0)), bot, bot),
        ("Wait on cement", float(sec.get("woc_hr", 0)), bot, bot),
        ("Wellhead / BOP", float(sec.get("bop_hr", 0)), bot, bot),
    ]
    flat = sum(a[1] for a in acts)
    npt = flat * float(sec.get("npt_pct", 0)) / 100.0 * npt_mult
    acts.append(("NPT allowance", npt, bot, bot))
    return acts, drill_hr


def plan_well(sections, rig_rate_day, spread_rate_day, mob_cost=0.0, mob_days=0.0):
    rows, t_hr = [], mob_days * 24.0
    curve_t, curve_d, curve_c = [0.0, t_hr / 24.0], [0.0, 0.0], [0.0, mob_cost + mob_days * (rig_rate_day + spread_rate_day)]
    cost = curve_c[-1]
    daily = rig_rate_day + spread_rate_day
    afe = {"Mobilisation": mob_cost + mob_days * daily, "Rig & spread (time)": 0.0, "Bits": 0.0,
           "Drilling fluids": 0.0, "Casing & liners": 0.0, "Cementing": 0.0,
           "Logging & evaluation": 0.0, "Other services": 0.0}
    per_section = []
    for sec in sections:
        acts, drill_hr = section_activities(sec)
        sec_hr = 0.0
        for name, hr, d0, d1 in acts:
            t_hr += hr
            sec_hr += hr
            cost += hr / 24.0 * daily
            curve_t.append(t_hr / 24.0)
            curve_d.append(d1)
            curve_c.append(cost)
            rows.append({"section": sec["name"], "activity": name, "hours": hr,
                         "end_day": t_hr / 24.0, "depth": d1})
        length = max(float(sec["bottom_md"]) - float(sec["top_md"]), 0.0)
        mats = {
            "Bits": float(sec.get("bit_cost", 0)) * max(int(sec.get("bits", 1) or 1), 1),
            "Drilling fluids": float(sec.get("mud_cost_per_len", 0)) * length,
            "Casing & liners": float(sec.get("casing_cost_per_len", 0)) * float(sec["bottom_md"]),
            "Cementing": float(sec.get("cement_cost", 0)),
            "Logging & evaluation": float(sec.get("logging_cost", 0)),
            "Other services": float(sec.get("other_cost", 0)),
        }
        for k, v in mats.items():
            afe[k] += v
        cost += sum(mats.values())
        curve_c[-1] = cost
        afe["Rig & spread (time)"] += sec_hr / 24.0 * daily
        per_section.append({"section": sec["name"], "days": sec_hr / 24.0,
                            "drilling_days": drill_hr / 24.0,
                            "cost": sec_hr / 24.0 * daily + sum(mats.values())})
    return {"activities": rows, "curve_days": np.array(curve_t), "curve_depth": np.array(curve_d),
            "curve_cost": np.array(curve_c), "total_days": t_hr / 24.0, "total_cost": cost,
            "afe": afe, "sections": per_section}


def monte_carlo(sections, rig_rate_day, spread_rate_day, mob_cost=0.0, mob_days=0.0,
                rop_range=(0.7, 1.0, 1.3), npt_range=(0.5, 1.0, 2.5), rate_range=(0.95, 1.0, 1.1),
                n=2000, seed=7):
    """Triangular multipliers on ROP, NPT allowance and daily rates.
    Returns arrays of total days and cost with P10/P50/P90 (P90 = high case)."""
    rng = np.random.default_rng(seed)
    rop_m = rng.triangular(*rop_range, size=n)
    npt_m = rng.triangular(*npt_range, size=n)
    rate_m = rng.triangular(*rate_range, size=n)
    days = np.zeros(n)
    costs = np.zeros(n)
    base = plan_well(sections, rig_rate_day, spread_rate_day, mob_cost, mob_days)
    materials = base["total_cost"] - base["afe"]["Rig & spread (time)"] - mob_days * (rig_rate_day + spread_rate_day)
    for k in range(n):
        hrs = mob_days * 24.0
        for sec in sections:
            acts, _ = section_activities(sec, rop_m[k], npt_m[k])
            hrs += sum(a[1] for a in acts)
        days[k] = hrs / 24.0
        costs[k] = materials + (days[k]) * (rig_rate_day + spread_rate_day) * rate_m[k]
    pct = lambda a: {"P10": float(np.percentile(a, 10)), "P50": float(np.percentile(a, 50)),
                     "P90": float(np.percentile(a, 90)), "mean": float(a.mean())}
    return {"days": days, "cost": costs, "days_stats": pct(days), "cost_stats": pct(costs)}
