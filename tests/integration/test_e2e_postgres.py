import json
import shutil
import subprocess
from pathlib import Path

import pytest

from queryreceipts.cli import main

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "pgfleet"

PGFLEET_RUNNER = ("docker cp {sql} pgfleet:/tmp/r.sql >/dev/null && "
                  "docker exec pgfleet psql -X -q -U postgres -d fleetdb "
                  "-f /tmp/r.sql")


@pytest.fixture(scope="session")
def pgfleet():
    try:
        r = subprocess.run(
            ["docker", "exec", "pgfleet", "psql", "-U", "postgres",
             "-d", "fleetdb", "-c", "SELECT 1"],
            capture_output=True, timeout=30)
        if r.returncode != 0:
            pytest.skip("pgfleet container not reachable — "
                        "run scripts/pgfleet_up.sh")
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("docker not available")


def test_full_pg_loop_yields_proven_certificate(pgfleet, tmp_path, capsys):
    """The entire cure loop on Postgres, driven by the driver transport
    (`receipts run`) — engine pack #2 proving the pack abstraction."""
    root = tmp_path / "pgfleet-case"
    assert main(["init", str(root), "--engine", "postgres",
                 "--database", "fleetdb", "--symptom", "report slow",
                 "--runner-cmd", PGFLEET_RUNNER]) == 0
    shutil.copyfile(EXAMPLES / "original.sql", root / "original.sql")
    (root / "optimized").mkdir()
    shutil.copyfile(EXAMPLES / "optimized_v1.sql",
                    root / "optimized" / "optimized_v1.sql")

    # diagnostics
    assert main(["prescribe", "diagnostics", "--case", str(root)]) == 0
    assert main(["run", "prescriptions/diagnostics.sql",
                 "--environment", "synthetic", "--case", str(root)]) == 0
    capsys.readouterr()
    assert main(["parse", "ev-0001", "--case", str(root),
                 "--section", "baseline"]) == 0
    assert "execution" in capsys.readouterr().out

    # validation (CTE rewrite through the inject-style template)
    assert main(["prescribe", "validation",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--natural-key", "res_id", "--case", str(root)]) == 0
    assert main(["run", "prescriptions/validation_v1.sql",
                 "--environment", "synthetic", "--case", str(root)]) == 0
    assert main(["grade", "ev-0002", "--case", str(root)]) == 0
    assert "PROVEN" in capsys.readouterr().out

    # benchmark — pinned protocol: run twice, second run counts
    assert main(["prescribe", "benchmark",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--case", str(root)]) == 0
    assert main(["run", "prescriptions/benchmark_v1.sql",
                 "--environment", "synthetic", "--case", str(root)]) == 0
    assert main(["run", "prescriptions/benchmark_v1.sql",
                 "--environment", "synthetic", "--case", str(root)]) == 0
    capsys.readouterr()

    # certify against the SECOND benchmark capture (ev-0004)
    assert main(["certify", "--validation", "ev-0002",
                 "--benchmark", "ev-0004",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--case", str(root)]) == 0
    assert "PROVEN" in capsys.readouterr().out

    cert = json.loads(
        (root / "certificates" / "certificate_0001.json").read_text())
    assert cert["verdict"] == "PROVEN"
    assert cert["benchmark"]["improvement"]["elapsed_pct"] > 30
    assert cert["gates"]["gate:database"] == "fleetdb"
