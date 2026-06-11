"""Grade saved validation results.

Three-valued: PROVEN (every test PASS), REFUTED (any FAIL), UNVERIFIED
(no parseable test rows — the capture itself is the problem). Gate rows
(INFO) are echoed through for the certificate to cite.
"""
from __future__ import annotations

import re

ROW_RE = re.compile(
    r"^(?P<name>\S+)\s+(?P<status>PASS|FAIL|INFO)\s+(?P<detail>.*?)\s*$",
    re.MULTILINE)


def grade_validation(text: str) -> dict:
    rows = [m.groupdict() for m in ROW_RE.finditer(text)]
    tests = [r for r in rows if r["status"] in ("PASS", "FAIL")]
    gates = {r["name"]: r["detail"] for r in rows if r["status"] == "INFO"}
    if not tests:
        return {"verdict": "UNVERIFIED",
                "reason": "no test rows found in capture — re-run the "
                          "validation prescription and save the full grid",
                "counts": {"PASS": 0, "FAIL": 0, "INFO": len(gates)},
                "failures": [], "gates": gates, "tests": []}
    failures = [{"test_name": r["name"], "detail": r["detail"]}
                for r in tests if r["status"] == "FAIL"]
    verdict = "REFUTED" if failures else "PROVEN"
    return {"verdict": verdict,
            "counts": {"PASS": sum(r["status"] == "PASS" for r in tests),
                       "FAIL": len(failures), "INFO": len(gates)},
            "failures": failures, "gates": gates,
            "tests": [{"test_name": r["name"], "status": r["status"],
                       "detail": r["detail"]} for r in tests]}


def grade_benchmark(text: str) -> dict:
    from .stats_io import SectionNotFound, extract_section, parse
    sides = {}
    for side in ("original", "optimized"):
        try:
            section = extract_section(text, side)
        except SectionNotFound:
            return {"verdict": "UNVERIFIED",
                    "reason": f"section {side!r} missing from benchmark "
                              "capture — run the full prescription"}
        parsed = parse(section)
        sides[side] = {
            "elapsed_ms": parsed["time"]["elapsed_ms"],
            "cpu_ms": parsed["time"]["cpu_ms"],
            "logical_reads": sum(t["logical_reads"]
                                 for t in parsed["tables"]),
        }

    def pct(before: int, after: int) -> float | None:
        if before <= 0:
            return None
        return round(100 * (before - after) / before, 1)

    o, n = sides["original"], sides["optimized"]
    return {"verdict": "MEASURED", "original": o, "optimized": n,
            "improvement": {
                "elapsed_pct": pct(o["elapsed_ms"], n["elapsed_ms"]),
                "cpu_pct": pct(o["cpu_ms"], n["cpu_ms"]),
                "reads_pct": pct(o["logical_reads"], n["logical_reads"]),
            }}
