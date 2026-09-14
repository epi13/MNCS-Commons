from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


PROJECTS = Path(__file__).resolve().parents[2]
CORPUS = Path(__file__).resolve().parent / "fixtures" / "verification-plan-corpus.json"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load consumer adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _consumers() -> list[tuple[str, ModuleType]]:
    paths = {
        "ravel": PROJECTS / "RAVEL/src/ravel/family_contract.py",
        "mncs-test": PROJECTS / "mncs-test/tools/family_contract.py",
        "mncs-actions": PROJECTS / "mncs-actions/lib/mncs_family_contract.py",
        "mncs-forge-mcp": PROJECTS / "mncs-forge-mcp/src/mncs_forge/verification_plan_contract.py",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        pytest.skip("cross-consumer adapters unavailable: " + ", ".join(missing))
    return [(name, _load(f"contract_consumer_{name.replace('-', '_')}", path)) for name, path in paths.items()]


def _materialize(value: dict) -> dict:
    from mncs_commons.verification_plan import plan_identity

    result = copy.deepcopy(value)
    result["plan_id"] = plan_identity(result)
    return result


def _mutate(plan: dict, kind: str, tmp_path: Path) -> tuple[dict, dict[str, object]]:
    value = copy.deepcopy(plan)
    kwargs: dict[str, object] = {}
    if kind == "malformed_identity":
        value["plan_id"] = "Z" * 64
    elif kind == "altered_plan_identity":
        value["plan_id"] = "0" * 64
    elif kind == "unknown_level":
        value["selection"]["level"] = "unknown"
        value = _materialize(value)
    elif kind == "unknown_reason":
        value["selection"]["escalation_reasons"] = ["debug_guess"]
        value = _materialize(value)
    elif kind == "incomplete_impact":
        value["impact"]["complete"] = False
        value = _materialize(value)
    elif kind == "stale_source_binding":
        source = tmp_path / "source.mncs"
        source.write_text("current", encoding="utf-8")
        value["source"]["path"] = str(source)
        value["source"]["sha256"] = "0" * 64
        value = _materialize(value)
        kwargs = {"source_path": source, "plan_path": tmp_path / "plan.json"}
    elif kind == "inventory_mismatch":
        value["selection"]["selected_test_identities"] = ["mncs:test-case:missing"]
        value = _materialize(value)
        kwargs = {"inventory_test_identities": ["mncs:test-case:one"]}
    elif kind == "unsupported_schema":
        value["schema_version"] = "mncs.verification-plan/99"
        value["plan_id"] = "0" * 64
    else:  # pragma: no cover - corpus is intentionally closed
        raise AssertionError(kind)
    return value, kwargs


def test_identical_verification_plan_corpus_has_one_disposition_across_consumers(tmp_path: Path) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    base = _materialize(corpus["valid_plan"])
    consumers = _consumers()

    for name, module in consumers:
        assert module.validate_plan(base) == base, name

    for mutation in corpus["mutations"]:
        value, kwargs = _mutate(base, mutation["kind"], tmp_path)
        dispositions: dict[str, str] = {}
        for name, module in consumers:
            with pytest.raises(ValueError) as error:
                module.validate_plan(value, **kwargs)
            dispositions[name] = getattr(error.value, "code", "ValueError")
        assert set(dispositions.values()) == {mutation["error"]}, (
            mutation["name"],
            dispositions,
        )
