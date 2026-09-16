"""Session state with explicit Apply.

Rules
* The project dict is the single source of truth, shared by every page.
* Inputs live inside ``edit_form`` blocks. Typing only changes the form; the
  project changes when the form's Apply button is pressed.
* After Apply the change is logged ("Data modified"), autosaved to disk and
  every widget is rebuilt from the project, so no page can show or write back
  stale values.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from . import model, persist

PKEY = "ks_project"
REV = "ks_rev"
LOG = "ks_changes"        # list of {"section", "fields", "time"} since load/reset
SAVED = "ks_saved_rev"    # change count at last file download
FLASH = "ks_flash"
_PENDING = "_ks_pending"  # list of (label, getter, setter, value) while a form renders


# ---------------------------------------------------------------------------
# project lifecycle
# ---------------------------------------------------------------------------
def init():
    ss = st.session_state
    if PKEY in ss:
        return
    sid = st.query_params.get("sid")
    restored = persist.load(sid) if persist.valid_sid(sid) else None
    if restored:
        ss[PKEY], meta = restored
        ss[LOG] = meta.get("changes", [])
        ss[SAVED] = meta.get("saved", len(ss[LOG]))
        ss["ks_page"] = meta.get("page", "studio")
        ss[FLASH] = "Your last applied design was restored."
    else:
        sid = sid if persist.valid_sid(sid) else persist.new_sid()
        ss[PKEY] = model.new_project()
        ss[LOG] = []
        ss[SAVED] = 0
        ss["ks_page"] = st.query_params.get("page", "studio")
    ss["ks_sid"] = sid
    st.query_params["sid"] = sid
    ss.setdefault(REV, 0)


def project():
    return st.session_state[PKEY]


def rev():
    return st.session_state.get(REV, 0)


def autosave():
    ss = st.session_state
    persist.save(ss.get("ks_sid"), ss[PKEY], {"changes": ss.get(LOG, [])[-200:], "saved": ss.get(SAVED, 0),
                                               "page": ss.get("ks_page", "studio")})


def bump():
    """Rebuild every widget and table from the project on the next run."""
    old = rev()
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and (k.endswith(f"_r{old}") or k.startswith("ks_base_")):
            del st.session_state[k]
    st.session_state[REV] = old + 1


def replace_project(p, reason="Project loaded"):
    ss = st.session_state
    ss[PKEY] = p
    ss[LOG] = []
    ss[SAVED] = 0
    ss[FLASH] = reason
    bump()
    autosave()


def go_to(page_id):
    st.session_state["ks_page"] = page_id
    st.query_params["page"] = page_id
    for k in [k for k in st.session_state.keys() if isinstance(k, str) and k.startswith("ks_base_")]:
        del st.session_state[k]
    autosave()


def mark_saved():
    st.session_state[SAVED] = len(st.session_state.get(LOG, []))
    autosave()


def status():
    """(modified_since_load, unsaved_to_file, last_change or None)."""
    log = st.session_state.get(LOG, [])
    return bool(log), len(log) > st.session_state.get(SAVED, 0), (log[-1] if log else None)


def key(*parts):
    return "ks_" + "_".join(str(x) for x in parts) + f"_r{rev()}"


def record_change(section, fields):
    st.session_state[LOG].append({"section": section, "fields": fields, "time": dt.datetime.now().strftime("%H:%M:%S")})
    st.session_state[FLASH] = f"Data modified: {section} ({', '.join(fields[:4])}{'…' if len(fields) > 4 else ''}). All pages now use the new values."


# ---------------------------------------------------------------------------
# forms
# ---------------------------------------------------------------------------
class edit_form:
    """``with state.edit_form("casing", "Casing program"):`` – inputs inside
    are staged and written to the project only when Apply is pressed."""

    def __init__(self, form_id, section, container=None, button="Apply", note=True):
        self.fid, self.section, self.c, self.button, self.note = form_id, section, container or st, button, note

    def __enter__(self):
        if st.session_state.get(_PENDING) is not None:
            raise RuntimeError("edit_form blocks cannot be nested")
        self._form = self.c.form(key=key("form", self.fid), border=True)
        self._form.__enter__()
        st.session_state[_PENDING] = []
        return self

    def __exit__(self, exc_type, exc, tb):
        pending = st.session_state.get(_PENDING) or []
        st.session_state[_PENDING] = None
        if exc_type is not None:
            self._form.__exit__(exc_type, exc, tb)
            return False
        a, b = st.columns([1, 3])
        clicked = a.form_submit_button(self.button, type="primary", use_container_width=True)
        if self.note:
            b.caption("Changes take effect for every page when you press Apply.")
        self._form.__exit__(None, None, None)
        if clicked:
            changed = [label for label, getter, setter, value in pending if _differs(getter(), value)]
            for label, getter, setter, value in pending:
                setter(value)
            if changed:
                record_change(self.section, changed)
            else:
                st.session_state[FLASH] = f"No changes to apply in {self.section}."
            bump()
            autosave()
            st.rerun()
        return False


def _differs(a, b):
    if isinstance(a, list) or isinstance(b, list):
        return _norm(a) != _norm(b)
    try:
        return abs(float(a) - float(b)) > 1e-12
    except (TypeError, ValueError):
        return a != b


def _norm(v):
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    try:
        return round(float(v), 9)
    except (TypeError, ValueError):
        return v


def stage(label, getter, setter, value):
    """Stage a value (inside a form) or write it immediately (outside)."""
    pending = st.session_state.get(_PENDING)
    if pending is None:
        setter(value)
    else:
        pending.append((label, getter, setter, value))
    return value


def _field(section, field):
    p = project()
    return (lambda: p[section][field]), (lambda v: p[section].__setitem__(field, v))


# ---------------------------------------------------------------------------
# widgets bound to project fields
# ---------------------------------------------------------------------------
def num(label, section, field, container=None, step=None, fmt=None, min_value=None, max_value=None,
        help=None, integer=False):
    c = container or st
    cur = project()[section][field]
    cast = int if integer else float
    kw = {k: cast(v) for k, v in (("min_value", min_value), ("max_value", max_value), ("step", step)) if v is not None}
    val = cast(cur)
    if "min_value" in kw:
        val = max(val, kw["min_value"])
    if "max_value" in kw:
        val = min(val, kw["max_value"])
    if fmt:
        kw["format"] = fmt
    v = c.number_input(label, value=val, key=key(section, field), help=help, **kw)
    return stage(label, *_field(section, field), cast(v))


def select(label, section, field, options, container=None, format_func=None, help=None):
    c = container or st
    cur = project()[section][field]
    idx = options.index(cur) if cur in options else 0
    v = c.selectbox(label, options, index=idx, key=key(section, field), format_func=format_func or str, help=help)
    return stage(label, *_field(section, field), v)


def text(label, section, field, container=None, help=None):
    c = container or st
    v = c.text_input(label, value=str(project()[section][field]), key=key(section, field), help=help)
    return stage(label, *_field(section, field), v)


def toggle(label, section, field, container=None, help=None):
    c = container or st
    v = c.checkbox(label, value=bool(project()[section][field]), key=key(section, field), help=help)
    return stage(label, *_field(section, field), bool(v))


def table_rev(table_id):
    return st.session_state.get(f"ks_trev_{table_id}", 0)


def bump_table(table_id):
    st.session_state[f"ks_trev_{table_id}"] = table_rev(table_id) + 1


def editor(table_id, records, columns, column_config=None, num_rows="dynamic", height=None,
           container=None, setter=None, dropna_cols=None, label=None, getter=None):
    """Data editor. Inside a form the edited rows are staged and committed
    through ``setter`` on Apply."""
    c = container or st
    base_key = f"ks_base_{table_id}_{rev()}_{table_rev(table_id)}"
    widget_key = key("ed", table_id, table_rev(table_id))
    if base_key not in st.session_state or widget_key not in st.session_state:
        st.session_state[base_key] = pd.DataFrame(records, columns=columns)
    kw = {"height": height} if height else {}
    df = c.data_editor(st.session_state[base_key], key=widget_key, num_rows=num_rows, column_config=column_config or {},
                       use_container_width=True, hide_index=True, **kw)
    if dropna_cols:
        df = df.dropna(subset=dropna_cols)
    clean = [{k: (None if (isinstance(v, float) and pd.isna(v)) else (v.item() if hasattr(v, "item") else v))
              for k, v in r.items()} for r in df.to_dict("records")]
    snapshot = [{k: r.get(k) for k in columns} for r in records]
    n_changed = sum(1 for a, b in zip(clean, snapshot) if _norm(a) != _norm(b)) + abs(len(clean) - len(snapshot))
    name = label or table_id.replace("_", " ").capitalize()
    stage(f"{name} table: {n_changed} row{'s' if n_changed != 1 else ''} changed", getter or (lambda: snapshot),
          setter or (lambda r: None), clean)
    return clean


def set_table(table_id, section_path, new_records, section_label=None):
    """Programmatic table replacement (import, copy plan), logged as a change."""
    p = project()
    target = p
    for part in section_path[:-1]:
        target = target[part]
    target[section_path[-1]] = new_records
    bump_table(table_id)
    record_change(section_label or table_id.replace("_", " ").capitalize(), [f"{len(new_records)} rows replaced"])
    autosave()


def flash():
    msg = st.session_state.pop(FLASH, None)
    if msg:
        (st.info if msg.startswith("No changes") else st.success)(msg)
