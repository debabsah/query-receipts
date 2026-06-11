# QueryReceipts Plan 1: Proof-Engine Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working, installable `receipts` CLI with case files, an append-only evidence ledger with provenance, and the SQL Server pack's read-side parsers (STATISTICS IO/TIME, showplan XML, plan diff).

**Architecture:** Pure-stdlib Python package (`queryreceipts`, src layout). The engine consumes *evidence artifacts* (files registered with sha256 + provenance) recorded in a per-investigation *case* (a directory with `case.json` + append-only `ledger.jsonl`). Engine packs live under `queryreceipts/packs/<engine>/`; this plan builds the SQL Server pack's parsers only (no prescriptions/certificates yet — that's Plan 2). The CLI is `argparse` subcommands, each with a `--json` mode for the future plugin skin.

**Tech Stack:** Python ≥3.10, stdlib only at runtime (hashlib, json, dataclasses, argparse, xml.etree, re, pathlib). pytest (dev-only). Build backend: hatchling.

**Design constraints carried from README (the spec):**
- The engine never connects to anything; it reads registered files.
- Three-valued honesty everywhere: a value the capture doesn't contain is reported absent, never defaulted.
- Sensitivity posture: parameter *values* in plans are reported as present/absent, never extracted by default.
- Every derived summary is appended to the ledger citing the source artifact id.

**File structure (locked in by this plan):**

```
query-receipts/
├── pyproject.toml
├── LICENSE
├── .gitignore
├── src/queryreceipts/
│   ├── __init__.py            # version only
│   ├── cli.py                 # argparse entry: init/add/status/parse/diff
│   ├── case.py                # Case: init/find/ledger/evidence registration
│   ├── evidence.py            # Evidence dataclass, sha256, vocab constants
│   └── packs/
│       ├── __init__.py        # kind → parser dispatch table
│       └── sqlserver/
│           ├── __init__.py
│           ├── stats_io.py    # STATISTICS IO + TIME + warnings parser
│           ├── planxml.py     # showplan parser: multi-stmt, skew, spills, params
│           └── plandiff.py    # structural diff of two parsed plans
└── tests/
    ├── fixtures/
    │   ├── stats_io_realistic.txt
    │   └── plan_two_statements.sqlplan
    ├── test_evidence.py
    ├── test_case.py
    ├── test_cli.py
    ├── test_stats_io.py
    ├── test_planxml.py
    └── test_plandiff.py
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `.gitignore`, `src/queryreceipts/__init__.py`, `tests/test_package.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_package.py
import queryreceipts


def test_version_is_a_string():
    assert isinstance(queryreceipts.__version__, str)
```

- [x] **Step 2: Run it to verify failure**

Run: `python3 -m pytest tests/test_package.py -q` (from repo root)
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'queryreceipts'`

- [x] **Step 3: Create the scaffold**

`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "queryreceipts"
version = "0.1.0"
description = "Provably faster: query tuning where every fix ships with receipts."
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [{ name = "Debabrata Saha" }]
dependencies = []

[project.scripts]
receipts = "queryreceipts.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.hatch.build.targets.wheel]
packages = ["src/queryreceipts"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`src/queryreceipts/__init__.py`:
```python
__version__ = "0.1.0"
```

`LICENSE`: MIT license text, copyright `2026 Debabrata Saha`.

`.gitignore`:
```
__pycache__/
*.egg-info/
.venv/
dist/
.DS_Store
.pytest_cache/
```

- [x] **Step 4: Install editable into a venv and verify test passes**

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
.venv/bin/python -m pytest tests/test_package.py -q
```
Expected: `1 passed`

- [x] **Step 5: Commit**

```bash
git add pyproject.toml LICENSE .gitignore src tests
git commit -m "feat: package scaffold (queryreceipts, stdlib-only, receipts entry point)"
```

---

### Task 2: Evidence artifacts

**Files:**
- Create: `src/queryreceipts/evidence.py`
- Test: `tests/test_evidence.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_evidence.py
import pytest

from queryreceipts.evidence import Evidence, sha256_of, validate_vocab


def test_sha256_of_known_content(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("receipts\n", encoding="utf-8")
    # sha256 of b"receipts\n"
    assert sha256_of(p) == (
        "503ba4e2698a1ef4a86f6ba1a4534eb6489d1cbd9bb5e2b5e029ac86ad102f78"
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
        validate_vocab(kind="stats_io", transport="telepathy", environment="production")
```

NOTE: if the hard-coded sha256 in the first test is wrong, compute the true value with `python3 -c "import hashlib;print(hashlib.sha256(b'receipts\n').hexdigest())"` and fix the **test**, not the function.

- [x] **Step 2: Run to verify failure** — `pytest tests/test_evidence.py -q`, expected `ModuleNotFoundError`/`ImportError`.

- [x] **Step 3: Implement**

```python
# src/queryreceipts/evidence.py
"""Evidence artifacts: files with provenance.

The proof engine never trusts a bare file. Registration computes a content
hash and records who captured it, where, when, and via which transport.
Every downstream claim cites an artifact id. An empty captured_at stays
empty — unknown provenance is reported, never invented.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

KINDS = (
    "stats_io", "plan_xml", "rowcounts", "index_inventory",
    "stats_inventory", "validation_results", "benchmark_results", "other",
)
TRANSPORTS = ("courier", "approve-each", "mcp", "driver", "ci")
ENVIRONMENTS = ("production", "staging", "stats-clone", "synthetic")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_vocab(*, kind: str, transport: str, environment: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if transport not in TRANSPORTS:
        raise ValueError(f"unknown transport {transport!r}; expected one of {TRANSPORTS}")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {environment!r}; expected one of {ENVIRONMENTS}")


@dataclass(frozen=True)
class Evidence:
    artifact_id: str
    path: str            # case-root-relative, POSIX separators
    sha256: str
    kind: str
    engine: str
    transport: str
    environment: str
    runner: str
    captured_at: str     # ISO-8601 supplied by the runner; "" if unknown
    registered_at: str   # ISO-8601 stamped at registration
    notes: str = ""

    def to_event(self) -> dict:
        return {"event": "evidence_registered", **asdict(self)}

    @classmethod
    def from_event(cls, event: dict) -> "Evidence":
        return cls(**{k: v for k, v in event.items()
                      if k in cls.__dataclass_fields__})
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_evidence.py -q`, expected `3 passed`.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: evidence artifacts with sha256 + provenance vocab"`

---

### Task 3: Case files and the append-only ledger

**Files:**
- Create: `src/queryreceipts/case.py`
- Test: `tests/test_case.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_case.py
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
```

- [x] **Step 2: Run to verify failure** — `pytest tests/test_case.py -q`, expected `ImportError`.

