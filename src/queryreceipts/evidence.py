"""Evidence artifacts: files with provenance.

The proof engine never trusts a bare file. Registration computes a content
hash and records who captured it, where, when, and via which transport.
Every downstream claim cites an artifact id. An empty captured_at stays
empty — unknown provenance is reported, never invented.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

KINDS = (
    "stats_io", "plan_xml", "pg_explain", "rowcounts", "index_inventory",
    "stats_inventory", "validation_results", "benchmark_results", "other",
)
TRANSPORTS = ("courier", "approve-each", "mcp", "driver", "ci")
ENVIRONMENTS = ("production", "staging", "stats-clone", "synthetic")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_vocab(*, kind: str, transport: str, environment: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if transport not in TRANSPORTS:
        raise ValueError(
            f"unknown transport {transport!r}; expected one of {TRANSPORTS}")
    if environment not in ENVIRONMENTS:
        raise ValueError(
            f"unknown environment {environment!r}; "
            f"expected one of {ENVIRONMENTS}")


@dataclass(frozen=True)
class Evidence:
    artifact_id: str
    path: str            # case-root-relative, POSIX separators
    sha256: str
    kind: str
    engine: str
    transport: str
    environment: str
    runner: str
    captured_at: str     # ISO-8601 supplied by the runner; "" if unknown
    registered_at: str   # ISO-8601 stamped at registration
    notes: str = ""

    def to_event(self) -> dict:
        return {"event": "evidence_registered", **asdict(self)}

    @classmethod
    def from_event(cls, event: dict) -> "Evidence":
        return cls(**{k: v for k, v in event.items()
                      if k in cls.__dataclass_fields__})
