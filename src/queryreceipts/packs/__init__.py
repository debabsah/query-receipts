"""Engine packs. Dispatch: evidence kind -> (parse, render)."""
from __future__ import annotations

from .sqlserver import stats_io


def get_parser(kind: str):
    table = {
        "stats_io": (stats_io.parse, stats_io.render),
    }
    if kind not in table:
        raise KeyError(
            f"no parser for kind {kind!r}; parseable kinds: {sorted(table)}")
    return table[kind]
