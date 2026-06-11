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
