import json
from pathlib import Path

from mncs_commons.architecture import architecture_query, load_architecture_model, validate_architecture_model


ROOT = Path(__file__).resolve().parents[1]


def test_architecture_model_is_valid():
    result = validate_architecture_model(load_architecture_model(ROOT), workspace_root=ROOT)
    assert result["valid"], result
    assert result["capability_count"] >= 8


def test_validator_rejects_unjustified_parallel_implementation():
    value = json.loads((ROOT / "family/architecture-model-v1.json").read_text())
    value["capabilities"][0]["active_alternates"] = [
        {"path": "native/example/v2.mncs", "role": "implementation"}
    ]
    result = validate_architecture_model(value)
    assert not result["valid"]
    assert any("multiple active implementations" in error for error in result["errors"])


def test_validator_rejects_survivor_direction_contradiction():
    value = json.loads((ROOT / "family/architecture-model-v1.json").read_text())
    debug = next(item for item in value["capabilities"] if item["id"] == "debug.decision-policy")
    # The current model has retired the Debug shadow.  Exercise the validator's
    # legacy convergence rule with an explicitly injected, malformed record.
    debug["shadow"] = {
        "path": "mncs_debug/analysis.py",
        "supersedes": "legacy semantic policy",
        "parity_event": "legacy parity",
        "retirement_condition": "legacy removal",
        "survivor": "mncs_debug/analysis.py",
        "retirement_direction": "canonical_survivor",
        "parity_state": "pending",
        "retirement_state": "active",
    }
    result = validate_architecture_model(value)
    assert not result["valid"]
    assert any("survivor contradicts" in error for error in result["errors"])


def test_validator_rejects_achieved_shadow_that_is_still_active():
    value = json.loads((ROOT / "family/architecture-model-v1.json").read_text())
    actions = next(item for item in value["capabilities"] if item["id"] == "actions.family-verification")
    # The current model has retired the Actions shadow.  Keep the test as a
    # guard for malformed legacy records without reintroducing a live shadow.
    actions["shadow"] = {
        "path": "scripts/selective_family_verify.py",
        "supersedes": "legacy semantic policy",
        "parity_event": "legacy parity",
        "retirement_condition": "legacy removal",
        "survivor": "native/mncs/actions/family.mncs",
        "retirement_direction": "canonical_survivor",
        "parity_state": "achieved",
        "retirement_state": "active",
    }
    result = validate_architecture_model(value)
    assert not result["valid"]
    assert any("parity is achieved" in error for error in result["errors"])


def test_validator_rejects_adapter_as_canonical_evidence():
    value = json.loads((ROOT / "family/architecture-model-v1.json").read_text())
    policy = next(item for item in value["capabilities"] if item["id"] == "ravel.verification-policy")
    policy["evidence"] = [{"path": "src/ravel/impact.py", "role": "semantic_authority"}]
    result = validate_architecture_model(value)
    assert not result["valid"]
    assert any("does not identify the canonical implementation" in error for error in result["errors"])


def test_validator_rejects_missing_active_alternate():
    value = json.loads((ROOT / "family/architecture-model-v1.json").read_text())
    value["capabilities"][0]["active_alternates"] = [{"path": "missing/native.mncs", "role": "shadow"}]
    result = validate_architecture_model(value, workspace_root=ROOT)
    assert not result["valid"]
    assert any("active alternate path does not exist" in error for error in result["errors"])


def test_architecture_queries_are_progressive_and_content_addressed():
    value = load_architecture_model(ROOT)
    targeted = architecture_query(value, "capability", "ravel.verification-policy")
    full = architecture_query(value, "changes", "unknown-identity")
    unchanged = architecture_query(value, "changes", value["content_identity"])
    assert targeted["projection"]["mode"] == "targeted"
    assert full["projection"]["mode"] == "full"
    assert len(json.dumps(full)) > len(json.dumps(targeted))
    assert unchanged["projection"]["mode"] == "unchanged"
    assert unchanged["projection"]["counts"]["capabilities"] == 0


def test_architecture_queries_return_retained_identity_delta():
    value = load_architecture_model(ROOT)
    delta = architecture_query(
        value,
        "changes",
        "sha256:28e2626037aad47f5f4cd14e8f4d7ecdbc8efca07fe8c46916aeedf35321f7ac",
    )
    assert delta["projection"]["mode"] == "delta"
    assert delta["delta"]["from"].startswith("sha256:")
    assert delta["delta"]["chain"][-1]["current_content_identity"] == value["content_identity"]
