"""Minimal Streamlit / Plotly stand-ins so every page can be executed
headless where the real packages are unavailable. Widgets return their
default value; layout calls return containers with the same API."""
from __future__ import annotations

import sys
import types


class _Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)


class _SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


def make_streamlit():
    st = types.ModuleType("streamlit")
    st.session_state = _SessionState()
    st.CALLS = []
    noop = lambda *a, **k: None
    for n in ("markdown", "caption", "subheader", "error", "warning", "info", "success", "write", "dataframe",
              "plotly_chart", "set_page_config", "rerun", "json", "code", "title", "divider", "metric", "table"):
        setattr(st, n, (lambda nm: lambda *a, **k: st.CALLS.append(nm))(n))
    st.download_button = lambda label, data, *a, **k: (st.CALLS.append("download"), isinstance(data, (bytes, str)) or (_ for _ in ()).throw(TypeError("download data")))[0] and False
    def number_input(label, value=0.0, min_value=None, max_value=None, step=None, **k):
        # mirror Streamlit's hard errors: bounds and mixed int/float types
        nums = [x for x in (value, min_value, max_value, step) if x is not None]
        if len({type(x) for x in nums if not isinstance(x, bool)} - {int, float}) or \
                (any(isinstance(x, int) for x in nums) and any(isinstance(x, float) for x in nums)):
            raise TypeError(f"number_input '{label}': mixed numeric types {[type(x).__name__ for x in nums]}")
        if min_value is not None and value < min_value or max_value is not None and value > max_value:
            raise ValueError(f"number_input '{label}': value {value} outside [{min_value}, {max_value}]")
        return value
    st.number_input = number_input
    st.text_input = lambda label, value="", **k: value
    st.text_area = lambda label, value="", **k: value
    st.checkbox = lambda label, value=False, **k: value
    st.toggle = st.checkbox
    st.selectbox = lambda label, options, index=0, **k: list(options)[index] if len(list(options)) else None
    st.radio = lambda label, options, index=0, **k: list(options)[index]
    def slider(label, min_value=None, max_value=None, value=None, step=None, **k):
        vals = value if isinstance(value, (tuple, list)) else [value]
        for v in vals:
            if v is not None and min_value is not None and not (min_value <= v <= max_value):
                raise ValueError(f"slider '{label}': {v} outside [{min_value}, {max_value}]")
        return value
    st.slider = slider
    st.multiselect = lambda label, options, default=None, **k: list(default or [])
    st.select_slider = lambda label, options=(), value=None, **k: value
    st.button = lambda *a, **k: False
    st.form_submit_button = lambda *a, **k: False
    st.file_uploader = lambda *a, **k: None
    st.data_editor = lambda df, **k: df.copy()
    st.columns = lambda spec, **k: [_Ctx(st) for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs = lambda names: [_Ctx(st) for _ in names]
    st.expander = lambda *a, **k: _Ctx(st)
    st.form = lambda *a, **k: _Ctx(st)
    st.container = lambda *a, **k: _Ctx(st)
    st.sidebar = _Ctx(st)
    st.spinner = lambda *a, **k: _Ctx(st)

    def cache_data(fn=None, **k):
        if fn is None:
            return lambda f: f
        return fn
    st.cache_data = cache_data

    cc = types.SimpleNamespace()
    for n in ("NumberColumn", "TextColumn", "SelectboxColumn", "CheckboxColumn", "Column"):
        setattr(cc, n, lambda *a, **k: None)
    st.column_config = cc
    return st


class _Fig:
    def __init__(self, *a, **k):
        self.data = list(a[0]) if a and isinstance(a[0], list) else ([a[0]] if a else [])

    def add_trace(self, t, *a, **k):
        self.data.append(t)
        return self

    def __getattr__(self, name):
        return lambda *a, **k: self


def make_plotly():
    plotly = types.ModuleType("plotly")
    go = types.ModuleType("plotly.graph_objects")
    go.Figure = _Fig
    for n in ("Scatter", "Scatter3d", "Bar", "Histogram", "Surface", "Mesh3d", "Heatmap", "Pie", "Waterfall", "Indicator", "Box"):
        setattr(go, n, (lambda nm: lambda *a, **k: (nm, k))(n))
    sub = types.ModuleType("plotly.subplots")
    sub.make_subplots = lambda *a, **k: _Fig()
    plotly.graph_objects = go
    plotly.subplots = sub
    return {"plotly": plotly, "plotly.graph_objects": go, "plotly.subplots": sub}


def install():
    try:
        import streamlit  # noqa: F401
        import plotly  # noqa: F401
        return False
    except ImportError:
        sys.modules["streamlit"] = make_streamlit()
        sys.modules.update(make_plotly())
        return True
