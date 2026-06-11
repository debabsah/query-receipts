# CI mode: receipts as a pipeline gate

Two complementary uses.

## 1. Tamper gate — protect certified cases

If investigation cases live in your repo (they're plain directories), gate
every PR on their integrity. `receipts verify` re-hashes every evidence
file against the append-only ledger, checks ledger consistency, and checks
that every certificate's citations still resolve — exit 1 on any violation:

```yaml
- run: pip install "git+https://github.com/debabsah/query-receipts"
- name: certificates still mean what they say
  run: |
    for case in cases/*/; do receipts verify --case "$case"; done
```

A "fixed-up" capture, an edited ledger, or a certificate whose evidence
changed after certification all fail the build. Nobody re-litigates numbers
in review — the gate already did.

## 2. Prevention loop — re-prove rewrites on every change

When a PR touches SQL that has a certified rewrite, re-run the proof
against a stats-representative database (a container restored from a
schema+stats clone — never production):

```yaml
- run: bash scripts/db_up.sh          # your stats-clone container
- name: re-prove the rewrite
  run: |
    receipts prescribe validation --rewrite optimized/optimized_v1.sql \
      --natural-key OrderID --case "$CASE"
    receipts run "$CASE/prescriptions/validation_v1.sql" \
      --environment stats-clone --case "$CASE" \
      --runner-cmd 'psql -X -q -d mydb -f {sql}'
    receipts grade ev-0002 --case "$CASE" | tee /dev/stderr | grep -q PROVEN
```

`receipts run` is the driver transport: it executes the prescription via
your runner command, saves the capture at the prescribed path, and registers
it with `transport=ci`-grade provenance (the full runner command never
enters the ledger — only its first token — so secrets stay in CI env vars).

This repo's own [ci.yml](../.github/workflows/ci.yml) is the worked
example: every push boots SQL Server 2022 *and* Postgres 16 and requires
both end-to-end loops to produce PROVEN certificates.
