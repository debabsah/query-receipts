import json

from queryreceipts.cli import main


def test_init_creates_case(tmp_path, capsys):
    rc = main(["init", str(tmp_path / "c"), "--engine", "sqlserver",
               "--database", "Sales", "--symptom", "slow nightly job"])
    assert rc == 0
    assert (tmp_path / "c" / "case.json").exists()
    assert "opened case" in capsys.readouterr().out


def test_init_twice_fails_cleanly(tmp_path, capsys):
    args = ["init", str(tmp_path / "c"), "--engine", "sqlserver",
            "--database", "S", "--symptom", "x"]
    assert main(args) == 0
    assert main(args) == 1
    assert "already contains" in capsys.readouterr().err


def test_add_registers_and_status_reports(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver",
          "--database", "S", "--symptom", "x"])
    cap = root / "runs" / "baseline" / "diagnostics.txt"
    cap.parent.mkdir(parents=True)
    cap.write_text("Table 'T'. Scan count 1, logical reads 5",
                   encoding="utf-8")
    rc = main(["add", str(cap), "--kind", "stats_io", "--transport",
               "courier", "--environment", "production", "--runner", "analyst",
               "--case", str(root)])
    assert rc == 0
    assert "ev-0001" in capsys.readouterr().out

    rc = main(["status", "--case", str(root), "--json"])
    assert rc == 0
    state = json.loads(capsys.readouterr().out)
    assert state["case"]["case"] == "c"
    assert state["evidence"][0]["artifact_id"] == "ev-0001"


def test_parse_subcommand_summarizes_registered_evidence(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver",
          "--database", "S", "--symptom", "x"])
    cap = root / "diag.txt"
    cap.write_text(
        "Table 'BIG'. Scan count 4, logical reads 2000000, "
        "physical reads 0.\n"
        " SQL Server Execution Times:\n"
        "   CPU time = 5000 ms,  elapsed time = 9000 ms.\n",
        encoding="utf-8")
    main(["add", str(cap), "--kind", "stats_io", "--transport", "courier",
          "--environment", "synthetic", "--runner", "analyst",
          "--case", str(root)])
    rc = main(["parse", "ev-0001", "--case", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BIG" in out and "2,000,000" in out
    # a summary_derived event cites the source artifact
    from queryreceipts.case import Case
    events = Case.find(root).events()
    derived = [e for e in events if e["event"] == "summary_derived"]
    assert derived and derived[0]["source"] == "ev-0001"


def test_prescribe_grade_certify_loop(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver",
          "--database", "FleetDB", "--symptom", "slow"])
    (root / "original.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    opt = root / "optimized" / "optimized_v1.sql"
    opt.parent.mkdir(parents=True)
    opt.write_text("SELECT 1 AS x", encoding="utf-8")

    rc = main(["prescribe", "validation", "--rewrite",
               str(opt), "--natural-key", "x", "--case", str(root)])
    assert rc == 0
    assert (root / "prescriptions" / "validation_v1.sql").exists()

    results = root / "validation" / "v1_results.txt"
    results.parent.mkdir(parents=True)
    results.write_text(
        "row_count                      PASS   old=1 new=1\n"
        "gate:database                  INFO   FleetDB\n", encoding="utf-8")
    main(["add", str(results), "--kind", "validation_results",
          "--transport", "courier", "--environment", "synthetic",
          "--runner", "analyst", "--case", str(root)])
    capsys.readouterr()

    rc = main(["grade", "ev-0001", "--case", str(root)])
    assert rc == 0
    assert "PROVEN" in capsys.readouterr().out

    rc = main(["certify", "--validation", "ev-0001",
               "--rewrite", "optimized/optimized_v1.sql",
               "--case", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UNVERIFIED" in out   # no benchmark yet — named, not papered over
    assert "benchmark" in out


def test_run_executes_prescription_and_registers_driver_evidence(
        tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver", "--database", "S",
          "--symptom", "x", "--runner-cmd",
          "cat {sql} >/dev/null; "
          "printf \"Table 'T'. Scan count 9, logical reads 77\""])
    (root / "original.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    main(["prescribe", "diagnostics", "--case", str(root)])
    rc = main(["run", "prescriptions/diagnostics.sql",
               "--environment", "synthetic", "--case", str(root)])
    assert rc == 0
    cap = root / "runs" / "baseline" / "diagnostics.txt"
    assert "logical reads 77" in cap.read_text(encoding="utf-8")
    from queryreceipts.case import Case
    ev = Case.find(root).get_evidence("ev-0001")
    assert ev.transport == "driver"
    assert ev.kind == "stats_io"
    assert ev.runner == "cat"  # first token only — commands may hold secrets
    assert "printf" not in (root / "ledger.jsonl").read_text(
        encoding="utf-8")


def test_run_refuses_files_that_are_not_prescriptions(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver", "--database", "S",
          "--symptom", "x", "--runner-cmd", "cat {sql}"])
    (root / "random.sql").write_text("SELECT 1", encoding="utf-8")
    rc = main(["run", "random.sql", "--environment", "synthetic",
               "--case", str(root)])
    assert rc == 1
    assert "not a rendered prescription" in capsys.readouterr().err


def test_prescribe_validation_escapes_quotes_into_literals(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver",
          "--database", "FleetDB", "--symptom", "slow"])
    (root / "original.sql").write_text(
        "SELECT 1 AS x WHERE 'a' = 'a'", encoding="utf-8")
    opt = root / "optimized" / "optimized_v1.sql"
    opt.parent.mkdir(parents=True)
    opt.write_text("SELECT 1 AS x WHERE 'a' = 'a' /* v2 */",
                   encoding="utf-8")
    assert main(["prescribe", "validation", "--rewrite", str(opt),
                 "--natural-key", "x", "--case", str(root)]) == 0
    text = (root / "prescriptions" / "validation_v1.sql").read_text(
        encoding="utf-8")
    assert "WHERE ''a'' = ''a''" in text   # quotes doubled inside N'…'
    assert "{{" not in text
