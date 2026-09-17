from __future__ import annotations

import copy
import json
from pathlib import Path

from mncs_commons.verification_plan import plan_identity, validate_plan


ROOT = Path(__file__).resolve().parents[1]


def _plan() -> dict:
    value = json.loads(
        (ROOT / "tests/fixtures/verification-plan-corpus.json").read_text(
            encoding="utf-8"
        )
    )
    value = value["valid_plan"]
    assert isinstance(value, dict)
    value["plan_id"] = plan_identity(value)
    return value


def test_identity_metadata_closes_the_real_contract_set() -> None:
    metadata = json.loads(
        (ROOT / "family/native-contract-identity-v1.json").read_text(encoding="utf-8")
    )
    assert metadata["fullExternalContractIdentity"]["status"] == "closed"
    assert "mncs.verification-plan/1" in metadata["contracts"]
    assert "mncs.test-result/1" in metadata["contracts"]
    assert "mncs.check-result/1" in metadata["contracts"]


def test_semantic_tampering_rotates_plan_identity() -> None:
    base = _plan()
    for path in (
        ("source", "sha256"),
        ("impact", "graph_identity"),
        ("selection", "selected_test_identities"),
        ("proof", "required_evidence"),
        ("provenance", "policy"),
    ):
        mutated = copy.deepcopy(base)
        parent = mutated
        for key in path[:-1]:
            parent = parent[key]
        key = path[-1]
        if isinstance(parent[key], list):
            parent[key] = list(parent[key]) + ["phase-v-tamper"]
        elif isinstance(parent[key], bool):
            parent[key] = not parent[key]
        else:
            parent[key] = str(parent[key]) + "-tamper"
        assert plan_identity(mutated) != base["plan_id"], path


def test_declared_nonsemantic_extension_is_stable_and_readable() -> None:
    base = _plan()
    extended = copy.deepcopy(base)
    extended["presentation_extension"] = {"label": "human-facing"}
    assert plan_identity(extended) == base["plan_id"]
    validated = validate_plan(extended)
    assert validated["presentation_extension"] == {"label": "human-facing"}
