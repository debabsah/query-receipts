import json
import subprocess
import sys


def test_mcp_server_speaks_jsonrpc_and_creates_case(tmp_path):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "init_case",
                    "arguments": {"path": str(tmp_path / "c"),
                                  "engine": "sqlserver", "database": "S",
                                  "symptom": "slow"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "case_status",
                    "arguments": {"case": str(tmp_path / "c")}}},
    ]
    stdin = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "queryreceipts.cli", "mcp-serve"],
        input=stdin, capture_output=True, text=True, timeout=60)
    lines = [json.loads(line) for line in proc.stdout.splitlines()
             if line.strip()]
    by_id = {m.get("id"): m for m in lines}

    assert by_id[1]["result"]["serverInfo"]["name"] == "queryreceipts"
    names = [t["name"] for t in by_id[2]["result"]["tools"]]
    for expected in ("init_case", "prescribe", "run_prescription",
                     "add_evidence", "parse_evidence", "grade",
                     "certify", "case_status"):
        assert expected in names
    assert by_id[3]["result"]["isError"] is False
    assert (tmp_path / "c" / "case.json").exists()
    assert "slow" in by_id[4]["result"]["content"][0]["text"]


def test_mcp_server_reports_tool_errors_not_crashes(tmp_path):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "grade",
                    "arguments": {"case": str(tmp_path), "artifact": "ev-0001"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "no/such-method"},
    ]
    stdin = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "queryreceipts.cli", "mcp-serve"],
        input=stdin, capture_output=True, text=True, timeout=60)
    lines = [json.loads(line) for line in proc.stdout.splitlines()
             if line.strip()]
    by_id = {m.get("id"): m for m in lines}
    assert by_id[1]["result"]["isError"] is True   # no case there
    assert by_id[2]["error"]["code"] == -32601
