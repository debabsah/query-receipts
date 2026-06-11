# QueryReceipts Plan 2: The Proof Loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The cure loop's proof half: `receipts prescribe` (diagnostics / validation / benchmark SQL rendered with comparability gates and a pre-registered protocol), `receipts grade` (parse saved results into verdicts), `receipts certify` (a three-valued certificate citing every artifact).

**Architecture:** SQL templates live as package data under `packs/sqlserver/templates/`; `prescription.py` renders them (marker substitution, refuses to emit unrendered markers) and logs a `prescription_issued` ledger event with the expected save path. `grading.py` parses validation-results text into PASS/FAIL/gate rows. `certificate.py` assembles the verdict — PROVEN only when every check passed and every required artifact exists; any FAIL → REFUTED; anything missing → UNVERIFIED with the missing capture named — and renders `certificate.md` + `certificate.json` into the case.

**Tech Stack:** unchanged — stdlib only (importlib.resources for templates), pytest.

**Carry-over invariants:** validation runs both queries in ONE session (comparability by construction) and additionally echoes gate rows (engine version, db, SET options) into the results so the grader can verify and the certificate can cite. Benchmark protocol (run count, headline metric) is pinned in the ledger BEFORE results exist. Temp tables only; no writes to user objects.

**File structure:**

```
src/queryreceipts/
├── prescription.py                      # render + issue prescriptions
├── certificate.py                       # verdict assembly + render
└── packs/sqlserver/
    ├── grading.py                       # validation-results parser
    └── templates/
        ├── diagnostics.sql.tmpl
        ├── validation.sql.tmpl
        └── benchmark.sql.tmpl
tests/
├── test_prescription.py
├── test_grading.py
├── test_certificate.py
└── fixtures/validation_results_pass.txt, validation_results_fail.txt
```

---

### Task 1: Template rendering and the prescription module

**Files:**
- Create: `src/queryreceipts/prescription.py`, `src/queryreceipts/packs/sqlserver/templates/diagnostics.sql.tmpl`
- Test: `tests/test_prescription.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_prescription.py
import pytest

from queryreceipts.case import Case
from queryreceipts.prescription import (
    UnrenderedMarker, issue, render_template)

META = {"case": "c", "engine": "sqlserver", "database": "FleetDB",
        "symptom": "slow"}


def test_render_replaces_markers_and_injects_sql():
    out = render_template(
        "USE [{{DB_NAME}}];\n-- ===INJECT_ORIGINAL_QUERY===\n",
        {"DB_NAME": "FleetDB"},
        {"INJECT_ORIGINAL_QUERY": "SELECT 1 AS x"})
    assert "USE [FleetDB];" in out
    assert "SELECT 1 AS x" in out
    assert "{{" not in out and "===INJECT" not in out


def test_render_refuses_unrendered_markers():
    with pytest.raises(UnrenderedMarker, match="DB_NAME"):
        render_template("USE [{{DB_NAME}}];", {}, {})


def test_issue_writes_prescription_and_ledger_event(tmp_path):
    case = Case.init(tmp_path / "c", META)
    (case.root / "original.sql").write_text("SELECT 1 AS x",
                                            encoding="utf-8")
    p = issue(case, "diagnostics", values={}, save_as="diagnostics.sql",
              expected_capture="runs/baseline/diagnostics.txt")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "USE [FleetDB];" in text
    assert "SELECT 1 AS x" in text
    issued = [e for e in case.events() if e["event"] == "prescription_issued"]
    assert issued[0]["expected_capture"] == "runs/baseline/diagnostics.txt"
    assert issued[0]["prescription"] == "diagnostics"
```

- [x] **Step 2: Run to verify failure** — `pytest tests/test_prescription.py -q`, expected `ImportError`.

- [x] **Step 3: Implement**

`src/queryreceipts/packs/sqlserver/templates/diagnostics.sql.tmpl`:
```sql
/* receipts prescription: diagnostics (baseline IO/TIME capture)
   Run in SSMS, Results to Text (Ctrl+T). Save the ENTIRE output to:
   {{EXPECTED_CAPTURE}}
*/
USE [{{DB_NAME}}];
SET NOCOUNT ON;

PRINT '====BEGIN_SECTION:baseline_io_time====';
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

-- ===INJECT_ORIGINAL_QUERY===

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
PRINT '====END_SECTION:baseline_io_time====';
```

