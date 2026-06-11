"""Postgres grading. Validation grading is engine-neutral (token-based
PASS/FAIL/INFO rows) and shared; benchmark grading reads the EXPLAIN
(ANALYZE, BUFFERS, FORMAT JSON) sections. Postgres reports no CPU time —
cpu_pct stays None rather than being invented."""
from __future__ import annotations

from ..sections import SectionNotFound, extract_section
from ..sqlserver.grading import grade_validation  # noqa: F401 (shared)
from .explain import parse as parse_explain


def grade_benchmark(text: str) -> dict:
    sides = {}
    for side in ("original", "optimized"):
        try:
            section = extract_section(text, side)
        except SectionNotFound:
            return {"verdict": "UNVERIFIED",
                    "reason": f"section {side!r} missing from benchmark "
                              "capture — run the full prescription"}
        try:
            p = parse_explain(section)
        except ValueError as exc:
            return {"verdict": "UNVERIFIED",
                    "reason": f"section {side!r}: {exc}"}
        sides[side] = {
            "elapsed_ms": p["execution_time_ms"],
            "cpu_ms": None,
            "logical_reads": p["total_shared_hit"] + p["total_shared_read"],
        }

    def pct(before, after):
        if not before or before <= 0:
            return None
        return round(100 * (before - after) / before, 1)

    o, n = sides["original"], sides["optimized"]
    return {"verdict": "MEASURED", "original": o, "optimized": n,
            "improvement": {
                "elapsed_pct": pct(o["elapsed_ms"], n["elapsed_ms"]),
                "cpu_pct": None,
                "reads_pct": pct(o["logical_reads"], n["logical_reads"]),
            }}
