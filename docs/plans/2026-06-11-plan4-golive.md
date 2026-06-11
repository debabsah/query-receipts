# QueryReceipts Plan 4: Go-Live

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkboxes track steps.

**Goal:** Close the CTE validation limitation, ship the Claude Code plugin skin, write the worked example, polish for release, publish to github.com/debabsah/query-receipts (public, MIT), tag v0.1.0.

**Constraint from user:** any LLM-based test of the plugin/skill runs on **Sonnet**.

---

### Task 1: General validation materialization (CTE-capable)

The derived-table wrapper (`SELECT * INTO #t FROM (q) _x`) rejects CTE-headed
queries. Replace with general materialization:

- Queries are embedded as escaped `N'…'` literals (`{{ORIGINAL_QUERY_LITERAL}}`,
  `{{OPTIMIZED_QUERY_LITERAL}}`; Python escapes `'` → `''`).
- `sys.dm_exec_describe_first_result_set(@q)` builds the column list; staging
  tables `##ReceiptsOld`/`##ReceiptsNew` are created via dynamic DDL and filled
  with `INSERT … EXEC sp_executesql @q` (handles CTEs, any SELECT shape).
- Outer batch copies staging into `#OldResult`/`#NewResult`, drops staging.
  Header documents: don't run two validations concurrently on one server
  (fixed global-temp names); if describe fails → RAISERROR + RETURN
  (grader sees no rows → UNVERIFIED, never a false verdict).
- Rest of the test battery is unchanged.

**Files:** modify `templates/validation.sql.tmpl`, `cli.py` (`cmd_prescribe`
passes literals), `tests/test_prescription.py` (new interface), add
`examples/fleetdb/optimized_v1_cte.sql` + e2e test
`test_cte_rewrite_validates_proven` (validation-only loop, expects PROVEN).

- [ ] failing unit test: CTE rewrite renders into literals, no unrendered markers
- [ ] template rewrite + cli literal passing
- [ ] unit suite green
- [ ] e2e (both tests) green against fleetdb
- [ ] commit

### Task 2: Claude Code plugin skin

**Files:** `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`skills/query-receipts/SKILL.md`.

SKILL.md drives the CLI conversationally: interview → `receipts init` →
diagnostics loop (courier instructions verbatim from prescriptions) → the
model drafts rewrites under hard rules (identical SELECT list/order; no
hints/index DDL as first move; every claim cites an artifact id) → validation
→ benchmark → certify. The skill NEVER declares success without a PROVEN
certificate and surfaces UNVERIFIED/REFUTED verbatim. CLI invocation:
`receipts` if installed, else `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/src python3 -m queryreceipts.cli`.

- [ ] manifests + SKILL.md written
- [ ] Sonnet smoke test: one `claude` agent (model sonnet) follows SKILL.md
      cold — verifies every referenced command exists and works; fix mismatches
- [ ] commit

### Task 3: Worked example

**Files:** `docs/examples/fleetdb-walkthrough.md` — the FleetDB case end to
end with the real measured numbers (reads −99.8%, elapsed −91.3%, 16/16
checks) and the certificate excerpt; doubles as the credibility artifact the
old project never had.

- [ ] walkthrough written, numbers match the e2e run
- [ ] commit

### Task 4: Release polish + publish

- [ ] README: Install (pipx/pip from git), Quickstart (5 commands), plugin
      install, status table (shipped vs roadmap: MCP/driver transport,
      Postgres pack, CI mode)
- [ ] CHANGELOG.md for 0.1.0
- [ ] full unit + integration suites green
- [ ] `gh repo create debabsah/query-receipts --public --source . --push`
- [ ] tag v0.1.0, push, `gh release create`
- [ ] commit + verify repo renders
