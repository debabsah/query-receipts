"""Engine packs. Dispatch: evidence kind -> (parse, render)."""
from __future__ import annotations

from .sqlserver import planxml, stats_io


def get_parser(kind: str):
    table = {
        "stats_io": (stats_io.parse, stats_io.render),
        "plan_xml": (planxml.parse_and_analyze, planxml.render),
    }
    if kind not in table:
        raise KeyError(
            f"no parser for kind {kind!r}; parseable kinds: {sorted(table)}")
    return table[kind]
