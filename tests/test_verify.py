from queryreceipts.cli import main


def _case_with_evidence(tmp_path):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver", "--database", "S",
          "--symptom", "x"])
    cap = root / "runs" / "baseline" / "diagnostics.txt"
    cap.parent.mkdir(parents=True)
    cap.write_text("Table 'T'. Scan count 1, logical reads 5",
                   encoding="utf-8")
    main(["add", str(cap), "--kind", "stats_io", "--transport", "courier",
          "--environment", "synthetic", "--runner", "analyst",
          "--case", str(root)])
    return root, cap


def test_verify_passes_on_intact_case(tmp_path, capsys):
    root, _ = _case_with_evidence(tmp_path)
    rc = main(["verify", "--case", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out and "1 evidence artifact" in out


def test_verify_fails_on_tampered_capture(tmp_path, capsys):
    root, cap = _case_with_evidence(tmp_path)
    cap.write_text("Table 'T'. Scan count 1, logical reads 999999",
                   encoding="utf-8")  # someone "improved" the numbers
    rc = main(["verify", "--case", str(root)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "TAMPERED" in out and "ev-0001" in out


def test_verify_fails_on_missing_capture_and_broken_seq(tmp_path, capsys):
    root, cap = _case_with_evidence(tmp_path)
    cap.unlink()
    ledger = root / "ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    rc = main(["verify", "--case", str(root)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert "non-monotonic" in out


def test_verify_checks_certificate_citations(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver", "--database", "S",
          "--symptom", "x"])
    v = root / "validation" / "v1_results.txt"
    v.parent.mkdir(parents=True)
    v.write_text("row_count   PASS   old=1 new=1\n", encoding="utf-8")
    main(["add", str(v), "--kind", "validation_results", "--transport",
          "courier", "--environment", "synthetic", "--runner", "d",
          "--case", str(root)])
    main(["certify", "--validation", "ev-0001", "--rewrite", "x.sql",
          "--case", str(root)])
    assert main(["verify", "--case", str(root)]) == 0
    # tamper AFTER certification: the certificate's citation must break
    v.write_text("row_count   PASS   old=2 new=2\n", encoding="utf-8")
    capsys.readouterr()
    rc = main(["verify", "--case", str(root)])
    assert rc == 1
    assert "cert-0001" in capsys.readouterr().out
