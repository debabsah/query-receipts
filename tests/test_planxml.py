from pathlib import Path

from queryreceipts.packs.sqlserver.planxml import parse_plan

FIXTURE = Path(__file__).parent / "fixtures" / "plan_two_statements.sqlplan"


def _plan():
    return parse_plan(FIXTURE.read_text(encoding="utf-8"))


def test_all_statements_are_parsed_not_just_the_first():
    plan = _plan()
    assert len(plan["statements"]) == 2
    assert plan["statements"][0]["cost"] == 1423.68
    assert plan["statements"][1]["cost"] == 0.05


def test_operators_carry_est_actual_and_self_cost():
    s1 = _plan()["statements"][0]
    root = next(o for o in s1["operators"] if o["node_id"] == 0)
    assert root["physical_op"] == "Hash Match"
    assert root["est_rows"] == 120.0
    assert root["actual_rows"] == 12000
    # self cost = subtree minus direct children subtrees
    assert abs(root["est_self_cost"] - (1423.68 - 800.10 - 403.20)) < 0.01
    scan = next(o for o in s1["operators"] if o["node_id"] == 1)
    assert scan["object"] == "[FleetDB].[dbo].[RESERVATION].[PK_RESERVATION]"


def test_statement_without_runtime_info_reports_actuals_as_none():
    s2 = _plan()["statements"][1]
    assert all(o["actual_rows"] is None for o in s2["operators"])
