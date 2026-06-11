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
