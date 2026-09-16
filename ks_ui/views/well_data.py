"""Well data: header, formations, targets, actual survey, offset wells,
drillstring & bit, fluid & rig."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from .. import state, theme

CC = st.column_config


def _import_csv(label, table_id, section_path, required, key_suffix):
    up = st.file_uploader(label, type=["csv", "txt"], key=state.key("up", key_suffix))
    if up is not None:
        try:
            df = pd.read_csv(io.StringIO(up.getvalue().decode("utf-8", errors="ignore")), sep=None, engine="python")
            df.columns = [c.strip().lower() for c in df.columns]
            alias = {"measured depth": "md", "md_m": "md", "inclination": "inc", "incl": "inc",
                     "azimuth": "azi", "az": "azi", "azim": "azi"}
            df = df.rename(columns={c: alias.get(c, c) for c in df.columns})
            missing = [c for c in required if c not in df.columns]
            if missing:
                st.error(f"Columns missing from file: {', '.join(missing)}. Expected {', '.join(required)}.")
                return
            recs = df[required].dropna().astype(float).sort_values(required[0]).to_dict("records")
            if st.button(f"Replace table with {len(recs)} imported rows", key=state.key("imp", key_suffix)):
                state.set_table(table_id, section_path, recs)
                st.rerun()
        except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
            st.error(f"Could not read the file: {exc}")


def render():
    p = state.project()
    st.markdown(theme.header_html("Well data", "Shared inputs used by every engineering module"), unsafe_allow_html=True)
    tabs = st.tabs(["Header", "Formations", "Targets", "Actual survey", "Offset wells", "Drillstring & bit", "Fluid & rig"])

    with tabs[0]:
        a, b, c = st.columns(3)
        state.text("Well name", "header", "well_name", a)
        state.text("Field", "header", "field", b)
        state.text("Rig", "header", "rig", c)
        state.text("Operator", "header", "operator", a)
        state.text("Planned spud date", "header", "spud_date", b)
        state.num("RKB elevation above MSL (m)", "header", "rkb_elev_m", c, step=1.0, min_value=0.0)
        state.num("Water depth (m)", "header", "water_depth_m", a, step=5.0, min_value=0.0, help="0 for land wells")
        state.num("Slot north offset (m)", "header", "surface_n", b, step=1.0)
        state.num("Slot east offset (m)", "header", "surface_e", c, step=1.0)
        state.num("Vertical section azimuth (°)", "header", "vs_azimuth", a, step=1.0, min_value=0.0, max_value=360.0)
        st.markdown(theme.note_html("Depths are metres from RKB. Engineering calculations run internally in field units (ft, lbf, psi, ppg)."), unsafe_allow_html=True)

    with tabs[1]:
        st.caption("Top TVD (m RKB), bulk density (g/cc), pore pressure (ppg EMW), Poisson's ratio, UCS (psi), friction angle (°), sonic DT and normal-trend DT (µs/ft) for the Eaton option.")
        state.editor("formations", p["formations"],
                     ["name", "top_tvd", "lithology", "rho", "pp", "nu", "ucs", "phi", "dt", "dt_n"],
                     {"name": CC.TextColumn("Formation"), "top_tvd": CC.NumberColumn("Top TVD (m)", min_value=0.0),
                      "lithology": CC.TextColumn("Lithology"), "rho": CC.NumberColumn("ρb (g/cc)", min_value=1.0, max_value=3.2, format="%.2f"),
                      "pp": CC.NumberColumn("Pore (ppg)", min_value=6.0, max_value=22.0, format="%.2f"),
                      "nu": CC.NumberColumn("ν", min_value=0.05, max_value=0.49, format="%.2f"),
                      "ucs": CC.NumberColumn("UCS (psi)", min_value=0.0), "phi": CC.NumberColumn("φ (°)", min_value=0.0, max_value=60.0),
                      "dt": CC.NumberColumn("DT"), "dt_n": CC.NumberColumn("DT normal")},
                     setter=lambda r: p.__setitem__("formations", sorted(r, key=lambda x: x["top_tvd"])),
                     dropna_cols=["top_tvd", "rho", "pp", "nu"])

    with tabs[2]:
        st.caption("Target centre in local coordinates (m) with tolerance radius.")
        state.editor("targets", p["targets"], ["name", "tvd", "north", "east", "radius"],
                     {"name": CC.TextColumn("Target"), "tvd": CC.NumberColumn("TVD (m)"), "north": CC.NumberColumn("North (m)"),
                      "east": CC.NumberColumn("East (m)"), "radius": CC.NumberColumn("Radius (m)", min_value=0.0)},
                     setter=lambda r: p.__setitem__("targets", r), dropna_cols=["tvd", "north", "east"])

    with tabs[3]:
        st.caption("Imported or existing survey stations (MD m, inclination °, azimuth °). Drawn against the plan in every view.")
        state.editor("actual_survey", p["actual_survey"], ["md", "inc", "azi"],
                     {"md": CC.NumberColumn("MD (m)", min_value=0.0), "inc": CC.NumberColumn("Inc (°)", min_value=0.0, max_value=180.0),
                      "azi": CC.NumberColumn("Azi (°)", min_value=0.0, max_value=360.0)},
                     setter=lambda r: p.__setitem__("actual_survey", r), dropna_cols=["md", "inc", "azi"])
        _import_csv("Import survey CSV (md, inc, azi)", "actual_survey", ["actual_survey"], ["md", "inc", "azi"], "act")

    with tabs[4]:
        st.caption("Offset wells described by slot offset and a build-hold profile.")
        state.editor("offsets", p["offset_wells"], ["name", "surface_n", "surface_e", "kop", "bur", "hold_inc", "azimuth", "td"],
                     {"name": CC.TextColumn("Well"), "surface_n": CC.NumberColumn("Slot N (m)"), "surface_e": CC.NumberColumn("Slot E (m)"),
                      "kop": CC.NumberColumn("KOP (m)", min_value=0.0), "bur": CC.NumberColumn("BUR (°/30 m)", min_value=0.1),
                      "hold_inc": CC.NumberColumn("Hold inc (°)", min_value=0.0, max_value=95.0),
                      "azimuth": CC.NumberColumn("Azimuth (°)"), "td": CC.NumberColumn("TD MD (m)", min_value=10.0)},
                     setter=lambda r: p.__setitem__("offset_wells", r), dropna_cols=["surface_n", "surface_e", "kop", "bur", "hold_inc", "azimuth", "td"])

    with tabs[5]:
        a, b, c = st.columns(3)
        state.num("Bit size (in)", "bit", "size_in", a, step=0.125, min_value=2.0)
        state.select("Bit type", "bit", "type", ["PDC", "Roller cone"], b)
        state.text("Nozzles (1/32 in, comma separated)", "bit", "nozzles", c)
        st.caption("Components from the bit upward. The last row runs to surface; its length is ignored. Weight is adjusted weight in air including tool joints.")
        state.editor("drillstring", p["drillstring"],
                     ["name", "od", "id", "tj_od", "weight", "length_m", "tensile_yield", "mu_torque", "in_bha"],
                     {"name": CC.TextColumn("Component"), "od": CC.NumberColumn("OD (in)", min_value=1.0, format="%.3f"),
                      "id": CC.NumberColumn("ID (in)", min_value=0.0, format="%.3f"), "tj_od": CC.NumberColumn("TJ OD (in)", format="%.3f"),
                      "weight": CC.NumberColumn("Weight (lb/ft)", min_value=0.1), "length_m": CC.NumberColumn("Length (m)", min_value=0.0),
                      "tensile_yield": CC.NumberColumn("Tensile yield (lbf)", min_value=0.0),
                      "mu_torque": CC.NumberColumn("Make-up torque (ft-lb)", min_value=0.0), "in_bha": CC.CheckboxColumn("BHA")},
                     setter=lambda r: p.__setitem__("drillstring", r), dropna_cols=["od", "id", "weight", "length_m"])

    with tabs[6]:
        a, b, c = st.columns(3)
        state.num("Mud weight (ppg)", "fluid", "mud_ppg", a, step=0.1, min_value=6.0, max_value=22.0)
        state.select("Rheology model", "fluid", "model", ["power_law", "bingham"], b,
                     format_func=lambda x: {"power_law": "Power law (API RP 13D)", "bingham": "Bingham plastic"}[x])
        state.num("Cuttings SG", "fluid", "cuttings_sg", c, step=0.05, min_value=1.5, max_value=3.5)
        st.markdown("**Fann 35 readings**")
        cols = st.columns(6)
        for col, fld in zip(cols, ["r600", "r300", "r200", "r100", "r6", "r3"]):
            state.num(f"θ{fld[1:]}", "fluid", fld, col, step=1.0, min_value=0.1)
        f = p["fluid"]
        st.caption(f"PV {f['r600']-f['r300']:.0f} cP, YP {2*f['r300']-f['r600']:.0f} lbf/100ft², LSYP {2*f['r3']-f['r6']:.0f} lbf/100ft²")
        st.markdown("**Rig**")
        a, b, c = st.columns(3)
        state.num("Travelling block weight (klbf)", "rig", "block_weight_klbf", a, step=5.0, min_value=0.0)
        state.num("Hookload capacity (klbf)", "rig", "hookload_capacity_klbf", b, step=50.0, min_value=1.0)
        state.num("Top drive torque limit (ft-lb)", "rig", "top_drive_torque", c, step=1000.0, min_value=1.0)
        state.num("Pump pressure rating (psi)", "rig", "pump_rating_psi", a, step=250.0, min_value=1.0)
        state.num("Max flow (gpm)", "rig", "max_flow_gpm", b, step=50.0, min_value=1.0)
        state.num("Pump output (bbl/stk)", "rig", "pump_output_bbl_stk", c, step=0.005, fmt="%.4f", min_value=0.001)
        state.num("Surface equipment loss (psi)", "rig", "surface_loss_psi", a, step=10.0, min_value=0.0)
        state.num("MWD / motor / RSS pressure drop (psi)", "rig", "tool_loss_psi", b, step=25.0, min_value=0.0)
