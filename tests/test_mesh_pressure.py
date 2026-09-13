"""Always-on mirror checks for the MNCS-native pressure lifecycle kernel."""

from __future__ import annotations

import json
from pathlib import Path

from mncs_commons.pressure import _resolution_ready, _validate_transition_shape

CORPUS = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "mncs_commons"
    / "mesh"
    / "mncs"
    / "corpora"
    / "pressure-lifecycle-corpus.json"
)


def _integer(argument: dict) -> int:
    return int(argument["integer"]["value"])


def _boolean(argument: dict) -> bool:
    return bool(argument["boolean"]["value"])


def test_pressure_corpus_is_complete_and_mirror_agrees() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(corpus["cases"]) == 13
    states = [
        "discovered",
        "confirmed",
        "accepted",
        "implementing",
        "available",
        "verifying",
        "resolved",
        "duplicate",
        "rejected",
        "superseded",
        "deferred",
        "obsolete",
    ]
    seen: set[str] = set()
    for case in corpus["cases"]:
        assert case["id"] not in seen
        seen.add(case["id"])
        function = case["request"]["target"]["function"]
        arguments = case["request"]["arguments"]
        if function == "transition_allowed":
            current = _integer(arguments[0])
            target = _integer(arguments[1])
            expected = (
                target < len(states)
                and current < len(states)
                and _validate_transition_shape(states[current], states[target]) is None
            )
        elif function == "unresolved":
            current = _integer(arguments[0])
            expected = states[current] not in {
                "resolved",
                "duplicate",
                "rejected",
                "superseded",
                "obsolete",
            }
        elif function == "resolution_ready":
            expected = _resolution_ready(*[_integer(argument) for argument in arguments])
        else:
            raise AssertionError(f"unknown pressure kernel function: {function}")
        assert _boolean(case["expected"][0]) == expected, case["id"]


def test_pressure_source_is_the_normative_kernel() -> None:
    source = CORPUS.parent.parent / "commons" / "pressure" / "lifecycle.mncs"
    text = source.read_text(encoding="utf-8")
    assert "module commons.pressure.lifecycle;" in text
    assert "fn transition_allowed" in text
    assert "fn unresolved" in text
    assert "fn resolution_ready" in text
    assert "host owns JSON" in text
