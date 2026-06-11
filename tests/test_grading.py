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


def test_benchmark_grading_compares_sections():
    from queryreceipts.packs.sqlserver.grading import grade_benchmark
    capture = (
        "====BEGIN_SECTION:original====\n"
        "Table 'BIG'. Scan count 4, logical reads 2000000, "
        "physical reads 0.\n"
        " SQL Server Execution Times:\n"
        "   CPU time = 90000 ms,  elapsed time = 120000 ms.\n"
        "====END_SECTION:original====\n"
        "====BEGIN_SECTION:optimized====\n"
        "Table 'BIG'. Scan count 1, logical reads 40000, "
        "physical reads 0.\n"
        " SQL Server Execution Times:\n"
        "   CPU time = 4000 ms,  elapsed time = 6000 ms.\n"
        "====END_SECTION:optimized====\n")
    g = grade_benchmark(capture)
    assert g["original"]["elapsed_ms"] == 120000
    assert g["optimized"]["elapsed_ms"] == 6000
    assert g["improvement"]["elapsed_pct"] == 95.0
    assert g["improvement"]["reads_pct"] == 98.0


def test_benchmark_grading_unverified_when_a_section_is_missing():
    from queryreceipts.packs.sqlserver.grading import grade_benchmark
    g = grade_benchmark("====BEGIN_SECTION:original====\n"
                        " SQL Server Execution Times:\n"
                        "   CPU time = 1 ms,  elapsed time = 2 ms.\n"
                        "====END_SECTION:original====\n")
    assert g["verdict"] == "UNVERIFIED"
    assert "optimized" in g["reason"]
