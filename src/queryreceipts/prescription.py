"""Prescriptions: capture requests the engine issues to a transport.

A prescription is rendered SQL plus instructions: run it, save the output to
the expected path, register it as evidence. Rendering refuses to emit any
unrendered {{MARKER}} or ===INJECT_*=== — half-rendered SQL handed to a
human courier is how investigations go wrong.
"""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from .case import Case


class UnrenderedMarker(Exception):
    pass


MARKER_RE = re.compile(r"\{\{(\w+)\}\}")
INJECT_RE = re.compile(r"^-- ===(\w+)===\s*$", re.MULTILINE)


def render_template(template: str, values: dict, injections: dict) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", str(val))
    for key, sql in injections.items():
        out = out.replace(f"-- ==={key}===", sql)
    leftover = MARKER_RE.findall(out) + INJECT_RE.findall(out)
    if leftover:
        raise UnrenderedMarker(
            f"unrendered markers remain: {sorted(set(leftover))}")
    return out


def load_template(engine: str, name: str) -> str:
    pkg = f"queryreceipts.packs.{engine}"
    return (resources.files(pkg) / "templates" / f"{name}.sql.tmpl"
            ).read_text(encoding="utf-8")


def issue(case: Case, name: str, *, values: dict, save_as: str,
          expected_capture: str, injections: dict | None = None) -> Path:
    injections = dict(injections or {})
    base_values = {"DB_NAME": case.meta.get("database", ""),
                   "EXPECTED_CAPTURE": expected_capture, **values}
    if "INJECT_ORIGINAL_QUERY" not in injections:
        original = case.root / "original.sql"
        if original.exists():
            injections["INJECT_ORIGINAL_QUERY"] = original.read_text(
                encoding="utf-8")
    rendered = render_template(
        load_template(case.meta.get("engine", "sqlserver"), name),
        base_values, injections)
    out_path = case.root / save_as
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    case.append({"event": "prescription_issued", "prescription": name,
                 "rendered_to": save_as,
                 "expected_capture": expected_capture})
    if name == "benchmark":
        case.append({"event": "protocol_pinned", "prescription": name,
                     "runs_per_query": 2,
                     "headline_metric": "second_run_elapsed_ms",
                     "note": "pinned before results exist; "
                             "cherry-picking is a FAIL"})
    return out_path