- [x] **Step 3: Implement**

```python
# src/queryreceipts/case.py
"""Case files: an append-only ledger of an investigation.

A case is a directory holding case.json (metadata), ledger.jsonl (append-only
event journal — the receipts), and evidence files at prescribed paths. State
is derived by replaying the ledger; nothing is edited in place.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .evidence import Evidence, sha256_of, validate_vocab

CASE_FILE = "case.json"
LEDGER_FILE = "ledger.jsonl"


class CaseError(Exception):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Case:
    root: Path
    meta: dict

    @classmethod
    def init(cls, root: Path, meta: dict) -> "Case":
        root = Path(root)
        if (root / CASE_FILE).exists():
            raise CaseError(f"{root} already contains a case")
        root.mkdir(parents=True, exist_ok=True)
        meta = {**meta, "schema_version": 1, "created_at": utcnow()}
        (root / CASE_FILE).write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        case = cls(root=root, meta=meta)
        case.append({"event": "case_opened", **meta})
        return case

    @classmethod
    def find(cls, start: Path) -> "Case":
        start = Path(start).resolve()
        for candidate in (start, *start.parents):
            if (candidate / CASE_FILE).exists():
                meta = json.loads(
                    (candidate / CASE_FILE).read_text(encoding="utf-8"))
                return cls(root=candidate, meta=meta)
        raise CaseError(f"no {CASE_FILE} found from {start} upward")

    def append(self, event: dict) -> dict:
        event = {"seq": self._next_seq(), "at": utcnow(), **event}
        with (self.root / LEDGER_FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def events(self) -> list[dict]:
        path = self.root / LEDGER_FILE
        if not path.exists():
            return []
        return [json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def _next_seq(self) -> int:
        events = self.events()
        return (events[-1]["seq"] + 1) if events else 1
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_case.py -q`, expected `5 passed`.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: case files with append-only JSONL ledger"`

---

### Task 4: Evidence registration on a case

**Files:**
- Modify: `src/queryreceipts/case.py` (add methods to `Case`)
- Test: `tests/test_case.py` (append tests)

- [x] **Step 1: Write the failing tests** (append to `tests/test_case.py`)

```python
def _capture(case, rel="runs/baseline/diagnostics.txt", text="Table 'T'. Scan count 1, logical reads 5"):
    p = case.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_register_evidence_appends_ledger_and_assigns_id(tmp_path):
    case = Case.init(tmp_path / "c", META)
    p = _capture(case)
    ev = case.register_evidence(
        p, kind="stats_io", transport="courier",
        environment="production", runner="analyst")
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
            environment="production", runner="analyst")


def test_artifact_ids_are_sequential(tmp_path):
    case = Case.init(tmp_path / "c", META)
    a = _capture(case, "a.txt")
    b = _capture(case, "b.txt")
    ev1 = case.register_evidence(a, kind="other", transport="courier",
                                 environment="synthetic", runner="analyst")
    ev2 = case.register_evidence(b, kind="other", transport="courier",
                                 environment="synthetic", runner="analyst")
    assert (ev1.artifact_id, ev2.artifact_id) == ("ev-0001", "ev-0002")
```

- [x] **Step 2: Run to verify failure** — `pytest tests/test_case.py -q`, expected `AttributeError: register_evidence`.

- [x] **Step 3: Implement** (add to `Case` in `case.py`)

```python
    def register_evidence(self, path: Path, *, kind: str, transport: str,
                          environment: str, runner: str,
                          captured_at: str = "", notes: str = "") -> Evidence:
        validate_vocab(kind=kind, transport=transport, environment=environment)
        path = Path(path).resolve()
        try:
            rel = path.relative_to(self.root.resolve())
        except ValueError:
            raise CaseError(
                f"{path} is not inside the case directory {self.root}; "
                "save captures at prescribed paths inside the case") from None
        n = sum(1 for e in self.events()
                if e["event"] == "evidence_registered") + 1
        ev = Evidence(
            artifact_id=f"ev-{n:04d}", path=rel.as_posix(),
            sha256=sha256_of(path), kind=kind,
            engine=self.meta.get("engine", ""), transport=transport,
            environment=environment, runner=runner,
            captured_at=captured_at, registered_at=utcnow(), notes=notes)
        self.append(ev.to_event())
        return ev

    def evidence(self) -> list[Evidence]:
        return [Evidence.from_event(e) for e in self.events()
                if e["event"] == "evidence_registered"]

    def get_evidence(self, artifact_id: str) -> Evidence:
        for ev in self.evidence():
            if ev.artifact_id == artifact_id:
                return ev
        raise CaseError(f"no evidence with id {artifact_id}")
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_case.py -q`, expected `8 passed`.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: evidence registration with case-relative paths and sequential ids"`

---

### Task 5: CLI — init, add, status

**Files:**
- Create: `src/queryreceipts/cli.py`
- Test: `tests/test_cli.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
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
    cap.write_text("Table 'T'. Scan count 1, logical reads 5", encoding="utf-8")
    rc = main(["add", str(cap), "--kind", "stats_io", "--transport", "courier",
               "--environment", "production", "--runner", "analyst",
               "--case", str(root)])
    assert rc == 0
    assert "ev-0001" in capsys.readouterr().out

    rc = main(["status", "--case", str(root), "--json"])
    assert rc == 0
    state = json.loads(capsys.readouterr().out)
    assert state["case"]["case"] == "c"
    assert state["evidence"][0]["artifact_id"] == "ev-0001"
```

- [x] **Step 2: Run to verify failure** — `pytest tests/test_cli.py -q`, expected `ImportError`.

- [x] **Step 3: Implement**

