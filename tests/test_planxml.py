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


def test_skew_ranks_worst_misestimates_only_where_actuals_exist():
    from queryreceipts.packs.sqlserver.planxml import analyze
    report = analyze(_plan())
    skew = report["statements"][0]["skew"]
    assert skew[0]["node_id"] in (0, 2)          # both are 100x under-estimates
    assert skew[0]["ratio"] == 100.0
    assert report["statements"][1]["skew"] == []  # no actuals -> no fake skew


def test_warnings_and_parameters_surface():
    from queryreceipts.packs.sqlserver.planxml import analyze
    s1 = analyze(_plan())["statements"][0]
    assert "SpillToTempDb" in s1["plan_warnings"]
    assert s1["parameters"] == [
        {"name": "@from", "compiled_value_present": True}]


def test_render_under_2kb_and_leads_with_cost_and_skew():
    from queryreceipts.packs.sqlserver.planxml import analyze, render
    out = render(analyze(_plan()))
    assert len(out) < 2000
    assert "1423.68" in out
    assert "100.0x" in out
    assert "SpillToTempDb" in out
    assert "compiled parameter values present" in out
