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
        "mncds",
    }
    for item in registry["contracts"]:
        assert item["sourceFingerprint"].startswith("sha256:")
        assert item["schemaVersion"].endswith(("v0.1", "v0.2-alpha.1"))


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
        classifier=ref("mncs-harness", "actor-route", "harness://actor/critic-a", "9"),
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
    assert {"type": "rerun_of", "target": "cre-tristate-a"} in stored_second["relationships"]

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


def replication(
    replication_id: str,
    *,
    outcome: str = "PASS",
    target: str = "cre-tristate-a",
) -> dict[str, object]:
    from mncs_commons.family import make_replication_record

    return make_replication_record(
        replication_id=replication_id,
        created_at="2026-08-23T12:00:00Z",
        target_record=target,
        outcome=outcome,
        independence={
            "harness": "mncs-control-mcp:replication-orchestrator",
            "machine": "fabric-worker-01",
            "provider": "mncs-fabric",
            "artifactAncestry": [
                "mncs:compiler:backend-artifact:" + "9" * 64,
            ],
        },
        references=[
            {
                "relation": "compiler_record",
                "reference": ref(
                    "mncs-language",
                    "LanguageExperimentResult",
                    f"mncs:language:experiment:result:{replication_id}",
                    "d",
                    scope={"backend": "mncs-portable-wasm-mvp"},
                ),
            },
            {
                "relation": "execution",
                "reference": ref(
                    "mncs-fabric",
                    "FamilyExecutionReference",
                    f"mncs-fabric://execution/{replication_id}/attempt/1",
                    "f",
                ),
            },
            {
                "relation": "evaluation",
                "reference": ref(
                    "mncs-forge",
                    "ConceptEvaluation",
                    f"mncs-forge://evaluation/{replication_id}",
                    "b",
                ),
            },
        ],
        summary=(
            f"Replication of {target}: the exact frozen realization executed once on an "
            "explicitly requested Fabric worker with independent execution evidence."
        ),
    )


def test_replication_record_binds_typed_evidence_and_validates(tmp_path: Path) -> None:
    record = replication("replication-happy")
    report = validate_record(record)
    assert report.valid, report.diagnostics
    assert record["kind"] == "Replication"
    assert record["details"]["outcome"] == "PASS"
    relationship_types = {item["type"] for item in record["relationships"]}
    assert {
        "replicates",
        "attempts",
        "executes",
        "evaluates",
        "compiled_from",
    } <= relationship_types
    assert set(record["provenance"]["sourceRecords"]) == {
        "mncs:language:experiment:result:replication-happy",
        "mncs-fabric://execution/replication-happy/attempt/1",
        "mncs-forge://evaluation/replication-happy",
    }

    store = CommonsStore(tmp_path / "store")
    store.init()
    application = CommonsApplication(store)
    application.add(experiment("cre-tristate-a"))
    identity = application.add(record)
    assert identity.kind == "Replication"

    # The durable graph links the replication back to its experiment.
    correlated = application.replications("cre-tristate-a")
    replications = correlated.get("replications", [])
    assert any(item["metadata"]["recordId"] == "replication-happy" for item in replications)
    assert correlated["outcomes"].get("PASS") == 1

    extracted = __import__(
        "mncs_commons.family", fromlist=["producer_references"]
    ).producer_references(record)
    assert {item["producer"] for item in extracted} >= {
        "mncs-language",
        "mncs-fabric",
        "mncs-forge",
    }


def test_failed_replication_uses_failed_to_replicate_relationship(tmp_path: Path) -> None:
    failed = replication("replication-broken", outcome="FAIL")
    assert validate_record(failed).valid
    types = {item["type"] for item in failed["relationships"]}
    assert {"failed_to_replicate", "attempts"} <= types
    assert "replicates" not in types


def test_unknown_outcome_asserts_attempt_without_success_or_failure(tmp_path: Path) -> None:
    from mncs_commons.application import CommonsApplication
    from mncs_commons.store import CommonsStore

    unknown = replication("replication-unknown", outcome="UNKNOWN")
    assert validate_record(unknown).valid
    assert unknown["details"]["outcome"] == "UNKNOWN"
    # UNKNOWN asserts the attempt but never collapses into demonstrated
    # success or demonstrated failure.
    types = {item["type"] for item in unknown["relationships"]}
    assert "attempts" in types
    assert "replicates" not in types
    assert "failed_to_replicate" not in types

    store = CommonsStore(tmp_path / "store")
    store.init()
    application = CommonsApplication(store)
    application.add(experiment("cre-tristate-a"))
    application.add(replication("replication-pass"))
    application.add(unknown)
    correlated = application.replications("cre-tristate-a")
    assert correlated["outcomes"].get("PASS") == 1
    assert correlated["outcomes"].get("UNKNOWN") == 1


