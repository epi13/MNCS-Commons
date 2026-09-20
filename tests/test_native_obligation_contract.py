from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_ROOT = ROOT.parent / "mncs-language"


def test_native_obligation_contract_laws_are_executable() -> None:
    mncs = Path(os.environ.get("MNCS_BINARY", LANGUAGE_ROOT / "target/debug/mncs"))
    environment = dict(os.environ)
    environment["MNCS_LIBRARY_PATH"] = ":".join(
        [str(LANGUAGE_ROOT / "library"), str(ROOT / "src/mncs_commons/mesh")]
    )
    completed = subprocess.run(
        [
            str(mncs),
            "call",
            str(ROOT / "tests/fixtures/native-obligation-contract-probe.mncs"),
            "--module",
            "tests.native_obligation_contract_probe",
            "--function",
            "all",
            "--args-json",
            "[]",
            "--library",
            str(LANGUAGE_ROOT / "library"),
            "--library",
            str(ROOT / "src/mncs_commons/mesh"),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    report = json.loads(completed.stdout)
    fields = dict(report["call"]["returned"][0]["record"]["fields"])
    assert fields == {
        "active": {"boolean": {"value": True}},
        "reference_only_excluded": {"boolean": {"value": True}},
        "new_execution_required": {"boolean": {"value": True}},
        "native_test_executor": {"boolean": {"value": True}},
    }
