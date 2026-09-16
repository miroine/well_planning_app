"""Shared Plotly figures (no Streamlit calls)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from ks_engine import trajectory as tj

from . import model, theme


def _tube(traj, radius_fn, n_theta=16, every=2, exaggeration=1.0):
    """Parametric tube surface around a trajectory (EOU visual)."""
    md = traj["md"][::every]
    s = tj.interpolate_at_md(traj, md)
    t = tj._tangent(s["inc"], s["azi"])
    ref = np.array([0.0, 0.0, 1.0])
    X, Y, Z = [], [], []
    theta = np.linspace(0, 2 * np.pi, n_theta)
    for k in range(len(md)):
        tk = t[k]
        a = ref if abs(np.dot(tk, ref)) < 0.95 else np.array([1.0, 0.0, 0.0])
        u = np.cross(tk, a)
        u /= np.linalg.norm(u)
        v = np.cross(tk, u)
        r = radius_fn(md[k]) * exaggeration
        pts = np.array([s["north"][k], s["east"][k], s["tvd"][k]])[:, None] + r * (np.outer(u, np.cos(theta)) + np.outer(v, np.sin(theta)))
        X.append(pts[1])
        Y.append(pts[0])
        Z.append(pts[2])
    return np.array(X), np.array(Y), np.array(Z)


def well_3d(p, traj, bit_md=None, show_eou=True, show_offsets=True, show_actual=True, height=520,
            eou_exaggeration=3.0, camera=None):
    fig = go.Figure()
    lim = p["limits"]
    if show_eou:
        X, Y, Z = _tube(traj, lambda m: tj.uncertainty_radius(m, lim["anticol_r0"], lim["anticol_growth"]),
                        exaggeration=eou_exaggeration)
        fig.add_trace(go.Surface(x=X, y=Y, z=Z, showscale=False, opacity=0.14, hoverinfo="skip",
                                 colorscale=[[0, theme.MOSS_LIGHT], [1, theme.MOSS_LIGHT]], name="EOU"))
    fig.add_trace(go.Scatter3d(x=traj["east"], y=traj["north"], z=traj["tvd"], mode="lines",
                               line=dict(color=theme.TRAJ, width=6), name="Planned",
                               customdata=np.stack([traj["md"], traj["inc"], traj["azi"]], axis=-1),
                               hovertemplate="MD %{customdata[0]:.0f} m<br>TVD %{z:.0f} m<br>Inc %{customdata[1]:.1f}°"
                                             "<br>Azi %{customdata[2]:.1f}°<extra></extra>"))
    if show_actual:
        act = model.actual_trajectory_m(p)
        if act is not None:
            fig.add_trace(go.Scatter3d(x=act["east"], y=act["north"], z=act["tvd"], mode="lines+markers",
                                       line=dict(color=theme.AMBER, width=4), marker=dict(size=2.5),
                                       name="Actual survey"))
    if show_offsets:
        for o in model.offset_trajectories_m(p):
            fig.add_trace(go.Scatter3d(x=o["east"], y=o["north"], z=o["tvd"], mode="lines",
                                       line=dict(color="#6E8798", width=3, dash="dash"), name=o["name"]))
    for tg in p.get("targets", []):
        try:
            fig.add_trace(go.Scatter3d(x=[tg["east"]], y=[tg["north"]], z=[tg["tvd"]], mode="markers+text",
                                       marker=dict(size=7, color="#4FC1B0"), text=[tg["name"]],
                                       textposition="middle right", textfont=dict(color="#CFE9E4"),
                                       name=tg["name"], showlegend=False))
        except (KeyError, TypeError):
            continue
    if bit_md is not None:
        b = tj.interpolate_at_md(traj, [bit_md])
        fig.add_trace(go.Scatter3d(x=b["east"], y=b["north"], z=b["tvd"], mode="markers+text",
                                   marker=dict(size=6, color=theme.AMBER, line=dict(color="#fff", width=1)),
                                   text=[f"Bit {bit_md:,.0f} mMD"], textposition="middle right",
                                   textfont=dict(color="#fff"), name="Bit", showlegend=False))
    theme.plotly_layout(fig, height=height, dark=True)
    axis = dict(backgroundcolor=theme.NAVY, gridcolor="#1E4461", zerolinecolor="#1E4461", color="#8FA6B6")
    fig.update_layout(scene=dict(xaxis=dict(title="East (m)", **axis), yaxis=dict(title="North (m)", **axis),
                                 zaxis=dict(title="TVD (m)", autorange="reversed", **axis),
                                 aspectmode="data", camera=camera or dict(eye=dict(x=1.5, y=1.5, z=0.6))),
                      margin=dict(l=0, r=0, t=10, b=0))
    return fig


def plan_view(p, traj, bit_md=None, height=520, dark=True):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=traj["east"], y=traj["north"], mode="lines", line=dict(color=theme.TRAJ, width=3), name="Planned"))
    act = model.actual_trajectory_m(p)
    if act is not None:
        fig.add_trace(go.Scatter(x=act["east"], y=act["north"], mode="lines+markers", line=dict(color=theme.AMBER), name="Actual"))
    for o in model.offset_trajectories_m(p):
        fig.add_trace(go.Scatter(x=o["east"], y=o["north"], mode="lines", line=dict(color="#6E8798", dash="dash"), name=o["name"]))
    for tg in p.get("targets", []):
        th = np.linspace(0, 2 * np.pi, 60)
        r = float(tg.get("radius") or 0)
        fig.add_trace(go.Scatter(x=tg["east"] + r * np.cos(th), y=tg["north"] + r * np.sin(th), mode="lines",
                                 line=dict(color="#4FC1B0"), name=tg["name"], showlegend=False))
    if bit_md is not None:
        b = tj.interpolate_at_md(traj, [bit_md])
        fig.add_trace(go.Scatter(x=b["east"], y=b["north"], mode="markers", marker=dict(color=theme.AMBER, size=11), name="Bit"))
    theme.plotly_layout(fig, height=height, dark=dark)
    fig.update_xaxes(title="East (m)")
    fig.update_yaxes(title="North (m)", scaleanchor="x", scaleratio=1)
    return fig


def section_view(p, traj, bit_md=None, height=520, dark=True, show_casing=True):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=traj["vs"], y=traj["tvd"], mode="lines", line=dict(color=theme.TRAJ, width=3), name="Planned"))
    act = model.actual_trajectory_m(p)
    if act is not None:
        fig.add_trace(go.Scatter(x=act["vs"], y=act["tvd"], mode="lines+markers", line=dict(color=theme.AMBER), name="Actual"))
    h = p["header"]
    for o in model.offset_trajectories_m(p):
        vs = tj.vertical_section(o["north"], o["east"], h["vs_azimuth"], h["surface_n"], h["surface_e"])
        fig.add_trace(go.Scatter(x=vs, y=o["tvd"], mode="lines", line=dict(color="#6E8798", dash="dash"), name=o["name"]))
    if show_casing:
        for c in model.casing_rows(p):
            s = tj.interpolate_at_md(traj, [c["shoe_md"]])
            vs = tj.vertical_section(s["north"], s["east"], h["vs_azimuth"], h["surface_n"], h["surface_e"])
            fig.add_trace(go.Scatter(x=vs, y=s["tvd"], mode="markers+text", marker=dict(symbol="triangle-left", size=11, color="#C9D6DF"),
                                     text=[c["name"].split(" ")[-1]], textposition="middle left", showlegend=False,
                                     textfont=dict(color="#C9D6DF" if dark else theme.INK, size=10)))
    for tg in p.get("targets", []):
        vs = tj.vertical_section([tg["north"]], [tg["east"]], h["vs_azimuth"], h["surface_n"], h["surface_e"])
        fig.add_trace(go.Scatter(x=vs, y=[tg["tvd"]], mode="markers+text", marker=dict(color="#4FC1B0", size=10),
                                 text=[tg["name"]], textposition="bottom center", showlegend=False))
    if bit_md is not None:
        b = tj.interpolate_at_md(traj, [bit_md])
        vs = tj.vertical_section(b["north"], b["east"], h["vs_azimuth"], h["surface_n"], h["surface_e"])
        fig.add_trace(go.Scatter(x=vs, y=b["tvd"], mode="markers", marker=dict(color=theme.AMBER, size=11), name="Bit"))
    theme.plotly_layout(fig, height=height, dark=dark)
    fig.update_xaxes(title=f"Vertical section @ {h['vs_azimuth']:.0f}° (m)")
    fig.update_yaxes(title="TVD (m)", autorange="reversed", scaleanchor="x", scaleratio=1)
    return fig


def schematic(p, traj, bit_md=None, height=720, depth_ref="MD"):
    """Wellbore schematic: half-section drawing with casing, cement, open
    hole, formation tops (TVD converted to MD), seabed and string at bit."""
    fig = go.Figure()
    rows = model.casing_rows(p)
    td_md = float(traj["md"][-1])
    h = p["header"]
    to_y = (lambda md: model.tvd_at_md_m(traj, md)) if depth_ref == "TVD" else (lambda md: md)
    seabed = h["rkb_elev_m"] + h["water_depth_m"]
    max_d = max([r["hole_in"] for r in rows] + [p["bit"]["size_in"]]) / 2 + 4
    # formations band (left)
    fs = sorted(p["formations"], key=lambda f: f["top_tvd"])
    palette = ["#E7EEF2", "#D8E4EA", "#EDE6D6", "#E3EBD5", "#F3E3D9", "#E1DDEB"]
    for i, f in enumerate(fs):
        top_tvd = float(f["top_tvd"])
        bot_tvd = float(fs[i + 1]["top_tvd"]) if i + 1 < len(fs) else float(traj["tvd"][-1])
        y0 = top_tvd if depth_ref == "TVD" else float(np.interp(top_tvd, traj["tvd"], traj["md"]))
        y1 = bot_tvd if depth_ref == "TVD" else float(np.interp(bot_tvd, traj["tvd"], traj["md"]))
        fig.add_shape(type="rect", x0=-max_d - 14, x1=-max_d - 2, y0=y0, y1=y1, fillcolor=palette[i % len(palette)],
                      line=dict(width=0.5, color=theme.LINE))
        fig.add_annotation(x=-max_d - 8, y=(y0 + y1) / 2, text=f["name"], showarrow=False, font=dict(size=10, color=theme.INK))
    fig.add_shape(type="line", x0=-max_d - 14, x1=max_d + 16, y0=to_y(seabed), y1=to_y(seabed),
                  line=dict(color=theme.MOSS, dash="dot"))
    fig.add_annotation(x=max_d + 16, y=to_y(seabed), text="Seabed", showarrow=False, xanchor="right", yshift=8,
                       font=dict(size=10, color=theme.MOSS))
    # open hole to TD
    last_shoe = rows[-1]["shoe_md"] if rows else 0.0
    oh = p["bit"]["size_in"] / 2
    for sgn in (-1, 1):
        fig.add_shape(type="line", x0=sgn * oh, x1=sgn * oh, y0=to_y(last_shoe), y1=to_y(td_md),
                      line=dict(color="#8A6D3B", width=1.5, dash="dot"))
    # casing strings, largest first
    for c in sorted(rows, key=lambda r: -r["od"]):
        ro, ri, rh = c["od"] / 2, c["id"] / 2, c["hole_in"] / 2
        y_top, y_shoe, y_toc = to_y(c["top_md"]), to_y(c["shoe_md"]), to_y(max(c.get("toc_md") or c["top_md"], c["top_md"]))
        for sgn in (-1, 1):
            fig.add_shape(type="rect", x0=sgn * ro, x1=sgn * rh, y0=y_toc, y1=y_shoe, fillcolor="#C8CDD2",
                          line=dict(width=0), opacity=0.9, layer="below")
            fig.add_shape(type="rect", x0=sgn * ri, x1=sgn * ro, y0=y_top, y1=y_shoe, fillcolor=theme.NAVY, line=dict(width=0))
            fig.add_shape(type="path", path=f"M {sgn*ro} {y_shoe} L {sgn*(ro+1.2)} {y_shoe} L {sgn*ro} {y_shoe - 0.012 * max(y_shoe, 500)} Z",
                          fillcolor=theme.NAVY, line=dict(width=0))
        fig.add_annotation(x=max_d + 2, y=y_shoe, xanchor="left", showarrow=False, align="left",
                           text=f"{c['name']} @ {c['shoe_md']:,.0f} mMD<br><span style='color:{theme.MUTED}'>{c['grade']} {c['weight_ppf']:.1f} ppf, LOT {c['lot_emw']:.1f} ppg</span>",
                           font=dict(size=10, color=theme.INK))
    if bit_md is not None:
        comps = p["drillstring"]
        bot = bit_md
        for k, c in enumerate(comps):
            top = max(bot - float(c["length_m"]), 0.0) if k < len(comps) - 1 else 0.0
            r = float(c["od"]) / 2
            fig.add_shape(type="rect", x0=-r, x1=r, y0=to_y(top), y1=to_y(bot),
                          fillcolor=theme.AMBER if c.get("in_bha", True) else "#9BB0BF", line=dict(width=0), opacity=0.85)
            bot = top
            if bot <= 0:
                break
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(opacity=0), showlegend=False, hoverinfo="skip"))
    theme.plotly_layout(fig, height=height, legend=False)
    y_bottom = to_y(td_md) * 1.03
    fig.update_yaxes(title=f"{depth_ref} (m RKB)", range=[y_bottom, 0])
    fig.update_xaxes(visible=False, range=[-max_d - 15, max_d + 26])
    return fig
