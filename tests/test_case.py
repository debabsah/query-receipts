import json

import pytest

from queryreceipts.case import Case, CaseError

META = {"case": "slow-batch", "engine": "sqlserver",
        "database": "Sales", "symptom": "nightly job runs 30m instead of 2m"}


def test_init_creates_case_json_and_opening_event(tmp_path):
    case = Case.init(tmp_path / "c", META)
    on_disk = json.loads((case.root / "case.json").read_text())
    assert on_disk["case"] == "slow-batch"
    events = case.events()
    assert [e["event"] for e in events] == ["case_opened"]
    assert events[0]["seq"] == 1


def test_init_refuses_existing_case(tmp_path):
    Case.init(tmp_path / "c", META)
    with pytest.raises(CaseError, match="already contains"):
        Case.init(tmp_path / "c", META)


def test_find_walks_upward(tmp_path):
    case = Case.init(tmp_path / "c", META)
    nested = case.root / "runs" / "baseline"
    nested.mkdir(parents=True)
    found = Case.find(nested)
    assert found.root == case.root


def test_find_raises_when_absent(tmp_path):
    with pytest.raises(CaseError, match="no case.json"):
        Case.find(tmp_path)


def test_append_assigns_monotonic_seq(tmp_path):
    case = Case.init(tmp_path / "c", META)
    case.append({"event": "note", "text": "hello"})
    case.append({"event": "note", "text": "again"})
    seqs = [e["seq"] for e in case.events()]
    assert seqs == [1, 2, 3]


def _capture(case, rel="runs/baseline/diagnostics.txt",
             text="Table 'T'. Scan count 1, logical reads 5"):
    p = case.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_register_evidence_appends_ledger_and_assigns_id(tmp_path):
    case = Case.init(tmp_path / "c", META)
    p = _capture(case)
    ev = case.register_evidence(
        p, kind="stats_io", transport="courier",
        environment="production", runner="deb")
    assert ev.artifact_id == "ev-0001"
    assert ev.path == "runs/baseline/diagnostics.txt"
    assert len(ev.sha256) == 64
    assert case.get_evidence("ev-0001") == ev


def test_register_evidence_outside_case_root_is_refused(tmp_path):
    case = Case.init(tmp_path / "c", META)
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(CaseError, match="inside the case directory"):
        case.register_evidence(
            outside, kind="stats_io", transport="courier",
            environment="production", runner="deb")


def test_artifact_ids_are_sequential(tmp_path):
    case = Case.init(tmp_path / "c", META)
    a = _capture(case, "a.txt")
    b = _capture(case, "b.txt")
    ev1 = case.register_evidence(a, kind="other", transport="courier",
                                 environment="synthetic", runner="deb")
    ev2 = case.register_evidence(b, kind="other", transport="courier",
                                 environment="synthetic", runner="deb")
    assert (ev1.artifact_id, ev2.artifact_id) == ("ev-0001", "ev-0002")