`src/queryreceipts/prescription.py`:
```python
"""Prescriptions: capture requests the engine issues to a transport.

A prescription is rendered SQL plus instructions: run it, save the output to
the expected path, register it as evidence. Rendering refuses to emit any
unrendered {{MARKER}} or ===INJECT_*=== — half-rendered SQL handed to a
human courier is how investigations go wrong.
"""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from .case import Case


class UnrenderedMarker(Exception):
    pass


MARKER_RE = re.compile(r"\{\{(\w+)\}\}")
INJECT_RE = re.compile(r"^-- ===(\w+)===\s*$", re.MULTILINE)


def render_template(template: str, values: dict, injections: dict) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", str(val))
    for key, sql in injections.items():
        out = out.replace(f"-- ==={key}===", sql)
    leftover = MARKER_RE.findall(out) + INJECT_RE.findall(out)
    if leftover:
        raise UnrenderedMarker(
            f"unrendered markers remain: {sorted(set(leftover))}")
    return out


def load_template(engine: str, name: str) -> str:
    pkg = f"queryreceipts.packs.{engine}.templates"
    return (resources.files(pkg) / f"{name}.sql.tmpl").read_text(
        encoding="utf-8")


def issue(case: Case, name: str, *, values: dict, save_as: str,
          expected_capture: str, injections: dict | None = None) -> Path:
    injections = dict(injections or {})
    base_values = {"DB_NAME": case.meta.get("database", ""),
                   "EXPECTED_CAPTURE": expected_capture, **values}
    if "INJECT_ORIGINAL_QUERY" not in injections:
        original = case.root / "original.sql"
        if original.exists():
            injections["INJECT_ORIGINAL_QUERY"] = original.read_text(
                encoding="utf-8")
    rendered = render_template(
        load_template(case.meta.get("engine", "sqlserver"), name),
        base_values, injections)
    out_path = case.root / save_as
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    case.append({"event": "prescription_issued", "prescription": name,
                 "rendered_to": save_as,
                 "expected_capture": expected_capture})
    return out_path
```

Note: `templates/` needs no `__init__.py`; `resources.files` reads package data, and hatchling ships everything under `src/queryreceipts/`.

- [x] **Step 4: Run to verify pass** — `pytest tests/test_prescription.py -q`, `3 passed`.
- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: prescriptions — rendered capture requests that refuse half-rendered SQL"`

---

### Task 2: Validation template (the equivalence proof)

**Files:**
- Create: `src/queryreceipts/packs/sqlserver/templates/validation.sql.tmpl`
- Test: `tests/test_prescription.py` (append)

- [x] **Step 1: Write the failing test** (append)

```python
def test_validation_prescription_renders_gates_and_both_queries(tmp_path):
    case = Case.init(tmp_path / "c", META)
    (case.root / "original.sql").write_text("SELECT 1 AS x",
                                            encoding="utf-8")
    rw = case.root / "optimized" / "optimized_v1.sql"
    rw.parent.mkdir(parents=True)
    rw.write_text("SELECT 1 AS x /* faster */", encoding="utf-8")
    p = issue(case, "validation",
              values={"NATURAL_KEY": "x"},
              save_as="prescriptions/validation_v1.sql",
              expected_capture="validation/runs/v1_results.txt",
              injections={"INJECT_OPTIMIZED_QUERY":
                          rw.read_text(encoding="utf-8")})
    text = p.read_text(encoding="utf-8")
    assert "gate:engine_version" in text
    assert "SELECT 1 AS x /* faster */" in text
    assert "EXCEPT" in text
    assert "grain_per_natkey" in text
```

- [x] **Step 2: Run to verify failure** — expected `FileNotFoundError` (template missing).

- [x] **Step 3: Create the template** — the industrialized successor of sql-query-tuner's `validation.sql` (bidirectional EXCEPT authoritative, checksum labeled probabilistic, per-column null/distinct/minmaxsum via bracket-escaped dynamic SQL, bidirectional grain check), PLUS comparability gate rows echoed into the same results grid:

```sql
/* receipts prescription: validation — equivalence proof, ORIGINAL vs OPTIMIZED
   Both queries materialize in THIS session (same SET context by construction);
   gate rows record the context so the certificate can cite it.
   Run in SSMS; save the final result grid to: {{EXPECTED_CAPTURE}}
   Output columns: test_name, status, detail.
   status vocabulary: PASS / FAIL for tests, INFO for gates.
*/
USE [{{DB_NAME}}];
SET NOCOUNT ON;

IF OBJECT_ID('tempdb..#OldResult')   IS NOT NULL DROP TABLE #OldResult;
SELECT * INTO #OldResult FROM (
-- ===INJECT_ORIGINAL_QUERY===
) AS _o;

IF OBJECT_ID('tempdb..#NewResult')   IS NOT NULL DROP TABLE #NewResult;
SELECT * INTO #NewResult FROM (
-- ===INJECT_OPTIMIZED_QUERY===
) AS _n;

IF OBJECT_ID('tempdb..#TestResults') IS NOT NULL DROP TABLE #TestResults;
CREATE TABLE #TestResults (
    test_name NVARCHAR(200), status CHAR(4), detail NVARCHAR(2000));

/* ----- comparability gates (INFO rows) ----- */
INSERT #TestResults VALUES ('gate:engine_version', 'INFO',
    CONVERT(NVARCHAR(200), SERVERPROPERTY('ProductVersion')));
INSERT #TestResults VALUES ('gate:database', 'INFO', DB_NAME());
INSERT #TestResults VALUES ('gate:ansi_nulls', 'INFO',
    CONVERT(NVARCHAR(10), SESSIONPROPERTY('ANSI_NULLS')));
INSERT #TestResults VALUES ('gate:quoted_identifier', 'INFO',
    CONVERT(NVARCHAR(10), SESSIONPROPERTY('QUOTED_IDENTIFIER')));
INSERT #TestResults VALUES ('gate:language', 'INFO', @@LANGUAGE);
INSERT #TestResults VALUES ('gate:datefirst', 'INFO',
    CONVERT(NVARCHAR(10), @@DATEFIRST));

/* ----- test 1: row_count ----- */
DECLARE @oc INT, @nc INT;
SELECT @oc = COUNT(*) FROM #OldResult;
SELECT @nc = COUNT(*) FROM #NewResult;
INSERT #TestResults VALUES ('row_count',
    CASE WHEN @oc = @nc THEN 'PASS' ELSE 'FAIL' END,
    CONCAT('old=', @oc, ' new=', @nc));

/* ----- test 2: checksum_agg (probabilistic indicator only) ----- */
DECLARE @oh BIGINT, @nh BIGINT;
SELECT @oh = CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM #OldResult;
SELECT @nh = CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM #NewResult;
INSERT #TestResults VALUES ('checksum_agg',
    CASE WHEN @oh = @nh THEN 'PASS' ELSE 'FAIL' END,
    CONCAT('old=', @oh, ' new=', @nh, ' (probabilistic; EXCEPT is authoritative)'));

/* ----- tests 3+4: bidirectional EXCEPT (authoritative) ----- */
DECLARE @om INT, @nm INT;
SELECT @om = COUNT(*) FROM
    (SELECT * FROM #OldResult EXCEPT SELECT * FROM #NewResult) o;
SELECT @nm = COUNT(*) FROM
    (SELECT * FROM #NewResult EXCEPT SELECT * FROM #OldResult) n;
INSERT #TestResults VALUES ('except_old_to_new',
    CASE WHEN @om = 0 THEN 'PASS' ELSE 'FAIL' END,
    CONCAT(@om, ' rows missing in NEW'));
INSERT #TestResults VALUES ('except_new_to_old',
    CASE WHEN @nm = 0 THEN 'PASS' ELSE 'FAIL' END,
    CONCAT(@nm, ' extra rows in NEW'));

/* ----- tests 5/6/7: per-column null_dist / distinct_count / minmaxsum ----- */
DECLARE @col SYSNAME, @col_b NVARCHAR(258), @sql NVARCHAR(MAX), @typ SYSNAME;
DECLARE col_cur CURSOR LOCAL FAST_FORWARD FOR
SELECT c.name, ty.name
FROM tempdb.sys.columns c
INNER JOIN tempdb.sys.types ty ON ty.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('tempdb..#OldResult');
OPEN col_cur;
FETCH NEXT FROM col_cur INTO @col, @typ;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @col_b = N'[' + REPLACE(@col, N']', N']]') + N']';
    SET @sql = N'
        DECLARE @on INT, @nn INT;
        SELECT @on = SUM(CASE WHEN ' + @col_b + N' IS NULL THEN 1 ELSE 0 END) FROM #OldResult;
        SELECT @nn = SUM(CASE WHEN ' + @col_b + N' IS NULL THEN 1 ELSE 0 END) FROM #NewResult;
        INSERT #TestResults VALUES (
            ''null_dist:' + REPLACE(@col, N'''', N'''''') + N''',
            CASE WHEN ISNULL(@on,0) = ISNULL(@nn,0) THEN ''PASS'' ELSE ''FAIL'' END,
            CONCAT(''old='', ISNULL(@on,0), '' new='', ISNULL(@nn,0)));';
    EXEC sp_executesql @sql;
    SET @sql = N'
        DECLARE @od INT, @nd INT;
        SELECT @od = COUNT(DISTINCT ' + @col_b + N') FROM #OldResult;
        SELECT @nd = COUNT(DISTINCT ' + @col_b + N') FROM #NewResult;
        INSERT #TestResults VALUES (
            ''distinct_count:' + REPLACE(@col, N'''', N'''''') + N''',
            CASE WHEN @od = @nd THEN ''PASS'' ELSE ''FAIL'' END,
            CONCAT(''old='', @od, '' new='', @nd));';
    EXEC sp_executesql @sql;
    IF @typ IN (N'int', N'bigint', N'smallint', N'tinyint', N'decimal',
                N'numeric', N'float', N'real', N'money', N'smallmoney')
    BEGIN
        SET @sql = N'
            DECLARE @omin SQL_VARIANT, @omax SQL_VARIANT, @osum SQL_VARIANT;
            DECLARE @nmin SQL_VARIANT, @nmax SQL_VARIANT, @nsum SQL_VARIANT;
            SELECT @omin = MIN(' + @col_b + N'), @omax = MAX(' + @col_b + N'),
                   @osum = SUM(TRY_CAST(' + @col_b + N' AS DECIMAL(38,4))) FROM #OldResult;
            SELECT @nmin = MIN(' + @col_b + N'), @nmax = MAX(' + @col_b + N'),
                   @nsum = SUM(TRY_CAST(' + @col_b + N' AS DECIMAL(38,4))) FROM #NewResult;
            INSERT #TestResults VALUES (
                ''minmaxsum:' + REPLACE(@col, N'''', N'''''') + N''',
                CASE WHEN ISNULL(CAST(@omin AS NVARCHAR(50)),'''') = ISNULL(CAST(@nmin AS NVARCHAR(50)),'''')
                      AND ISNULL(CAST(@omax AS NVARCHAR(50)),'''') = ISNULL(CAST(@nmax AS NVARCHAR(50)),'''')
                      AND ISNULL(CAST(@osum AS NVARCHAR(50)),'''') = ISNULL(CAST(@nsum AS NVARCHAR(50)),'''')
                     THEN ''PASS'' ELSE ''FAIL'' END,
                CONCAT(''old='', CAST(@omin AS NVARCHAR(50)), ''/'', CAST(@omax AS NVARCHAR(50)), ''/'', CAST(@osum AS NVARCHAR(50)),
                       '' new='', CAST(@nmin AS NVARCHAR(50)), ''/'', CAST(@nmax AS NVARCHAR(50)), ''/'', CAST(@nsum AS NVARCHAR(50))));';
        EXEC sp_executesql @sql;
    END
    FETCH NEXT FROM col_cur INTO @col, @typ;
END
CLOSE col_cur; DEALLOCATE col_cur;

/* ----- tests 8+9: natural-key duplicates + bidirectional grain strata ----- */
DECLARE @nk SYSNAME = N'{{NATURAL_KEY}}';
IF @nk IS NOT NULL AND @nk <> N''
BEGIN
    DECLARE @nk_b NVARCHAR(258) = N'[' + REPLACE(@nk, N']', N']]') + N']';
    SET @sql = N'
        DECLARE @od INT, @nd INT;
        SELECT @od = COUNT(*) - COUNT(DISTINCT ' + @nk_b + N') FROM #OldResult;
        SELECT @nd = COUNT(*) - COUNT(DISTINCT ' + @nk_b + N') FROM #NewResult;
        INSERT #TestResults VALUES (''dup_on_natkey'',
            CASE WHEN @od = @nd THEN ''PASS'' ELSE ''FAIL'' END,
            CONCAT(''old_dups='', @od, '' new_dups='', @nd));';
    EXEC sp_executesql @sql;
    SET @sql = N'
        DECLARE @miss INT, @extra INT;
        SELECT @miss = COUNT(*) FROM (
            SELECT ' + @nk_b + N' AS k, COUNT(*) AS c FROM #OldResult GROUP BY ' + @nk_b + N'
            EXCEPT
            SELECT ' + @nk_b + N' AS k, COUNT(*) AS c FROM #NewResult GROUP BY ' + @nk_b + N') x;
        SELECT @extra = COUNT(*) FROM (
            SELECT ' + @nk_b + N' AS k, COUNT(*) AS c FROM #NewResult GROUP BY ' + @nk_b + N'
            EXCEPT
            SELECT ' + @nk_b + N' AS k, COUNT(*) AS c FROM #OldResult GROUP BY ' + @nk_b + N') y;
        INSERT #TestResults VALUES (''grain_per_natkey'',
            CASE WHEN @miss = 0 AND @extra = 0 THEN ''PASS'' ELSE ''FAIL'' END,
            CONCAT(@miss, '' strata missing in NEW, '', @extra, '' strata extra in NEW''));';
    EXEC sp_executesql @sql;
END
ELSE
    INSERT #TestResults VALUES ('grain_per_natkey', 'INFO',
        'skipped: no natural key provided');

SELECT test_name, status, detail FROM #TestResults
ORDER BY CASE status WHEN 'FAIL' THEN 0 WHEN 'PASS' THEN 1 ELSE 2 END,
         test_name;
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_prescription.py -q`, `4 passed`.
- [x] **Step 5: Commit** — `git add -A && git commit -m "feat(sqlserver): validation prescription — equivalence proof with comparability gates"`

