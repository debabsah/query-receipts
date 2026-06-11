# QueryReceipts

**Provably faster.** Query tuning where every fix ships with receipts: an
equivalence proof, a plan diff, and a benchmark delta — a certificate a DBA
can take to a change-advisory board.

Short name: **Receipts** (CLI: `receipts`).

## The thesis

LLMs made query-tuning *advice* free. What stays scarce is:

1. **Evidence acquisition** — getting the right captures out of locked-down,
   messy production systems.
2. **Verification** — proving a proposed rewrite returns identical results
   and is actually faster.
3. **Trust & audit** — showing a skeptical reviewer exactly why a change is
   safe, with provenance for every claim.

QueryReceipts owns the scarce part. The model suggests; the product proves.

## The core asset

A **proof engine**, built once and reused everywhere:

- Equivalence certification (row counts, bidirectional EXCEPT, per-column
  distributions, grain reconciliation on a natural key).
- Plan/trace diffing (est-vs-actual skew, spills, conversions, operator deltas).
- Benchmark attestation (before/after IO and time, warm/cold cache).

Wrapped in capture packs per engine: SQL Server first, then Postgres,
Snowflake, BigQuery.

## The transport invariant

The proof engine never connects to anything. It consumes **evidence
artifacts** — files with provenance (who ran it, where, when, how it
traveled, content hash) — and emits **capture prescriptions** and
**certificates**. Transports fulfill prescriptions:

- **Human courier** (air-gapped): user runs the prescribed script in
  SSMS/psql, saves output to the prescribed path.
- **Approve-each-script**: agent proposes, human executes or one-click
  approves.
- **MCP-connected**: an MCP server fulfills capture prescriptions
  automatically.
- **Direct driver** (ODBC/JDBC): full read access, zero-friction loop.
- **CI runner**: prevention mode, captures against a stats-clone.

Air-gapped is the *base case*, not the degraded case. Every connected mode
is the same loop with a faster courier. A feature that cannot work
air-gapped gets redesigned or explicitly marked transport-dependent — never
silently assumed connected.

## Composable dimensions

Orthogonal axes, combinable by design; every evidence artifact records its
coordinates in the case file:

- **Engine pack**: SQL Server / Postgres / MySQL / Snowflake / BigQuery …
- **Transport**: courier / approve-each / MCP / driver / CI.
- **Permission tier**: read-only / VIEW DATABASE STATE / sysadmin — capture
  menus are keyed to what the tier can actually see.
- **Data sensitivity**: metadata-only / sampled rows / full rows. Strictest
  cell (air-gapped + metadata-only) must remain fully usable.
- **Workload shape**: single SELECT / view / stored proc / DML-ETL / batch.
- **Environment**: production / staging / stats-clone.
- **Mode**: cure (episodic investigation) / prevention (CI gate).

Unreachable cells are represented honestly: the engine prescribes the
missing permission or capture instead of pretending.

## Sequencing

1. **Cure** (now): episodic verified-fix engine; cloud-warehouse cost savings
   as the quantifiable-ROI wedge.
2. **Air-gap posture** (early, cheap): the audit trail proving the AI never
   touched the system — the enterprise differentiator.
3. **Prevention** (later): CI gate — equivalence + plan-shape regression check
   on every PR that touches SQL. Same proof engine, habitual usage.
4. **Platform** (earned, not started): generalize the harness only after one
   domain is won.

## Non-negotiables

- Every claim cites its capture, or names the missing capture instead of
  guessing.
- The investigation persists as a replayable case file — the compounding,
  org-specific asset.
- No suggestion ships without its receipts.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Engine code is stdlib-only by policy: a proof tool should carry zero
supply-chain surface. pytest is the only dev dependency.

Integration tests drive the full cure loop against a live SQL Server 2022
container (FleetDB, a deterministic synthetic workload mirroring a real
production pathology):

```bash
bash scripts/fleetdb_up.sh        # needs Docker; first run takes minutes
.venv/bin/python -m pytest -m integration
bash scripts/fleetdb_down.sh
```

## Known limitations (tracked, not hidden)

- Validation materializes queries via a derived-table wrapper, so a rewrite
  whose outermost statement is a CTE (`WITH …`) cannot be validated yet —
  the grader correctly returns UNVERIFIED rather than guessing. General
  materialization (INSERT…EXEC + `dm_exec_describe_first_result_set`) is
  planned.
- Single-statement SELECT workloads only; stored procs and DML-ETL
  validation are future work.

## Lineage

Conceived 2026-06-11 from a first-principles review of the `sql-query-tuner`
skill (sibling folder), whose equivalence-validation harness and
evidence-citation rules are the kernel this product industrializes.

Philosophical imports from the `analytics-office` plugin (sibling), adapted
not copied:

- **Comparability gate first** (from prove-my-parity): before any old-vs-new
  comparison — same parameters, same data as-of, same session semantics — or
  the proof is declared invalid, not run anyway.
- **Stratified comparison over matching totals**: aggregate equality with
  offsetting per-segment errors is a FAIL, not a PASS.
- **Verdicts carry provenance and age**: a certificate is stamped against a
  data snapshot, schema version, and stats state; it expires on drift.
- **Pre-registered success criteria** (from explore-my-data): benchmark
  protocol and the headline metric are pinned *before* measuring, killing
  cherry-picked warm-cache wins.
- **Three-valued honesty**: PROVEN / REFUTED / UNVERIFIED-with-named-missing-
  capture. Never "safe beyond the evidence"; UNKNOWN stays UNKNOWN.
- **Blast-radius grading** (from audit-my-assumptions): findings and
  escalations are prioritized by what they can silently corrupt, not by
  loudness.

What deliberately does *not* port: analytics-office is constitutionally
read-only and never produces the deliverable. QueryReceipts must produce it
(rewrite + certificate) and, in connected modes, execute captures. The
read-only law is therefore demoted to (a) the air-gapped mode and (b) a
standing posture: never write to the target system; proofs use session-local
scratch only.
