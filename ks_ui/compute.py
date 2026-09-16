"""Cached computations keyed by a deterministic md5 of the project JSON."""
from __future__ import annotations

import json

import streamlit as st

from . import model


@st.cache_data(show_spinner=False, max_entries=64)
def _summary(blob: str):
    return model.operation_summary(json.loads(blob))


def summary(p):
    res = _summary(model.project_to_json(p))
    return res


@st.cache_data(show_spinner=False, max_entries=16)
def _cost_mc(blob: str):
    return model.cost_mc(json.loads(blob))


def cost_mc(p):
    return _cost_mc(json.dumps({"cost": p["cost"]}, sort_keys=True, default=float))
