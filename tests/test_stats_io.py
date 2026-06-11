from pathlib import Path

import pytest

from queryreceipts.packs.sqlserver.stats_io import (
    SectionNotFound, extract_section, parse)

FIXTURE = Path(__file__).parent / "fixtures" / "stats_io_realistic.txt"


def test_tables_aggregate_across_statements_and_rank_by_reads():
    result = parse(FIXTURE.read_text(encoding="utf-8"))
    tables = result["tables"]
    assert tables[0]["table"] == "Worktable"
    assert tables[0]["logical_reads"] == 11969839
    traveler = next(t for t in tables if t["table"] == "TRAVELER")
    assert traveler["logical_reads"] == 250329 + 1104
    assert traveler["scan_count"] == 23648 + 2
    assert traveler["statements"] == 2
    assert traveler["lob_logical_reads"] == 12


def test_section_extraction_honest_about_missing_sections():
    text = FIXTURE.read_text(encoding="utf-8")
    assert "START NightlyExtract" in extract_section(text, "baseline_io_time")
    with pytest.raises(SectionNotFound, match="rowcounts"):
        extract_section(text, "rowcounts")


def test_text_without_any_markers_is_treated_as_one_section():
    assert extract_section(
        "Table 'X'. Scan count 1, logical reads 2", "anything") \
        == "Table 'X'. Scan count 1, logical reads 2"
