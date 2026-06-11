# Changelog

## [0.2.0] - 2026-06-11

The pre-approved roadmap, shipped:

- **Driver transport** — `receipts run` executes prescriptions via a
  configurable runner command (`{sql}` placeholder), saves the capture at
  the prescribed path, and registers it with provenance; runner commands
  never enter the ledger (first token only — secrets stay out).
- **MCP transport** — `receipts mcp-serve`: the full toolset as a stdio
  MCP server (stdlib JSON-RPC), usable from any MCP client.
- **Postgres pack** — `--engine postgres`: EXPLAIN (ANALYZE, BUFFERS,
  FORMAT JSON) parsing with loops-aware skew detection, inject-style
  validation (CTEs native), pg benchmark grading (CPU honestly absent).
  Proven by a second full-loop e2e (pgfleet) ending in a PROVEN certificate.
- **CI mode** — `receipts verify`: re-hashes evidence, checks ledger
  monotonicity and certificate citations, exit 1 on tamper; repo CI now
  re-proves both engines' cure loops on every push; docs/ci-recipe.md.
- Engine-aware pack registry; shared section parsing; certificate/grade
  renderers skip absent metrics instead of inventing them.

## [0.1.0] - 2026-06-11

Initial release — the cure loop, proven end to end.

- `receipts` CLI (stdlib-only): `init`, `add`, `parse`, `diff`, `prescribe`,
  `grade`, `certify`, `status`; `--json` everywhere.
- Case files with an append-only JSONL ledger; evidence registration with
  sha256 + provenance (transport / environment / runner vocabularies).
- SQL Server pack: STATISTICS IO/TIME parser (sections, repeated-table
  aggregation, lob reads, compile-vs-execution time, warnings); showplan
  parser (all statements, est-vs-actual skew, spills, self-cost attribution,
  missing indexes, parameter-presence sensitivity flag); plan diff.
- Proof loop: prescriptions that refuse half-rendered SQL; validation with
  comparability gates and CTE-capable materialization
  (`dm_exec_describe_first_result_set` + `INSERT…EXEC`); benchmark protocol
  pinned in the ledger before results exist; three-valued certificates
  (PROVEN / REFUTED / UNVERIFIED) citing every artifact hash.
- FleetDB synthetic workload + integration suite driving the full loop
  against SQL Server 2022 in Docker; e2e certificate: reads −99.8%,
  elapsed −91.3%, 16/16 equivalence checks.
- Claude Code plugin (`query-receipts`) — conversational skin over the CLI,
  cold-tested with a Sonnet agent.
