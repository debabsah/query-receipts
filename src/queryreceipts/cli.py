"""receipts — query tuning with receipts.

Subcommands operate on a case directory (--case PATH, default: walk upward
from cwd). Every subcommand supports --json for machine consumption.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .case import Case, CaseError


def _find_case(args) -> Case:
    start = Path(args.case) if args.case else Path.cwd()
    return Case.find(start)


def cmd_init(args) -> int:
    root = Path(args.path)
    meta = {"case": root.name, "engine": args.engine,
            "database": args.database, "symptom": args.symptom}
    if args.runner_cmd:
        meta["runner_cmd"] = args.runner_cmd
    case = Case.init(root, meta)
    print(f"opened case {case.meta['case']} at {case.root}")
    return 0


def cmd_add(args) -> int:
    case = _find_case(args)
    ev = case.register_evidence(
        Path(args.file), kind=args.kind, transport=args.transport,
        environment=args.environment, runner=args.runner,
        captured_at=args.captured_at, notes=args.notes)
    print(f"registered {ev.artifact_id}: {ev.path} "
          f"(sha256 {ev.sha256[:12]}…)")
    return 0


def cmd_verify(args) -> int:
    """CI gate: prove the case file is intact — every evidence file still
    matches its registered hash, the ledger is append-only-consistent, and
    every certificate's citations still resolve. Exit 1 on any violation."""
    from .evidence import sha256_of
    case = _find_case(args)
    problems = []
    events = case.events()
    seqs = [e["seq"] for e in events]
    if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
        problems.append("ledger seq is non-monotonic — journal was edited "
                        "or reordered")
    evidence = case.evidence()
    broken_ids = set()
    for ev in evidence:
        p = case.root / ev.path
        if not p.exists():
            problems.append(f"MISSING {ev.artifact_id}: {ev.path}")
            broken_ids.add(ev.artifact_id)
        elif sha256_of(p) != ev.sha256:
            problems.append(f"TAMPERED {ev.artifact_id}: {ev.path} no "
                            "longer matches its registered sha256")
            broken_ids.add(ev.artifact_id)
    certs = [e for e in events if e["event"] == "certificate_issued"]
    known = {ev.artifact_id for ev in evidence}
    for c in certs:
        for aid in c.get("evidence", []):
            if aid not in known:
                problems.append(f"{c['certificate_id']} cites unknown "
                                f"artifact {aid}")
            elif aid in broken_ids:
                problems.append(f"{c['certificate_id']} citation broken: "
                                f"{aid} no longer matches the hash it was "
                                "certified against")
    if problems:
        print(f"VERIFY FAILED — {len(problems)} problem(s):")
        for pr in problems:
            print(f"  {pr}")
        return 1
    print(f"OK: ledger consistent, {len(evidence)} evidence artifact(s) "
          f"match their hashes, {len(certs)} certificate(s) intact")
    return 0


def cmd_status(args) -> int:
    case = _find_case(args)
    evidence = [ev.__dict__ for ev in case.evidence()]
    if args.json:
        print(json.dumps({"case": case.meta, "evidence": evidence,
                          "events": len(case.events())}, indent=2))
        return 0
    print(f"case: {case.meta['case']}  engine: {case.meta.get('engine')}")
    print(f"symptom: {case.meta.get('symptom')}")
    print(f"ledger events: {len(case.events())}")
    for ev in evidence:
        print(f"  {ev['artifact_id']}  {ev['kind']:<18} {ev['path']}")
    return 0


def cmd_parse(args) -> int:
    from .packs import get_parser
    from .packs.sections import extract_section
    case = _find_case(args)
    ev = case.get_evidence(args.artifact)
    parse_fn, render_fn = get_parser(ev.kind,
                                     case.meta.get("engine", "sqlserver"))
    text = (case.root / ev.path).read_text(encoding="utf-8", errors="replace")
    if args.section:
        text = extract_section(text, args.section)
    parsed = parse_fn(text)
    case.append({"event": "summary_derived", "source": ev.artifact_id,
                 "kind": ev.kind, "section": args.section or ""})
    if args.json:
        print(json.dumps(parsed, indent=2))
    else:
        print(render_fn(parsed), end="")
    return 0


def cmd_diff(args) -> int:
    from .packs.sqlserver.plandiff import diff_plans, render_diff
    from .packs.sqlserver.planxml import parse_plan
    case = _find_case(args)
    plans = []
    for ref in (args.plan_a, args.plan_b):
        ev = case.get_evidence(ref)
        if ev.kind != "plan_xml":
            raise CaseError(f"{ref} is kind {ev.kind!r}, need plan_xml")
        text = (case.root / ev.path).read_text(encoding="utf-8",
                                               errors="replace")
        plans.append(parse_plan(text))
    d = diff_plans(*plans)
    case.append({"event": "plans_diffed",
                 "a": args.plan_a, "b": args.plan_b})
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print(render_diff(d), end="")
    return 0