```python
# src/queryreceipts/cli.py
"""receipts — query tuning with receipts.

Subcommands operate on a case directory (--case PATH, default: walk upward
from cwd). Every subcommand supports --json for machine consumption.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .case import Case, CaseError


def _find_case(args) -> Case:
    start = Path(args.case) if args.case else Path.cwd()
    return Case.find(start)


def cmd_init(args) -> int:
    root = Path(args.path)
    meta = {"case": root.name, "engine": args.engine,
            "database": args.database, "symptom": args.symptom}
    case = Case.init(root, meta)
    print(f"opened case {case.meta['case']} at {case.root}")
    return 0


def cmd_add(args) -> int:
    case = _find_case(args)
    ev = case.register_evidence(
        Path(args.file), kind=args.kind, transport=args.transport,
        environment=args.environment, runner=args.runner,
        captured_at=args.captured_at, notes=args.notes)
    print(f"registered {ev.artifact_id}: {ev.path} (sha256 {ev.sha256[:12]}…)")
    return 0


def cmd_status(args) -> int:
    case = _find_case(args)
    evidence = [ev.__dict__ for ev in case.evidence()]
    if args.json:
        print(json.dumps({"case": case.meta, "evidence": evidence,
                          "events": len(case.events())}, indent=2))
        return 0
    print(f"case: {case.meta['case']}  engine: {case.meta.get('engine')}")
    print(f"symptom: {case.meta.get('symptom')}")
    print(f"ledger events: {len(case.events())}")
    for ev in evidence:
        print(f"  {ev['artifact_id']}  {ev['kind']:<18} {ev['path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="receipts")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="open a new case")
    sp.add_argument("path")
    sp.add_argument("--engine", required=True)
    sp.add_argument("--database", required=True)
    sp.add_argument("--symptom", required=True)
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("add", help="register a capture as evidence")
    sp.add_argument("file")
    sp.add_argument("--kind", required=True)
    sp.add_argument("--transport", required=True)
    sp.add_argument("--environment", required=True)
    sp.add_argument("--runner", required=True)
    sp.add_argument("--captured-at", default="", dest="captured_at")
    sp.add_argument("--notes", default="")
    sp.add_argument("--case", default=None)
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("status", help="show case state")
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CaseError, ValueError, OSError) as exc:
        print(f"receipts: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_cli.py -q`, expected `3 passed`. Also smoke the entry point: `.venv/bin/receipts --help` prints usage.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: receipts CLI with init/add/status"`

---

### Task 6: STATISTICS IO parser — tables and sections

**Files:**
- Create: `src/queryreceipts/packs/__init__.py`, `src/queryreceipts/packs/sqlserver/__init__.py`, `src/queryreceipts/packs/sqlserver/stats_io.py`
- Create: `tests/fixtures/stats_io_realistic.txt`
- Test: `tests/test_stats_io.py`

- [x] **Step 1: Create the realistic fixture** (modeled on real-world capture quirks: modern long format, repeated tables, Worktable spool, warnings, interleaved TIME output; identifiers fictionalized)

```
# tests/fixtures/stats_io_realistic.txt
====BEGIN_SECTION:baseline_io_time====
START FleetExtract original baseline

 SQL Server parse and compile time: 
   CPU time = 391 ms, elapsed time = 391 ms.

 SQL Server Execution Times:
   CPU time = 0 ms,  elapsed time = 0 ms.
Warning: Null value is eliminated by an aggregate or other SET operation.
Table 'ROUTE_SEGMENT'. Scan count 67396, logical reads 734732, physical reads 1, page server reads 0, read-ahead reads 11, page server read-ahead reads 0, lob logical reads 0, lob physical reads 0, lob page server reads 0, lob read-ahead reads 0, lob page server read-ahead reads 0.
Table 'Worktable'. Scan count 66139, logical reads 11969839, physical reads 0, page server reads 0, read-ahead reads 0, page server read-ahead reads 0, lob logical reads 0, lob physical reads 0, lob page server reads 0, lob read-ahead reads 0, lob page server read-ahead reads 0.
Table 'STATUS_CODE'. Scan count 0, logical reads 34996, physical reads 0, page server reads 0, read-ahead reads 0, page server read-ahead reads 0, lob logical reads 0, lob physical reads 0, lob page server reads 0, lob read-ahead reads 0, lob page server read-ahead reads 0.
Table 'TRAVELER'. Scan count 23648, logical reads 250329, physical reads 28, page server reads 0, read-ahead reads 1, page server read-ahead reads 0, lob logical reads 0, lob physical reads 0, lob page server reads 0, lob read-ahead reads 0, lob page server read-ahead reads 0.

 SQL Server Execution Times:
   CPU time = 137640 ms,  elapsed time = 158029 ms.
Table 'TRAVELER'. Scan count 2, logical reads 1104, physical reads 0, page server reads 0, read-ahead reads 0, page server read-ahead reads 0, lob logical reads 12, lob physical reads 0, lob page server reads 0, lob read-ahead reads 0, lob page server read-ahead reads 0.

 SQL Server Execution Times:
   CPU time = 16 ms,  elapsed time = 21 ms.
====END_SECTION:baseline_io_time====
```

- [x] **Step 2: Write the failing tests**

```python
# tests/test_stats_io.py
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
    assert "START FleetExtract" in extract_section(text, "baseline_io_time")
    with pytest.raises(SectionNotFound, match="baseline_io_time"):
        extract_section(text, "rowcounts")


def test_text_without_any_markers_is_treated_as_one_section():
    assert extract_section("Table 'X'. Scan count 1, logical reads 2", "anything") \
        == "Table 'X'. Scan count 1, logical reads 2"
```

- [x] **Step 3: Run to verify failure** — `pytest tests/test_stats_io.py -q`, expected `ImportError`.

- [x] **Step 4: Implement** (`packs/__init__.py` and `packs/sqlserver/__init__.py` are empty for now)

```python
# src/queryreceipts/packs/sqlserver/stats_io.py
"""Parse SQL Server STATISTICS IO / STATISTICS TIME output.

Handles the modern long line format (page server / lob counters), repeated
per-statement table lines (aggregated per table), parse/compile vs execution
time separation, and engine warnings. Captures may be sectioned with
====BEGIN_SECTION:name==== / ====END_SECTION:name==== markers.
"""
from __future__ import annotations

import re

TABLE_RE = re.compile(
    r"Table '(?P<table>[^']+)'\. Scan count (?P<scans>\d+), "
    r"logical reads (?P<reads>\d+)")
LOB_RE = re.compile(r"lob logical reads (?P<lob>\d+)")
TIME_RE = re.compile(
    r"CPU time = (?P<cpu>\d+) ms,\s*elapsed time = (?P<elapsed>\d+) ms")
WARNING_RE = re.compile(r"^Warning: (?P<msg>.+?)\s*$", re.MULTILINE)
COMPILE_HEADER = "parse and compile time"
EXEC_HEADER = "Execution Times"
SECTION_BEGIN = "====BEGIN_SECTION:{name}===="
SECTION_END = "====END_SECTION:{name}===="


class SectionNotFound(Exception):
    pass


def extract_section(text: str, name: str) -> str:
    if "====BEGIN_SECTION:" not in text:
        return text  # unmarked capture: the whole file is the section
    begin = SECTION_BEGIN.format(name=name)
    if begin not in text:
        found = sorted(set(re.findall(r"====BEGIN_SECTION:(\w+)====", text)))
        raise SectionNotFound(
            f"section {name!r} not in capture; sections present: {found}")
    start = text.index(begin) + len(begin)
    end = SECTION_END.format(name=name)
    stop = text.index(end, start) if end in text else len(text)
    return text[start:stop]


def parse(text: str) -> dict:
    tables: dict[str, dict] = {}
    exec_times: list[dict] = []
    compile_times: list[dict] = []
    mode = "exec"  # TIME lines with no seen header are execution times
    for line in text.splitlines():
        if COMPILE_HEADER in line:
            mode = "compile"
            continue
        if EXEC_HEADER in line:
            mode = "exec"
            continue
        t = TIME_RE.search(line)
        if t:
            bucket = compile_times if mode == "compile" else exec_times
            bucket.append({"cpu_ms": int(t["cpu"]),
                           "elapsed_ms": int(t["elapsed"])})
            mode = "exec"
            continue
        m = TABLE_RE.search(line)
        if m:
            rec = tables.setdefault(m["table"], {
                "logical_reads": 0, "scan_count": 0,
                "lob_logical_reads": 0, "statements": 0})
            rec["logical_reads"] += int(m["reads"])
            rec["scan_count"] += int(m["scans"])
            rec["statements"] += 1
            lob = LOB_RE.search(line)
            if lob:
                rec["lob_logical_reads"] += int(lob["lob"])
    rows = [{"table": name, **vals} for name, vals in tables.items()]
    rows.sort(key=lambda r: r["logical_reads"], reverse=True)
    return {
        "tables": rows,
        "time": {
            "cpu_ms": sum(e["cpu_ms"] for e in exec_times),
            "elapsed_ms": sum(e["elapsed_ms"] for e in exec_times),
            "statements": len(exec_times),
        },
        "compile": {
            "cpu_ms": sum(c["cpu_ms"] for c in compile_times),
            "elapsed_ms": sum(c["elapsed_ms"] for c in compile_times),
        },
        "warnings": WARNING_RE.findall(text),
    }
```

