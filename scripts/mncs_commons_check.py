#!/usr/bin/env python3
"""Owner-native mesh check for the MNCS-Commons family boundary.

Runs the deterministic mesh test scope (the offline-first
content-addressed Commons Mesh surface this pressure campaign grows:
evidence, node, rights, security, storage) and writes one
mncs.check-result/1 document. Exit 0 always carries the verdict file;
a FAIL verdict is data, never a crash.

Scope is deliberately the deterministic mesh unit scope, not the full
suite: ``test_mesh_interop.py`` shells out to the ``mncs`` toolchain
per kernel (tens of minutes) and stays in this repo's own CI with the
whole ``pytest -q`` matrix plus the example/compat validators. The
boundary declaration in the caller workflow says exactly this.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from pathlib import Path

RESULT_SCHEMA = "mncs.check-result/1"
CHECK_ID = "commons-mesh-tests"
PROVIDER = "mncs-commons-pytest"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--revision", default="working-tree")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    # Deterministic unit scope only, including the always-on law-parity
    # tests that bind the Python mirrors to the normative MNCS kernels
    # (test_mesh_interest_full, test_mesh_lifecycle). test_mesh_interop.py
    # is toolchain-latency-bound and runs in the dedicated interop lane
    # plus this repository's own CI instead.
    targets = sorted(
        path
        for path in glob.glob("tests/test_mesh_*.py", root_dir=repo)
        if Path(path).name != "test_mesh_interop.py"
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q"],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo,
        timeout=1800,
    )
    verdict = "PASS" if completed.returncode == 0 else "FAIL"
    tail = (completed.stdout + completed.stderr)[-800:]
    last = tail.strip().splitlines()[-1] if tail.strip() else "no output"
    result = {
        "schema_version": RESULT_SCHEMA,
        "id": CHECK_ID,
        "provider": PROVIDER,
        "verdict": verdict,
        "summary": f"pytest {len(targets)} mesh scopes exit={completed.returncode}: {last}",
        "subject": {"repository": "MNCS-Commons", "revision": args.revision},
    }
    destination = Path(args.result_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"id": CHECK_ID, "verdict": verdict}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