---

### Task 3: Benchmark template with pre-registered protocol

**Files:**
- Create: `src/queryreceipts/packs/sqlserver/templates/benchmark.sql.tmpl`
- Modify: `src/queryreceipts/prescription.py` (protocol pinning for benchmarks)
- Test: `tests/test_prescription.py` (append)

- [x] **Step 1: Write the failing test** (append)

```python
def test_benchmark_prescription_pins_protocol_before_results(tmp_path):
    case = Case.init(tmp_path / "c", META)
    (case.root / "original.sql").write_text("SELECT 1 AS x",
                                            encoding="utf-8")
    issue(case, "benchmark", values={},
          save_as="prescriptions/benchmark_v1.sql",
          expected_capture="benchmarks/v1_results.txt",
          injections={"INJECT_OPTIMIZED_QUERY": "SELECT 1 AS x"})
    pinned = [e for e in case.events() if e["event"] == "protocol_pinned"]
    assert pinned, "benchmark prescription must pin protocol in the ledger"
    assert pinned[0]["headline_metric"] == "second_run_elapsed_ms"
    assert pinned[0]["runs_per_query"] == 2
```

- [x] **Step 2: Run to verify failure** — expected `FileNotFoundError` or missing event.

- [x] **Step 3: Implement**

`benchmark.sql.tmpl`:
```sql
/* receipts prescription: benchmark — ORIGINAL vs OPTIMIZED, IO/TIME
   PROTOCOL (pinned in the case ledger BEFORE you run this):
     run this script TWICE back-to-back; the SECOND run's elapsed time is the
     headline metric (warm cache). Save the SECOND run's full output to:
     {{EXPECTED_CAPTURE}}
*/
USE [{{DB_NAME}}];
SET NOCOUNT ON;

PRINT '====BEGIN_SECTION:original====';
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

-- ===INJECT_ORIGINAL_QUERY===

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
PRINT '====END_SECTION:original====';

PRINT '====BEGIN_SECTION:optimized====';
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

-- ===INJECT_OPTIMIZED_QUERY===

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
PRINT '====END_SECTION:optimized====';
```