- [x] **Step 5: Run to verify pass** — `pytest tests/test_stats_io.py -q`, expected `3 passed`.

- [x] **Step 6: Commit** — `git add -A && git commit -m "feat(sqlserver): STATISTICS IO parser with sections, lob reads, aggregation"`

---

### Task 7: STATISTICS TIME assertions + renderer + CLI `parse`

**Files:**
- Modify: `src/queryreceipts/packs/sqlserver/stats_io.py` (add `render`)
- Modify: `src/queryreceipts/packs/__init__.py` (dispatch table)
- Modify: `src/queryreceipts/cli.py` (add `parse` subcommand)
- Test: `tests/test_stats_io.py`, `tests/test_cli.py` (append)

- [x] **Step 1: Write the failing tests** (append to `tests/test_stats_io.py`)

```python
def test_time_separates_compile_from_execution():
    result = parse(FIXTURE.read_text(encoding="utf-8"))
    assert result["compile"] == {"cpu_ms": 391, "elapsed_ms": 391}
    assert result["time"]["cpu_ms"] == 0 + 137640 + 16
    assert result["time"]["elapsed_ms"] == 0 + 158029 + 21
    assert result["time"]["statements"] == 3
    assert result["warnings"] == [
        "Null value is eliminated by an aggregate or other SET operation."]


def test_render_is_compact_and_leads_with_the_symptom_numbers():
    from queryreceipts.packs.sqlserver.stats_io import render
    out = render(parse(FIXTURE.read_text(encoding="utf-8")))
    lines = out.splitlines()
    assert lines[0].startswith("elapsed 158,050 ms")
    assert "Worktable" in out and "11,969,839" in out
    assert len(out) < 2000  # parser-first: summaries stay context-small
```

And append to `tests/test_cli.py`:

```python
def test_parse_subcommand_summarizes_registered_evidence(tmp_path, capsys):
    root = tmp_path / "c"
    main(["init", str(root), "--engine", "sqlserver",
          "--database", "S", "--symptom", "x"])
    cap = root / "diag.txt"
    cap.write_text(
        "Table 'BIG'. Scan count 4, logical reads 2000000, physical reads 0.\n"
        " SQL Server Execution Times:\n"
        "   CPU time = 5000 ms,  elapsed time = 9000 ms.\n",
        encoding="utf-8")
    main(["add", str(cap), "--kind", "stats_io", "--transport", "courier",
          "--environment", "synthetic", "--runner", "analyst", "--case", str(root)])
    rc = main(["parse", "ev-0001", "--case", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BIG" in out and "2,000,000" in out
    # a summary_derived event cites the source artifact
    from queryreceipts.case import Case
    events = Case.find(root).events()
    derived = [e for e in events if e["event"] == "summary_derived"]
    assert derived and derived[0]["source"] == "ev-0001"
```

- [x] **Step 2: Run to verify failure** — `pytest tests/test_stats_io.py tests/test_cli.py -q`, expected failures on `render` import and `parse` subcommand.

- [x] **Step 3: Implement**

Add to `stats_io.py`:

```python
def render(parsed: dict) -> str:
    t = parsed["time"]
    c = parsed["compile"]
    lines = [
        f"elapsed {t['elapsed_ms']:,} ms | cpu {t['cpu_ms']:,} ms "
        f"| {t['statements']} timed statement(s) "
        f"| compile {c['cpu_ms']:,} ms cpu",
    ]
    if parsed["warnings"]:
        lines.append(f"warnings: {len(parsed['warnings'])} "
                     f"(first: {parsed['warnings'][0]})")
    lines.append("rank | table | logical_reads | scans | stmts | lob_reads")
    for i, r in enumerate(parsed["tables"][:15], 1):
        lines.append(
            f"{i} | {r['table']} | {r['logical_reads']:,} | "
            f"{r['scan_count']:,} | {r['statements']} | "
            f"{r['lob_logical_reads']:,}")
    if len(parsed["tables"]) > 15:
        lines.append(f"… {len(parsed['tables']) - 15} more tables omitted")
    return "\n".join(lines) + "\n"
```

`src/queryreceipts/packs/__init__.py`:

```python
"""Engine packs. Dispatch: evidence kind -> (parse, render)."""
from __future__ import annotations

from .sqlserver import stats_io


def get_parser(kind: str):
    table = {
        "stats_io": (stats_io.parse, stats_io.render),
    }
    if kind not in table:
        raise KeyError(
            f"no parser for kind {kind!r}; parseable kinds: {sorted(table)}")
    return table[kind]
```

Add to `cli.py` (new command + registration in `build_parser`):

```python
def cmd_parse(args) -> int:
    from .packs import get_parser
    from .packs.sqlserver.stats_io import extract_section
    case = _find_case(args)
    ev = case.get_evidence(args.artifact)
    parse_fn, render_fn = get_parser(ev.kind)
    text = (case.root / ev.path).read_text(encoding="utf-8", errors="replace")
    if args.section:
        text = extract_section(text, args.section)
    parsed = parse_fn(text)
    case.append({"event": "summary_derived", "source": ev.artifact_id,
                 "kind": ev.kind, "section": args.section or ""})
    print(json.dumps(parsed, indent=2) if args.json else render_fn(parsed),
          end="" if not args.json else "\n")
    return 0
```

