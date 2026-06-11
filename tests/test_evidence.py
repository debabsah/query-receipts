import pytest

from queryreceipts.evidence import Evidence, sha256_of, validate_vocab


def test_sha256_of_known_content(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("receipts\n", encoding="utf-8")
    assert sha256_of(p) == (
        "159da7125af95b1ab41ac5e9f7ff55d9988e10687a1cfdbdad854fd8602d11b5"
    )


def test_evidence_event_round_trip():
    ev = Evidence(
        artifact_id="ev-0001", path="runs/baseline/diagnostics.txt",
        sha256="ab" * 32, kind="stats_io", engine="sqlserver",
        transport="courier", environment="production", runner="analyst",
        captured_at="", registered_at="2026-06-11T00:00:00+00:00", notes="",
    )
    event = ev.to_event()
    assert event["event"] == "evidence_registered"
    assert Evidence.from_event(event) == ev


def test_validate_vocab_rejects_unknown_transport():
    with pytest.raises(ValueError, match="transport"):
        validate_vocab(kind="stats_io", transport="telepathy",
                       environment="production")