In `prescription.py`, after the `prescription_issued` append inside `issue()`, add:

```python
    if name == "benchmark":
        case.append({"event": "protocol_pinned", "prescription": name,
                     "runs_per_query": 2,
                     "headline_metric": "second_run_elapsed_ms",
                     "note": "pinned before results exist; "
                             "cherry-picking is a FAIL"})
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_prescription.py -q`, `5 passed`.
- [x] **Step 5: Commit** — `git add -A && git commit -m "feat(sqlserver): benchmark prescription pins protocol before results exist"`

---

### Task 4: Validation grading

**Files:**
- Create: `src/queryreceipts/packs/sqlserver/grading.py`
- Create: `tests/fixtures/validation_results_pass.txt`, `tests/fixtures/validation_results_fail.txt`
- Test: `tests/test_grading.py`

- [x] **Step 1: Create fixtures** (SSMS "Results to Text" shape: header, dashes, space-aligned columns)

`tests/fixtures/validation_results_pass.txt`:
```
test_name                      status detail
------------------------------ ------ ----------------------------------------
checksum_agg                   PASS   old=-163057 new=-163057 (probabilistic; EXCEPT is authoritative)
dup_on_natkey                  PASS   old_dups=0 new_dups=0
except_new_to_old              PASS   0 extra rows in NEW
except_old_to_new              PASS   0 rows missing in NEW
distinct_count:x               PASS   old=42 new=42
grain_per_natkey               PASS   0 strata missing in NEW, 0 strata extra in NEW
minmaxsum:x                    PASS   old=1/99/2079.0000 new=1/99/2079.0000
null_dist:x                    PASS   old=0 new=0
row_count                      PASS   old=66139 new=66139
gate:ansi_nulls                INFO   1
gate:database                  INFO   FleetDB
gate:datefirst                 INFO   7
gate:engine_version            INFO   16.0.4075.1
gate:language                  INFO   us_english
gate:quoted_identifier         INFO   1

(15 rows affected)
```

`tests/fixtures/validation_results_fail.txt`: same but `row_count` line reads
`row_count                      FAIL   old=66139 new=66024` and except_old_to_new reads
`except_old_to_new              FAIL   115 rows missing in NEW`.

- [x] **Step 2: Write the failing tests**

```python
# tests/test_grading.py
from pathlib import Path

from queryreceipts.packs.sqlserver.grading import grade_validation

FIXTURES = Path(__file__).parent / "fixtures"


def test_all_pass_grades_proven():
    g = grade_validation(
        (FIXTURES / "validation_results_pass.txt").read_text())
    assert g["verdict"] == "PROVEN"
    assert g["counts"] == {"PASS": 9, "FAIL": 0, "INFO": 6}
    assert g["gates"]["gate:database"] == "FleetDB"


def test_any_fail_grades_refuted_and_names_failures():
    g = grade_validation(
        (FIXTURES / "validation_results_fail.txt").read_text())
    assert g["verdict"] == "REFUTED"
    names = [f["test_name"] for f in g["failures"]]
    assert "row_count" in names and "except_old_to_new" in names


def test_empty_or_garbled_capture_is_unverified():
    g = grade_validation("SSMS crashed, nothing here")
    assert g["verdict"] == "UNVERIFIED"
    assert "no test rows" in g["reason"]
```

- [x] **Step 3: Run to verify failure** — `ImportError`.

- [x] **Step 4: Implement**

```python
# src/queryreceipts/packs/sqlserver/grading.py
"""Grade saved validation results.

Three-valued: PROVEN (every test PASS), REFUTED (any FAIL), UNVERIFIED
(no parseable test rows — the capture itself is the problem). Gate rows
(INFO) are echoed through for the certificate to cite.
"""
from __future__ import annotations

import re

ROW_RE = re.compile(
    r"^(?P<name>\S+)\s+(?P<status>PASS|FAIL|INFO)\s+(?P<detail>.*?)\s*$",
    re.MULTILINE)


def grade_validation(text: str) -> dict:
    rows = [m.groupdict() for m in ROW_RE.finditer(text)]
    tests = [r for r in rows if r["status"] in ("PASS", "FAIL")]
    gates = {r["name"]: r["detail"] for r in rows if r["status"] == "INFO"}
    if not tests:
        return {"verdict": "UNVERIFIED",
                "reason": "no test rows found in capture — re-run the "
                          "validation prescription and save the full grid",
                "counts": {"PASS": 0, "FAIL": 0, "INFO": len(gates)},
                "failures": [], "gates": gates, "tests": []}
    failures = [{"test_name": r["name"], "detail": r["detail"]}
                for r in tests if r["status"] == "FAIL"]
    verdict = "REFUTED" if failures else "PROVEN"
    return {"verdict": verdict,
            "counts": {"PASS": sum(r["status"] == "PASS" for r in tests),
                       "FAIL": len(failures), "INFO": len(gates)},
            "failures": failures, "gates": gates,
            "tests": [{"test_name": r["name"], "status": r["status"],
                       "detail": r["detail"]} for r in tests]}
```

