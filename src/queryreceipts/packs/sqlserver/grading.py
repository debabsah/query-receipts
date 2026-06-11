"""Grade saved validation results.

Three-valued: PROVEN (every test PASS), REFUTED (any FAIL), UNVERIFIED
(no parseable test rows — the capture itself is the problem). Gate rows
(INFO) are echoed through for the certificate to cite.
"""
from __future__ import annotations

import re

ROW_RE = re.compile(
    r"^(?P<name>\S+)\s+(?P<status>PASS|FAIL|INFO)\s+(?P<detail>.*?)\s*$",
    re.MULTILINE)


def grade_validation(text: str) -> dict:
    rows = [m.groupdict() for m in ROW_RE.finditer(text)]
    tests = [r for r in rows if r["status"] in ("PASS", "FAIL")]
    gates = {r["name"]: r["detail"] for r in rows if r["status"] == "INFO"}
    if not tests:
        return {"verdict": "UNVERIFIED",
                "reason": "no test rows found in capture — re-run the "
                          "validation prescription and save the full grid",
                "counts": {"PASS": 0, "FAIL": 0, "INFO": len(gates)},
                "failures": [], "gates": gates, "tests": []}
    failures = [{"test_name": r["name"], "detail": r["detail"]}
                for r in tests if r["status"] == "FAIL"]
    verdict = "REFUTED" if failures else "PROVEN"
    return {"verdict": verdict,
            "counts": {"PASS": sum(r["status"] == "PASS" for r in tests),
                       "FAIL": len(failures), "INFO": len(gates)},
            "failures": failures, "gates": gates,
            "tests": [{"test_name": r["name"], "status": r["status"],
                       "detail": r["detail"]} for r in tests]}
