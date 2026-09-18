import json
from pathlib import Path

from mncs_commons.architecture import load_architecture_model, validate_architecture_model


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
