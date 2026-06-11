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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="receipts")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="open a new case")
    sp.add_argument("path")
    sp.add_argument("--engine", required=True)
    sp.add_argument("--database", required=True)
    sp.add_argument("--symptom", required=True)
    sp.set_defaults(func=cmd_init)

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
