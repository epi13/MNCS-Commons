from __future__ import annotations

import copy
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
        "mismatch_count": 0,
        "parity_count": 10,
    }
    assert all(case["parity"] for case in report["cases"])


def test_native_identity_rotates_when_contract_semantics_change() -> None:
    from tools.contract_identity_corpus import build_corpus, call_native

    mncs = Path(os.environ.get("MNCS_BINARY", LANGUAGE_ROOT / "target/debug/mncs"))
    host_fields, _, _ = build_corpus()
    base_args = {"record": {"type": "ContractIdentityCorpus", "fields": host_fields}}
    base = call_native(mncs, base_args)

    mutated_fields = copy.deepcopy(host_fields)
    verdict = mutated_fields["test_result"]["record"]["fields"]["verdict"]["finite"]
    verdict["variant"] = "FAIL"
    mutated = call_native(
        mncs,
        {"record": {"type": "ContractIdentityCorpus", "fields": mutated_fields}},
    )

    assert mutated["test_result"] != base["test_result"]
    assert mutated["check_result"] == base["check_result"]


def test_nonsemantic_plan_extensions_do_not_rotate_identity() -> None:
    from tools.contract_identity_corpus import build_corpus, external_identity

    _, corpus, _ = build_corpus()
    base = external_identity("verification_plan", corpus["verification_plan"])
    extended = copy.deepcopy(corpus["verification_plan"])
    extended["presentation_extension"] = {"note": "changed transport annotation"}
    extended["diagnostic_annotations"] = ["different diagnostic wording"]

    assert external_identity("verification_plan", extended) == base
