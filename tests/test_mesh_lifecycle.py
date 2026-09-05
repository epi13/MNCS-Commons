"""Lifecycle transition law: the MNCS kernel owns it, Python agrees with it.

The normative law lives in
``src/mncs_commons/mesh/mncs/commons/mesh/lifecycle.mncs``; the checked-in
``commons-lifecycle-corpus.json`` pins its truth table. These always-on
tests bind the Python runtime (``mncs_commons.lifecycle``) to the same
contract without needing the toolchain: discriminant order, per-case
mask parity, and validity agreement. Backend execution of the same
corpus is covered by ``test_mesh_interop.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mncs_commons.lifecycle import _ALLOWED, validate_transition
from mncs_commons.models import LifecycleState

CORPUS = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "mncs_commons"
    / "mesh"
    / "mncs"
    / "corpora"
    / "commons-lifecycle-corpus.json"
)

STATES = [item.value for item in LifecycleState]

MASK_BY_CODE = {
    "UNKNOWN_CURRENT_STATE": 1,
    "UNKNOWN_TARGET_STATE": 2,
    "FORBIDDEN_TRANSITION": 4,
    "STALE_TRANSITION": 8,
    "AUTHORITY_DOMAIN_REQUIRED": 16,
}


def _load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_lifecycle_discriminants_follow_enum_order():
    """Kernel discriminants 0-8 are LifecycleState declaration order."""

    assert STATES == [
        "proposed",
        "reproduced",
        "verified",
        "accepted",
        "disputed",
        "superseded",
        "expired",
        "rejected",
        "withdrawn",
    ]
    assert set(_ALLOWED) == set(STATES)


def _mask_of(report) -> int:
    mask = 0
    for item in report.diagnostics:
        mask |= MASK_BY_CODE[item.code]
    return mask


def _name(index: int) -> str:
    if 0 <= index <= 8:
        return STATES[index]
    return "nope-not-a-state"


def test_python_runtime_agrees_with_lifecycle_corpus():
    corpus = _load_corpus()
    assert len(corpus["cases"]) == 484
    for case in corpus["cases"]:
        request = case["request"]
        function = request["target"]["function"]
        expected = case["expected"][0]
        if function == "transition_allowed":
            current = int(request["arguments"][0]["integer"]["value"])
            target = int(request["arguments"][1]["integer"]["value"])
            allowed = _name(current) in _ALLOWED and _name(target) in _ALLOWED.get(
                _name(current), frozenset()
            )
            assert bool(expected["boolean"]["value"]) == allowed, case["id"]
        elif function == "transition_check":
            current = int(request["arguments"][0]["integer"]["value"])
            target = int(request["arguments"][1]["integer"]["value"])
            from_matches = bool(request["arguments"][2]["boolean"]["value"])
            authority_ok = bool(request["arguments"][3]["boolean"]["value"])
            current_name = _name(current)
            event = {
                "transition": {
                    "from": current_name if from_matches else "something-else",
                    "to": _name(target),
                },
                "authority": {"domain": "d" if authority_ok else ""},
            }
            report = validate_transition(current_name, _name(target), event)
            assert int(expected["integer"]["value"]) == _mask_of(report), case["id"]
            assert (expected["integer"]["value"] == 0) == report.valid, case["id"]
        else:
            raise AssertionError(f"unknown function {function}")


def test_lifecycle_corpus_ids_are_stable():
    seen = set()
    for case in _load_corpus()["cases"]:
        assert re.fullmatch(r"(allowed|check)-(-?\d+)-(-?\d+)(-([01]{2}))?", case["id"]), case["id"]
        assert case["id"] not in seen, case["id"]
        seen.add(case["id"])
