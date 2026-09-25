"""Always-on mirror checks for the MNCS-native pressure lifecycle kernel."""

from __future__ import annotations

import json
from pathlib import Path

from mncs_commons.pressure import (
    _native_available_awaiting_consumer,
    _native_requires_revalidation,
    _native_resolution_ready,
    _native_transition_allowed,
    _native_unresolved,
    _native_verification_state,
)

CORPUS = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "mncs_commons"
    / "mesh"
    / "mncs"
    / "corpora"
    / "pressure-lifecycle-corpus.json"
)

PROJECTION_CORPUS = CORPUS.with_name("pressure-projection-corpus.json")


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
                _native_transition_allowed(states[current], states[target])
                if target < len(states) and current < len(states)
                else False
            )
        elif function == "unresolved":
            current = _integer(arguments[0])
            expected = _native_unresolved(current)
        elif function == "resolution_ready":
            expected = _native_resolution_ready(*[_integer(argument) for argument in arguments])
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
    assert "fn verification_state" in text
    assert "fn available_awaiting_consumer" in text
    assert "fn requires_revalidation" in text
    assert "host owns JSON" in text


def test_projection_corpus_is_complete_and_mirror_agrees() -> None:
    corpus = json.loads(PROJECTION_CORPUS.read_text(encoding="utf-8"))
    assert len(corpus["cases"]) == 11
    seen: set[str] = set()
    for case in corpus["cases"]:
        assert case["id"] not in seen
        seen.add(case["id"])
        function = case["request"]["target"]["function"]
        arguments = case["request"]["arguments"]
        if function == "verification_state":
            values = [int(argument["integer"]["value"]) for argument in arguments]
            expected = _native_verification_state(*values)
            assert int(case["expected"][0]["integer"]["value"]) == expected, case["id"]
        elif function == "available_awaiting_consumer":
            status = int(arguments[0]["integer"]["value"])
            current = bool(arguments[1]["boolean"]["value"])
            expected = _native_available_awaiting_consumer(status, current)
            assert bool(case["expected"][0]["boolean"]["value"]) == expected, case["id"]
        elif function == "requires_revalidation":
            unresolved = bool(arguments[0]["boolean"]["value"])
            current = bool(arguments[1]["boolean"]["value"])
            assert bool(case["expected"][0]["boolean"]["value"]) == _native_requires_revalidation(
                unresolved, current
            ), case["id"]
        else:
            raise AssertionError(f"unknown pressure projection function: {function}")
