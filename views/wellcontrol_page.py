"""06 Well control: kill sheet, influx, MAASP, kick tolerance, volumetric."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ks_engine.units import FT2M

from .. import model, state, theme


def kill_sheet_html(p, wc):
    s = wc["schedule"]
    rows = "".join(f"<tr><td>{st_:,.0f}</td><td>{md*FT2M:,.0f}</td><td>{pr:,.0f}</td></tr>"
                   for st_, md, pr in zip(s["strokes"], s["md"], s["pressure"]))
    h = p["header"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Kill sheet {html.escape(h['well_name'])}</title>
<style>body{{font-family:'IBM Plex Sans',Arial,sans-serif;color:#1B2A36;margin:28px;max-width:780px}}h1{{color:#00243D;font-size:20px}}
table{{border-collapse:collapse;width:100%;margin:10px 0}}td,th{{border:1px solid #DCE3E8;padding:4px 8px;text-align:right}}th{{background:#F4F6F8}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:4px 24px}}.grid div{{display:flex;justify-content:space-between;border-bottom:1px solid #eee}}
@media print{{body{{margin:10mm}}}}</style></head><body>
<h1>Wait-and-weight kill sheet: {html.escape(h['well_name'])}</h1>
<div class="grid">
<div><span>Bit depth MD / TVD</span><b>{p['opcase']['bit_md_m']:,.0f} m / {wc['tvd_ft']*FT2M:,.0f} m</b></div>
<div><span>Original mud weight</span><b>{p['fluid']['mud_ppg']:.2f} ppg</b></div>
<div><span>SIDPP / SICP</span><b>{p['well_control']['sidpp']:,.0f} / {p['well_control']['sicp']:,.0f} psi</b></div>
<div><span>Kill mud weight</span><b>{wc['kmw']:.2f} ppg</b></div>
<div><span>SCR pressure</span><b>{p['well_control']['scr_psi']:,.0f} psi @ {p['well_control']['scr_spm']:.0f} spm</b></div>
<div><span>ICP / FCP</span><b>{s['icp']:,.0f} / {s['fcp']:,.0f} psi</b></div>
<div><span>Strokes surface to bit</span><b>{s['strokes_to_bit']:,.0f}</b></div>
<div><span>MAASP (current MW)</span><b>{wc['maasp']:,.0f} psi</b></div>
</div>
<table><tr><th>Strokes</th><th>KMW front MD (m)</th><th>Drill-pipe pressure (psi)</th></tr>{rows}</table>
<p style="font-size:11px;color:#5B6B78">Deviated-well schedule: friction interpolated by string volume, hydrostatic by TVD. Screening tool; verify against the approved well control procedure.</p>
</body></html>"""