- [x] **Step 5: Run to verify pass** — `pytest tests/test_grading.py -q`, `3 passed`.
- [x] **Step 6: Commit** — `git add -A && git commit -m "feat(sqlserver): validation grading — PROVEN/REFUTED/UNVERIFIED"`

---

### Task 5: Benchmark grading

**Files:**
- Modify: `src/queryreceipts/packs/sqlserver/grading.py` (add `grade_benchmark`)
- Test: `tests/test_grading.py` (append)

- [x] **Step 1: Write the failing tests** (append)

```python
def test_benchmark_grading_compares_sections():
    from queryreceipts.packs.sqlserver.grading import grade_benchmark
    capture = (
        "====BEGIN_SECTION:original====\n"
        "Table 'BIG'. Scan count 4, logical reads 2000000, physical reads 0.\n"
        " SQL Server Execution Times:\n"
        "   CPU time = 90000 ms,  elapsed time = 120000 ms.\n"
        "====END_SECTION:original====\n"
        "====BEGIN_SECTION:optimized====\n"
        "Table 'BIG'. Scan count 1, logical reads 40000, physical reads 0.\n"
        " SQL Server Execution Times:\n"
        "   CPU time = 4000 ms,  elapsed time = 6000 ms.\n"
        "====END_SECTION:optimized====\n")
    g = grade_benchmark(capture)
    assert g["original"]["elapsed_ms"] == 120000
    assert g["optimized"]["elapsed_ms"] == 6000
    assert g["improvement"]["elapsed_pct"] == 95.0
    assert g["improvement"]["reads_pct"] == 98.0


def test_benchmark_grading_unverified_when_a_section_is_missing():
    from queryreceipts.packs.sqlserver.grading import grade_benchmark
    g = grade_benchmark("====BEGIN_SECTION:original====\n"
                        " SQL Server Execution Times:\n"
                        "   CPU time = 1 ms,  elapsed time = 2 ms.\n"
                        "====END_SECTION:original====\n")
    assert g["verdict"] == "UNVERIFIED"
    assert "optimized" in g["reason"]
```

- [x] **Step 2: Run to verify failure** — `ImportError: grade_benchmark`.

- [x] **Step 3: Implement** (append to `grading.py`)

```python
def grade_benchmark(text: str) -> dict:
    from .stats_io import SectionNotFound, extract_section, parse
    sides = {}
    for side in ("original", "optimized"):
        try:
            section = extract_section(text, side)
        except SectionNotFound:
            return {"verdict": "UNVERIFIED",
                    "reason": f"section {side!r} missing from benchmark "
                              "capture — run the full prescription"}
        parsed = parse(section)
        sides[side] = {
            "elapsed_ms": parsed["time"]["elapsed_ms"],
            "cpu_ms": parsed["time"]["cpu_ms"],
            "logical_reads": sum(t["logical_reads"]
                                 for t in parsed["tables"]),
        }

    def pct(before: int, after: int) -> float | None:
        if before <= 0:
            return None
        return round(100 * (before - after) / before, 1)

    o, n = sides["original"], sides["optimized"]
    return {"verdict": "MEASURED", "original": o, "optimized": n,
            "improvement": {
                "elapsed_pct": pct(o["elapsed_ms"], n["elapsed_ms"]),
                "cpu_pct": pct(o["cpu_ms"], n["cpu_ms"]),
                "reads_pct": pct(o["logical_reads"], n["logical_reads"]),
            }}
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_grading.py -q`, `5 passed`.
- [x] **Step 5: Commit** — `git add -A && git commit -m "feat(sqlserver): benchmark grading — section comparison, honest about missing halves"`

---

### Task 6: Certificates

**Files:**
- Create: `src/queryreceipts/certificate.py`
- Test: `tests/test_certificate.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_certificate.py
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
    issued = [e for e in case.events() if e["event"] == "certificate_issued"]
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
```

- [x] **Step 2: Run to verify failure** — `ImportError`.

- [x] **Step 3: Implement**

