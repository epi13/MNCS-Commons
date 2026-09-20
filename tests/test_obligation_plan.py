from __future__ import annotations

from mncs_commons.obligation_plan import (
    OBLIGATION_PLAN_SCHEMA,
    ObligationPlanError,
    inventory_identity,
    obligation_plan_identity,
    validate_inventory,
    validate_obligation_plan,
)


def _inventory() -> dict:
    return {
        "schema_version": "mncs-family.verification-obligation-inventory/v1",
        "repository": "fixture",
        "revision": 1,
        "obligations": [
            {
                "identity": "fixture.semantic.regression",
                "title": "native semantic regression",
                "guarantee_domain": "semantic",
                "evidence_role": "canonical_regression",
                "lifecycle": "permanent",
                "scope": "local",
                "subjects": ["fixture:function"],
                "invalidation_dependencies": ["fixture.contract/1"],
                "executor": {
                    "provider": "mncs-test",
                    "kind": "native_first_class_test",
                    "entrypoint": "mncs test",
                    "declaration_identities": ["fixture:test"],
                },
                "evidence_identity": {
                    "subject_fields": ["subject_fingerprint"],
                    "definition_fields": ["obligation_identity"],
                    "execution_fields": ["test_case_identity", "verifier_identity"],
                },
            }
        ],
    }


def test_inventory_is_identity_bound_and_orthogonal() -> None:
    normalized = validate_inventory(_inventory())
    assert inventory_identity(normalized) != ""
    assert normalized["obligations"][0]["evidence_role"] == "canonical_regression"


def test_plan_distinguishes_current_reuse_from_new_execution() -> None:
    plan = {
        "schema_version": OBLIGATION_PLAN_SCHEMA,
        "verification_plan_id": "v-plan",
        "source": {"path": "source.mncs", "sha256": "a" * 64},
        "impact_identity": "impact",
        "inventory": {"repository": "fixture", "revision": 1, "identity": "inventory"},
        "obligations": [
            {
                "identity": "fixture.semantic.regression",
                "status": "current",
                "lifecycle": "permanent",
                "guarantee_domain": "semantic",
                "evidence_role": "canonical_regression",
                "reason": "current identity-bound PASS evidence",
                "evidence_identities": ["evidence:one"],
                "test_case_identities": ["test:one"],
            }
        ],
        "evidence": [
            {
                "status": "PASS",
                "evidence_identity": "evidence:one",
                "obligation_identity": "fixture.semantic.regression",
                "subject_fingerprint": "a" * 64,
            }
        ],
        "stop": {
            "sufficient_to_stop": True,
            "required_obligation_identities": ["fixture.semantic.regression"],
            "new_execution_required": [],
            "escalation_reasons": [],
            "boundary": "changed_item",
        },
    }
    plan["obligation_plan_id"] = obligation_plan_identity(plan)
    assert validate_obligation_plan(plan)["obligation_plan_id"] == plan["obligation_plan_id"]


def test_duplicate_inventory_identity_fails_closed() -> None:
    value = _inventory()
    value["obligations"].append(dict(value["obligations"][0]))
    try:
        validate_inventory(value)
    except ObligationPlanError as error:
        assert error.code == "DUPLICATE_IDENTITY"
    else:
        raise AssertionError("duplicate obligation identity was accepted")
