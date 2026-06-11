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
    (out / f"certificate_{n:04d}.md").write_text(
        render_certificate(cert), encoding="utf-8")
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