```python
# src/queryreceipts/certificate.py
"""Certificates: the receipts.

A certificate is three-valued and cites everything. PROVEN requires every
validation test to PASS and a graded benchmark. Any FAIL → REFUTED. Anything
missing → UNVERIFIED, with each missing piece named. The certificate carries
the sha256 of every artifact it relied on and the comparability gates the
validation recorded; it is stamped, not timeless — conditions list what
invalidates it.
"""
from __future__ import annotations

import json

from .case import Case, utcnow
from .packs.sqlserver.grading import grade_benchmark, grade_validation

CONDITIONS = [
    "valid for the schema and statistics state at capture time",
    "invalidated by schema changes to referenced tables",
    "invalidated by edits to original or optimized SQL",
]


def issue_certificate(case: Case, *, validation_id: str | None,
                      benchmark_id: str | None, rewrite: str) -> dict:
    missing, evidence, gates = [], [], {}
    validation = benchmark = None

    if validation_id:
        ev = case.get_evidence(validation_id)
        evidence.append({"artifact_id": ev.artifact_id, "kind": ev.kind,
                         "sha256": ev.sha256, "path": ev.path})
        validation = grade_validation(
            (case.root / ev.path).read_text(encoding="utf-8",
                                            errors="replace"))
        gates = validation["gates"]
    else:
        missing.append("validation results (run the validation "
                       "prescription, register the capture)")

    if benchmark_id:
        ev = case.get_evidence(benchmark_id)
        evidence.append({"artifact_id": ev.artifact_id, "kind": ev.kind,
                         "sha256": ev.sha256, "path": ev.path})
        benchmark = grade_benchmark(
            (case.root / ev.path).read_text(encoding="utf-8",
                                            errors="replace"))
        if benchmark["verdict"] == "UNVERIFIED":
            missing.append(f"benchmark incomplete: {benchmark['reason']}")
    else:
        missing.append("benchmark results (run the benchmark "
                       "prescription, register the capture)")

    if validation and validation["verdict"] == "UNVERIFIED":
        missing.append(f"validation unreadable: {validation['reason']}")

    if validation and validation["verdict"] == "REFUTED":
        verdict = "REFUTED"
    elif missing:
        verdict = "UNVERIFIED"
    else:
        verdict = "PROVEN"

    n = sum(1 for e in case.events()
            if e["event"] == "certificate_issued") + 1
    cert = {"certificate_id": f"cert-{n:04d}", "issued_at": utcnow(),
            "case": case.meta.get("case"), "rewrite": rewrite,
            "verdict": verdict, "missing": missing, "gates": gates,
            "validation": validation, "benchmark": benchmark,
            "evidence": evidence, "conditions": CONDITIONS}

    out = case.root / "certificates"
    out.mkdir(exist_ok=True)
    (out / f"certificate_{n:04d}.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8")
    (out / f"certificate_{n:04d}.md").write_text(render_certificate(cert),
                                                 encoding="utf-8")
    case.append({"event": "certificate_issued",
                 "certificate_id": cert["certificate_id"],
                 "verdict": verdict, "rewrite": rewrite,
                 "evidence": [e["artifact_id"] for e in evidence]})
    return cert


def render_certificate(cert: dict) -> str:
    lines = [
        f"# Certificate {cert['certificate_id']} — {cert['verdict']}",
        "",
        f"Case: {cert['case']}  |  Rewrite: `{cert['rewrite']}`  |  "
        f"Issued: {cert['issued_at']}",
        "",
    ]
    if cert["verdict"] == "PROVEN":
        v = cert["validation"]["counts"]
        lines.append(f"Equivalence: {v['PASS']} checks passed, 0 failed.")
        imp = cert["benchmark"]["improvement"]
        lines.append(
            f"Performance: elapsed -{imp['elapsed_pct']}%, "
            f"cpu -{imp['cpu_pct']}%, reads -{imp['reads_pct']}% "
            "(per pinned protocol).")
    elif cert["verdict"] == "REFUTED":
        lines.append("The rewrite is NOT equivalent:")
        for f in cert["validation"]["failures"]:
            lines.append(f"- {f['test_name']}: {f['detail']}")
    else:
        lines.append("Cannot certify yet — missing:")
        for m in cert["missing"]:
            lines.append(f"- {m}")
    if cert["gates"]:
        lines.append("")
        lines.append("Comparability gates (recorded in-session):")
        for k, v in sorted(cert["gates"].items()):
            lines.append(f"- {k} = {v}")
    lines.append("")
    lines.append("Evidence:")
    for e in cert["evidence"]:
        lines.append(f"- {e['artifact_id']} {e['kind']} "
                     f"sha256:{e['sha256'][:12]}… ({e['path']})")
    lines.append("")
    lines.append("Conditions:")
    for c in cert["conditions"]:
        lines.append(f"- {c}")
    return "\n".join(lines) + "\n"
```

- [x] **Step 4: Run to verify pass** — `pytest tests/test_certificate.py -q`, `3 passed`.
- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: certificates — three-valued, artifact-citing, condition-stamped"`

---

### Task 7: CLI wiring — prescribe / grade / certify

**Files:**
- Modify: `src/queryreceipts/cli.py`
- Test: `tests/test_cli.py` (append)

- [x] **Step 1: Write the failing test** (append)

```python
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
    assert "UNVERIFIED" in out      # no benchmark yet — named, not papered over
    assert "benchmark" in out
```

- [x] **Step 2: Run to verify failure** — argparse error (unknown command).

- [x] **Step 3: Implement** — add to `cli.py`:

