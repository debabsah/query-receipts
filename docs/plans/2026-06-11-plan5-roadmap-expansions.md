# QueryReceipts Plan 5: Roadmap Expansions — Transports, Postgres, CI

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. TDD per step; commit per task.

**Goal:** Ship the three pre-approved expansions as v0.2.0: (1) driver + MCP transports, (2) the Postgres engine pack with its own e2e workload, (3) CI mode (`receipts verify` + the repo's own dogfood CI), then release.

**Architecture decisions (locked):**
- **Engine-aware pack registry.** `packs.get_pack(engine)` returns `{parsers: {kind: (parse, render)}, grade_validation, grade_benchmark, diagnostics_kind, validation_style}`. `cli` and `certificate.py` dispatch through it — no more hard-wired sqlserver imports. `extract_section`/`SectionNotFound` move to `packs/sections.py` (sqlserver.stats_io re-exports for compat).
- **Driver transport = runner command, not a DB driver.** Stdlib-only stays true: `receipts run <rendered-prescription> --runner-cmd "<shell cmd with {sql}>"` executes via `sh -c`, saves stdout to the prescription's `expected_capture`, auto-registers evidence (`transport=driver`). Only the command's first token is recorded as `runner` — full commands may contain secrets and never enter the ledger. `init --runner-cmd` persists a case default.
- **MCP transport = receipts as a stdio MCP server.** `receipts mcp-serve` speaks newline-delimited JSON-RPC (initialize / tools/list / tools/call), exposing tools that wrap the CLI verbs (init_case, prescribe, run_prescription, add_evidence, parse_evidence, grade, certify, case_status, verify). Handlers build argv and capture `cli.main` stdout — one code path, no drift.
- **Postgres pack.** Materialization is native (`CREATE TEMP TABLE x AS (query)` accepts CTEs) → validation uses inject style, not literals. Gates: version(), current_database(), TimeZone, DateStyle. Per-column battery via a `DO $$` block + format(). Output uses `\pset format unaligned` + `fieldsep '  '` + `tuples_only` so the existing token-based grader parses it unchanged. Diagnostics + benchmark use `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` between `\echo` section markers; new kind `pg_explain`; pg benchmark grader reads root-plan Execution Time + Shared Hit/Read blocks (cpu_pct stays None — Postgres doesn't report it; renderers skip None).
- **pgfleet workload** mirrors FleetDB logically (same tables/pathology, PG syntax: LIMIT 1 correlated subquery + `EXTRACT(YEAR …)` non-sargable original; window/grouped-join sargable rewrite). Container `pgfleet`, postgres:16, port 15432, db `fleetdb`. The pg e2e drives the loop through **`receipts run`** (dogfooding the driver transport).
- **CI mode v1:** `receipts verify --case` re-hashes every evidence file against the ledger, checks seq monotonicity and certificate citations; exit 1 on any violation (tamper-evidence gate for PRs). Repo CI (`.github/workflows/ci.yml`): unit job always; integration job boots both containers and runs `pytest -m integration`. `docs/ci-recipe.md` documents wiring this into a user's PR gate.

**Tasks:**

1. Pack-registry refactor + sections module; all existing tests stay green. Commit.
2. `receipts run`: unit test (fake runner writes capture + registers driver evidence; secret-free ledger), e2e: fleetdb full loop driven by `run`. Commit.
3. `receipts mcp-serve`: protocol unit test over a subprocess (initialize, tools/list, tools/call init_case). Commit.
4. Postgres pack templates + `pg_explain` parser + pg benchmark grader, fixture-driven unit tests. Commit.
5. pgfleet schema/datagen/query pair + scripts/pgfleet_up.sh|down.sh + e2e full pg loop → PROVEN certificate. Commit.
6. `receipts verify` + tamper unit tests; ci.yml; docs/ci-recipe.md. Commit.
7. README/CHANGELOG 0.2.0, version bumps, suites green, push, tag v0.2.0, release.
