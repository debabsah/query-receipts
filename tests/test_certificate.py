import json

from queryreceipts.case import Case
from queryreceipts.certificate import issue_certificate

META = {"case": "c", "engine": "sqlserver", "database": "FleetDB",
        "symptom": "slow"}

VALIDATION_PASS = (
    "row_count                      PASS   old=10 new=10\n"
    "except_old_to_new              PASS   0 rows missing in NEW\n"
    "except_new_to_old              PASS   0 extra rows in NEW\n"
    "gate:database                  INFO   FleetDB\n")
BENCH = (
    "====BEGIN_SECTION:original====\n"
    " SQL Server Execution Times:\n"
    "   CPU time = 90000 ms,  elapsed time = 120000 ms.\n"
    "====END_SECTION:original====\n"
    "====BEGIN_SECTION:optimized====\n"
    " SQL Server Execution Times:\n"
    "   CPU time = 4000 ms,  elapsed time = 6000 ms.\n"
    "====END_SECTION:optimized====\n")


def _case_with(tmp_path, validation_text, bench_text=None):
    case = Case.init(tmp_path / "c", META)
    v = case.root / "validation" / "v1_results.txt"
    v.parent.mkdir(parents=True)
    v.write_text(validation_text, encoding="utf-8")
    ev_v = case.register_evidence(v, kind="validation_results",
                                  transport="courier",
                                  environment="synthetic", runner="analyst")
    ev_b = None
    if bench_text is not None:
        b = case.root / "benchmarks" / "v1_results.txt"
        b.parent.mkdir(parents=True)
        b.write_text(bench_text, encoding="utf-8")
        ev_b = case.register_evidence(b, kind="benchmark_results",
                                      transport="courier",
                                      environment="synthetic", runner="analyst")
    return case, ev_v, ev_b


def test_proven_certificate_cites_artifacts_and_hashes(tmp_path):
    case, ev_v, ev_b = _case_with(tmp_path, VALIDATION_PASS, BENCH)
    cert = issue_certificate(case, validation_id=ev_v.artifact_id,
                             benchmark_id=ev_b.artifact_id,
                             rewrite="optimized/optimized_v1.sql")
    assert cert["verdict"] == "PROVEN"
    assert cert["evidence"][0]["sha256"] == ev_v.sha256
    assert cert["benchmark"]["improvement"]["elapsed_pct"] == 95.0
    md = (case.root / "certificates" / "certificate_0001.md").read_text()
    assert "PROVEN" in md and ev_v.sha256[:12] in md
    data = json.loads(
        (case.root / "certificates" / "certificate_0001.json").read_text())
    assert data["verdict"] == "PROVEN"
    issued = [e for e in case.events()
              if e["event"] == "certificate_issued"]
    assert issued and issued[0]["verdict"] == "PROVEN"


def test_failed_validation_yields_refuted(tmp_path):
    failed = VALIDATION_PASS.replace(
        "row_count                      PASS   old=10 new=10",
        "row_count                      FAIL   old=10 new=9")
    case, ev_v, ev_b = _case_with(tmp_path, failed, BENCH)
    cert = issue_certificate(case, validation_id=ev_v.artifact_id,
                             benchmark_id=ev_b.artifact_id,
                             rewrite="optimized/optimized_v1.sql")
    assert cert["verdict"] == "REFUTED"


def test_missing_benchmark_yields_unverified_with_named_gap(tmp_path):
    case, ev_v, _ = _case_with(tmp_path, VALIDATION_PASS)
    cert = issue_certificate(case, validation_id=ev_v.artifact_id,
                             benchmark_id=None,
                             rewrite="optimized/optimized_v1.sql")
    assert cert["verdict"] == "UNVERIFIED"
    assert "benchmark" in cert["missing"][0]
