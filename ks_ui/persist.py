"""Autosave: the applied project is written to disk after every Apply, load
or reset, keyed by a session id kept in the page URL (?sid=...). Reopening or
refreshing the same URL restores the design, so nothing depends on
Streamlit's in-memory session surviving."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid

from . import model

DIR = os.environ.get("WELLPLAN_AUTOSAVE_DIR",
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".autosave"))
_SID = re.compile(r"^[a-f0-9]{32}$")


def new_sid():
    return uuid.uuid4().hex


def valid_sid(sid):
    return isinstance(sid, str) and bool(_SID.match(sid))


def path(sid):
    return os.path.join(DIR, f"{sid}.json")


def save(sid, project, meta):
    if not valid_sid(sid):
        return False
    try:
        os.makedirs(DIR, exist_ok=True)
        blob = json.dumps({"project": project, "meta": meta}, default=float)
        fd, tmp = tempfile.mkstemp(dir=DIR, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(blob)
        os.replace(tmp, path(sid))  # atomic: never leaves a half-written file
        return True
    except OSError:
        return False


def load(sid):
    if not valid_sid(sid) or not os.path.exists(path(sid)):
        return None
    try:
        with open(path(sid)) as f:
            data = json.load(f)
        project = model.project_from_json(json.dumps(data["project"]))
        return project, data.get("meta", {})
    except (OSError, ValueError, KeyError, TypeError):
        return None
