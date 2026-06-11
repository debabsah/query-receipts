# QueryReceipts Plan 3: Synthetic Workload + End-to-End Proof

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FleetDB — a deterministic synthetic SQL Server workload mirroring the real-world pathology (correlated-subquery spool + non-sargable predicate, reservation-system shape) — plus an integration test that drives the ENTIRE cure loop against a live SQL Server 2022 container and asserts a PROVEN certificate.

**Architecture:** All SQL execution happens via `docker exec sqlcmd` (no Python DB driver — stdlib-only stays true; the harness plays the role of a `driver` transport). FleetDB files live in `examples/fleetdb/`. Integration tests are pytest-marked `integration`, deselected by default, auto-skipped when the container isn't reachable.

**Tech Stack:** Docker (mcr.microsoft.com/mssql/server:2022-latest, linux/amd64 under emulation), sqlcmd in-container at `/opt/mssql-tools18/bin/sqlcmd`, pytest markers.

**Workload design (locked):**
- Tables: RESERVATION (200k), RESERVATION_ITEM (600k, 3/reservation), TRAVELER (400k, 2/reservation), STATUS_CODE dim. Deterministic via `GENERATE_SERIES` + modular arithmetic; no RAND()/NEWID().
- `UPDATED_AT` unique per (RES_ID) by construction → "latest status" is deterministic → original/rewrite truly equivalent.
- original.sql pathology: per-row correlated `TOP 1 … ORDER BY UPDATED_AT DESC` + correlated COUNT + non-sargable `YEAR(START_DATE) = 2025`.
- optimized_v1.sql: ROW_NUMBER window for latest status, GROUP BY join for counts, sargable date range. Identical SELECT list, order, names. Natural key: RES_ID.
- Container: name `fleetdb`, port 14333→1433, SA password `Receipts!Pr00f1`.

---

### Task 1: FleetDB schema, datagen, and the query pair

**Files:**
- Create: `examples/fleetdb/schema.sql`, `examples/fleetdb/datagen.sql`, `examples/fleetdb/original.sql`, `examples/fleetdb/optimized_v1.sql`

- [ ] **Step 1: schema.sql**

```sql
IF DB_ID('FleetDB') IS NULL CREATE DATABASE FleetDB;
GO
USE FleetDB;
GO
IF OBJECT_ID('dbo.RESERVATION_ITEM') IS NOT NULL DROP TABLE dbo.RESERVATION_ITEM;
IF OBJECT_ID('dbo.TRAVELER') IS NOT NULL DROP TABLE dbo.TRAVELER;
IF OBJECT_ID('dbo.RESERVATION') IS NOT NULL DROP TABLE dbo.RESERVATION;
IF OBJECT_ID('dbo.STATUS_CODE') IS NOT NULL DROP TABLE dbo.STATUS_CODE;
GO
CREATE TABLE dbo.STATUS_CODE (
    STATUS_ID   INT          NOT NULL PRIMARY KEY,
    CODE        VARCHAR(20)  NOT NULL
);
CREATE TABLE dbo.RESERVATION (
    RES_ID      INT          NOT NULL PRIMARY KEY,
    START_DATE  DATE         NOT NULL,
    CHANNEL     VARCHAR(10)  NOT NULL,
    TOTAL_DUE   DECIMAL(12,2) NOT NULL
);
CREATE TABLE dbo.RESERVATION_ITEM (
    ITEM_ID     INT          NOT NULL PRIMARY KEY,
    RES_ID      INT          NOT NULL,
    STATUS_ID   INT          NOT NULL,
    UPDATED_AT  DATETIME2(0) NOT NULL
);
CREATE TABLE dbo.TRAVELER (
    TRAVELER_ID INT          NOT NULL PRIMARY KEY,
    RES_ID      INT          NOT NULL,
    AGE         INT          NOT NULL
);
GO
```

