from pathlib import Path

from queryreceipts.packs.sqlserver.grading import grade_validation

FIXTURES = Path(__file__).parent / "fixtures"


def test_all_pass_grades_proven():
    g = grade_validation(
        (FIXTURES / "validation_results_pass.txt").read_text())
    assert g["verdict"] == "PROVEN"
    assert g["counts"] == {"PASS": 9, "FAIL": 0, "INFO": 6}
    assert g["gates"]["gate:database"] == "FleetDB"


def test_any_fail_grades_refuted_and_names_failures():
    g = grade_validation(
        (FIXTURES / "validation_results_fail.txt").read_text())
    assert g["verdict"] == "REFUTED"
    names = [f["test_name"] for f in g["failures"]]
    assert "row_count" in names and "except_old_to_new" in names


def test_empty_or_garbled_capture_is_unverified():
    g = grade_validation("SSMS crashed, nothing here")
    assert g["verdict"] == "UNVERIFIED"
    assert "no test rows" in g["reason"]
