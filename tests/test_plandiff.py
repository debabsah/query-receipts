import copy
from pathlib import Path

from queryreceipts.packs.sqlserver.plandiff import diff_plans, render_diff
from queryreceipts.packs.sqlserver.planxml import parse_plan

FIXTURE = Path(__file__).parent / "fixtures" / "plan_two_statements.sqlplan"


def _variant():
    """Same plan, mutated: join flips Hash->Loop, cost drops, spill gone."""
    plan = parse_plan(FIXTURE.read_text(encoding="utf-8"))
    v = copy.deepcopy(plan)
    s = v["statements"][0]
    s["cost"] = 12.5
    root = next(o for o in s["operators"] if o["node_id"] == 0)
    root["physical_op"] = "Nested Loops"
    root["warnings"] = []
    return plan, v


def test_diff_reports_cost_join_and_warning_changes():
    a, b = _variant()
    d = diff_plans(a, b)
    s0 = d["statements"][0]
    assert s0["cost"] == {"a": 1423.68, "b": 12.5}
    assert s0["operator_changes"]["removed"] == {"Hash Match": 1}
    assert s0["operator_changes"]["added"] == {"Nested Loops": 1}
    assert s0["warning_changes"]["removed"] == ["SpillToTempDb"]
    # statement 2 unchanged
    assert d["statements"][1]["operator_changes"]["added"] == {}


def test_diff_handles_statement_count_mismatch():
    a, b = _variant()
    b["statements"] = b["statements"][:1]
    d = diff_plans(a, b)
    assert d["unmatched_statements"] == {"a": 1, "b": 0}


def test_render_diff_mentions_the_join_flip():
    a, b = _variant()
    out = render_diff(diff_plans(a, b))
    assert "Hash Match" in out and "Nested Loops" in out
    assert "1423.68" in out and "12.5" in out