def cmd_prescribe(args) -> int:
    from .packs import get_pack
    from .prescription import issue
    case = _find_case(args)
    pack = get_pack(case.meta.get("engine", "sqlserver"))
    n = sum(1 for e in case.events()
            if e["event"] == "prescription_issued"
            and e["prescription"] == args.kind) + 1
    injections = {}
    values = {}
    if args.kind in ("validation", "benchmark"):
        if not args.rewrite:
            raise CaseError(f"--rewrite is required for {args.kind}")
        rewrite = Path(args.rewrite)
        if not rewrite.is_absolute():
            rewrite = case.root / rewrite
        rewrite_sql = rewrite.read_text(encoding="utf-8")
        injections["INJECT_OPTIMIZED_QUERY"] = rewrite_sql
    if args.kind == "validation":
        original = case.root / "original.sql"
        if not original.exists():
            raise CaseError("validation needs original.sql in the case root")
        if pack["validation_style"] == "literal":
            # queries embedded as N'…' literals (dynamic-SQL materialization)
            values["ORIGINAL_QUERY_LITERAL"] = original.read_text(
                encoding="utf-8").replace("'", "''")
            values["OPTIMIZED_QUERY_LITERAL"] = rewrite_sql.replace("'", "''")
        values["NATURAL_KEY"] = args.natural_key or ""
        save_as = f"prescriptions/validation_v{n}.sql"
        expected = f"validation/v{n}_results.txt"
        register_kind = "validation_results"
    elif args.kind == "benchmark":
        save_as = f"prescriptions/benchmark_v{n}.sql"
        expected = f"benchmarks/v{n}_results.txt"
        register_kind = "benchmark_results"
    else:
        save_as = "prescriptions/diagnostics.sql"
        expected = "runs/baseline/diagnostics.txt"
        register_kind = pack["diagnostics_kind"]
    p = issue(case, args.kind, values=values, save_as=save_as,
              expected_capture=expected, injections=injections)
    print(f"prescription written: {p}")
    print(f"run it, save output to {case.root / expected}, then: "
          f"receipts add {case.root / expected} --kind {register_kind} ...")
    return 0


def cmd_run(args) -> int:
    """Driver transport: execute a rendered prescription via the configured
    runner command and auto-register the capture. The full command never
    enters the ledger (it may contain secrets) — only its first token."""
    import shlex
    import subprocess
    from .case import utcnow
    from .packs import get_pack
    case = _find_case(args)
    runner = args.runner_cmd or case.meta.get("runner_cmd")
    if not runner:
        raise CaseError("no runner command: pass --runner-cmd or set it "
                        "with init --runner-cmd (driver transport)")
    if "{sql}" not in runner:
        raise CaseError("runner command must contain a {sql} placeholder")
    target = Path(args.prescription)
    if not target.is_absolute():
        target = case.root / target
    try:
        rel = target.resolve().relative_to(case.root.resolve()).as_posix()
    except ValueError:
        raise CaseError(
            f"{target} is not inside the case directory") from None
    event = next((e for e in reversed(case.events())
                  if e["event"] == "prescription_issued"
                  and e["rendered_to"] == rel), None)
    if event is None:
        raise CaseError(f"{rel} is not a rendered prescription in this case")
    cmd = runner.replace("{sql}", shlex.quote(str(target)))
    proc = subprocess.run(["sh", "-c", cmd], capture_output=True,
                          text=True, timeout=args.timeout)
    capture = case.root / event["expected_capture"]
    capture.parent.mkdir(parents=True, exist_ok=True)
    out = proc.stdout + (("\n" + proc.stderr) if proc.stderr.strip() else "")
    capture.write_text(out, encoding="utf-8")
    pack = get_pack(case.meta.get("engine", "sqlserver"))
    kind = {"diagnostics": pack["diagnostics_kind"],
            "validation": "validation_results",
            "benchmark": "benchmark_results"}.get(
                event["prescription"], "other")
    ev = case.register_evidence(
        capture, kind=kind, transport="driver",
        environment=args.environment, runner=runner.split()[0],
        captured_at=utcnow(),
        notes=f"receipts run, exit {proc.returncode}")
    print(f"ran {rel} -> {event['expected_capture']} "
          f"(exit {proc.returncode}); registered {ev.artifact_id}")
    if proc.returncode != 0:
        print(f"receipts: runner exited {proc.returncode}; capture "
              "registered anyway — grade it to see what happened",
              file=sys.stderr)
        return 1
    return 0