```python
    sp = sub.add_parser("parse", help="parse registered evidence into a summary")
    sp.add_argument("artifact", help="artifact id, e.g. ev-0001")
    sp.add_argument("--section", default=None)
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_parse)
```

Also extend the `except` clause in `main` to include `KeyError`.

- [x] **Step 4: Run to verify pass** — `pytest -q`, expected all green.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: parse subcommand + stats_io renderer, summaries cite source artifacts"`

---

### Task 8: Plan XML fixture + statement/operator parsing

**Files:**
- Create: `tests/fixtures/plan_two_statements.sqlplan`
- Create: `src/queryreceipts/packs/sqlserver/planxml.py`
- Test: `tests/test_planxml.py`

- [x] **Step 1: Create the fixture** — a hand-crafted, valid showplan with two statements; statement 1 has a Hash Join with a tempdb spill, actuals showing a 100× misestimate, a missing index, and a compiled parameter; statement 2 is a trivial scan with no runtime info.

```xml
<?xml version="1.0" encoding="utf-16"?>
<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan" Version="1.564">
  <BatchSequence><Batch><Statements>
    <StmtSimple StatementText="SELECT r.ID FROM RESERVATION r JOIN TRAVELER t ON t.RES_ID = r.ID WHERE r.START_DATE &gt; @from" StatementId="1" StatementSubTreeCost="1423.68" StatementEstRows="120" StatementType="SELECT">
      <QueryPlan CachedPlanSize="512" CompileTime="391" CompileCPU="391" CompileMemory="8192">
        <MissingIndexes>
          <MissingIndexGroup Impact="91.5">
            <MissingIndex Database="[FleetDB]" Schema="[dbo]" Table="[RESERVATION]">
              <ColumnGroup Usage="EQUALITY"><Column Name="[STATUS_ID]" ColumnId="3"/></ColumnGroup>
              <ColumnGroup Usage="INCLUDE"><Column Name="[START_DATE]" ColumnId="5"/></ColumnGroup>
            </MissingIndex>
          </MissingIndexGroup>
        </MissingIndexes>
        <MemoryGrantInfo SerialRequiredMemory="512" SerialDesiredMemory="1024" RequestedMemory="1024" GrantedMemory="1024" MaxUsedMemory="892"/>
        <RelOp NodeId="0" PhysicalOp="Hash Match" LogicalOp="Inner Join" EstimateRows="120" EstimatedTotalSubtreeCost="1423.68">
          <RunTimeInformation>
            <RunTimeCountersPerThread Thread="0" ActualRows="12000" ActualEndOfScans="1" ActualExecutions="1"/>
          </RunTimeInformation>
          <Warnings>
            <SpillToTempDb SpillLevel="2" SpilledThreadCount="1"/>
          </Warnings>
          <Hash>
            <RelOp NodeId="1" PhysicalOp="Clustered Index Scan" LogicalOp="Clustered Index Scan" EstimateRows="729842" EstimatedTotalSubtreeCost="800.10">
              <RunTimeInformation>
                <RunTimeCountersPerThread Thread="0" ActualRows="729842" ActualEndOfScans="1" ActualExecutions="1"/>
              </RunTimeInformation>
              <IndexScan Ordered="false">
                <Object Database="[FleetDB]" Schema="[dbo]" Table="[RESERVATION]" Index="[PK_RESERVATION]" IndexKind="Clustered"/>
              </IndexScan>
            </RelOp>
            <RelOp NodeId="2" PhysicalOp="Index Seek" LogicalOp="Index Seek" EstimateRows="120" EstimatedTotalSubtreeCost="403.20">
              <RunTimeInformation>
                <RunTimeCountersPerThread Thread="0" ActualRows="12000" ActualEndOfScans="1" ActualExecutions="1"/>
              </RunTimeInformation>
              <IndexScan Ordered="true">
                <Object Database="[FleetDB]" Schema="[dbo]" Table="[TRAVELER]" Index="[IX_TRAVELER_RES]" IndexKind="NonClustered"/>
              </IndexScan>
            </RelOp>
          </Hash>
        </RelOp>
        <ParameterList>
          <ColumnReference Column="@from" ParameterDataType="datetime" ParameterCompiledValue="'2025-04-01 00:00:00.000'"/>
        </ParameterList>
      </QueryPlan>
    </StmtSimple>
    <StmtSimple StatementText="SELECT COUNT(*) FROM STATUS_CODE" StatementId="2" StatementSubTreeCost="0.05" StatementEstRows="1" StatementType="SELECT">
      <QueryPlan>
        <RelOp NodeId="0" PhysicalOp="Stream Aggregate" LogicalOp="Aggregate" EstimateRows="1" EstimatedTotalSubtreeCost="0.05">
          <StreamAggregate>
            <RelOp NodeId="1" PhysicalOp="Index Scan" LogicalOp="Index Scan" EstimateRows="202" EstimatedTotalSubtreeCost="0.04">
              <IndexScan Ordered="false">
                <Object Database="[FleetDB]" Schema="[dbo]" Table="[STATUS_CODE]" Index="[IX_STATUS_CODE]" IndexKind="NonClustered"/>
              </IndexScan>
            </RelOp>
          </StreamAggregate>
        </RelOp>
      </QueryPlan>
    </StmtSimple>
  </Statements></Batch></BatchSequence>
</ShowPlanXML>
```

Save as UTF-8 (the `utf-16` in the declaration is what SSMS writes, but ElementTree reads the actual bytes; write the file UTF-8 **without** the encoding attribute to keep the fixture honest: use `<?xml version="1.0"?>`).

- [x] **Step 2: Write the failing tests**

```python
# tests/test_planxml.py
from pathlib import Path

from queryreceipts.packs.sqlserver.planxml import parse_plan

FIXTURE = Path(__file__).parent / "fixtures" / "plan_two_statements.sqlplan"


def _plan():
    return parse_plan(FIXTURE.read_text(encoding="utf-8"))


def test_all_statements_are_parsed_not_just_the_first():
    plan = _plan()
    assert len(plan["statements"]) == 2
    assert plan["statements"][0]["cost"] == 1423.68
    assert plan["statements"][1]["cost"] == 0.05


def test_operators_carry_est_actual_and_self_cost():
    s1 = _plan()["statements"][0]
    root = next(o for o in s1["operators"] if o["node_id"] == 0)
    assert root["physical_op"] == "Hash Match"
    assert root["est_rows"] == 120.0
    assert root["actual_rows"] == 12000
    # self cost = subtree minus direct children subtrees
    assert abs(root["est_self_cost"] - (1423.68 - 800.10 - 403.20)) < 0.01
    scan = next(o for o in s1["operators"] if o["node_id"] == 1)
    assert scan["object"] == "[FleetDB].[dbo].[RESERVATION].[PK_RESERVATION]"


def test_statement_without_runtime_info_reports_actuals_as_none():
    s2 = _plan()["statements"][1]
    assert all(o["actual_rows"] is None for o in s2["operators"])
```

