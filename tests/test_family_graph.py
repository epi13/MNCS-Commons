from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from mncs_commons.family_graph import (
    FamilyGraphError,
    consumers_for,
    load_graph,
    validate_generated_provider_metadata,
    validate_verification_manifest,
)


DEFAULT_GRAPH = Path(__file__).resolve().parents[1] / "family" / "semantic-edges-v1.json"


def graph_path() -> Path:
    """Resolve the graph under test, allowing sync CI to test its candidate."""

    return Path(os.environ.get("MNCS_FAMILY_GRAPH_PATH", DEFAULT_GRAPH))


def test_checked_in_graph_has_digest_bound_edges_and_selective_consumers() -> None:
    graph = load_graph(graph_path())
    consumers = consumers_for(
        graph,
        producer_repository="ravel",
        contract_identity="mncs.verification-plan/1",
    )
    assert [edge["consumer_repository"] for edge in consumers] == [
        "mncs-actions",
        "mncs-forge-mcp",
        "mncs-test",
    ]
    assert all(edge["fingerprint"] for edge in consumers)
    assert graph["graph_identity"]
    coverage = graph["coverage"]
    assert coverage["registered_family_project_count"] == 20
    assert coverage["classified_project_count"] == 20
    assert coverage["semantic_graph_participant_count"] == 6
    assert coverage["explicit_nonparticipant_count"] == 14
    assert coverage["unclassified_project_count"] == 0
    assert coverage["coverage_status"] == "complete"
    assert coverage["topology_status"] == "complete_among_declared_participants"


def test_graph_mutation_is_rejected(tmp_path: Path) -> None:
    value = json.loads(graph_path().read_text(encoding="utf-8"))
    value["edges"][0]["consumer_repository"] = "ravel"
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        load_graph(path)


