import json
import shutil
from pathlib import Path

import pytest

from queryreceipts.cli import main

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "fleetdb"


def test_full_cure_loop_yields_proven_certificate(fleetdb, tmp_path, capsys):
    root = tmp_path / "fleetdb-case"
    # 1. open the case
    assert main(["init", str(root), "--engine", "sqlserver",
                 "--database", "FleetDB",
                 "--symptom", "extract slow, high reads"]) == 0
    shutil.copyfile(EXAMPLES / "original.sql", root / "original.sql")
    (root / "optimized").mkdir()
    shutil.copyfile(EXAMPLES / "optimized_v1.sql",
                    root / "optimized" / "optimized_v1.sql")

    # 2. diagnostics: prescribe -> run -> register -> parse
    assert main(["prescribe", "diagnostics", "--case", str(root)]) == 0
    cap = root / "runs" / "baseline" / "diagnostics.txt"
    fleetdb(root / "prescriptions" / "diagnostics.sql", cap)
    assert main(["add", str(cap), "--kind", "stats_io",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    assert main(["parse", "ev-0001", "--case", str(root),
                 "--section", "baseline_io_time"]) == 0
    capsys.readouterr()

    # 3. validation: prescribe -> run -> register -> grade
    assert main(["prescribe", "validation",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--natural-key", "RES_ID", "--case", str(root)]) == 0
    vres = root / "validation" / "v1_results.txt"
    fleetdb(root / "prescriptions" / "validation_v1.sql", vres)
    assert main(["add", str(vres), "--kind", "validation_results",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    assert main(["grade", "ev-0002", "--case", str(root)]) == 0
    assert "PROVEN" in capsys.readouterr().out

    # 4. benchmark: prescribe -> run twice (pinned protocol) -> register
    assert main(["prescribe", "benchmark",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--case", str(root)]) == 0
    bres = root / "benchmarks" / "v1_results.txt"
    fleetdb(root / "prescriptions" / "benchmark_v1.sql")        # warm-up run
    fleetdb(root / "prescriptions" / "benchmark_v1.sql", bres)  # measured run
    assert main(["add", str(bres), "--kind", "benchmark_results",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    capsys.readouterr()

    # 5. certify
    assert main(["certify", "--validation", "ev-0002",
                 "--benchmark", "ev-0003",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--case", str(root)]) == 0
    out = capsys.readouterr().out
    assert "PROVEN" in out

    cert = json.loads(
        (root / "certificates" / "certificate_0001.json").read_text())
    assert cert["verdict"] == "PROVEN"
    assert cert["benchmark"]["improvement"]["reads_pct"] > 30
    assert cert["gates"]["gate:database"] == "FleetDB"


FLEETDB_RUNNER = ("docker cp {sql} fleetdb:/tmp/r.sql >/dev/null && "
                  "docker exec fleetdb /opt/mssql-tools18/bin/sqlcmd -C "
                  "-S localhost -U sa -P 'Receipts!Pr00f1' -d FleetDB "
                  "-i /tmp/r.sql")


def test_driver_transport_runs_prescription_itself(fleetdb, tmp_path,
                                                   capsys):
    """`receipts run` with a runner command — no human courier."""
    root = tmp_path / "fleetdb-driver-case"
    assert main(["init", str(root), "--engine", "sqlserver",
                 "--database", "FleetDB", "--symptom", "slow",
                 "--runner-cmd", FLEETDB_RUNNER]) == 0
    shutil.copyfile(EXAMPLES / "original.sql", root / "original.sql")
    assert main(["prescribe", "diagnostics", "--case", str(root)]) == 0
    assert main(["run", "prescriptions/diagnostics.sql",
                 "--environment", "synthetic", "--case", str(root)]) == 0
    capsys.readouterr()
    assert main(["parse", "ev-0001", "--case", str(root),
                 "--section", "baseline_io_time"]) == 0
    out = capsys.readouterr().out
    assert "RESERVATION" in out
    from queryreceipts.case import Case
    ev = Case.find(root).get_evidence("ev-0001")
    assert ev.transport == "driver"
    assert ev.runner == "docker"


def test_cte_rewrite_validates_proven(fleetdb, tmp_path, capsys):
    """A WITH-headed rewrite must pass through the general
    materialization path — the limitation the first e2e run exposed."""
    root = tmp_path / "fleetdb-cte-case"
    assert main(["init", str(root), "--engine", "sqlserver",
                 "--database", "FleetDB", "--symptom", "slow"]) == 0
    shutil.copyfile(EXAMPLES / "original.sql", root / "original.sql")
    (root / "optimized").mkdir()
    shutil.copyfile(EXAMPLES / "optimized_v1_cte.sql",
                    root / "optimized" / "optimized_v1.sql")

    assert main(["prescribe", "validation",
                 "--rewrite", "optimized/optimized_v1.sql",
                 "--natural-key", "RES_ID", "--case", str(root)]) == 0
    vres = root / "validation" / "v1_results.txt"
    fleetdb(root / "prescriptions" / "validation_v1.sql", vres)
    assert main(["add", str(vres), "--kind", "validation_results",
                 "--transport", "driver", "--environment", "synthetic",
                 "--runner", "e2e", "--case", str(root)]) == 0
    assert main(["grade", "ev-0001", "--case", str(root)]) == 0
    assert "PROVEN" in capsys.readouterr().out
