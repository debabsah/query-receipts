"""Parse PostgreSQL EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) captures.

Postgres reports estimated (Plan Rows) and actual rows natively; actual
rows are per-loop averages, so totals multiply by Actual Loops — skipping
that multiplication is the classic way to misread nested-loop plans.
Root-node buffer counters are inclusive totals for the whole query.
"""
from __future__ import annotations

import json


def parse(text: str) -> dict:
    start = text.find("[")
    if start == -1:
        raise ValueError("no JSON plan found in capture — run the "
                         "prescription with FORMAT JSON intact")
    try:
        doc, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"no JSON plan found in capture ({exc})") from None
    entry = doc[0]
    root = entry["Plan"]

    nodes: list[dict] = []

    def walk(node: dict, depth: int) -> None:
        loops = node.get("Actual Loops", 1) or 1
        actual_total = node.get("Actual Rows", 0) * loops
        nodes.append({
            "node": node.get("Node Type", ""),
            "relation": node.get("Relation Name",
                                 node.get("Index Name", "")),
            "plan_rows": node.get("Plan Rows", 0),
            "actual_rows_total": actual_total,
            "loops": loops,
            "actual_total_time_ms": node.get("Actual Total Time", 0.0),
            "depth": depth,
        })
        for child in node.get("Plans", []):
            walk(child, depth + 1)

    walk(root, 0)

    skew = []
    for n in nodes:
        if n["plan_rows"] <= 0:
            continue
        ratio = max(n["actual_rows_total"], 1) / max(n["plan_rows"], 1)
        ratio = round(max(ratio, 1 / ratio), 1)
        if ratio >= 10:
            skew.append({**{k: n[k] for k in
                            ("node", "relation", "plan_rows",
                             "actual_rows_total")},
                         "ratio": ratio})
    skew.sort(key=lambda s: s["ratio"], reverse=True)

    return {
        "execution_time_ms": entry.get("Execution Time"),
        "planning_time_ms": entry.get("Planning Time"),
        "total_shared_hit": root.get("Shared Hit Blocks", 0),
        "total_shared_read": root.get("Shared Read Blocks", 0),
        "nodes": nodes,
        "skew": skew[:5],
    }


def render(parsed: dict) -> str:
    lines = [
        f"execution {parsed['execution_time_ms']} ms | "
        f"planning {parsed['planning_time_ms']} ms | "
        f"buffers shared hit={parsed['total_shared_hit']:,} "
        f"read={parsed['total_shared_read']:,}",
    ]
    for s in parsed["skew"]:
        lines.append(f"  skew {s['ratio']}x {s['node']}"
                     f"{' on ' + s['relation'] if s['relation'] else ''}: "
                     f"plan {s['plan_rows']:,} vs actual "
                     f"{s['actual_rows_total']:,}")
    top = sorted(parsed["nodes"],
                 key=lambda n: n["actual_total_time_ms"], reverse=True)[:5]
    for n in top:
        rel = f" on {n['relation']}" if n["relation"] else ""
        lines.append(f"  node {n['node']}{rel}: "
                     f"{n['actual_total_time_ms']:.1f} ms (incl), "
                     f"rows {n['actual_rows_total']:,} x{n['loops']} loops")
    return "\n".join(lines) + "\n"
