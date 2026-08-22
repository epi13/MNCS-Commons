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


def run(workspace: Path) -> dict[str, object]:
    _sources(workspace)
    from epi13_local_harness.actor_provenance import build_actor_provenance
    from mncs_control_mcp.experiments import build_concept_manifest, validate_spec
    from mncs_fabric.receipts import build_family_execution_reference
    from mncs_forge.concept_experiments import build_concept_evaluation

    from mncs_commons import CommonsApplication, CommonsStore, make_concept_experiment_record

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
            {
                "relation": "compiler_record",
                "reference": _reference(
                    language,
                    "CompilationStudyResult",
                    scope={"backend": backend_identity},
                ),
            },
            {
                "relation": "execution",
                "reference": _reference(
                    execution,
                    "FamilyExecutionReference",
                    scope={"backend": execution["backend_identity"], "attempt": 1},
                ),
            },
            {
                "relation": "evaluation",
                "reference": _reference(
                    evaluation,
                    "ConceptEvaluation",
                    scope={"status": evaluation["status"]},
                ),
            },
        ],
        status="TERMINAL",
    )
    with tempfile.TemporaryDirectory(prefix="mncs-family-record-") as directory:
        store = CommonsStore(Path(directory) / "store")
        store.init()
        application = CommonsApplication(store)
        application.add(record)
        graph = application.experiment(experiment_id)
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
        ],
        "evaluation_status": evaluation["status"],
        "execution_source_outcome": execution["source_outcome"],
        "graph": graph,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(run(args.workspace.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