def test_replication_rejects_non_tri_state_outcomes() -> None:
    import pytest as _pytest

    from mncs_commons.family import FamilyRecordError, make_replication_record

    with _pytest.raises(FamilyRecordError, match="PASS, FAIL, or UNKNOWN"):
        make_replication_record(
            replication_id="r",
            created_at="2026-08-23T12:00:00Z",
            target_record="cre-tristate-a",
            outcome="CONFORMANT",
            independence={},
            references=[],
            summary="must fail closed on invented statuses",
        )


def test_replication_rejects_malformed_producer_references() -> None:
    bad = replication("replication-badref")
    bad["details"]["references"][0]["reference"]["contentDigest"] = "sha256:NOThex"
    report = validate_record(bad)
    codes = {item.code for item in report.diagnostics}
    assert "INVALID_PRODUCER_REFERENCE" in codes


def _development_record_projection(
    record_id: str,
    *,
    computed_status: str,
    supersedes: str | None = None,
) -> dict[str, object]:
    from mncs_commons import (
        make_development_record_record,
        producer_reference,
    )

    references = [
        {
            "relation": "evaluation",
            "reference": producer_reference(
                "mncs-forge",
                "concept-evaluation",
                "mncs-forge.concept-evaluation.v0.1",
                f"mncs-forge://evaluation/{record_id}",
                content_digest="sha256:" + "d" * 64,
            ),
        },
        {
            "relation": "candidate",
            "reference": producer_reference(
                "github.com/epi13/mncs-language",
                "Commit",
                "git",
                "67fc26f49ef7c12130f9828231253464a6ce0388",
                artifact={
                    "identity": (
                        "mncs-language@67fc26f49ef7c12130f9828231253464a6ce0388"
                    ),
                    "kind": "source-revision",
                },
            ),
        },
    ]
    return make_development_record_record(
        development_record_id=record_id,
        created_at="2026-08-25T00:00:00Z",
        mncds_version="0.2-alpha.1",
        record_digest="sha256:" + "e" * 64,
        profile="MNCDS-D1",
        epoch_id="epoch.span-fix-1",
        computed_status=computed_status,
        summary="Projection of a validated MNCDS development record.",
        references=references,
        selected_candidate_id="candidate.mncs-language-cdee978",
        supersedes_record_id=supersedes,
        concept_experiment_ids=["cre-family-spine-fixture-a"],
    )


def test_development_record_projection_preserves_tri_state(tmp_path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    application = CommonsApplication(store)
    added = application.add(_development_record_projection("dev.rec.a", computed_status="UNKNOWN"))
    assert added.kind == "DevelopmentRecord"

    lineage = application.development_record("development-record:dev.rec.a")
    assert lineage["computedStatus"] == "UNKNOWN"
    assert lineage["authorityBoundary"]
    targets = {edge["target"] for edge in lineage["edges"]}
    assert "cre-family-spine-fixture-a" in targets
    details = lineage["developmentRecord"]["details"]
    assert details["schema"] == "commons.mncs.dev/development-record/v0alpha1"
    assert details["recordDigest"].startswith("sha256:")


def test_development_supersession_chain_is_reconstructable(tmp_path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    application = CommonsApplication(store)
    application.add(_development_record_projection("dev.rec.a", computed_status="PASS"))
    successor = application.add(
        _development_record_projection(
            "dev.rec.b", computed_status="FAIL", supersedes="dev.rec.a"
        )
    )
    lineage = application.development_record(successor.digest)
    assert {"successor": "dev.rec.b", "predecessor": "dev.rec.a"} in lineage[
        "supersession"
    ]
    # FAIL is preserved exactly in the projection.
    assert lineage["computedStatus"] == "FAIL"


def test_development_record_rejects_non_tri_state_and_bad_digest() -> None:
    import pytest as _pytest

    from mncs_commons.family import FamilyRecordError

    with _pytest.raises(FamilyRecordError, match="PASS, FAIL, or UNKNOWN"):
        _development_record_projection("dev.bad", computed_status="CONFORMANT")
    from mncs_commons.family import make_development_record_record

    with _pytest.raises(FamilyRecordError, match="sha256"):
        make_development_record_record(
            development_record_id="dev.bad2",
            created_at="2026-08-25T00:00:00Z",
            mncds_version="0.2-alpha.1",
            record_digest="md5:" + "e" * 32,
            profile="MNCDS-D1",
            epoch_id="epoch.span-fix-1",
            computed_status="PASS",
            summary="bad digest must fail closed",
            references=[],
        )
