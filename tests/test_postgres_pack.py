from pathlib import Path

import pytest

from queryreceipts.packs.postgres.explain import parse, render
from queryreceipts.packs.sections import extract_section

FIXTURE = Path(__file__).parent / "fixtures" / "pg_explain_basic.txt"


def _section():
    return extract_section(FIXTURE.read_text(encoding="utf-8"), "baseline")


def test_explain_parse_times_buffers_and_skew():
    p = parse(_section())
    assert p["execution_time_ms"] == 130.5
    assert p["planning_time_ms"] == 1.2
    # root node buffers are inclusive totals
    assert p["total_shared_hit"] == 100
    assert p["total_shared_read"] == 900
    # Index Scan: 2 rows/loop x 6000 loops = 12000 total vs plan 2 -> 6000x.
    # Loops multiplication makes it the WORST skew — the classic nested-loop
    # misread this parser exists to prevent.
    assert p["skew"][0]["node"] == "Index Scan"
    assert p["skew"][0]["ratio"] == 6000.0
    # Hash Join: plan 120 vs actual 12000 (loops=1) -> 100x
    hj = next(s for s in p["skew"] if s["node"] == "Hash Join")
    assert hj["ratio"] == 100.0


def test_explain_parse_rejects_captures_without_json():
    with pytest.raises(ValueError, match="no JSON plan"):
        parse("ERROR: relation does not exist")


def test_explain_render_compact():
    out = render(parse(_section()))
    assert len(out) < 2000
    assert "130.5" in out and "Hash Join" in out and "reservation" in out


def test_pg_benchmark_grading_compares_sections():
    from queryreceipts.packs.postgres.grading import grade_benchmark
    sec = _section()
    capture = (
        "====BEGIN_SECTION:original====\n" + sec +
        "\n====END_SECTION:original====\n"
        "====BEGIN_SECTION:optimized====\n" +
        sec.replace('"Execution Time": 130.5', '"Execution Time": 13.0')
           .replace('"Shared Read Blocks": 900,', '"Shared Read Blocks": 90,', 1) +
        "\n====END_SECTION:optimized====\n")
    g = grade_benchmark(capture)
    assert g["verdict"] == "MEASURED"
    assert g["original"]["elapsed_ms"] == 130.5
    assert g["optimized"]["elapsed_ms"] == 13.0
    assert g["improvement"]["elapsed_pct"] == 90.0
    assert g["improvement"]["cpu_pct"] is None  # postgres doesn't report cpu


def test_pg_validation_prescription_uses_inject_style(tmp_path):
    from queryreceipts.case import Case
    from queryreceipts.cli import main
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "postgres",
          "--database", "fleetdb", "--symptom", "slow"])
    (root / "original.sql").write_text(
        "SELECT 1 AS x WHERE 'a' = 'a'", encoding="utf-8")
    opt = root / "optimized" / "optimized_v1.sql"
    opt.parent.mkdir(parents=True)
    opt.write_text("WITH c AS (SELECT 1 AS x) SELECT x FROM c",
                   encoding="utf-8")
    assert main(["prescribe", "validation", "--rewrite", str(opt),
                 "--natural-key", "x", "--case", str(root)]) == 0
    text = (root / "prescriptions" / "validation_v1.sql").read_text(
        encoding="utf-8")
    assert "CREATE TEMP TABLE old_result" in text
    assert "WHERE 'a' = 'a'" in text          # injected verbatim, no escaping
    assert "WITH c AS (SELECT 1 AS x)" in text
    assert "gate:engine_version" in text
    assert "{{" not in text
