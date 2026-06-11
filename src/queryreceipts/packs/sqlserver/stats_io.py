"""Parse SQL Server STATISTICS IO / STATISTICS TIME output.

Handles the modern long line format (page server / lob counters), repeated
per-statement table lines (aggregated per table), parse/compile vs execution
time separation, and engine warnings. Captures may be sectioned with
====BEGIN_SECTION:name==== / ====END_SECTION:name==== markers.
"""
from __future__ import annotations

import re

TABLE_RE = re.compile(
    r"Table '(?P<table>[^']+)'\. Scan count (?P<scans>\d+), "
    r"logical reads (?P<reads>\d+)")
LOB_RE = re.compile(r"lob logical reads (?P<lob>\d+)")
TIME_RE = re.compile(
    r"CPU time = (?P<cpu>\d+) ms,\s*elapsed time = (?P<elapsed>\d+) ms")
WARNING_RE = re.compile(r"^Warning: (?P<msg>.+?)\s*$", re.MULTILINE)
COMPILE_HEADER = "parse and compile time"
EXEC_HEADER = "Execution Times"
SECTION_BEGIN = "====BEGIN_SECTION:{name}===="
SECTION_END = "====END_SECTION:{name}===="


class SectionNotFound(Exception):
    pass


def extract_section(text: str, name: str) -> str:
    if "====BEGIN_SECTION:" not in text:
        return text  # unmarked capture: the whole file is the section
    begin = SECTION_BEGIN.format(name=name)
    if begin not in text:
        found = sorted(set(re.findall(r"====BEGIN_SECTION:(\w+)====", text)))
        raise SectionNotFound(
            f"section {name!r} not in capture; sections present: {found}")
    start = text.index(begin) + len(begin)
    end = SECTION_END.format(name=name)
    stop = text.index(end, start) if end in text else len(text)
    return text[start:stop]


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
