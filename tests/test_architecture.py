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
    debug["shadow"]["survivor"] = "mncs_debug/analysis.py"
    result = validate_architecture_model(value)
    assert not result["valid"]
    assert any("survivor contradicts" in error for error in result["errors"])


def test_validator_rejects_achieved_shadow_that_is_still_active():
    value = json.loads((ROOT / "family/architecture-model-v1.json").read_text())
    actions = next(item for item in value["capabilities"] if item["id"] == "actions.family-verification")
    actions["shadow"]["parity_state"] = "achieved"
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
