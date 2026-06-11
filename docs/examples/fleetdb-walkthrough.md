# Worked example: the FleetDB case

A complete QueryReceipts investigation, end to end, against a reproducible
workload you can run yourself. Every number below comes from the repo's own
integration test (`pytest -m integration`) driving a real SQL Server 2022
instance — nothing is illustrative or made up.

## The setup

FleetDB is a deterministic synthetic reservation system (200k reservations,
600k reservation items, 400k travelers) modeled on a real production
engagement's shape. The slow query has two classic pathologies:

- a correlated `TOP 1 … ORDER BY` subquery per output row ("latest status"),
  with no supporting index → repeated scans and a worktable spool;
- a non-sargable predicate, `YEAR(START_DATE) = 2025`.

Bring it up (Docker required):

```bash
bash scripts/fleetdb_up.sh
```

## The investigation

```bash
receipts init fleetdb-case --engine sqlserver --database FleetDB \
  --symptom "extract slow, high reads"
cp examples/fleetdb/original.sql fleetdb-case/original.sql

# 1. baseline
receipts prescribe diagnostics --case fleetdb-case
#   → run prescriptions/diagnostics.sql, save to runs/baseline/diagnostics.txt
receipts add fleetdb-case/runs/baseline/diagnostics.txt --kind stats_io \
  --transport courier --environment synthetic --runner you --case fleetdb-case
receipts parse ev-0001 --section baseline_io_time --case fleetdb-case
```

The 1 KB summary makes the diagnosis obvious — the top tables by logical
reads are dominated by the correlated access pattern (in the original
production capture this shape peaked at a single 12M-read Worktable).

The rewrite (`examples/fleetdb/optimized_v1_cte.sql`) replaces the correlated
subqueries with a `ROW_NUMBER()` window and a grouped join, and makes the
date predicate a half-open range. Identical SELECT list, names, and order —
hard rule #1.

```bash
# 2. prove equivalence
receipts prescribe validation --rewrite optimized/optimized_v1.sql \
  --natural-key RES_ID --case fleetdb-case
#   → run prescriptions/validation_v1.sql, save the grid
receipts add ... --kind validation_results ...
receipts grade ev-0002 --case fleetdb-case
# PROVEN: 16 checks passed, 0 failed (bidirectional EXCEPT, per-column
# null/distinct/min-max-sum, natural-key grain strata, + 6 gate rows)

# 3. measure (protocol pinned in the ledger BEFORE running: 2 runs, second counts)
receipts prescribe benchmark --rewrite optimized/optimized_v1.sql --case fleetdb-case
receipts add ... --kind benchmark_results ...

# 4. certify
receipts certify --validation ev-0002 --benchmark ev-0003 \
  --rewrite optimized/optimized_v1.sql --case fleetdb-case
```

## The certificate

```
# Certificate cert-0001 — PROVEN

Equivalence: 16 checks passed, 0 failed.
Performance: elapsed -91.3%, cpu -85.6%, reads -99.8% (per pinned protocol).

  original:  elapsed 1,545 ms | cpu 3,151 ms | logical reads 2,005,866
  optimized: elapsed   135 ms | cpu   453 ms | logical reads     4,070

Comparability gates (recorded in-session):
- gate:database = FleetDB
- gate:engine_version = 16.x
- gate:ansi_nulls / quoted_identifier / language / datefirst …

Evidence:
- ev-0002 validation_results sha256:…
- ev-0003 benchmark_results  sha256:…

Conditions:
- valid for the schema and statistics state at capture time
- invalidated by schema changes to referenced tables
- invalidated by edits to original or optimized SQL
```

## Why this matters

Any LLM could have suggested this rewrite. The product is everything after
the suggestion: the proof that 66k rows came back byte-identical, the
pre-pinned benchmark protocol that prevents cherry-picking, and a certificate
a DBA can take to a change-advisory board — with the hash of every capture
it relied on.

One more thing this example demonstrates honestly: the first version of the
validation template couldn't materialize CTE-headed rewrites. The e2e suite
caught it, the grader returned UNVERIFIED (not a false PROVEN), and the
general materialization path (`dm_exec_describe_first_result_set` +
`INSERT…EXEC`) now handles it — there's a dedicated regression test.
