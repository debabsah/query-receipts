import pytest

from queryreceipts.case import Case
from queryreceipts.prescription import (
    UnrenderedMarker, issue, render_template)

META = {"case": "c", "engine": "sqlserver", "database": "FleetDB",
        "symptom": "slow"}


def test_render_replaces_markers_and_injects_sql():
    out = render_template(
        "USE [{{DB_NAME}}];\n-- ===INJECT_ORIGINAL_QUERY===\n",
        {"DB_NAME": "FleetDB"},
        {"INJECT_ORIGINAL_QUERY": "SELECT 1 AS x"})
    assert "USE [FleetDB];" in out
    assert "SELECT 1 AS x" in out
    assert "{{" not in out and "===INJECT" not in out


def test_render_refuses_unrendered_markers():
    with pytest.raises(UnrenderedMarker, match="DB_NAME"):
        render_template("USE [{{DB_NAME}}];", {}, {})


def test_issue_writes_prescription_and_ledger_event(tmp_path):
    case = Case.init(tmp_path / "c", META)
    (case.root / "original.sql").write_text("SELECT 1 AS x",
                                            encoding="utf-8")
    p = issue(case, "diagnostics", values={}, save_as="diagnostics.sql",
              expected_capture="runs/baseline/diagnostics.txt")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "USE [FleetDB];" in text
    assert "SELECT 1 AS x" in text
    issued = [e for e in case.events()
              if e["event"] == "prescription_issued"]
    assert issued[0]["expected_capture"] == "runs/baseline/diagnostics.txt"
    assert issued[0]["prescription"] == "diagnostics"
