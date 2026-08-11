"""Validate the controller-local node contract and the process-boundary scenario."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.application import CommonsApplication
from mncs_commons.store import CommonsStore


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    descriptor = CommonsApplication.describe(binding="python-api")
    if descriptor["profile"]["executionAuthority"] != "none":
        raise RuntimeError("local descriptor advertised execution authority")
    if "record.publish" not in descriptor["interface"]["operations"]:
        raise RuntimeError("local descriptor omitted publication")
    with tempfile.TemporaryDirectory(prefix="commons-local-agent-") as temporary:
        store_path = Path(temporary) / "store"
        initialized = subprocess.run(
            [sys.executable, "-m", "mncs_commons.cli", "local", "init", str(store_path)],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if initialized.returncode != 0 or not json.loads(initialized.stdout)["initialized"]:
            raise RuntimeError("local init did not report initialization")
        if not CommonsApplication(CommonsStore(store_path)).local_doctor()["valid"]:
            raise RuntimeError("local doctor did not pass after init")
        scenario = subprocess.run(
            [sys.executable, "scripts/validate_agent_exchange.py"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if scenario.returncode != 0:
            raise RuntimeError(scenario.stderr or scenario.stdout)
    print(json.dumps({"status": "PASS", "profile": descriptor["profile"]["version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