- [x] **Step 3: Run to verify failure** — `pytest tests/test_planxml.py -q`, expected `ImportError`.

- [x] **Step 4: Implement**

```python
# src/queryreceipts/packs/sqlserver/planxml.py
"""Parse SQL Server showplan XML (.sqlplan).

Parses EVERY statement in the batch (multi-statement procs are the norm),
every operator with estimated vs actual rows (actuals stay None when the
plan has no RunTimeInformation — estimated plans don't get fake actuals),
self-cost attribution, spill/convert warnings, missing indexes, and
parameter presence. Parameter VALUES are never extracted: plans embed
compiled literals, and the engine treats them as sensitive by default.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

NS = "{http://schemas.microsoft.com/sqlserver/2004/07/showplan}"
STMT_TAGS = {f"{NS}StmtSimple", f"{NS}StmtCond", f"{NS}StmtCursor"}


def _tag(el: ET.Element) -> str:
    return el.tag.removeprefix(NS)


def parse_plan(text: str) -> dict:
    root = ET.fromstring(text)
    statements = []
    for el in root.iter():
        if el.tag in STMT_TAGS:
            statements.append(_parse_statement(el))
    return {"statements": statements}


def _parse_statement(stmt: ET.Element) -> dict:
    out = {
        "statement_id": int(stmt.get("StatementId", "0")),
        "statement_type": stmt.get("StatementType", ""),
        "text": (stmt.get("StatementText") or "")[:200],
        "cost": float(stmt.get("StatementSubTreeCost", "0") or 0),
        "est_rows": float(stmt.get("StatementEstRows", "0") or 0),
    }
    qp = stmt.find(f"{NS}QueryPlan")
    out["memory_grant_kb"] = None
    out["parameters"] = []
    out["missing_indexes"] = []
    out["operators"] = []
    if qp is None:
        return out

    mg = qp.find(f"{NS}MemoryGrantInfo")
    if mg is not None and mg.get("GrantedMemory") is not None:
        out["memory_grant_kb"] = int(mg.get("GrantedMemory"))

    for cr in qp.iter(f"{NS}ColumnReference"):
        if cr.get("Column", "").startswith("@"):
            out["parameters"].append({
                "name": cr.get("Column"),
                "compiled_value_present":
                    cr.get("ParameterCompiledValue") is not None,
            })

    for mi in qp.iter(f"{NS}MissingIndex"):
        entry = {"database": mi.get("Database", ""),
                 "schema": mi.get("Schema", ""),
                 "table": mi.get("Table", ""),
                 "equality": [], "inequality": [], "included": []}
        usage_key = {"EQUALITY": "equality", "INEQUALITY": "inequality",
                     "INCLUDE": "included"}
        for cg in mi.findall(f"{NS}ColumnGroup"):
            key = usage_key.get(cg.get("Usage", ""))
            if key:
                entry[key] = [c.get("Name", "")
                              for c in cg.findall(f"{NS}Column")]
        out["missing_indexes"].append(entry)

    # operators: walk RelOps; direct-children map gives self-cost
    rel_ops = list(qp.iter(f"{NS}RelOp"))
    children: dict[ET.Element, list[ET.Element]] = {r: [] for r in rel_ops}
    for rel in rel_ops:
        for desc in rel.iter(f"{NS}RelOp"):
            if desc is rel:
                continue
            # direct child = no intermediate RelOp between rel and desc
            anc = _nearest_relop_ancestor(desc, rel_ops, rel)
            if anc is rel:
                children[rel].append(desc)
    # Build a parent map once instead (cheaper and simpler):
    out["operators"] = _build_operators(qp, rel_ops)
    return out


def _nearest_relop_ancestor(el, rel_ops, candidate):  # replaced below
    raise NotImplementedError


def _build_operators(qp: ET.Element, rel_ops: list[ET.Element]) -> list[dict]:
    parent_of: dict[ET.Element, ET.Element] = {}
    for parent in qp.iter():
        for child in parent:
            parent_of[child] = parent

    def nearest_relop(el: ET.Element) -> ET.Element | None:
        cur = parent_of.get(el)
        while cur is not None:
            if cur.tag == f"{NS}RelOp":
                return cur
            cur = parent_of.get(cur)
        return None

    direct_children: dict[ET.Element, list[ET.Element]] = {
        r: [] for r in rel_ops}
    for rel in rel_ops:
        anc = nearest_relop(rel)
        if anc is not None:
            direct_children[anc].append(rel)

    ops = []
    for rel in rel_ops:
        subtree = float(rel.get("EstimatedTotalSubtreeCost", "0") or 0)
        child_cost = sum(
            float(c.get("EstimatedTotalSubtreeCost", "0") or 0)
            for c in direct_children[rel])
        actual = None
        rti = rel.find(f"{NS}RunTimeInformation")
        if rti is not None:
            actual = sum(
                int(th.get("ActualRows", "0") or 0)
                for th in rti.findall(f"{NS}RunTimeCountersPerThread"))
        warnings = []
        w = rel.find(f"{NS}Warnings")
        if w is not None:
            warnings = [_tag(child) for child in w]
            warnings += [k for k, v in w.attrib.items() if v == "true"]
        obj = None
        for o in rel.iter(f"{NS}Object"):
            if nearest_relop(o) is rel:
                parts = [o.get(k) for k in
                         ("Database", "Schema", "Table", "Index")]
                obj = ".".join(p for p in parts if p)
                break
        ops.append({
            "node_id": int(rel.get("NodeId", "-1")),
            "physical_op": rel.get("PhysicalOp", ""),
            "logical_op": rel.get("LogicalOp", ""),
            "est_rows": float(rel.get("EstimateRows", "0") or 0),
            "actual_rows": actual,
            "est_subtree_cost": subtree,
            "est_self_cost": max(0.0, subtree - child_cost),
            "object": obj,
            "warnings": warnings,
        })
    return ops
```

Then delete the dead `_nearest_relop_ancestor` stub and the `children` block in `_parse_statement` (artifact of drafting — final code calls only `_build_operators`). Final `_parse_statement` operator section is just:

```python
    rel_ops = list(qp.iter(f"{NS}RelOp"))
    out["operators"] = _build_operators(qp, rel_ops)
    return out
```

