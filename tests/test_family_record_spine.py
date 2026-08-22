from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mncs_commons.application import CommonsApplication
from mncs_commons.family import (
    FamilyRecordError,
    make_concept_experiment_record,
    make_failure_classification_record,
    producer_reference,
)
from mncs_commons.query import QueryFilter
from mncs_commons.store import CommonsStore, StoreError
from mncs_commons.validation import validate_record


def ref(
    producer: str,
    kind: str,
    stable_id: str,
    digest_char: str | None = None,
    *,
    scope: dict[str, object] | None = None,
) -> dict[str, object]:
    return producer_reference(
        producer,
        kind,
        "0.1",
        stable_id,
        content_digest=("sha256:" + digest_char * 64) if digest_char else None,
        scope=scope,
    )


def experiment(
    experiment_id: str,
    *,
    rerun_of: str | None = None,
    execution_digest: str = "e",
) -> dict[str, object]:
    actor = ref("mncs-harness", "actor-route", f"harness://actor/{experiment_id}", "a")
    return make_concept_experiment_record(
        experiment_id=experiment_id,
        concept_id="mncs:concept:tri-state-result-lattice",
        created_at="2026-08-21T20:00:00Z",
        language_profile="mncs-language:source-profile:0.2",
        target_profile={"capability": "tri-state-combine", "backendNeutral": True},
        hypothesis="UNKNOWN remains UNKNOWN unless an authorized producer establishes more.",
        task="Evaluate the finite PASS/UNKNOWN/FAIL combination table.",
        falsifiers=["UNKNOWN is strengthened to PASS"],
        protected_properties=["FAIL dominates", "PASS is neutral", "UNKNOWN is preserved"],
        frozen_inputs=[{"identity": "sha256:" + "1" * 64}],
        hidden_inputs=[],
        resource_budget={"wallSeconds": 30, "attempts": 2},
        actors=[
            {
                "role": "experimenter",
                "reference": actor,
                "model": "model:fixture",
                "provider": "provider:fixture",
                "worker": "worker:fixture",
                "route": "harness:route:fixture",
                "tools": ["read_file"],
            }
        ],
        references=[
            {
                "relation": "compiler_record",
                "reference": ref(
                    "mncs-language",
                    "language-experiment-result",
                    f"mncs:language:experiment:result:{experiment_id}",
                    "c",
                ),
            },
            {
                "relation": "backend",
                "reference": ref(
                    "mncs-language",
                    "backend-identity",
                    "mncs:language:backend:reference-interpreter",
                    scope={"backend": "reference-interpreter"},
                ),
            },
            {
                "relation": "execution",
                "reference": ref(
                    "mncs-fabric",
                    "execution-attempt",
                    f"mncs-fabric://execution/{experiment_id}/attempt/1",
                    execution_digest,
                ),
            },
            {
                "relation": "evaluation",
                "reference": ref(
                    "mncs-forge",
                    "concept-evaluation",
                    f"mncs-forge://evaluation/{experiment_id}",
                    "f",
                ),
            },
        ],
        status="TERMINAL",
        rerun_of=rerun_of,
    )


def test_reference_and_experiment_validation_are_fail_closed() -> None:
    value = experiment("cre-tristate-a")
    assert validate_record(value).valid
    damaged = copy.deepcopy(value)
    damaged["details"]["references"][0]["reference"]["contentDigest"] = "sha256:not-a-digest"
    codes = {item.code for item in validate_record(damaged).diagnostics}
    assert "INVALID_PRODUCER_REFERENCE" in codes
    with pytest.raises(FamilyRecordError):
        producer_reference("mncs-language", "result", "0.1", "x", content_digest="bad")


def test_family_producer_compatibility_registry_covers_bootstrap_path() -> None:
    registry = json.loads(
        (Path(__file__).parents[1] / "compat" / "family-record-producers.json").read_text()
    )
    assert registry["referenceSchema"] == "commons.mncs.dev/producer-reference/v0alpha1"
    assert {item["producer"] for item in registry["contracts"]} == {
        "mncs-control-mcp",
        "mncs-harness",
        "mncs-fabric",
        "mncs-language",
        "mncs-forge",
    }
    for item in registry["contracts"]:
        assert item["sourceFingerprint"].startswith("sha256:")
        assert item["schemaVersion"].endswith("v0.1")


def test_tri_state_rerun_graph_query_and_duplicate_publication(tmp_path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    application = CommonsApplication(store)
    first = experiment("cre-tristate-a")
    added_first = application.add(first)
    receipt = application.publish(first)
    assert receipt["deliveryStatus"] == "DUPLICATE"

    failure = make_failure_classification_record(
        classification_id="classification:cre-tristate-a:1",
        experiment_id="cre-tristate-a",
        failure_reference=ref(
            "mncs-forge", "concept-evaluation", "mncs-forge://evaluation/cre-tristate-a", "f"
        ),
        classification="compiler_lowering_gap",
        disposition="CLAIMED",
        classifier=ref(
            "mncs-harness", "actor-route", "harness://actor/critic-a", "9"
        ),
        evidence_references=[],
        rationale="The critic claims a lowering gap; independent support remains unavailable.",
        created_at="2026-08-21T20:01:00Z",
    )
    application.add(failure)
    second = experiment("cre-tristate-b", rerun_of="cre-tristate-a", execution_digest="d")
    added_second = application.add(second)

    graph = application.experiment("cre-tristate-a")
    assert graph["experiment"]["details"]["experimentStatus"] == "TERMINAL"
    assert graph["producerReferences"]["evaluation"][0]["producer"] == "mncs-forge"
    assert any(item["kind"] == "FailureClassification" for item in graph["relatedRecords"])
    stored_first = store.get(added_first.digest)
    execution_reference = next(
        item["reference"]
        for item in stored_first["details"]["references"]
        if item["relation"] == "execution"
    )
    assert execution_reference["contentDigest"] == "sha256:" + "e" * 64
    stored_second = store.get(added_second.digest)
    assert {"type": "rerun_of", "target": "cre-tristate-a"} in stored_second[
        "relationships"
    ]

    assert sorted(
        item["metadata"]["recordId"]
        for item in application.query(QueryFilter(concept="mncs:concept:tri-state-result-lattice"))
    ) == ["cre-tristate-a", "cre-tristate-b"]
    assert len(application.query(QueryFilter(backend="reference-interpreter"))) == 2
    assert len(application.query(QueryFilter(participant="model:fixture"))) == 2
    classified = application.query(QueryFilter(failure_classification="compiler_lowering_gap"))
    assert [item["metadata"]["recordId"] for item in classified] == ["cre-tristate-a"]


def test_same_stable_producer_identity_cannot_change_digest(tmp_path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    store.add_record(experiment("cre-tristate-a", execution_digest="a"))
    conflicting = experiment("cre-tristate-b", execution_digest="b")
    execution_reference = next(
        item["reference"]
        for item in conflicting["details"]["references"]
        if item["relation"] == "execution"
    )
    execution_reference["stableId"] = "mncs-fabric://execution/cre-tristate-a/attempt/1"
    with pytest.raises(StoreError, match="different content digest"):
        store.add_record(conflicting)