```python
def cmd_prescribe(args) -> int:
    from .prescription import issue
    case = _find_case(args)
    n = sum(1 for e in case.events()
            if e["event"] == "prescription_issued"
            and e["prescription"] == args.kind) + 1
    injections = {}
    values = {}
    if args.kind in ("validation", "benchmark"):
        if not args.rewrite:
            raise CaseError(f"--rewrite is required for {args.kind}")
        rewrite = Path(args.rewrite)
        if not rewrite.is_absolute():
            rewrite = case.root / rewrite
        injections["INJECT_OPTIMIZED_QUERY"] = rewrite.read_text(
            encoding="utf-8")
    if args.kind == "validation":
        values["NATURAL_KEY"] = args.natural_key or ""
        save_as = f"prescriptions/validation_v{n}.sql"
        expected = f"validation/v{n}_results.txt"
    elif args.kind == "benchmark":
        save_as = f"prescriptions/benchmark_v{n}.sql"
        expected = f"benchmarks/v{n}_results.txt"
    else:
        save_as = "prescriptions/diagnostics.sql"
        expected = "runs/baseline/diagnostics.txt"
    p = issue(case, args.kind, values=values, save_as=save_as,
              expected_capture=expected, injections=injections)
    print(f"prescription written: {p}")
    print(f"run it, save output to {case.root / expected}, then: "
          f"receipts add {case.root / expected} --kind "
          f"{'validation_results' if args.kind == 'validation' else 'benchmark_results' if args.kind == 'benchmark' else 'stats_io'} ...")
    return 0


def cmd_grade(args) -> int:
    from .packs.sqlserver.grading import grade_benchmark, grade_validation
    case = _find_case(args)
    ev = case.get_evidence(args.artifact)
    text = (case.root / ev.path).read_text(encoding="utf-8",
                                           errors="replace")
    if ev.kind == "validation_results":
        g = grade_validation(text)
    elif ev.kind == "benchmark_results":
        g = grade_benchmark(text)
    else:
        raise CaseError(f"cannot grade kind {ev.kind!r}")
    case.append({"event": "graded", "source": ev.artifact_id,
                 "verdict": g["verdict"]})
    if args.json:
        print(json.dumps(g, indent=2))
    else:
        print(f"{g['verdict']}: {ev.artifact_id} ({ev.kind})")
        for f in g.get("failures", []):
            print(f"  FAIL {f['test_name']}: {f['detail']}")
        if g.get("reason"):
            print(f"  {g['reason']}")
        if g.get("improvement"):
            imp = g["improvement"]
            print(f"  elapsed -{imp['elapsed_pct']}% | cpu -{imp['cpu_pct']}%"
                  f" | reads -{imp['reads_pct']}%")
    return 0


def cmd_certify(args) -> int:
    from .certificate import issue_certificate, render_certificate
    case = _find_case(args)
    cert = issue_certificate(case, validation_id=args.validation,
                             benchmark_id=args.benchmark,
                             rewrite=args.rewrite)
    if args.json:
        print(json.dumps(cert, indent=2))
    else:
        print(render_certificate(cert), end="")
    return 0
```

Registrations in `build_parser()`:

```python
    sp = sub.add_parser("prescribe", help="render a capture prescription")
    sp.add_argument("kind", choices=["diagnostics", "validation", "benchmark"])
    sp.add_argument("--rewrite", default=None,
                    help="path to optimized SQL (validation/benchmark)")
    sp.add_argument("--natural-key", default=None, dest="natural_key")
    sp.add_argument("--case", default=None)
    sp.set_defaults(func=cmd_prescribe)

    sp = sub.add_parser("grade", help="grade a registered results capture")
    sp.add_argument("artifact")
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_grade)

    sp = sub.add_parser("certify", help="issue a certificate for a rewrite")
    sp.add_argument("--validation", default=None)
    sp.add_argument("--benchmark", default=None)
    sp.add_argument("--rewrite", required=True)
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_certify)
```

- [x] **Step 4: Run to verify pass** — `pytest -q`, all green.
- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: prescribe/grade/certify — the proof loop in the CLI"`

---

### Task 8: Wrap-up

- [x] **Step 1:** Full suite: `.venv/bin/python -m pytest -q` — all pass. Smoke: `receipts --help` shows all 8 subcommands.
- [x] **Step 2:** Tick all checkboxes in this plan, commit `chore: plan 2 complete — proof loop`.

---

## Self-review notes

- Validation/benchmark templates are the industrialized v0.1.1 lineage (bracket-escaping, TRY_CAST overflow guard, bidirectional grain) plus gates and pinned protocol — the two analytics-office imports this plan owes.
- Single-SELECT limitation of `SELECT * INTO #t FROM (…)` persists in this plan; multi-statement/DML validation is a known Plan 3+ item — do not claim otherwise in docs.
- `grade_benchmark` returns `verdict: MEASURED`, not PROVEN — performance is measured, equivalence is proven; the certificate composes both.
- Type check: `issue()` signature matches all call sites; `grade_validation`/`grade_benchmark` consumed by both CLI and certificate module; certificate uses `case.get_evidence` from Plan 1.
