from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_ROOT = ROOT.parent / "mncs-language"


def test_phase6_corpus_revalidates_native_external_identity_relation() -> None:
    mncs = Path(os.environ.get("MNCS_BINARY", LANGUAGE_ROOT / "target/debug/mncs"))
    environment = dict(os.environ)
    environment["MNCS_LIBRARY_PATH"] = ":".join(
        [str(LANGUAGE_ROOT / "library"), str(ROOT / "src/mncs_commons/mesh")]
    )
    completed = subprocess.run(
        ["python3", str(ROOT / "tools/contract_identity_corpus.py"), "--mncs", str(mncs)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    report = json.loads(completed.stdout)
    assert report["summary"] == {
        "case_count": 10,
        "mismatch_count": 10,
        "parity_count": 0,
    }
    assert all(not case["parity"] for case in report["cases"])