(Deliberately NO index on RESERVATION_ITEM(RES_ID) and none on TRAVELER(RES_ID) — that's the pathology.)

- [ ] **Step 2: datagen.sql** (deterministic, set-based)

```sql
USE FleetDB;
SET NOCOUNT ON;
INSERT dbo.STATUS_CODE (STATUS_ID, CODE) VALUES
 (1,'HELD'),(2,'CONFIRMED'),(3,'PAID'),(4,'CANCELLED'),(5,'COMPLETE');

INSERT dbo.RESERVATION (RES_ID, START_DATE, CHANNEL, TOTAL_DUE)
SELECT value,
       DATEADD(DAY, value % 1095, '2024-01-01'),       -- 3 years spread
       CASE value % 3 WHEN 0 THEN 'WEB' WHEN 1 THEN 'AGENT' ELSE 'API' END,
       CAST(50 + (value % 900) AS DECIMAL(12,2))
FROM GENERATE_SERIES(1, 200000);

INSERT dbo.RESERVATION_ITEM (ITEM_ID, RES_ID, STATUS_ID, UPDATED_AT)
SELECT s.value,
       ((s.value - 1) / 3) + 1,
       1 + (s.value % 5),
       DATEADD(SECOND, s.value % 3, DATEADD(MINUTE, ((s.value - 1) / 3) % 525600, '2024-01-01'))
FROM GENERATE_SERIES(1, 600000) s;
-- UPDATED_AT: per RES_ID the 3 items differ by seconds → unique latest.

INSERT dbo.TRAVELER (TRAVELER_ID, RES_ID, AGE)
SELECT s.value, ((s.value - 1) / 2) + 1, 18 + (s.value % 60)
FROM GENERATE_SERIES(1, 400000) s;
GO
```

- [ ] **Step 3: original.sql** (the slow query — output grain RES_ID)

```sql
SELECT r.RES_ID,
       r.START_DATE,
       (SELECT TOP 1 sc.CODE
        FROM dbo.RESERVATION_ITEM ri
        JOIN dbo.STATUS_CODE sc ON sc.STATUS_ID = ri.STATUS_ID
        WHERE ri.RES_ID = r.RES_ID
        ORDER BY ri.UPDATED_AT DESC) AS LATEST_STATUS,
       (SELECT COUNT(*) FROM dbo.TRAVELER t
        WHERE t.RES_ID = r.RES_ID) AS TRAVELER_COUNT
FROM dbo.RESERVATION r
WHERE YEAR(r.START_DATE) = 2025
```

- [ ] **Step 4: optimized_v1.sql** (equivalent, sargable, set-based)

```sql
WITH latest AS (
    SELECT ri.RES_ID, sc.CODE,
           ROW_NUMBER() OVER (PARTITION BY ri.RES_ID
                              ORDER BY ri.UPDATED_AT DESC) AS rn
    FROM dbo.RESERVATION_ITEM ri
    JOIN dbo.STATUS_CODE sc ON sc.STATUS_ID = ri.STATUS_ID
), tc AS (
    SELECT t.RES_ID, COUNT(*) AS TRAVELER_COUNT
    FROM dbo.TRAVELER t
    GROUP BY t.RES_ID
)
SELECT r.RES_ID,
       r.START_DATE,
       l.CODE AS LATEST_STATUS,
       ISNULL(tc.TRAVELER_COUNT, 0) AS TRAVELER_COUNT
FROM dbo.RESERVATION r
LEFT JOIN latest l ON l.RES_ID = r.RES_ID AND l.rn = 1
LEFT JOIN tc ON tc.RES_ID = r.RES_ID
WHERE r.START_DATE >= '2025-01-01' AND r.START_DATE < '2026-01-01'
```

Equivalence note: original's correlated TOP 1 returns NULL when a reservation has no items (cannot happen — datagen gives every reservation 3 items — but LEFT JOIN preserves the same semantics anyway); `ISNULL(…, 0)` matches COUNT's 0-for-no-rows. `YEAR(d)=2025` ⇔ the half-open range.

- [ ] **Step 5: Commit** — `git add examples && git commit -m "feat: FleetDB synthetic workload — deterministic, pathological, equivalent pair"`

---

### Task 2: Container lifecycle scripts

**Files:**
- Create: `scripts/fleetdb_up.sh`, `scripts/fleetdb_down.sh`

- [ ] **Step 1: fleetdb_up.sh**

```bash
#!/usr/bin/env bash
# Start (or reuse) the FleetDB SQL Server container and load the workload.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=fleetdb
PASS='Receipts!Pr00f1'
SQLCMD="/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P $PASS"

if [ -z "$(docker ps -q -f name=^${NAME}$)" ]; then
  docker rm -f $NAME >/dev/null 2>&1 || true
  docker run -d --name $NAME --platform linux/amd64 \
    -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD="$PASS" \
    -p 14333:1433 mcr.microsoft.com/mssql/server:2022-latest
fi

echo "waiting for SQL Server…"
for i in $(seq 1 60); do
  if docker exec $NAME $SQLCMD -Q "SELECT 1" >/dev/null 2>&1; then break; fi
  sleep 5
  [ "$i" = 60 ] && { echo "SQL Server never came up"; exit 1; }
done

echo "loading schema + data…"
for f in schema.sql datagen.sql; do
  docker cp examples/fleetdb/$f $NAME:/tmp/$f
  docker exec $NAME $SQLCMD -b -i /tmp/$f
done
echo "FleetDB ready on localhost,14333 (sa / $PASS)"
```

- [ ] **Step 2: fleetdb_down.sh**

```bash
#!/usr/bin/env bash
docker rm -f fleetdb 2>/dev/null && echo "fleetdb removed" || echo "fleetdb was not running"
```

- [ ] **Step 3:** `chmod +x scripts/*.sh`, commit — `git commit -m "feat: fleetdb container lifecycle scripts"`

---

### Task 3: Integration harness

**Files:**
- Create: `tests/integration/__init__.py` (empty), `tests/integration/conftest.py`
- Modify: `pyproject.toml` (marker + default deselect)

- [ ] **Step 1: pyproject.toml additions**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: drives the fleetdb docker container"]
addopts = "-m 'not integration'"
```

(Run integration explicitly: `pytest -m integration`.)

- [ ] **Step 2: conftest.py**

```python
# tests/integration/conftest.py
import subprocess

import pytest

SQLCMD = ["docker", "exec", "fleetdb", "/opt/mssql-tools18/bin/sqlcmd",
          "-C", "-S", "localhost", "-U", "sa", "-P", "Receipts!Pr00f1",
          "-d", "FleetDB"]


def fleetdb_available() -> bool:
    try:
        r = subprocess.run([*SQLCMD, "-Q", "SELECT 1"],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def fleetdb():
    if not fleetdb_available():
        pytest.skip("fleetdb container not reachable — "
                    "run scripts/fleetdb_up.sh")
    return run_sql


def run_sql(sql_path, out_path=None, timeout=600):
    """Copy a SQL file into the container, run it, return stdout
    (optionally also saving it to out_path)."""
    subprocess.run(["docker", "cp", str(sql_path), "fleetdb:/tmp/run.sql"],
                   check=True, capture_output=True)
    r = subprocess.run([*SQLCMD, "-i", "/tmp/run.sql"],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"sqlcmd failed: {r.stdout}\n{r.stderr}")
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(r.stdout, encoding="utf-8")
    return r.stdout
```

- [ ] **Step 3:** Unit suite still green (`pytest -q`), commit — `git commit -m "feat: integration harness — fleetdb fixture, marker, sqlcmd runner"`

---

### Task 4: The end-to-end cure-loop test

**Files:**
- Create: `tests/integration/test_e2e_cure_loop.py`

- [ ] **Step 1: Write the test** (this is the product's acceptance test)

```python
# tests/integration/test_e2e_cure_loop.py
import json
import shutil
from pathlib import Path

import pytest

from queryreceipts.cli import main

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "fleetdb"


def test_full_cure_loop_yields_proven_certificate(fleetdb, tmp_path, capsys):
    root = tmp_path / "fleetdb-case"
    # 1. open the case
    assert main(["init", str(root), "--engine", "sqlserver",
                 "--database", "FleetDB",
                 "--symptom", "extract slow, high reads"]) == 0
    shutil.copyfile(EXAMPLES / "original.sql", root / "original.sql")
    (root / "optimized").mkdir()
    shutil.copyfile(EXAMPLES / "optimized_v1.sql",
                    root / "optimized" / "optimized_v1.sql")

    # 2. diagnostics: prescribe -> run -> register -> parse
    assert main(["prescribe", "diagnostics", "--case", str(root)]) == 0
    cap = root / "runs" / "baseline" / "diagnostics.txt"
    fleetdb(root / "prescriptions" / "diagnostics.sql", cap)
    assert main(["add", str(cap), "--kind", "stats_io",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    assert main(["parse", "ev-0001", "--case", str(root),
                 "--section", "baseline_io_time"]) == 0
    capsys.readouterr()

    # 3. validation: prescribe -> run -> register -> grade
    assert main(["prescribe", "validation",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--natural-key", "RES_ID", "--case", str(root)]) == 0
    vres = root / "validation" / "v1_results.txt"
    fleetdb(root / "prescriptions" / "validation_v1.sql", vres)
    assert main(["add", str(vres), "--kind", "validation_results",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    assert main(["grade", "ev-0002", "--case", str(root)]) == 0
    assert "PROVEN" in capsys.readouterr().out

    # 4. benchmark: prescribe -> run twice (pinned protocol) -> register
    assert main(["prescribe", "benchmark",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--case", str(root)]) == 0
    bres = root / "benchmarks" / "v1_results.txt"
    fleetdb(root / "prescriptions" / "benchmark_v1.sql")        # warm-up run
    fleetdb(root / "prescriptions" / "benchmark_v1.sql", bres)  # measured run
    assert main(["add", str(bres), "--kind", "benchmark_results",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    capsys.readouterr()

    # 5. certify
    assert main(["certify", "--validation", "ev-0002",
                 "--benchmark", "ev-0003",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--case", str(root)]) == 0
    out = capsys.readouterr().out
    assert "PROVEN" in out

    cert = json.loads(
        (root / "certificates" / "certificate_0001.json").read_text())
    assert cert["verdict"] == "PROVEN"
    assert cert["benchmark"]["improvement"]["reads_pct"] > 30
    assert cert["gates"]["gate:database"] == "FleetDB"
```

- [ ] **Step 2: Bring the workload up** — `bash scripts/fleetdb_up.sh` (first datagen run takes minutes under emulation).

- [ ] **Step 3: Run it** — `.venv/bin/python -m pytest -m integration -v`. Debug what reality breaks (sqlcmd output formats, timing) by reading the case dir artifacts; fix product code or harness as evidence dictates, keeping unit suite green.

- [ ] **Step 4: Commit** — `git commit -m "feat: e2e cure loop against live SQL Server — PROVEN certificate"`

---

### Task 5: Wrap-up

- [ ] Full unit suite green; e2e green; tick checkboxes; update README Development section with the integration-test workflow; commit `chore: plan 3 complete`.

---

## Self-review notes

- The e2e test registers captures with `transport=driver` — honest: the harness runs SQL itself; courier mode is exercised by the unit tests' fixture-driven paths.
- sqlcmd's default text output differs from SSMS in column padding; `grading.ROW_RE` is format-agnostic (token-based), and `stats_io` parses message lines verbatim — if reality disagrees, fix the parser with a captured fixture, never the assertion.
- GENERATE_SERIES requires SQL Server 2022 — pinned image tag guarantees it.
- Workload sizes are emulation-friendly; if datagen is too slow under qemu, halve row counts in datagen.sql (keep ratios).