def render():
    p = state.project()
    st.markdown(theme.header_html("Well control", "Kill sheet, influx identification, MAASP and kick tolerance"), unsafe_allow_html=True)
    traj, plan = model.trajectory_m(p)
    if traj is None:
        st.error(plan.message)
        return
    a, b, c, d = st.columns(4)
    state.num("Bit depth (m MD)", "opcase", "bit_md_m", a, step=10.0, min_value=1.0)
    state.num("SIDPP (psi)", "well_control", "sidpp", b, step=10.0, min_value=0.0)
    state.num("SICP (psi)", "well_control", "sicp", c, step=10.0, min_value=0.0)
    state.num("Pit gain (bbl)", "well_control", "pit_gain", d, step=1.0, min_value=0.1)
    state.num("Slow circulating rate pressure (psi)", "well_control", "scr_psi", a, step=10.0, min_value=1.0)
    state.num("SCR pump rate (spm)", "well_control", "scr_spm", b, step=1.0, min_value=1.0)
    state.num("Trip margin on KMW (ppg)", "well_control", "margin_ppg", c, step=0.05, min_value=0.0)
    state.num("Pump output (bbl/stk)", "rig", "pump_output_bbl_stk", d, step=0.005, fmt="%.4f", min_value=0.001)

    wc = model.well_control_calc(p, traj)
    s = wc["schedule"]
    st.markdown(theme.metrics_html([
        ("Kill mud weight", f"{wc['kmw']:.2f}", "ppg"),
        ("Initial / final circulating", f"{s['icp']:,.0f} / {s['fcp']:,.0f}", "psi"),
        ("Strokes surface to bit", f"{s['strokes_to_bit']:,.0f}", f"stk, {wc['string_volume_bbl']:,.0f} bbl"),
        ("MAASP", f"{wc['maasp']:,.0f}", f"psi, LOT {wc['lot']:.2f} ppg"),
    ]), unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = go.Figure(go.Scatter(x=s["strokes"], y=s["pressure"], mode="lines+markers", line=dict(color=theme.NAVY), name="Drill-pipe pressure"))
        fig.add_hline(y=s["fcp"], line=dict(color=theme.MOSS, dash="dash"), annotation_text="FCP")
        theme.plotly_layout(fig, 360, legend=False)
        fig.update_xaxes(title="Strokes pumped")
        fig.update_yaxes(title="Drill-pipe pressure (psi)")
        st.plotly_chart(fig, use_container_width=True, key=state.key("wc", "kill"))
        st.download_button("Download printable kill sheet (HTML)", kill_sheet_html(p, wc).encode(), f"kill_sheet_{p['header']['well_name']}.html",
                           "text/html", key=state.key("wc", "dl"))
    with c2:
        inf = wc["influx"]
        st.markdown(theme.check_html({"check": "Influx type", "status": "fail" if inf["type"] == "gas" else "warn", "value": f"{inf['density_ppg']:.2f} ppg",
                                      "limit": "gas < 3, oil 3-7, water > 7", "note": f"Likely {inf['type']}; influx height {inf['height_ft']*FT2M:,.0f} m"}),
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({"Strokes": s["strokes"].round(0), "MD (m)": (s["md"] * FT2M).round(0), "DPP (psi)": s["pressure"].round(0)}),
                     hide_index=True, use_container_width=True, height=260)

    st.subheader("Kick tolerance")
    a, b, c = st.columns(3)
    state.num("Kick intensity over pore (ppg)", "well_control", "kick_intensity_ppg", a, step=0.1, min_value=0.0)
    state.num("Safety margin on MAASP (psi)", "well_control", "safety_psi", b, step=25.0, min_value=0.0)
    kt = wc["kick_tolerance"]
    status = "pass" if kt["volume_bbl"] >= 50 else ("warn" if kt["volume_bbl"] >= 25 else "fail")
    c.markdown(theme.check_html({"check": "Kick tolerance volume", "status": status, "value": f"{kt['volume_bbl']:,.1f} bbl",
                                 "limit": "50 bbl typical minimum", "note": f"Governed by {kt['limit']}; pore at bit {wc['pore_td']:.2f} ppg"}),
               unsafe_allow_html=True)

    st.subheader("Gas migration and volumetric method")
    a, b, c = st.columns(3)
    state.num("Shut-in pressure rise (psi)", "well_control", "migration_psi", a, step=10.0, min_value=0.0)
    state.num("Over time (hr)", "well_control", "migration_hr", b, step=0.1, min_value=0.01)
    state.num("Working pressure increment (psi)", "well_control", "working_psi", c, step=10.0, min_value=10.0)
    st.caption(f"Estimated migration velocity {wc['migration_fthr']*FT2M:,.0f} m/hr ({wc['migration_fthr']:,.0f} ft/hr).")
    if wc["volumetric"]:
        st.dataframe(pd.DataFrame(wc["volumetric"]).rename(columns={"cycle": "Cycle", "casing_pressure_hold_psi": "Hold casing pressure (psi)",
                                                                   "bleed_bbl": "Bleed per cycle (bbl)", "cumulative_bbl": "Cumulative (bbl)"}).round(1),
                     hide_index=True, use_container_width=True)
    else:
        st.warning("Casing pressure after safety and working margins already exceeds MAASP. Use a different well-control method.")
