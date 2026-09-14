from __future__ import annotations

import hashlib

import pytest

from mncs_commons.verification_plan import (
    PLAN_SCHEMA,
    PLAN_ID_ALGORITHM,
    VerificationPlanError,
    plan_identity,
    validate_plan,
)


def _plan() -> dict:
    value = {
        "schema_version": PLAN_SCHEMA,
        "source": {"path": "/workspace/source.mncs", "sha256": "a" * 64},
        "impact": {
            "graph_identity": "b" * 64,
            "roots": ["mncs:function:changed"],
            "affected_count": 1,
            "direct_dependents": [],
            "test_identities": ["mncs:test:one"],
            "risk_flags": [],
            "complete": True,
            "limitations": [],
            "cross_repository": {
                "graph_identity": "c" * 64,
                "edges": [],
                "selected_repositories": [],
                "complete": True,
                "limitations": [],
            },
        },
        "selection": {
            "level": "changed_item",
            "selected_test_identities": ["mncs:test:one"],
            "available_test_count": 1,
            "escalation_reasons": [],
            "selected_repositories": [],
            "available_repository_count": 0,
        },
        "proof": {
            "sufficient_to_stop": True,
            "required_evidence": ["selected_test_cases_pass"],
            "boundary": {
                "claimed_scope": "changed_item",
                "established": True,
                "executor": "mncs-test",
                "stop_condition": "selected_test_cases_pass",
            },
        },
        "provenance": {"provider": "test", "policy": "fixture"},
    }
    value["plan_id"] = plan_identity(value)
    return value


def test_canonical_identity_is_lowercase_sha256_and_stable() -> None:
    plan = _plan()
    assert plan["plan_id"] == hashlib.sha256(
        __import__("mncs_commons.verification_plan", fromlist=["canonical_plan_bytes"]).canonical_plan_bytes(plan)
    ).hexdigest()
    assert PLAN_ID_ALGORITHM.startswith("sha256(")
    assert validate_plan(plan)["plan_id"] == plan["plan_id"]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda p: p.update(plan_id="Z" * 64), "IDENTITY_INVALID"),
        (lambda p: p["selection"].update(level="unknown"), "IDENTITY_MISMATCH"),
        (lambda p: p["selection"].update(escalation_reasons=["debug_guess"]), "IDENTITY_MISMATCH"),
        (lambda p: p["impact"].update(complete=False), "IDENTITY_MISMATCH"),
    ],
)
def test_mutations_fail_closed_even_before_semantic_disposition(mutation, code: str) -> None:
    plan = _plan()
    mutation(plan)
    with pytest.raises(VerificationPlanError) as error:
        validate_plan(plan)
    assert error.value.code == code


def test_mutated_plan_can_be_reidentified_then_rejected_for_unknown_vocab() -> None:
    plan = _plan()
    plan["selection"]["level"] = "unknown"
    plan["plan_id"] = plan_identity(plan)
    with pytest.raises(VerificationPlanError) as error:
        validate_plan(plan)
    assert error.value.code == "VOCABULARY_UNKNOWN"


def test_stale_source_and_inventory_mismatch_are_common_dispositions(tmp_path) -> None:
    source = tmp_path / "source.mncs"
    source.write_text("current", encoding="utf-8")
    plan = _plan()
    plan["source"]["path"] = str(source)
    plan["source"]["sha256"] = "0" * 64
    plan["plan_id"] = plan_identity(plan)
    with pytest.raises(VerificationPlanError) as error:
        validate_plan(plan, source_path=source, plan_path=tmp_path / "plan.json")
    assert error.value.code == "SOURCE_STALE"

    plan = _plan()
    plan["selection"]["selected_test_identities"] = ["mncs:test:missing"]
    plan["plan_id"] = plan_identity(plan)
    with pytest.raises(VerificationPlanError) as error:
        validate_plan(plan, inventory_test_identities=["mncs:test:one"])
    assert error.value.code == "INVENTORY_MISMATCH"
