"""Session state: one project dict, a revision counter baked into every widget
key, and snapshot-based data editors.

Why: Streamlit ignores ``value=`` on keyed widgets once state exists, and a
keyed ``data_editor`` replays its stored deltas onto whatever base frame it is
given. Loading/resetting a project bumps ``ks_rev`` so every widget and editor
is recreated from the project; editors always receive the same base snapshot
within a revision so added rows are never duplicated.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import model

PKEY = "ks_project"
REV = "ks_rev"


def init():
    if PKEY not in st.session_state:
        st.session_state[PKEY] = model.new_project()
    st.session_state.setdefault(REV, 0)
    st.session_state.setdefault("ks_page", "studio")


def project():
    return st.session_state[PKEY]


def rev():
    return st.session_state.get(REV, 0)


def bump():
    """Invalidate all widget/editor state after a project load or reset."""
    old = rev()
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and (k.endswith(f"_r{old}") or k.startswith("ks_base_")):
            del st.session_state[k]
    st.session_state[REV] = old + 1


def replace_project(p):
    st.session_state[PKEY] = p
    bump()


def key(*parts):
    return "ks_" + "_".join(str(x) for x in parts) + f"_r{rev()}"


def num(label, section, field, container=None, step=None, fmt=None, min_value=None, max_value=None,
        help=None, integer=False):
    c = container or st
    p = project()
    cur = p[section][field]
    kw = {}
    if min_value is not None:
        kw["min_value"] = int(min_value) if integer else float(min_value)
    if max_value is not None:
        kw["max_value"] = int(max_value) if integer else float(max_value)
    if step is not None:
        kw["step"] = int(step) if integer else float(step)
    if fmt:
        kw["format"] = fmt
    v = c.number_input(label, value=int(cur) if integer else float(cur), key=key(section, field),
                       help=help, **kw)
    p[section][field] = int(v) if integer else float(v)
    return p[section][field]


def select(label, section, field, options, container=None, format_func=None, help=None):
    c = container or st
    p = project()
    cur = p[section][field]
    idx = options.index(cur) if cur in options else 0
    v = c.selectbox(label, options, index=idx, key=key(section, field),
                    format_func=format_func or (lambda x: str(x)), help=help)
    p[section][field] = v
    return v


def text(label, section, field, container=None, help=None):
    c = container or st
    p = project()
    v = c.text_input(label, value=str(p[section][field]), key=key(section, field), help=help)
    p[section][field] = v
    return v


def toggle(label, section, field, container=None, help=None):
    c = container or st
    p = project()
    v = c.checkbox(label, value=bool(p[section][field]), key=key(section, field), help=help)
    p[section][field] = bool(v)
    return v


def table_rev(table_id):
    return st.session_state.get(f"ks_trev_{table_id}", 0)


def bump_table(table_id):
    st.session_state[f"ks_trev_{table_id}"] = table_rev(table_id) + 1


def editor(table_id, records, columns, column_config=None, num_rows="dynamic", height=None,
           container=None, setter=None, dropna_cols=None):
    """Snapshot-based data editor. ``records`` is the project list; the edited
    rows are written back through ``setter(list_of_dicts)``."""
    c = container or st
    base_key = f"ks_base_{table_id}_{rev()}_{table_rev(table_id)}"
    if base_key not in st.session_state:
        st.session_state[base_key] = pd.DataFrame(records, columns=columns)
    kw = {"height": height} if height else {}
    df = c.data_editor(st.session_state[base_key], key=key("ed", table_id, table_rev(table_id)),
                       num_rows=num_rows, column_config=column_config or {}, use_container_width=True,
                       hide_index=True, **kw)
    if dropna_cols:
        df = df.dropna(subset=dropna_cols)
    rows = df.to_dict("records")
    clean = []
    for r in rows:
        clean.append({k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()})
    if setter:
        setter(clean)
    return clean


def set_table(table_id, section_path, new_records):
    """Programmatic table replacement (e.g. generated from a plan)."""
    p = project()
    target = p
    for part in section_path[:-1]:
        target = target[part]
    target[section_path[-1]] = new_records
    bump_table(table_id)
