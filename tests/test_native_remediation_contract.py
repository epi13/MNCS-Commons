from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_ROOT = ROOT.parent / "mncs-language"


def _decode_bytes(value) -> str:
    return bytes(item["byte"]["value"] for item in value["sequence"]["values"]).decode()


def test_native_remediation_contract_laws_are_executable() -> None:
    mncs = Path(os.environ.get("MNCS_BINARY", LANGUAGE_ROOT / "target/debug/mncs"))
    if not mncs.is_file():
        mncs = LANGUAGE_ROOT / "target/release/mncs"
    environment = dict(os.environ)
    environment["MNCS_LIBRARY_PATH"] = ":".join(
        [str(LANGUAGE_ROOT / "library"), str(ROOT / "src/mncs_commons/mesh")]
    )
    completed = subprocess.run(
        [
            str(mncs),
            "call",
            str(ROOT / "tests/fixtures/native-remediation-contract-probe.mncs"),
            "--module",
            "tests.native_remediation_contract_probe",
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
    assert fields["classify_ok"] == {"boolean": {"value": True}}
    assert fields["stop_ok"] == {"boolean": {"value": True}}
    assert fields["residual_ok"] == {"boolean": {"value": True}}
    assert fields["retry_ok"] == {"boolean": {"value": True}}
    assert _decode_bytes(fields["envelope_schema"]) == "mncs.remediation/1"
    assert _decode_bytes(fields["evidence_schema"]) == "mncs.remediation-evidence/1"


def test_remediation_policy_defaults_are_sane() -> None:
    policy = json.loads((ROOT / "family/remediation-policy-v1.json").read_text())
    assert policy["schema_version"] == "mncs.remediation-policy/1"
    assert policy["contract"] == "mncs.remediation/1"
    base = policy["retry"]["base_delay_secs"]
    cap = policy["retry"]["max_delay_secs"]
    assert isinstance(base, int) and isinstance(cap, int)
    assert 0 < base <= cap <= 4294967295
