"""Printable HTML engineering report (no Streamlit)."""
from __future__ import annotations

import datetime as dt
import html

from ks_engine.units import FT2M

from . import model, theme

E = html.escape


def _table(headers, rows):
    head = "".join(f"<th>{E(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{E(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build(p):
    h = p["header"]
    res = model.operation_summary(p)
    css = f"""body{{font-family:'IBM Plex Sans',Arial,sans-serif;color:{theme.INK};margin:0 auto;max-width:900px;padding:28px;font-size:13px}}
h1{{color:{theme.NAVY};font-size:22px;margin:0}}h2{{color:{theme.NAVY};font-size:15px;border-bottom:2px solid {theme.MOSS};padding-bottom:3px;margin-top:26px;page-break-after:avoid}}
table{{border-collapse:collapse;width:100%;margin:6px 0 10px}}th,td{{border:1px solid {theme.LINE};padding:3px 6px;text-align:left}}th{{background:{theme.PAPER}}}
.meta{{color:{theme.MUTED};margin:4px 0 14px}}.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.kpi div{{border:1px solid {theme.LINE};border-radius:6px;padding:6px 8px}}
.kpi b{{display:block;font-size:17px;color:{theme.NAVY}}}.pass{{color:#5E7000;font-weight:600}}.warn{{color:#B36600;font-weight:600}}.fail{{color:{theme.RED};font-weight:600}}
.foot{{color:{theme.MUTED};font-size:11px;margin-top:24px}}@media print{{body{{padding:10mm;max-width:none}}h2{{break-after:avoid}}table{{break-inside:auto}}tr{{break-inside:avoid}}}}"""
    parts = [f"<h1>Well engineering summary: {E(h['well_name'])}</h1>",
             f"<div class='meta'>{E(h['field'])} · {E(h['rig'])} · {E(h.get('operator',''))} · generated {dt.date.today().isoformat()}</div>"]
    if "error" in res:
        parts.append(f"<p class='fail'>Trajectory not feasible: {E(res['error'])}</p>")
    else:
        traj = res["traj"]
        oc = p["opcase"]
        parts.append("<h2>Active operation case</h2><div class='kpi'>" + "".join(
            f"<div>{E(l)}<b>{E(v)}</b>{E(u)}</div>" for l, v, u in [
                ("Hookload", f"{res['hookload']/1000:,.1f}", "klbf"), ("Surface torque", f"{res['surface_torque']/1000:,.1f}", "kft-lbf"),
                ("SPP", f"{res['spp']:,.0f}" if res["spp"] is not None else "n/a", "psi"),
                ("ECD at bit", f"{res['ecd_bit']:.2f}" if res["ecd_bit"] is not None else "n/a", "ppg")]) + "</div>")
        parts.append(f"<p>{E(oc['operation'].replace('_',' '))} at {oc['bit_md_m']:,.0f} mMD ({res['bit_tvd']:,.0f} mTVD, {res['inc_bit']:.1f}°), "
                     f"WOB {oc['wob_lb']:,.0f} lb, {oc['rpm']:.0f} RPM, {oc['flow_gpm']:.0f} gpm, MW {p['fluid']['mud_ppg']:.2f} ppg.</p>")
        parts.append("<h2>Engineering checks</h2>" + _table(["Group", "Check", "Status", "Value", "Limit", "Note"],
                     [[c["group"], c["check"], c["status"].upper(), c["value"], c["limit"], c["note"]]
                      for c in sorted(res["checks"], key=lambda c: {"fail": 0, "warn": 1, "pass": 2}[c["status"]])]))
        for s in ("PASS", "WARN", "FAIL"):
            parts[-1] = parts[-1].replace(f"<td>{s}</td>", f"<td class='{s.lower()}'>{s}</td>")
        md = traj["md"]
        idx = sorted(set(list(range(0, len(md), max(len(md) // 20, 1))) + [len(md) - 1]))
        parts.append("<h2>Trajectory (planned)</h2>" + _table(["MD (m)", "Inc (°)", "Azi (°)", "TVD (m)", "N (m)", "E (m)", "DLS (°/30m)"],
                     [[f"{md[i]:,.0f}", f"{traj['inc'][i]:.1f}", f"{traj['azi'][i]:.1f}", f"{traj['tvd'][i]:,.0f}",
                       f"{traj['north'][i]:,.0f}", f"{traj['east'][i]:,.0f}", f"{traj['dls'][i]:.2f}"] for i in idx]))
    rows = model.casing_rows(p)
    parts.append("<h2>Casing program</h2>" + _table(["String", "OD×wall (in)", "Grade", "Top–shoe (mMD)", "Burst (psi)", "Collapse (psi)", "Body yield (klbf)", "LOT (ppg)"],
                 [[r["name"], f"{r['od']}×{r['wall']}", r["grade"], f"{r['top_md']:,.0f}–{r['shoe_md']:,.0f}", f"{r['burst']:,.0f}",
                   f"{r['collapse']:,.0f}", f"{r['body_yield']/1000:,.0f}", f"{r['lot_emw']:.2f}"] for r in rows]))
    parts.append("<h2>Drillstring</h2>" + _table(["Component", "OD (in)", "ID (in)", "Weight (lb/ft)", "Length (m)"],
                 [[c["name"], c["od"], c["id"], c["weight"], c["length_m"]] for c in p["drillstring"]]))
    try:
        plan = model.cost_plan(p)
        parts.append("<h2>Time & cost (deterministic)</h2>" + _table(["Section", "Days", "Cost (MUSD)"],
                     [[s["section"], f"{s['days']:.1f}", f"{s['cost']/1e6:.2f}"] for s in plan["sections"]] +
                     [["Total incl. mobilisation", f"{plan['total_days']:.1f}", f"{plan['total_cost']/1e6:.2f}"]]))
    except Exception as exc:  # report must still render
        parts.append(f"<p>Cost plan unavailable: {E(str(exc))}</p>")
    parts.append("<div class='foot'>Screening-level results from Well Planning App. Verify with qualified engineers and approved software before operational use.</div>")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{E(h['well_name'])} engineering summary</title><style>{css}</style></head><body>{''.join(parts)}</body></html>"