def test_checked_in_graph_reconciles_against_repository_declarations() -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = Path(os.environ.get("MNCS_FAMILY_WORKSPACE", root.parent))
    if not all(
        (workspace / name / "family-semantic-contracts-v1.json").is_file()
        for name in ("RAVEL", "mncs-test", "mncs-actions", "mncs-forge-mcp", "mncs-debug", "mncs-language")
    ):
        pytest.skip("family sibling checkouts are not available; family CI runs this check")
    result = subprocess.run(
        ["python", "scripts/reconcile_semantic_edges.py", "--workspace", str(workspace), "--check"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_evidence_mutation_invalidates_reconciled_graph(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "family-workspace"
    workspace.mkdir()
    declarations = {
        "mncs-language": {
            "schema_version": "commons.mncs.semantic-contract-declarations/v1",
            "repository_id": "mncs-language",
            "revision": "1",
            "provides": [{
                "contract_identity": "mncs.semantic-impact/1",
                "contract_revision": "1",
                "exported_identity": "mncs-language:semantic-impact",
                "evidence": "contract/provider.txt",
            }],
            "consumes": [],
        },
        "ravel": {
            "schema_version": "commons.mncs.semantic-contract-declarations/v1",
            "repository_id": "ravel",
            "revision": "1",
            "provides": [],
            "consumes": [{
                "contract_identity": "mncs.semantic-impact/1",
                "contract_revision": "1",
                "consumer_identity": "ravel:impact",
                "evidence": "contract/consumer.txt",
                "verification": {
                    "check_identity": "ravel:impact-contract",
                    "executor": "ravel",
                    "surface": "consumer-contract",
                    "evidence": "contract/check.txt",
                },
            }],
        },
    }
    for repository_id, declaration in declarations.items():
        destination = workspace / repository_id
        destination.mkdir()
        (destination / "family-semantic-contracts-v1.json").write_text(
            json.dumps(declaration, indent=2) + "\n", encoding="utf-8"
        )
        for kind in ("provides", "consumes"):
            for entry in declaration[kind]:
                target = destination / entry["evidence"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"{repository_id}:{kind}\n", encoding="utf-8")
                verification = entry.get("verification")
                if verification:
                    check_path = destination / verification["evidence"]
                    check_path.parent.mkdir(parents=True, exist_ok=True)
                    check_path.write_text(
                        json.dumps(
                            {
                                "schema_version": "commons.mncs.family-verification-checks/v1",
                                "repository_id": repository_id,
                                "checks": [{
                                    "identity": entry["verification"]["check_identity"],
                                    "contract_identity": entry["contract_identity"],
                                    "runner": "declaration",
                                    "surface": entry["verification"]["surface"],
                                }],
                            }
                        ),
                        encoding="utf-8",
                    )

    output = tmp_path / "semantic-edges-v1.json"
    isolated_commons = tmp_path / "isolated-commons"
    isolated_commons.mkdir()
    command = [
        "python",
        str(root / "scripts" / "reconcile_semantic_edges.py"),
        "--workspace",
        str(workspace),
        "--commons-root",
        str(isolated_commons),
        "--output",
        str(output),
    ]
    generated = subprocess.run(
        command,
        cwd=root,
        env={"PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr or generated.stdout
    graph = load_graph(output)
    assert graph["source"]["declarations"][0]["evidence_digests"]
    assert all("consumer_evidence_sha256" in edge for edge in graph["edges"])

    evidence = workspace / "mncs-language" / "contract" / "provider.txt"
    evidence.write_text(evidence.read_text(encoding="utf-8") + "\n# semantic mutation\n", encoding="utf-8")
    checked = subprocess.run(
        [*command, "--check"],
        cwd=root,
        env={"PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode != 0
    assert "stale semantic graph" in checked.stdout


def test_repository_local_declaration_check_reports_compact_identity(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "repository"
    checkout.mkdir()
    declaration = {
        "schema_version": "commons.mncs.semantic-contract-declarations/v1",
        "repository_id": "ravel",
        "revision": "1",
        "provides": [{
            "contract_identity": "mncs.verification-plan/1",
            "contract_revision": "1",
            "exported_identity": "ravel:verification-plan",
            "evidence": "src/impact.py",
        }],
        "consumes": [],
    }
    (checkout / "family-semantic-contracts-v1.json").write_text(
        json.dumps(declaration), encoding="utf-8"
    )
    (checkout / "src").mkdir()
    (checkout / "src" / "impact.py").write_text("pass\n", encoding="utf-8")
    checked = subprocess.run(
        [
            "python",
            str(root / "scripts" / "validate_semantic_declaration.py"),
            "--root",
            str(checkout),
        ],
        cwd=root,
        env={"PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    output = json.loads(checked.stdout)
    assert output["repository_id"] == "ravel"
    assert len(output["declaration_identity"]) == 64
    assert output["evidence_digests"]["provides"]["src/impact.py"].startswith("sha256:")


def test_unknown_runner_and_executable_fields_are_rejected() -> None:
    base = {
        "schema_version": "commons.mncs.family-verification-checks/v1",
        "repository_id": "ravel",
        "checks": [
            {
                "identity": "ravel:check",
                "contract_identity": "mncs.verification-plan/1",
                "runner": "unknown-runner",
                "surface": "behavioral",
            }
        ],
    }
    with pytest.raises(FamilyGraphError):
        validate_verification_manifest(base, repository_id="ravel")

    base["checks"][0]["runner"] = "declaration"
    base["checks"][0]["command"] = "./run.sh"
    with pytest.raises(FamilyGraphError):
        validate_verification_manifest(base, repository_id="ravel")


def test_generated_provider_facts_fail_closed_when_stale() -> None:
    declaration = {
        "repository_id": "ravel",
        "provides": [
            {
                "contract_identity": "mncs.verification-plan/1",
                "contract_revision": "1",
                "exported_identity": "ravel:verification-plan",
                "evidence": "src/ravel/impact.py",
            }
        ],
    }
    generated = {
        "schema_version": "commons.mncs.generated-provider-metadata/v1",
        "repository_id": "ravel",
        "authority": {
            "kind": "language-owned-abi",
            "module_identity": "mncs.family.verification_plan.v1",
            "interface_identity": "0" * 64,
            "generator_version": "mncs-provider-facts/0.1",
            "binding_content_identity": "1" * 64,
            "provider_fact_identity": "2" * 64,
        },
        "providers": [
            {
                "contract_identity": "mncs.verification-plan/1",
                "contract_revision": "2",
                "exported_identity": "ravel:verification-plan",
                "evidence": "src/ravel/impact.py",
            }
        ],
    }
    with pytest.raises(FamilyGraphError, match="stale"):
        validate_generated_provider_metadata(
            generated, repository_id="ravel", declaration=declaration
        )


def test_generated_export_manifest_provider_facts_are_valid_without_typed_call_version() -> None:
    declaration = {
        "repository_id": "mncs-language",
        "provides": [
            {
                "contract_identity": "mncs.compiler.test-inventory/1",
                "contract_revision": "0.17",
                "exported_identity": "mncs-language:test-inventory",
                "evidence": "crates/mncs-cli/src/main.rs",
            }
        ],
    }
    generated = {
        "schema_version": "commons.mncs.generated-provider-metadata/v1",
        "repository_id": "mncs-language",
        "authority": {
            "kind": "language-owned-export-manifest",
            "module_identity": "mncs.cli.family-contracts.v1",
            "interface_identity": "0" * 64,
            "generator_version": "mncs-language-provider-facts/0.1",
            "binding_content_identity": "1" * 64,
            "provider_fact_identity": "2" * 64,
        },
        "providers": declaration["provides"],
    }
    normalized = validate_generated_provider_metadata(
        generated, repository_id="mncs-language", declaration=declaration
    )
    assert normalized["authority"]["kind"] == "language-owned-export-manifest"


def test_generated_provider_facts_reject_unknown_authority_kind() -> None:
    declaration = {
        "repository_id": "ravel",
        "provides": [
            {
                "contract_identity": "mncs.verification-plan/1",
                "contract_revision": "1",
                "exported_identity": "ravel:verification-plan",
                "evidence": "src/ravel/impact.py",
            }
        ],
    }
    generated = {
        "schema_version": "commons.mncs.generated-provider-metadata/v1",
        "repository_id": "ravel",
        "authority": {
            "kind": "scraped-source",
            "module_identity": "x",
            "interface_identity": "0" * 64,
            "generator_version": "x",
            "binding_content_identity": "1" * 64,
            "provider_fact_identity": "2" * 64,
        },
        "providers": declaration["provides"],
    }
    with pytest.raises(FamilyGraphError, match="unknown"):
        validate_generated_provider_metadata(generated, repository_id="ravel", declaration=declaration)


def test_generated_provider_facts_bind_evidence_content_when_checkout_is_available(tmp_path: Path) -> None:
    checkout = tmp_path / "mncs-language"
    evidence_path = checkout / "crates" / "mncs-cli" / "src" / "main.rs"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("exported contract facts\n", encoding="utf-8")
    declaration = {
        "repository_id": "mncs-language",
        "provides": [{
            "contract_identity": "mncs.compiler.test-inventory/1",
            "contract_revision": "0.17",
            "exported_identity": "mncs-language:test-inventory",
            "evidence": "crates/mncs-cli/src/main.rs",
        }],
    }
    evidence_identity = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    generated = {
        "schema_version": "commons.mncs.generated-provider-metadata/v1",
        "repository_id": "mncs-language",
        "authority": {
            "kind": "language-owned-export-manifest",
            "module_identity": "mncs.cli.family-contracts.v1",
            "interface_identity": "0" * 64,
            "generator_version": "mncs-language-provider-facts/0.1",
            "binding_content_identity": "1" * 64,
            "provider_fact_identity": "2" * 64,
            "evidence_digests": {"crates/mncs-cli/src/main.rs": evidence_identity},
        },
        "providers": declaration["provides"],
    }
    validate_generated_provider_metadata(
        generated,
        repository_id="mncs-language",
        declaration=declaration,
        checkout=checkout,
    )
    evidence_path.write_text("changed export facts\n", encoding="utf-8")
    with pytest.raises(FamilyGraphError, match="evidence is stale"):
        validate_generated_provider_metadata(
            generated,
            repository_id="mncs-language",
            declaration=declaration,
            checkout=checkout,
        )
