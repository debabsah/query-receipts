"""Diff two parsed plans of the same query (e.g. Query Store cheap vs
expensive). Statements align by order; a count mismatch is reported, not
papered over. Costs are optimizer estimates — the diff narrates shape
changes, it does not declare a winner."""
from __future__ import annotations

from collections import Counter


def _op_counter(stmt: dict) -> Counter:
    return Counter(o["physical_op"] for o in stmt["operators"])


def _warnings(stmt: dict) -> set:
    return {w for o in stmt["operators"] for w in o["warnings"]}


def _objects(stmt: dict) -> set:
    return {o["object"] for o in stmt["operators"] if o["object"]}


def diff_plans(a: dict, b: dict) -> dict:
    sa, sb = a["statements"], b["statements"]
    pairs = list(zip(sa, sb))
    statements = []
    for stmt_a, stmt_b in pairs:
        ca, cb = _op_counter(stmt_a), _op_counter(stmt_b)
        wa, wb = _warnings(stmt_a), _warnings(stmt_b)
        oa, ob = _objects(stmt_a), _objects(stmt_b)
        statements.append({
            "statement_id": stmt_a["statement_id"],
            "cost": {"a": stmt_a["cost"], "b": stmt_b["cost"]},
            "est_rows": {"a": stmt_a["est_rows"], "b": stmt_b["est_rows"]},
            "memory_grant_kb": {"a": stmt_a["memory_grant_kb"],
                                "b": stmt_b["memory_grant_kb"]},
            "operator_changes": {
                "added": dict(cb - ca),
                "removed": dict(ca - cb),
            },
            "object_changes": {
                "added": sorted(ob - oa),
                "removed": sorted(oa - ob),
            },
            "warning_changes": {
                "added": sorted(wb - wa),
                "removed": sorted(wa - wb),
            },
        })
    return {
        "statements": statements,
        "unmatched_statements": {"a": len(sa) - len(pairs),
                                 "b": len(sb) - len(pairs)},
    }


def render_diff(diff: dict) -> str:
    lines = ["plan diff (A -> B); costs are optimizer estimates"]
    un = diff["unmatched_statements"]
    if un["a"] or un["b"]:
        lines.append(f"  STATEMENT COUNT MISMATCH: {un['a']} extra in A, "
                     f"{un['b']} extra in B — pairwise diff covers the "
                     "matched prefix only")
    for s in diff["statements"]:
        lines.append(f"stmt {s['statement_id']}: cost {s['cost']['a']} -> "
                     f"{s['cost']['b']}")
        for label, key in (("ops added", "added"), ("ops removed", "removed")):
            if s["operator_changes"][key]:
                items = ", ".join(
                    f"{op} x{n}" for op, n in
                    sorted(s["operator_changes"][key].items()))
                lines.append(f"  {label}: {items}")
        for key in ("added", "removed"):
            for obj in s["object_changes"][key]:
                lines.append(f"  index/object {key}: {obj}")
            for w in s["warning_changes"][key]:
                lines.append(f"  warning {key}: {w}")
    return "\n".join(lines) + "\n"
