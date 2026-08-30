#!/usr/bin/env python3
"""Exercise the first cross-repository Concept Experiment Family Record flow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _sources(workspace: Path) -> None:
    repositories = (
        "MNCS-Commons",
        "mncs-control-mcp",
        "mncs-harness",
        "mncs-fabric",
        "mncs-forge-mcp",
        "machine-native-complexity-development-specification",
    )
    for repository in repositories:
        source = workspace / repository / "src"
        if not source.is_dir():
            raise SystemExit(f"required source checkout is unavailable: {source}")
        sys.path.insert(0, str(source))


def _reference(
    native: dict[str, object], record_kind: str, *, scope: dict[str, object]
) -> dict[str, object]:
    from mncs_commons import producer_reference

    digest = native.get("content_digest") or native.get("contentDigest")
    if isinstance(digest, str) and not digest.startswith("sha256:"):
        digest = "sha256:" + digest
    return producer_reference(
        str(native["producer"]),
        record_kind,
        str(native.get("schema_version") or native.get("schemaVersion") or native.get("schema")),
        str(native.get("stable_id") or native.get("stableId")),
        content_digest=str(digest) if digest else None,
        scope=scope,
    )


def _run_development_stage(
    manifest: dict[str, object],
    language: dict[str, object],
    execution: dict[str, object],
    evaluation: dict[str, object],
    experiment_record: dict[str, object],
    language_ref: dict[str, object],
    execution_ref: dict[str, object],
    evaluation_ref: dict[str, object],
) -> dict[str, object]:
    """Extend the spine through an MNCDS development record and Commons graph."""

    from mncds_validator.mncds import validate_development_value

    from mncs_commons import (
        CommonsApplication,
        CommonsStore,
        canonical_digest,
        make_development_record_record,
        normalize_producer_reference,
    )

    def normalize_like(reference: dict[str, object]) -> dict[str, object]:
        return normalize_producer_reference(reference)

    experiment_id = str(experiment_record["subject"]["identity"])
    candidate_a = "candidate.spine-fixture-a"
    candidate_b = "candidate.spine-fixture-b"
    development_record = {
        "schema_version": "0.2-alpha.1",
        "mncds_version": "0.2-alpha.1",
        "record_id": "development.family-spine-exercise",
        "profile": "MNCDS-D1",
        "epoch_id": "epoch.spine-1",
        "created_at": "2026-08-25T00:00:00Z",
        "supersedes_record_id": None,
        "charter": {
            "charter_id": "charter.spine-exercise",
            "problem_statement": (
                "UNKNOWN must survive the full producer chain without strengthening."
            ),
            "intended_use": (
                "Exercise Control -> Harness -> Language -> Fabric -> Forge -> "
                "Experiment -> MNCDS -> Commons."
            ),
            "exclusions": ["No assurance claim is made."],
            "contract_id": "contract.spine-exercise",
            "baseline_id": "baseline.spine-a",
            "environment_id": "environment.spine",
            "threat_model_id": "threat.status-collapse",
            "objective": {
                "objective_id": "objective.tri-state-preservation",
                "metric": "status-strengthening incidents",
                "unit": "incidents",
                "direction": "minimize",
                "minimum_useful_benefit": 0,
                "operational_rationale": "Any UNKNOWN-to-PASS promotion is a defect.",
            },
            "selection_policy_id": "selection.policy.exact-status-match",
            "planned_mncs_level": None,
            "hard_rejection_gates": ["gate.unknown-not-promoted"],
            "release_owner_id": "authority.spine-release",
            "rollback_owner_id": "authority.spine-release",
            "retirement_owner_id": "authority.spine-release",
        },
        "baseline": {
            "baseline_id": "baseline.spine-a",
            "artifact_id": "artifact.candidate-a",
            "source_id": "source.candidate-a",
            "build_id": "build.candidate-a",
            "dependency_ids": [],
            "environment_id": "environment.spine",
            "evaluator_ids": ["evaluator.forge-independent"],
            "results": [
                {
                    "evaluator_id": "evaluator.forge-independent",
                    "gate_id": "gate.unknown-not-promoted",
                    "partition_id": "partition.development",
                    "required": True,
                    "status": "UNKNOWN",
                    "evidence_id": "evidence.candidate-a",
                }
            ],
            "captured_at": "2026-08-25T00:00:00Z",
            "immutable": True,
        },
        "environment_lock": {
            "environment_id": "environment.spine",
            "toolchain_id": "toolchain.spine",
            "dependency_ids": [],
            "hardware_id": "hardware.fixture",
            "configuration_id": "configuration.spine",
            "permitted_variance": ["Fixture identities are pinned; timings vary."],
            "locked": True,
        },
        "roles": [
            {
                "role": "contract_authority",
                "authority_id": "authority.spine-contract",
                "executable_id": None,
            },
            {
                "role": "generator_authority",
                "authority_id": "authority.spine-generator",
                "executable_id": "generator:fixture",
            },
            {
                "role": "evaluator_authority",
                "authority_id": "authority.spine-evaluator",
                "executable_id": "forge:fixture-verifier",
            },
            {
                "role": "selection_authority",
                "authority_id": "authority.spine-selection",
                "executable_id": None,
            },
            {
                "role": "release_authority",
                "authority_id": "authority.spine-release",
                "executable_id": None,
            },
            {
                "role": "independent_reviewer",
                "authority_id": "authority.community-review-open-roster",
                "executable_id": None,
            },
        ],
        "authority_overlaps": [],
        "generator": {
            "generator_id": "generator:fixture",
            "configuration_id": "configuration.generator-spine",
            "authority_id": "authority.spine-generator",
            "executable_id": "generator:fixture-executable",
            "permissions": {
                "modify_contract": False,
                "modify_baseline": False,
                "modify_evaluators": False,
                "modify_selection_policy": False,
                "modify_thresholds": False,
                "access_protected_holdout": False,
                "network_access": False,
                "filesystem_scope": ["fixture workspace"],
                "process_scope": ["none"],
                "tool_ids": ["mncs-cli"],
                "mutation_scope": ["candidate sources"],
            },
            "resource_limits": {
                "max_candidates": 2,
                "max_wall_seconds": 60,
                "max_memory_bytes": 268435456,
                "max_processes": 2,
            },
        },
        "partitions": {
            "development_id": "partition.development",
            "selection_id": "partition.selection",
            "final_evaluation_id": None,
            "holdout_contaminated": False,
            "access_policy_ids": ["policy.fixture"],
        },
        "protected_evidence": [],
        "evaluators": [
            {
                "evaluator_id": "evaluator.forge-independent",
                "purpose": "development",
                "authority_id": "authority.spine-evaluator",
                "executable_id": "forge:fixture-verifier-executable",
                "configuration_id": "configuration.evaluator-spine",
                "environment_id": "environment.spine",
                "independent": False,
                "operator_independence": "UNKNOWN",
                "organizational_independence": "UNKNOWN",
                "regression_corpus_id": "corpus.spine-fixture",
            }
        ],
        "candidates": [
            {
                "candidate_id": candidate_a,
                "parent_ids": [],
                "epoch_id": "epoch.spine-1",
                "generator_id": "generator:fixture",
                "generation_sequence": 0,
                "materially_evaluated": True,
                "retained": True,
                "build_status": "PASS",
                "disposition": "rejected",
                "objective_value": None,
                "evaluator_results": [
                    {
                        "evaluator_id": "evaluator.forge-independent",
                        "gate_id": "gate.unknown-not-promoted",
                        "partition_id": "partition.development",
                        "required": True,
                        "status": "UNKNOWN",
                        "evidence_id": str(evaluation["stable_id"]),
                    }
                ],
            },
            {
                "candidate_id": candidate_b,
                "parent_ids": [candidate_a],
                "epoch_id": "epoch.spine-1",
                "generator_id": "generator:fixture",
                "generation_sequence": 1,
                "materially_evaluated": True,
                "retained": True,
                "build_status": "PASS",
                "disposition": "selected",
                "objective_value": None,
                "evaluator_results": [
                    {
                        "evaluator_id": "evaluator.forge-independent",
                        "gate_id": "gate.unknown-not-promoted",
                        "partition_id": "partition.selection",
                        "required": True,
                        "status": "UNKNOWN",
                        "evidence_id": str(evaluation["stable_id"]),
                    }
                ],
            },
        ],
        "candidate_aggregates": [],
        "selection": {
            "policy_id": "selection.policy.exact-status-match",
            "selection_epoch_id": "epoch.spine-1",
            "selected_candidate_id": candidate_b,
            "rule_recorded_before_final_evaluation": True,
            "unknown_policy": "human_review",
            "minimum_useful_benefit_met": True,
            "hard_gates_passed": True,
            "rationale": (
                "Candidate B preserves UNKNOWN exactly; acceptance is explicitly "
                "accept-with-UNKNOWN."
            ),
            "human_review": {
                "reviewer_id": "authority.spine-selection",
                "decision": "accept_with_unknown",
                "rationale": "Independent target evidence remains unavailable; no PASS is claimed.",
            },
        },
        "reproducibility": {
            "class": "EXACT",
            "seeds_preserved": True,
            "protocol": "Rerun the exercise script against pinned sibling checkouts.",
            "measurement_repetitions": 2,
            "comparison_statistic": "Exact status equality across producers.",
            "acceptance_bounds": "All statuses must reproduce exactly.",
            "failure_treatment": "Divergence is FAIL.",
        },
        "epochs": [
            {
                "epoch_id": "epoch.spine-1",
                "parent_epoch_id": None,
                "toolchain_id": "toolchain.spine",
                "corpus_id": "corpus.spine-fixture",
                "objective_id": "objective.tri-state-preservation",
                "contract_id": "contract.spine-exercise",
                "threshold_policy_id": "threshold.zero-strengthening",
                "development_partition_id": "partition.development",
                "final_partition_id": None,
                "change_evidence_ids": [str(evaluation["stable_id"])],
                "regression_fixture_ids": ["fixture.bounded-sum-baseline"],
            }
        ],
        "mncs_binding": None,
        "release_controls": None,
        "producer_bindings": [
            {
                "binding_id": "binding.language-study",
                "role": "diagnostic_evidence",
                "producer": "mncs-language",
                "record_kind": "CompilationStudyResult",
                "native_schema_version": "mncs-language.family-compiler-reference.v0.1",
                "stable_record_id": str(language["stableId"]),
                "content_digest": "sha256:" + str(language["contentDigest"]),
                "subject_candidate_id": candidate_b,
                "declared_scope": dict(language["scope"]),
                "compatibility_status": "supported",
                "evidence_status": "UNKNOWN",
                "notes": (
                    "Compiler evidence only; unresolved obligations keep producer "
                    "status UNKNOWN."
                ),
            },
            {
                "binding_id": "binding.execution-attempt",
                "role": "development_feedback",
                "producer": "mncs-fabric",
                "record_kind": "FamilyExecutionReference",
                "native_schema_version": "mncs-fabric.family-execution-reference.v0.1",
                "stable_record_id": str(execution["stable_id"]),
                "subject_candidate_id": candidate_a,
                "partition_id": "partition.development",
                "compatibility_status": "supported",
                "evidence_status": "UNKNOWN",
            },
            {
                "binding_id": "binding.forge-evaluation",
                "role": "selection_evidence",
                "producer": "mncs-forge",
                "record_kind": "ConceptEvaluation",
                "native_schema_version": "mncs-forge.concept-evaluation.v0.1",
                "stable_record_id": str(evaluation["stable_id"]),
                "subject_candidate_id": candidate_b,
                "partition_id": "partition.selection",
                "declared_scope": {
                    "concept_experiment_id": experiment_id,
                    "verifier_identity": "forge:fixture-verifier",
                    "candidate_identity": candidate_b,
                },
                "compatibility_status": "supported",
                "evidence_status": "UNKNOWN",
            },
        ],
        "extensions": {},
    }

    report = validate_development_value(development_record, target="family-spine-exercise")
    if not report.valid or report.computed_status != "UNKNOWN":
        raise SystemExit(
            f"MNCDS validation did not preserve the expected tri-state: {report.as_dict()}"
        )
    record_digest = canonical_digest(development_record)

    forge_reference = normalize_like(evaluation_ref)
    language_reference = normalize_like(language_ref)
    execution_reference = normalize_like(execution_ref)
    projection = make_development_record_record(
        development_record_id=development_record["record_id"],
        created_at="2026-08-25T00:00:01Z",
        mncds_version="0.2-alpha.1",
        record_digest=record_digest,
        profile=development_record["profile"],
        epoch_id=development_record["epoch_id"],
        computed_status=report.computed_status,
        summary=(
            "Development-process projection of the family spine exercise; "
            "UNKNOWN accepted under explicit human review."
        ),
        references=[
            {"relation": "evaluation", "reference": forge_reference},
            {"relation": "compiler_record", "reference": language_reference},
            {"relation": "execution", "reference": execution_reference},
        ],
        selected_candidate_id=candidate_b,
        concept_experiment_ids=[experiment_id],
    )

    with tempfile.TemporaryDirectory(prefix="mncs-family-record-dev-") as directory:
        store = CommonsStore(Path(directory) / "store")
        store.init()
        application = CommonsApplication(store)
        application.add(experiment_record)
        application.add(projection)
        graph = application.experiment(experiment_id)
        lineage = application.development_record(projection["metadata"]["recordId"])
        stored_projection = lineage["developmentRecord"]
    assert stored_projection["details"]["recordDigest"] == record_digest
    assert lineage["computedStatus"] == "UNKNOWN"
    edge_targets = {edge["target"] for edge in lineage["edges"]}
    assert experiment_id in edge_targets
    return {
        "experiment_id": experiment_id,
        "manifest_identity": manifest["manifest_identity"],
        "producer_order": [
            "mncs-control-mcp",
            "mncs-harness",
            "mncs-language",
            "mncs-fabric",
            "mncs-forge",
            "mncs-commons",
            "mncds",
        ],
        "evaluation_status": evaluation["status"],
        "execution_source_outcome": execution["source_outcome"],
        "graph": graph,
        "development_record_id": development_record["record_id"],
        "development_record_digest": record_digest,
        "development_computed_status": report.computed_status,
        "development_lineage_edges": len(lineage["edges"]),
    }


def run(workspace: Path) -> dict[str, object]:
    _sources(workspace)
    from epi13_local_harness.actor_provenance import build_actor_provenance
    from mncs_control_mcp.experiments import build_concept_manifest, validate_spec
    from mncs_fabric.receipts import build_family_execution_reference
    from mncs_forge.concept_experiments import build_concept_evaluation

    from mncs_commons import make_concept_experiment_record

    experiment_id = "cre-family-spine-fixture-a"
    spec = validate_spec(
        {
            "goal": "Check that UNKNOWN survives one backend-neutral compiler experiment.",
            "actors": [
                {
                    "name": "critic",
                    "role": "skeptic",
                    "worker": "fixture-worker",
                    "model": "fixture-model",
                }
            ],
            "stages": ["Compile, execute, and independently evaluate the frozen case."],
            "duration_seconds": 30,
            "max_turns": 1,
            "concept": {
                "concept_id": "mncs-language:tri-state-preservation",
                "language_profile": "mncs-language:research-0.1",
                "target_profile": {"backendNeutral": True, "candidate": "portable-wasm-mvp"},
                "hypothesis": "UNKNOWN remains UNKNOWN without stronger independent evidence.",
                "falsifiers": ["UNKNOWN is published as PASS"],
                "protected_properties": ["tri-state result exactness"],
                "governing_contracts": ["mncs-rfc:family-record-spine"],
                "frozen_inputs": [{"path": "examples/execution/bounded-sum-baseline.mncs.json"}],
            },
        }
    )
    manifest = build_concept_manifest(
        experiment_id, spec, frozen_at="2026-08-21T20:00:00Z"
    )
    actor = build_actor_provenance(
        role="skeptic",
        model_identity="fixture-model",
        provider_identity="fixture-provider",
        worker_identity="fixture-worker",
        route_identity="fixture-route",
        tool_exposure=["read_file"],
        policy_profile="fixture-bounded",
        prompt_digest="sha256:" + "1" * 64,
        session_identity=experiment_id,
        observed_at="2026-08-21T20:00:01Z",
    )
    language_process = subprocess.run(
        [
            "cargo",
            "run",
            "-q",
            "-p",
            "mncs-cli",
            "--",
            "compiler-study",
            "examples/execution/bounded-sum-baseline.mncs.json",
            "--node-id",
            "fixture-node",
            "--target",
            "portable-wasm-mvp",
            "--family-reference",
        ],
        cwd=workspace / "mncs-language",
        check=True,
        capture_output=True,
        text=True,
    )
    language = json.loads(language_process.stdout)
    backend_identity = language["compiler"]["backendIdentity"] or "mncs-language:backend:unrealized"
    execution = build_family_execution_reference(
        {
            "record_id": "sha256:" + "2" * 64,
            "job_identity": "fixture-job",
            "request_identity": "fixture-request",
            "outcome": "UNKNOWN",
            "node": {"node_id": "fixture-node", "node_fingerprint": "sha256:" + "3" * 64},
            "declared_environment": {"runtime": "fixture"},
            "policy_observations": {"network_policy": "none"},
            "target_identity": language["compiler"]["targetIdentity"],
        },
        attempt=1,
        backend_identity=backend_identity,
    )
    evaluation = build_concept_evaluation(
        concept_experiment_id=experiment_id,
        candidate_identity="candidate:fixture",
        language_profile=manifest["language_profile"],
        compiler_identity=language["compiler"]["compilerIdentity"],
        backend_identity=backend_identity,
        execution_identities=[execution["stable_id"]],
        verifier_identity="forge:fixture-verifier",
        verifier_version="0.1",
        obligation="UNKNOWN must not be strengthened",
        evidence_identities=[execution["stable_id"]],
        status="UNKNOWN",
        unresolved_obligations=["independent target evidence unavailable"],
        generator_identity="generator:fixture",
    )
    actor_reference = _reference(actor, "ActorProvenance", scope={"role": "skeptic"})
    language_ref = _reference(
        language,
        "CompilationStudyResult",
        scope={"backend": backend_identity},
    )
    execution_ref = _reference(
        execution,
        "FamilyExecutionReference",
        scope={"backend": execution["backend_identity"], "attempt": 1},
    )
    evaluation_ref = _reference(
        evaluation,
        "ConceptEvaluation",
        scope={"status": evaluation["status"]},
    )
    record = make_concept_experiment_record(
        experiment_id=experiment_id,
        concept_id=manifest["concept_id"],
        created_at=manifest["frozen_at"],
        language_profile=manifest["language_profile"],
        target_profile=manifest["target_profile"],
        hypothesis=manifest["hypothesis"],
        task=manifest["task"],
        falsifiers=manifest["falsifiers"],
        protected_properties=manifest["protected_properties"],
        frozen_inputs=manifest["frozen_inputs"],
        hidden_inputs=manifest["hidden_inputs"],
        resource_budget=manifest["resource_budget"],
        actors=[
            {
                "role": "skeptic",
                "model": "fixture-model",
                "worker": "fixture-worker",
                "reference": actor_reference,
            }
        ],
        references=[
            {"relation": "actor", "reference": actor_reference},
            {"relation": "compiler_record", "reference": language_ref},
            {"relation": "execution", "reference": execution_ref},
            {"relation": "evaluation", "reference": evaluation_ref},
        ],
        status="TERMINAL",
    )
    return _run_development_stage(
        manifest,
        language,
        execution,
        evaluation,
        record,
        language_ref,
        execution_ref,
        evaluation_ref,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(run(args.workspace.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
