import subprocess

import pytest

SQLCMD = ["docker", "exec", "fleetdb", "/opt/mssql-tools18/bin/sqlcmd",
          "-C", "-S", "localhost", "-U", "sa", "-P", "Receipts!Pr00f1",
          "-d", "FleetDB"]


def fleetdb_available() -> bool:
    try:
        r = subprocess.run([*SQLCMD, "-Q", "SELECT 1"],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def fleetdb():
    if not fleetdb_available():
        pytest.skip("fleetdb container not reachable — "
                    "run scripts/fleetdb_up.sh")
    return run_sql


def run_sql(sql_path, out_path=None, timeout=600):
    """Copy a SQL file into the container, run it, return stdout
    (optionally also saving it to out_path)."""
    subprocess.run(["docker", "cp", str(sql_path), "fleetdb:/tmp/run.sql"],
                   check=True, capture_output=True)
    r = subprocess.run([*SQLCMD, "-i", "/tmp/run.sql"],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"sqlcmd failed: {r.stdout}\n{r.stderr}")
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(r.stdout, encoding="utf-8")
    return r.stdout
