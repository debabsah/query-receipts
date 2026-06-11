"""Engine packs. One registry entry per engine; everything dispatches
through get_pack(engine) — no engine is special-cased elsewhere."""
from __future__ import annotations

from .postgres import explain as pg_explain
from .postgres import grading as pg_grading
from .sqlserver import grading as ss_grading
from .sqlserver import planxml, stats_io

REGISTRY: dict = {
    "sqlserver": {
        "parsers": {
            "stats_io": (stats_io.parse, stats_io.render),
            "plan_xml": (planxml.parse_and_analyze, planxml.render),
        },
        "grade_validation": ss_grading.grade_validation,
        "grade_benchmark": ss_grading.grade_benchmark,
        "diagnostics_kind": "stats_io",
        # validation embeds queries as N'…' literals
        # (general materialization needs dynamic SQL on this engine)
        "validation_style": "literal",
    },
    "postgres": {
        "parsers": {
            "pg_explain": (pg_explain.parse, pg_explain.render),
        },
        "grade_validation": pg_grading.grade_validation,
        "grade_benchmark": pg_grading.grade_benchmark,
        "diagnostics_kind": "pg_explain",
        # CREATE TEMP TABLE x AS (query) accepts CTEs natively
        "validation_style": "inject",
    },
}


def get_pack(engine: str) -> dict:
    if engine not in REGISTRY:
        raise KeyError(
            f"no pack for engine {engine!r}; engines: {sorted(REGISTRY)}")
    return REGISTRY[engine]


def get_parser(kind: str, engine: str = "sqlserver"):
    parsers = get_pack(engine)["parsers"]
    if kind not in parsers:
        raise KeyError(
            f"no {engine} parser for kind {kind!r}; "
            f"parseable kinds: {sorted(parsers)}")
    return parsers[kind]