- [x] **Step 5: Run to verify pass** — `pytest tests/test_planxml.py -q`, expected `3 passed`.

- [x] **Step 6: Commit** — `git add -A && git commit -m "feat(sqlserver): showplan parser — all statements, self-cost, actuals stay honest"`

---

### Task 9: Plan analysis — skew, warnings, render — and CLI wiring

**Files:**
- Modify: `src/queryreceipts/packs/sqlserver/planxml.py` (add `analyze`, `render`)
- Modify: `src/queryreceipts/packs/__init__.py` (register `plan_xml`)
- Test: `tests/test_planxml.py` (append)

- [x] **Step 1: Write the failing tests** (append)

```python
def test_skew_ranks_worst_misestimates_only_where_actuals_exist():
    from queryreceipts.packs.sqlserver.planxml import analyze
    report = analyze(_plan())
    skew = report["statements"][0]["skew"]
    assert skew[0]["node_id"] in (0, 2)          # both are 100x under-estimates
    assert skew[0]["ratio"] == 100.0
    assert report["statements"][1]["skew"] == []  # no actuals -> no fake skew


def test_warnings_and_parameters_surface():
    from queryreceipts.packs.sqlserver.planxml import analyze
    s1 = analyze(_plan())["statements"][0]
    assert "SpillToTempDb" in s1["plan_warnings"]
    assert s1["parameters"] == [
        {"name": "@from", "compiled_value_present": True}]


def test_render_under_2kb_and_leads_with_cost_and_skew():
    from queryreceipts.packs.sqlserver.planxml import analyze, render
    out = render(analyze(_plan()))
    assert len(out) < 2000
    assert "1423.68" in out
    assert "100.0x" in out
    assert "SpillToTempDb" in out
    assert "compiled parameter values present" in out
```

- [x] **Step 2: Run to verify failure** — expected `ImportError: analyze`.

- [x] **Step 3: Implement** (append to `planxml.py`)

```python
def analyze(plan: dict) -> dict:
    """Derive the tuner-facing report from a parsed plan."""
    statements = []
    for s in plan["statements"]:
        skew = []
        for o in s["operators"]:
            if o["actual_rows"] is None or o["est_rows"] <= 0:
                continue
            ratio = max(o["actual_rows"], 1) / max(o["est_rows"], 1)
            ratio = round(max(ratio, 1 / ratio), 1)  # symmetric: under or over
            if ratio >= 10:
                skew.append({"node_id": o["node_id"],
                             "op": o["physical_op"],
                             "est_rows": o["est_rows"],
                             "actual_rows": o["actual_rows"],
                             "ratio": ratio})
        skew.sort(key=lambda x: x["ratio"], reverse=True)
        plan_warnings = sorted({w for o in s["operators"]
                                for w in o["warnings"]})
        top_ops = sorted(s["operators"],
                         key=lambda o: o["est_self_cost"], reverse=True)[:5]
        statements.append({**s, "skew": skew[:5],
                           "plan_warnings": plan_warnings,
                           "top_self_cost_ops": top_ops})
    return {"statements": statements}


def parse_and_analyze(text: str) -> dict:
    return analyze(parse_plan(text))


def render(report: dict) -> str:
    lines = []
    for s in report["statements"]:
        lines.append(f"stmt {s['statement_id']} [{s['statement_type']}] "
                     f"cost={s['cost']} est_rows={s['est_rows']:,.0f} "
                     f"| {s['text'][:80]}")
        if s["memory_grant_kb"] is not None:
            lines.append(f"  memory grant: {s['memory_grant_kb']:,} KB")
        if any(p["compiled_value_present"] for p in s["parameters"]):
            names = [p["name"] for p in s["parameters"]]
            lines.append(f"  compiled parameter values present ({', '.join(names)}) "
                         "— treat plan file as sensitive")
        for w in s["plan_warnings"]:
            lines.append(f"  WARNING: {w}")
        for k in s["skew"]:
            lines.append(f"  skew {k['ratio']}x node {k['node_id']} "
                         f"{k['op']}: est {k['est_rows']:,.0f} vs "
                         f"actual {k['actual_rows']:,}")
        for o in s["top_self_cost_ops"][:3]:
            obj = f" -> {o['object']}" if o["object"] else ""
            lines.append(f"  op node {o['node_id']} {o['physical_op']} "
                         f"self-cost {o['est_self_cost']:.1f}{obj}")
        for mi in s["missing_indexes"]:
            lines.append(f"  missing index: {mi['table']} EQ={mi['equality']} "
                         f"INEQ={mi['inequality']} INC={mi['included']}")
    return "\n".join(lines) + "\n"
```

Register in `packs/__init__.py` (dispatch becomes):

```python
from .sqlserver import planxml, stats_io


def get_parser(kind: str):
    table = {
        "stats_io": (stats_io.parse, stats_io.render),
        "plan_xml": (planxml.parse_and_analyze, planxml.render),
    }
    if kind not in table:
        raise KeyError(
            f"no parser for kind {kind!r}; parseable kinds: {sorted(table)}")
    return table[kind]
```

(`cmd_parse` already dispatches by kind; `--section` only applies to text captures — guard it: if `args.section` and `ev.kind != "stats_io"`, error politely.)

- [x] **Step 4: Run to verify pass** — `pytest -q`, all green.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat(sqlserver): plan analysis — skew, spills, sensitivity flag, compact render"`

---

### Task 10: Plan diff

**Files:**
- Create: `src/queryreceipts/packs/sqlserver/plandiff.py`
- Modify: `src/queryreceipts/cli.py` (add `diff` subcommand)
- Test: `tests/test_plandiff.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_plandiff.py
import copy
from pathlib import Path

from queryreceipts.packs.sqlserver.plandiff import diff_plans, render_diff
from queryreceipts.packs.sqlserver.planxml import parse_plan

FIXTURE = Path(__file__).parent / "fixtures" / "plan_two_statements.sqlplan"


def _variant():
    """Same plan, mutated: join flips Hash->Loop, cost drops, spill gone."""
    plan = parse_plan(FIXTURE.read_text(encoding="utf-8"))
    v = copy.deepcopy(plan)
    s = v["statements"][0]
    s["cost"] = 12.5
    root = next(o for o in s["operators"] if o["node_id"] == 0)
    root["physical_op"] = "Nested Loops"
    root["warnings"] = []
    return plan, v


def test_diff_reports_cost_join_and_warning_changes():
    a, b = _variant()
    d = diff_plans(a, b)
    s0 = d["statements"][0]
    assert s0["cost"] == {"a": 1423.68, "b": 12.5}
    assert s0["operator_changes"]["removed"] == {"Hash Match": 1}
    assert s0["operator_changes"]["added"] == {"Nested Loops": 1}
    assert s0["warning_changes"]["removed"] == ["SpillToTempDb"]
    # statement 2 unchanged
    assert d["statements"][1]["operator_changes"]["added"] == {}


def test_diff_handles_statement_count_mismatch():
    a, b = _variant()
    b["statements"] = b["statements"][:1]
    d = diff_plans(a, b)
    assert d["unmatched_statements"] == {"a": 1, "b": 0}


def test_render_diff_mentions_the_join_flip():
    a, b = _variant()
    out = render_diff(diff_plans(a, b))
    assert "Hash Match" in out and "Nested Loops" in out
    assert "1423.68" in out and "12.5" in out
```

