---
name: query-receipts
description: Use when the user has a slow SQL Server query they want tuned with PROOF — drives the `receipts` CLI through an evidence-gated investigation. Every rewrite ends with a certificate (equivalence proof + benchmark delta), never a bare suggestion. Works offline (user runs SSMS, saves captures) or with any way to execute SQL.
---

# query-receipts

You drive a query-tuning investigation whose output is a **certificate**, not
an opinion. The `receipts` CLI owns evidence, grading, and certification; you
own analysis and the rewrite. You NEVER declare a rewrite safe or faster —
only a PROVEN certificate does.

## CLI invocation

Use `receipts` if on PATH; otherwise every command below works as:
`PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/src python3 -m queryreceipts.cli <args>`.
Every subcommand accepts `--json` when you need structured output.

## Hard rules

1. The rewrite preserves the SELECT list exactly: names, order, types.
2. No index DDL, hints, forced plans, or stats updates as a first move —
   candidate ideas go in case notes marked *DBA review*.
3. Every claim you make cites an artifact id (`ev-NNNN`) from the ledger; if
   the evidence doesn't exist yet, name the missing capture instead.
4. Surface UNVERIFIED and REFUTED verdicts verbatim. Never soften them.
5. Plan files can embed parameter values — treat `.sqlplan` captures as
   sensitive; the parser reports value *presence* only.
6. Read captures parser-first: `receipts parse <ev-id>` (~1 KB summary).
   Only Read a raw capture at a specific range when the summary flags an
   anomaly.

## Workflow

### 0. New case

Ask in ONE message: project shorthand, SQL Server version + DB name, symptom
in a sentence, where the query lives, the SQL (paste or path), how they can
run SQL (SSMS only / connection available), optional natural key for grain
checks. Then:

```
receipts init <dir> --engine sqlserver --database <DB> --symptom "<symptom>"
```

Save their query to `<dir>/original.sql`. All later commands take
`--case <dir>` (or run from inside it).

### 1. Baseline

```
receipts prescribe diagnostics --case <dir>
```

Hand the user the rendered file at `<dir>/prescriptions/diagnostics.sql` with
its embedded instructions (SSMS, Results to Text, save to the path the
prescription names). When they confirm:

```
receipts add <capture> --kind stats_io --transport courier \
  --environment production --runner "<who>" --case <dir>
receipts parse ev-0001 --section baseline_io_time --case <dir>
```

Analyze the summary: top tables by reads, Worktable presence (spool), elapsed
vs CPU. State your hypothesis citing the artifact id.

### 2. Rewrite

Draft `optimized/optimized_v1.sql` under the hard rules. Explain the change
in terms of the evidence (e.g. "ev-0001 shows 12M Worktable reads from the
correlated subquery; v1 replaces it with a windowed join"). Version every
attempt: `optimized_v2.sql`, never overwrite.

### 3. Prove it

```
receipts prescribe validation --rewrite optimized/optimized_v1.sql \
  --natural-key <KEY> --case <dir>
```

The rendered file lands at `prescriptions/validation_v<N>.sql` (versioned;
the CLI prints the exact path). User runs it and saves the grid; then:

```
receipts add <results-file> --kind validation_results --transport courier \
  --environment production --runner "<who>" --case <dir>
receipts grade <ev-id> --case <dir>
```
- PROVEN → continue. REFUTED → the rewrite is wrong; read the failures, fix,
  version up. UNVERIFIED → the capture is unusable; re-prescribe, don't guess.

### 4. Measure it

```
receipts prescribe benchmark --rewrite optimized/optimized_v1.sql --case <dir>
```

The rendered file lands at `prescriptions/benchmark_v<N>.sql`. The protocol
is pinned in the ledger before results exist: run TWICE, save the SECOND
run. Then:

```
receipts add <results-file> --kind benchmark_results --transport courier \
  --environment production --runner "<who>" --case <dir>
receipts grade <ev-id> --case <dir>
```

(`--transport/--environment/--runner` are required on every `add`, whatever
the kind — provenance is never optional.)

### 5. Certify

```
receipts certify --validation <ev> --benchmark <ev> \
  --rewrite optimized/optimized_v1.sql --case <dir>
```

Deliver the rendered certificate to the user. PROVEN means done; anything
else, the certificate names what's missing — go get it.

### Plan deep-dives (optional)

For plan-shape questions: register `.sqlplan` files (`--kind plan_xml`),
`receipts parse` for skew/spills/missing indexes, `receipts diff <a> <b>` to
compare two plans of the same query.

## Resumption

In an existing case directory: `receipts status --case <dir>` shows the
ledger; proceed from the last event. The ledger is append-only — never edit
case files by hand.
