"""Case files: an append-only ledger of an investigation.

A case is a directory holding case.json (metadata), ledger.jsonl (append-only
event journal — the receipts), and evidence files at prescribed paths. State
is derived by replaying the ledger; nothing is edited in place.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .evidence import Evidence, sha256_of, validate_vocab

CASE_FILE = "case.json"
LEDGER_FILE = "ledger.jsonl"


class CaseError(Exception):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Case:
    root: Path
    meta: dict

    @classmethod
    def init(cls, root: Path, meta: dict) -> "Case":
        root = Path(root)
        if (root / CASE_FILE).exists():
            raise CaseError(f"{root} already contains a case")
        root.mkdir(parents=True, exist_ok=True)
        meta = {**meta, "schema_version": 1, "created_at": utcnow()}
        (root / CASE_FILE).write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        case = cls(root=root, meta=meta)
        case.append({"event": "case_opened", **meta})
        return case

    @classmethod
    def find(cls, start: Path) -> "Case":
        start = Path(start).resolve()
        for candidate in (start, *start.parents):
            if (candidate / CASE_FILE).exists():
                meta = json.loads(
                    (candidate / CASE_FILE).read_text(encoding="utf-8"))
                return cls(root=candidate, meta=meta)
        raise CaseError(f"no {CASE_FILE} found from {start} upward")

    def append(self, event: dict) -> dict:
        event = {"seq": self._next_seq(), "at": utcnow(), **event}
        with (self.root / LEDGER_FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def events(self) -> list[dict]:
        path = self.root / LEDGER_FILE
        if not path.exists():
            return []
        return [json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def _next_seq(self) -> int:
        events = self.events()
        return (events[-1]["seq"] + 1) if events else 1

    def register_evidence(self, path: Path, *, kind: str, transport: str,
                          environment: str, runner: str,
                          captured_at: str = "", notes: str = "") -> Evidence:
        validate_vocab(kind=kind, transport=transport, environment=environment)
        path = Path(path).resolve()
        try:
            rel = path.relative_to(self.root.resolve())
        except ValueError:
            raise CaseError(
                f"{path} is not inside the case directory {self.root}; "
                "save captures at prescribed paths inside the case") from None
        n = sum(1 for e in self.events()
                if e["event"] == "evidence_registered") + 1
        ev = Evidence(
            artifact_id=f"ev-{n:04d}", path=rel.as_posix(),
            sha256=sha256_of(path), kind=kind,
            engine=self.meta.get("engine", ""), transport=transport,
            environment=environment, runner=runner,
            captured_at=captured_at, registered_at=utcnow(), notes=notes)
        self.append(ev.to_event())
        return ev

    def evidence(self) -> list[Evidence]:
        return [Evidence.from_event(e) for e in self.events()
                if e["event"] == "evidence_registered"]

    def get_evidence(self, artifact_id: str) -> Evidence:
        for ev in self.evidence():
            if ev.artifact_id == artifact_id:
                return ev
        raise CaseError(f"no evidence with id {artifact_id}")