- [x] **Step 2: Run to verify failure** — expected `ImportError`.

- [x] **Step 3: Implement**

```python
# src/queryreceipts/packs/sqlserver/plandiff.py
"""Diff two parsed plans of the same query (e.g. Query Store cheap vs
expensive). Statements align by order; a count mismatch is reported, not
papered over. Costs are optimizer estimates — the diff narrates shape
changes, it does not declare a winner."""
from __future__ import annotations

from collections import Counter


def _op_counter(stmt: dict) -> Counter:
    return Counter(o["physical_op"] for o in stmt["operators"])


def _warnings(stmt: dict) -> set:
    return {w for o in stmt["operators"] for w in o["warnings"]}


def _objects(stmt: dict) -> set:
    return {o["object"] for o in stmt["operators"] if o["object"]}


def diff_plans(a: dict, b: dict) -> dict:
    sa, sb = a["statements"], b["statements"]
    pairs = list(zip(sa, sb))
    statements = []
    for stmt_a, stmt_b in pairs:
        ca, cb = _op_counter(stmt_a), _op_counter(stmt_b)
        wa, wb = _warnings(stmt_a), _warnings(stmt_b)
        oa, ob = _objects(stmt_a), _objects(stmt_b)
        statements.append({
            "statement_id": stmt_a["statement_id"],
            "cost": {"a": stmt_a["cost"], "b": stmt_b["cost"]},
            "est_rows": {"a": stmt_a["est_rows"], "b": stmt_b["est_rows"]},
            "memory_grant_kb": {"a": stmt_a["memory_grant_kb"],
                                "b": stmt_b["memory_grant_kb"]},
            "operator_changes": {
                "added": dict(cb - ca),
                "removed": dict(ca - cb),
            },
            "object_changes": {
                "added": sorted(ob - oa),
                "removed": sorted(oa - ob),
            },
            "warning_changes": {
                "added": sorted(wb - wa),
                "removed": sorted(wa - wb),
            },
        })
    return {
        "statements": statements,
        "unmatched_statements": {"a": len(sa) - len(pairs),
                                 "b": len(sb) - len(pairs)},
    }


def render_diff(diff: dict) -> str:
    lines = ["plan diff (A -> B); costs are optimizer estimates"]
    un = diff["unmatched_statements"]
    if un["a"] or un["b"]:
        lines.append(f"  STATEMENT COUNT MISMATCH: {un['a']} extra in A, "
                     f"{un['b']} extra in B — pairwise diff covers the "
                     "matched prefix only")
    for s in diff["statements"]:
        lines.append(f"stmt {s['statement_id']}: cost {s['cost']['a']} -> "
                     f"{s['cost']['b']}")
        for label, key in (("ops added", "added"), ("ops removed", "removed")):
            if s["operator_changes"][key]:
                items = ", ".join(f"{op} x{n}" for op, n in
                                  sorted(s["operator_changes"][key].items()))
                lines.append(f"  {label}: {items}")
        for key in ("added", "removed"):
            for obj in s["object_changes"][key]:
                lines.append(f"  index/object {key}: {obj}")
            for w in s["warning_changes"][key]:
                lines.append(f"  warning {key}: {w}")
    return "\n".join(lines) + "\n"
```

CLI subcommand (in `cli.py`):

```python
def cmd_diff(args) -> int:
    from .packs.sqlserver.plandiff import diff_plans, render_diff
    from .packs.sqlserver.planxml import parse_plan
    case = _find_case(args)
    plans = []
    for ref in (args.plan_a, args.plan_b):
        ev = case.get_evidence(ref)
        if ev.kind != "plan_xml":
            raise CaseError(f"{ref} is kind {ev.kind!r}, need plan_xml")
        text = (case.root / ev.path).read_text(encoding="utf-8",
                                               errors="replace")
        plans.append(parse_plan(text))
    d = diff_plans(*plans)
    case.append({"event": "plans_diffed",
                 "a": args.plan_a, "b": args.plan_b})
    print(json.dumps(d, indent=2) if args.json else render_diff(d),
          end="" if not args.json else "\n")
    return 0
```

```python
    sp = sub.add_parser("diff", help="diff two registered plan_xml artifacts")
    sp.add_argument("plan_a")
    sp.add_argument("plan_b")
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_diff)
```

- [x] **Step 4: Run to verify pass** — `pytest -q`, all green.

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat(sqlserver): plan diff — shape changes, honest about estimate semantics"`

---

### Task 11: Wrap-up — full suite, README dev section, plan checkboxes

- [x] **Step 1: Full verification**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (~22). Also: `.venv/bin/receipts --help` lists init/add/status/parse/diff.

- [x] **Step 2: Add a Development section to README.md**

Append:

```markdown
## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Engine code is stdlib-only by policy: a proof tool should carry zero
supply-chain surface. pytest is the only dev dependency.
```

- [x] **Step 3: Tick all checkboxes in this plan file, commit**

```bash
git add -A && git commit -m "chore: plan 1 complete — proof-engine foundation"
```

---

## Self-review notes

- **Spec coverage:** evidence-artifact contract (README "transport invariant") → Tasks 2/4; parser-first context economy → render size assertions in Tasks 7/9; three-valued honesty → `actual_rows: None` (Task 8), `SectionNotFound` (Task 6), statement-mismatch reporting (Task 10); sensitivity posture → parameter presence-not-value (Tasks 8/9). Prescriptions, validation, certificates, synthetic workload: deliberately Plan 2. Plugin skin: Plan 3.
- **Type consistency:** `parse_plan` returns `{"statements": [...]}`; `analyze` consumes it and is what `get_parser` exposes for `plan_xml` via `parse_and_analyze`; `diff_plans` consumes two `parse_plan` outputs (not `analyze` outputs) — CLI `cmd_diff` calls `parse_plan` directly. Checked.
- **Placeholder scan:** Task 8's drafting artifact (`_nearest_relop_ancestor`) is explicitly deleted in its own step; no TBDs remain.
