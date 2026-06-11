"""Parse SQL Server showplan XML (.sqlplan).

Parses EVERY statement in the batch (multi-statement procs are the norm),
every operator with estimated vs actual rows (actuals stay None when the
plan has no RunTimeInformation — estimated plans don't get fake actuals),
self-cost attribution, spill/convert warnings, missing indexes, and
parameter presence. Parameter VALUES are never extracted: plans embed
compiled literals, and the engine treats them as sensitive by default.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

NS = "{http://schemas.microsoft.com/sqlserver/2004/07/showplan}"
STMT_TAGS = {f"{NS}StmtSimple", f"{NS}StmtCond", f"{NS}StmtCursor"}


def _tag(el: ET.Element) -> str:
    return el.tag.removeprefix(NS)


def parse_plan(text: str) -> dict:
    root = ET.fromstring(text)
    statements = []
    for el in root.iter():
        if el.tag in STMT_TAGS:
            statements.append(_parse_statement(el))
    return {"statements": statements}


def _parse_statement(stmt: ET.Element) -> dict:
    out = {
        "statement_id": int(stmt.get("StatementId", "0")),
        "statement_type": stmt.get("StatementType", ""),
        "text": (stmt.get("StatementText") or "")[:200],
        "cost": float(stmt.get("StatementSubTreeCost", "0") or 0),
        "est_rows": float(stmt.get("StatementEstRows", "0") or 0),
    }
    qp = stmt.find(f"{NS}QueryPlan")
    out["memory_grant_kb"] = None
    out["parameters"] = []
    out["missing_indexes"] = []
    out["operators"] = []
    if qp is None:
        return out

    mg = qp.find(f"{NS}MemoryGrantInfo")
    if mg is not None and mg.get("GrantedMemory") is not None:
        out["memory_grant_kb"] = int(mg.get("GrantedMemory"))

    for cr in qp.iter(f"{NS}ColumnReference"):
        if cr.get("Column", "").startswith("@"):
            out["parameters"].append({
                "name": cr.get("Column"),
                "compiled_value_present":
                    cr.get("ParameterCompiledValue") is not None,
            })

    usage_key = {"EQUALITY": "equality", "INEQUALITY": "inequality",
                 "INCLUDE": "included"}
    for mi in qp.iter(f"{NS}MissingIndex"):
        entry = {"database": mi.get("Database", ""),
                 "schema": mi.get("Schema", ""),
                 "table": mi.get("Table", ""),
                 "equality": [], "inequality": [], "included": []}
        for cg in mi.findall(f"{NS}ColumnGroup"):
            key = usage_key.get(cg.get("Usage", ""))
            if key:
                entry[key] = [c.get("Name", "")
                              for c in cg.findall(f"{NS}Column")]
        out["missing_indexes"].append(entry)

    out["operators"] = _build_operators(qp)
    return out


def _build_operators(qp: ET.Element) -> list[dict]:
    rel_ops = list(qp.iter(f"{NS}RelOp"))
    parent_of: dict[ET.Element, ET.Element] = {}
    for parent in qp.iter():
        for child in parent:
            parent_of[child] = parent

    def nearest_relop(el: ET.Element) -> ET.Element | None:
        cur = parent_of.get(el)
        while cur is not None:
            if cur.tag == f"{NS}RelOp":
                return cur
            cur = parent_of.get(cur)
        return None

    direct_children: dict[ET.Element, list[ET.Element]] = {
        r: [] for r in rel_ops}
    for rel in rel_ops:
        anc = nearest_relop(rel)
        if anc is not None:
            direct_children[anc].append(rel)

    ops = []
    for rel in rel_ops:
        subtree = float(rel.get("EstimatedTotalSubtreeCost", "0") or 0)
        child_cost = sum(
            float(c.get("EstimatedTotalSubtreeCost", "0") or 0)
            for c in direct_children[rel])
        actual = None
        rti = rel.find(f"{NS}RunTimeInformation")
        if rti is not None:
            actual = sum(
                int(th.get("ActualRows", "0") or 0)
                for th in rti.findall(f"{NS}RunTimeCountersPerThread"))
        warnings = []
        w = rel.find(f"{NS}Warnings")
        if w is not None:
            warnings = [_tag(child) for child in w]
            warnings += [k for k, v in w.attrib.items() if v == "true"]
        obj = None
        for o in rel.iter(f"{NS}Object"):
            if nearest_relop(o) is rel:
                parts = [o.get(k) for k in
                         ("Database", "Schema", "Table", "Index")]
                obj = ".".join(p for p in parts if p)
                break
        ops.append({
            "node_id": int(rel.get("NodeId", "-1")),
            "physical_op": rel.get("PhysicalOp", ""),
            "logical_op": rel.get("LogicalOp", ""),
            "est_rows": float(rel.get("EstimateRows", "0") or 0),
            "actual_rows": actual,
            "est_subtree_cost": subtree,
            "est_self_cost": max(0.0, subtree - child_cost),
            "object": obj,
            "warnings": warnings,
        })
    return ops


def analyze(plan: dict) -> dict:
    """Derive the tuner-facing report from a parsed plan."""
    statements = []
    for s in plan["statements"]:
        skew = []
        for o in s["operators"]:
            if o["actual_rows"] is None or o["est_rows"] <= 0:
                continue
            ratio = max(o["actual_rows"], 1) / max(o["est_rows"], 1)
            ratio = round(max(ratio, 1 / ratio), 1)  # symmetric: under or over
            if ratio >= 10:
                skew.append({"node_id": o["node_id"],
                             "op": o["physical_op"],
                             "est_rows": o["est_rows"],
                             "actual_rows": o["actual_rows"],
                             "ratio": ratio})
        skew.sort(key=lambda x: x["ratio"], reverse=True)
        plan_warnings = sorted({w for o in s["operators"]
                                for w in o["warnings"]})
        top_ops = sorted(s["operators"],
                         key=lambda o: o["est_self_cost"], reverse=True)[:5]
        statements.append({**s, "skew": skew[:5],
                           "plan_warnings": plan_warnings,
                           "top_self_cost_ops": top_ops})
    return {"statements": statements}


def parse_and_analyze(text: str) -> dict:
    return analyze(parse_plan(text))


def render(report: dict) -> str:
    lines = []
    for s in report["statements"]:
        lines.append(f"stmt {s['statement_id']} [{s['statement_type']}] "
                     f"cost={s['cost']} est_rows={s['est_rows']:,.0f} "
                     f"| {s['text'][:80]}")
        if s["memory_grant_kb"] is not None:
            lines.append(f"  memory grant: {s['memory_grant_kb']:,} KB")
        if any(p["compiled_value_present"] for p in s["parameters"]):
            names = [p["name"] for p in s["parameters"]]
            lines.append(
                f"  compiled parameter values present ({', '.join(names)}) "
                "— treat plan file as sensitive")
        for w in s["plan_warnings"]:
            lines.append(f"  WARNING: {w}")
        for k in s["skew"]:
            lines.append(f"  skew {k['ratio']}x node {k['node_id']} "
                         f"{k['op']}: est {k['est_rows']:,.0f} vs "
                         f"actual {k['actual_rows']:,}")
        for o in s["top_self_cost_ops"][:3]:
            obj = f" -> {o['object']}" if o["object"] else ""
            lines.append(f"  op node {o['node_id']} {o['physical_op']} "
                         f"self-cost {o['est_self_cost']:.1f}{obj}")
        for mi in s["missing_indexes"]:
            lines.append(f"  missing index: {mi['table']} "
                         f"EQ={mi['equality']} INEQ={mi['inequality']} "
                         f"INC={mi['included']}")
    return "\n".join(lines) + "\n"
