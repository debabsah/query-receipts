"""receipts as an MCP server (stdio, newline-delimited JSON-RPC 2.0).

Any MCP client — Claude Code, Claude Desktop, another agent — becomes a
transport: the model calls these tools, receipts owns evidence, grading,
and certificates. Tool handlers wrap the CLI verbs so there is exactly one
code path and the MCP surface can never drift from the CLI.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout

from . import __version__

PROTOCOL_VERSION = "2024-11-05"


def _opt(argv: list, flag: str, value) -> list:
    return argv + [flag, str(value)] if value not in (None, "") else argv


def _schema(required: dict, optional: dict | None = None) -> dict:
    props = {k: {"type": "string", "description": v}
             for k, v in {**required, **(optional or {})}.items()}
    return {"type": "object", "properties": props,
            "required": list(required)}


TOOLS = [
    {"name": "init_case",
     "description": "Open a new investigation case directory.",
     "inputSchema": _schema(
         {"path": "case directory to create", "engine": "e.g. sqlserver",
          "database": "target database name", "symptom": "one sentence"},
         {"runner_cmd": "driver-transport command containing {sql}"}),
     "argv": lambda a: _opt(
         ["init", a["path"], "--engine", a["engine"],
          "--database", a["database"], "--symptom", a["symptom"]],
         "--runner-cmd", a.get("runner_cmd"))},
    {"name": "prescribe",
     "description": "Render a capture prescription "
                    "(diagnostics|validation|benchmark).",
     "inputSchema": _schema(
         {"case": "case directory", "kind": "diagnostics|validation|benchmark"},
         {"rewrite": "path to optimized SQL", "natural_key": "grain key"}),
     "argv": lambda a: _opt(_opt(
         ["prescribe", a["kind"], "--case", a["case"]],
         "--rewrite", a.get("rewrite")), "--natural-key",
         a.get("natural_key"))},
    {"name": "run_prescription",
     "description": "Driver transport: execute a rendered prescription via "
                    "the runner command and register the capture.",
     "inputSchema": _schema(
         {"case": "case directory", "prescription": "rendered .sql path",
          "environment": "production|staging|stats-clone|synthetic"},
         {"runner_cmd": "override runner command containing {sql}"}),
     "argv": lambda a: _opt(
         ["run", a["prescription"], "--environment", a["environment"],
          "--case", a["case"]], "--runner-cmd", a.get("runner_cmd"))},
    {"name": "add_evidence",
     "description": "Register a capture file as evidence with provenance.",
     "inputSchema": _schema(
         {"case": "case directory", "file": "capture path",
          "kind": "stats_io|plan_xml|validation_results|benchmark_results|…",
          "transport": "courier|approve-each|mcp|driver|ci",
          "environment": "production|staging|stats-clone|synthetic",
          "runner": "who executed the capture"},
         {"notes": "free text"}),
     "argv": lambda a: _opt(
         ["add", a["file"], "--kind", a["kind"], "--transport",
          a["transport"], "--environment", a["environment"], "--runner",
          a["runner"], "--case", a["case"]], "--notes", a.get("notes"))},
    {"name": "parse_evidence",
     "description": "Parse registered evidence into a ~1KB summary.",
     "inputSchema": _schema(
         {"case": "case directory", "artifact": "artifact id, e.g. ev-0001"},
         {"section": "section name for sectioned captures"}),
     "argv": lambda a: _opt(
         ["parse", a["artifact"], "--case", a["case"]],
         "--section", a.get("section"))},
    {"name": "grade",
     "description": "Grade a validation or benchmark results capture.",
     "inputSchema": _schema(
         {"case": "case directory", "artifact": "artifact id"}),
     "argv": lambda a: ["grade", a["artifact"], "--case", a["case"]]},
    {"name": "certify",
     "description": "Issue a three-valued certificate for a rewrite.",
     "inputSchema": _schema(
         {"case": "case directory", "rewrite": "rewrite path"},
         {"validation": "validation artifact id",
          "benchmark": "benchmark artifact id"}),
     "argv": lambda a: _opt(_opt(
         ["certify", "--rewrite", a["rewrite"], "--case", a["case"]],
         "--validation", a.get("validation")),
         "--benchmark", a.get("benchmark"))},
    {"name": "case_status",
     "description": "Show case metadata, ledger size, and evidence list.",
     "inputSchema": _schema({"case": "case directory"}),
     "argv": lambda a: ["status", "--case", a["case"]]},
]


def _run_cli(argv: list[str]) -> tuple[int, str]:
    from .cli import main
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(argv)
    text = out.getvalue()
    if err.getvalue().strip():
        text += ("\n" if text else "") + err.getvalue()
    return rc, text


def handle(msg: dict) -> dict | None:
    mid = msg.get("id")
    method = msg.get("method", "")
    if method == "initialize":
        client = msg.get("params", {})
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": client.get("protocolVersion",
                                          PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "queryreceipts",
                           "version": __version__}}}
    if mid is None:  # notifications need no reply
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {k: t[k] for k in ("name", "description", "inputSchema")}
            for t in TOOLS]}}
    if method == "tools/call":
        params = msg.get("params", {})
        tool = next((t for t in TOOLS
                     if t["name"] == params.get("name")), None)
        if tool is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32602,
                "message": f"unknown tool {params.get('name')!r}"}}
        try:
            rc, text = _run_cli(tool["argv"](params.get("arguments", {})))
        except KeyError as exc:
            rc, text = 1, f"missing required argument: {exc}"
        except Exception as exc:  # tool errors are results, not crashes
            rc, text = 1, f"{type(exc).__name__}: {exc}"
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": text or "(no output)"}],
            "isError": rc != 0}}
    return {"jsonrpc": "2.0", "id": mid, "error": {
        "code": -32601, "message": f"unknown method {method!r}"}}


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0