def cmd_grade(args) -> int:
    from .packs import get_pack
    case = _find_case(args)
    pack = get_pack(case.meta.get("engine", "sqlserver"))
    ev = case.get_evidence(args.artifact)
    text = (case.root / ev.path).read_text(encoding="utf-8",
                                           errors="replace")
    if ev.kind == "validation_results":
        g = pack["grade_validation"](text)
    elif ev.kind == "benchmark_results":
        g = pack["grade_benchmark"](text)
    else:
        raise CaseError(f"cannot grade kind {ev.kind!r}")
    case.append({"event": "graded", "source": ev.artifact_id,
                 "verdict": g["verdict"]})
    if args.json:
        print(json.dumps(g, indent=2))
        return 0
    print(f"{g['verdict']}: {ev.artifact_id} ({ev.kind})")
    for f in g.get("failures", []):
        print(f"  FAIL {f['test_name']}: {f['detail']}")
    if g.get("reason"):
        print(f"  {g['reason']}")
    if g.get("improvement"):
        imp = g["improvement"]
        parts = [f"{k.removesuffix('_pct')} -{v}%"
                 for k, v in imp.items() if v is not None]
        print("  " + " | ".join(parts))
    return 0


def cmd_certify(args) -> int:
    from .certificate import issue_certificate, render_certificate
    case = _find_case(args)
    cert = issue_certificate(case, validation_id=args.validation,
                             benchmark_id=args.benchmark,
                             rewrite=args.rewrite)
    if args.json:
        print(json.dumps(cert, indent=2))
    else:
        print(render_certificate(cert), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="receipts")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="open a new case")
    sp.add_argument("path")
    sp.add_argument("--engine", required=True)
    sp.add_argument("--database", required=True)
    sp.add_argument("--symptom", required=True)
    sp.add_argument("--runner-cmd", default=None, dest="runner_cmd",
                    help="default driver-transport command; must contain "
                         "{sql}. Do not embed secrets — use env/.pgpass.")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser(
        "run", help="execute a rendered prescription via the runner command "
                    "(driver transport) and register the capture")
    sp.add_argument("prescription", help="path to the rendered .sql")
    sp.add_argument("--runner-cmd", default=None, dest="runner_cmd")
    sp.add_argument("--environment", required=True)
    sp.add_argument("--timeout", type=int, default=600)
    sp.add_argument("--case", default=None)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("add", help="register a capture as evidence")
    sp.add_argument("file")
    sp.add_argument("--kind", required=True)
    sp.add_argument("--transport", required=True)
    sp.add_argument("--environment", required=True)
    sp.add_argument("--runner", required=True)
    sp.add_argument("--captured-at", default="", dest="captured_at")
    sp.add_argument("--notes", default="")
    sp.add_argument("--case", default=None)
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("parse",
                        help="parse registered evidence into a summary")
    sp.add_argument("artifact", help="artifact id, e.g. ev-0001")
    sp.add_argument("--section", default=None)
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("diff", help="diff two registered plan_xml artifacts")
    sp.add_argument("plan_a")
    sp.add_argument("plan_b")
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("prescribe", help="render a capture prescription")
    sp.add_argument("kind",
                    choices=["diagnostics", "validation", "benchmark"])
    sp.add_argument("--rewrite", default=None,
                    help="path to optimized SQL (validation/benchmark)")
    sp.add_argument("--natural-key", default=None, dest="natural_key")
    sp.add_argument("--case", default=None)
    sp.set_defaults(func=cmd_prescribe)

    sp = sub.add_parser("grade", help="grade a registered results capture")
    sp.add_argument("artifact")
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_grade)

    sp = sub.add_parser("certify", help="issue a certificate for a rewrite")
    sp.add_argument("--validation", default=None)
    sp.add_argument("--benchmark", default=None)
    sp.add_argument("--rewrite", required=True)
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_certify)

    sp = sub.add_parser("mcp-serve",
                        help="serve the receipts toolset as a stdio MCP "
                             "server (MCP transport)")
    sp.set_defaults(func=lambda args: __import__(
        "queryreceipts.mcp_server", fromlist=["serve"]).serve())

    sp = sub.add_parser("verify",
                        help="CI gate: evidence hashes, ledger consistency, "
                             "certificate citations — exit 1 on violation")
    sp.add_argument("--case", default=None)
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("status", help="show case state")
    sp.add_argument("--case", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CaseError, ValueError, KeyError, OSError) as exc:
        print(f"receipts: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
