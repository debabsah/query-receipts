# Changelog

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
