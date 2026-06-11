"""Parse SQL Server STATISTICS IO / STATISTICS TIME output.

Handles the modern long line format (page server / lob counters), repeated
per-statement table lines (aggregated per table), parse/compile vs execution
time separation, and engine warnings. Captures may be sectioned with
====BEGIN_SECTION:name==== / ====END_SECTION:name==== markers.
"""
from __future__ import annotations

import re

from ..sections import SectionNotFound, extract_section  # noqa: F401 (re-export)

TABLE_RE = re.compile(
    r"Table '(?P<table>[^']+)'\. Scan count (?P<scans>\d+), "
    r"logical reads (?P<reads>\d+)")
LOB_RE = re.compile(r"lob logical reads (?P<lob>\d+)")
TIME_RE = re.compile(
    r"CPU time = (?P<cpu>\d+) ms,\s*elapsed time = (?P<elapsed>\d+) ms")
WARNING_RE = re.compile(r"^Warning: (?P<msg>.+?)\s*$", re.MULTILINE)
COMPILE_HEADER = "parse and compile time"
EXEC_HEADER = "Execution Times"


def parse(text: str) -> dict:
    tables: dict[str, dict] = {}
    exec_times: list[dict] = []
    compile_times: list[dict] = []
    mode = "exec"  # TIME lines with no seen header are execution times
    for line in text.splitlines():
        if COMPILE_HEADER in line:
            mode = "compile"
            continue
        if EXEC_HEADER in line:
            mode = "exec"
            continue
        t = TIME_RE.search(line)
        if t:
            bucket = compile_times if mode == "compile" else exec_times
            bucket.append({"cpu_ms": int(t["cpu"]),
                           "elapsed_ms": int(t["elapsed"])})
            mode = "exec"
            continue
        m = TABLE_RE.search(line)
        if m:
            rec = tables.setdefault(m["table"], {
                "logical_reads": 0, "scan_count": 0,
                "lob_logical_reads": 0, "statements": 0})
            rec["logical_reads"] += int(m["reads"])
            rec["scan_count"] += int(m["scans"])
            rec["statements"] += 1
            lob = LOB_RE.search(line)
            if lob:
                rec["lob_logical_reads"] += int(lob["lob"])
    rows = [{"table": name, **vals} for name, vals in tables.items()]
    rows.sort(key=lambda r: r["logical_reads"], reverse=True)
    return {
        "tables": rows,
        "time": {
            "cpu_ms": sum(e["cpu_ms"] for e in exec_times),
            "elapsed_ms": sum(e["elapsed_ms"] for e in exec_times),
            "statements": len(exec_times),
        },
        "compile": {
            "cpu_ms": sum(c["cpu_ms"] for c in compile_times),
            "elapsed_ms": sum(c["elapsed_ms"] for c in compile_times),
        },
        "warnings": WARNING_RE.findall(text),
    }


def render(parsed: dict) -> str:
    t = parsed["time"]
    c = parsed["compile"]
    lines = [
        f"elapsed {t['elapsed_ms']:,} ms | cpu {t['cpu_ms']:,} ms "
        f"| {t['statements']} timed statement(s) "
        f"| compile {c['cpu_ms']:,} ms cpu",
    ]
    if parsed["warnings"]:
        lines.append(f"warnings: {len(parsed['warnings'])} "
                     f"(first: {parsed['warnings'][0]})")
    lines.append("rank | table | logical_reads | scans | stmts | lob_reads")
    for i, r in enumerate(parsed["tables"][:15], 1):
        lines.append(
            f"{i} | {r['table']} | {r['logical_reads']:,} | "
            f"{r['scan_count']:,} | {r['statements']} | "
            f"{r['lob_logical_reads']:,}")
    if len(parsed["tables"]) > 15:
        lines.append(f"… {len(parsed['tables']) - 15} more tables omitted")
    return "\n".join(lines) + "\n"
