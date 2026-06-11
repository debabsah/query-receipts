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
               "courier", "--environment", "production", "--runner", "deb",
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
          "--environment", "synthetic", "--runner", "deb",
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
