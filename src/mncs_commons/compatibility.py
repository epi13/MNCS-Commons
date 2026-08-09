"""Explicit producer contracts, deterministic drift inspection, and resolution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from .models import Diagnostic

MAX_SOURCE_BYTES = 8 * 1024 * 1024


class CompatibilityStatus(StrEnum):
    EXACT = "EXACT"
    COMPATIBLE = "COMPATIBLE"
    COMPATIBLE_WITH_UNRESOLVED_FIELDS = "COMPATIBLE_WITH_UNRESOLVED_FIELDS"
    DRIFTED = "DRIFTED"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProducerContract:
    """One frozen producer record-family boundary."""

    contract_id: str
    producer: str
    record_type: str
    schema_version: str
    source_repository: str
    source_commit: str | None
    source_path: str | None
    source_fingerprint: str | None
    fixture_path: str | None
    adapter: str | None
    expected_status: CompatibilityStatus
    known_unresolved_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "contractId": self.contract_id,
            "producer": self.producer,
            "recordType": self.record_type,
            "schemaVersion": self.schema_version,
            "sourceRepository": self.source_repository,
            "sourceCommit": self.source_commit,
            "sourcePath": self.source_path,
            "sourceFingerprint": self.source_fingerprint,
            "fixturePath": self.fixture_path,
            "adapter": self.adapter,
            "expectedStatus": self.expected_status.value,
            "knownUnresolvedFields": list(self.known_unresolved_fields),
        }


@dataclass(frozen=True, slots=True)
class CompatibilityAssessment:
    contract: ProducerContract
    status: CompatibilityStatus
    observed_commit: str | None = None
    observed_fingerprint: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            **self.contract.as_dict(),
            "status": self.status.value,
            "observedCommit": self.observed_commit,
            "observedFingerprint": self.observed_fingerprint,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ContractResolution:
    contract: ProducerContract | None
    diagnostics: tuple[Diagnostic, ...] = ()


def _c(
    contract_id: str,
    producer: str,
    record_type: str,
    schema_version: str,
    source_repository: str,
    source_commit: str | None,
    source_path: str | None,
    source_fingerprint: str | None,
    fixture_path: str | None,
    adapter: str | None,
    expected_status: CompatibilityStatus,
    unresolved: tuple[str, ...] = (),
) -> ProducerContract:
    return ProducerContract(
        contract_id,
        producer,
        record_type,
        schema_version,
        source_repository,
        source_commit,
        source_path,
        source_fingerprint,
        fixture_path,
        adapter,
        expected_status,
        unresolved,
    )


_CONTRACTS = (
    _c(
        "forge:cell-execution:0.1",
        "forge",
        "forge-cell-execution",
        "0.1",
        "mncs-forge-mcp",
        "5a5691709b26a2f923e14674138bdb215471a5a7",
        "examples/forge-cell/execution-record.json",
        "sha256:5c9982b94cd7f443ac45445e95ca94b3032712babcdf71e62e5fa0489eef9fbc",
        "compat/forge/forge-cell-execution-0.1.json",
        "adapters.forge.from_forge_result",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("result_identity",),
    ),
    _c(
        "forge:execution-receipt:0.1",
        "forge",
        "mncs-execution-receipt",
        "0.1",
        "mncs-forge-mcp",
        "5a5691709b26a2f923e14674138bdb215471a5a7",
        "tests/fixtures/mncs-execution-receipt-0.1.schema.json",
        "sha256:f2e1860405052a40b100bead7c27dbe0cc3ac11d03dccca3fcb643b350ecab6e",
        "compat/forge/mncs-execution-receipt-0.1.json",
        "adapters.forge.from_execution_receipt",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("producer_result_fixture",),
    ),
    _c(
        "fabric:execution-record:0.1",
        "fabric",
        "fabric-execution-record",
        "mncs-fabric.execution-record.v0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/execution-record-v0.1.schema.json",
        "sha256:687599514a8eaff7da131854c1144ca2e53c9cd72deaee8440c2ef3bd7abcb87",
        "compat/fabric/execution-record-v0.1.json",
        "adapters.fabric.from_fabric_execution",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "fabric:artifact-manifest:0.1",
        "fabric",
        "fabric-artifact-manifest",
        "mncs-fabric.artifact-manifest.v0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/artifact-manifest-v0.1.schema.json",
        "sha256:9926d4b998de80c5f33f26520fad8fa3778f2f3d3275d1432c59ae0970f47b57",
        "compat/fabric/artifact-manifest-v0.1.json",
        "adapters.fabric.from_fabric_artifact_manifest",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "fabric:execution-bundle-binding:0.1",
        "fabric",
        "fabric-execution-bundle-binding",
        "0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/mncs-fabric.execution-bundle-binding.v0.1.schema.json",
        "sha256:1c954c562a2a6f4e9f6bc51c2fc1d9edc1ee7fd0098eae82e3f8eaacf2d0bc85",
        "compat/fabric/execution-bundle-binding-v0.1.json",
        "adapters.fabric.from_fabric_bundle_binding",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "fabric:job-plan:0.1",
        "fabric",
        "fabric-job-plan",
        "mncs-fabric.job-plan.v0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/job-plan-v0.1.schema.json",
        "sha256:86eab2fc88c3c4a26909cccac77c1b395aa778dc70d0cb9b2c061fa98101965b",
        "compat/fabric/job-plan-v0.1.json",
        "adapters.fabric.from_fabric_job_plan",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "fabric:node-capabilities:0.1",
        "fabric",
        "fabric-node-capabilities",
        "mncs-fabric.node-capabilities.v0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/node-capabilities-v0.1.schema.json",
        "sha256:c390a90f12e745d180439e518559635be385027f8ee4b19447889497c4459de1",
        "compat/fabric/node-capabilities-v0.1.json",
        "adapters.fabric.from_fabric_node_capabilities",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "fabric:cohort-result:0.1",
        "fabric",
        "fabric-cohort-result",
        "mncs-fabric.cohort-result.v0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/cohort-result-v0.1.schema.json",
        "sha256:1e0ca6d77d4afa02685687d7313ad97dd5ea1991d94ecd256d4d4507ae22e204",
        "compat/fabric/cohort-result-v0.1.json",
        "adapters.fabric.from_fabric_cohort_result",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("independence",),
    ),
    _c(
        "fabric:protocol-envelope:0.1",
        "fabric",
        "fabric-protocol-envelope",
        "mncs-fabric.protocol.v0.1",
        "mncs-fabric",
        "fd6a1e1fe617b77402a3d40c278776dd8f159fb0",
        "schemas/protocol-envelope-v0.1.schema.json",
        "sha256:4516129e40e9c3228ef751512b6c649637b33e2c4e2af3d0135fb0ad578de313",
        None,
        None,
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("authentication",),
    ),
    _c(
        "mnel:ledger-record:0.1",
        "mnel",
        "mnel-ledger-record",
        "mnel-ledger-record/0.1",
        "Machine-Native-Experimental-Learning",
        "3a44380c56ded6a1fae1aa7a6a908f28ad1dd953",
        "schemas/mnel-records.schema.json",
        "sha256:b45e609ddc64c2dd4859c3824048c39516f381e6036e9a3b047ce58b09088d90",
        "compat/mnel/mnel-episode-0.1.json",
        "adapters.mnel.from_mnel_observation",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "mnel:provider-study:0.4",
        "mnel",
        "mnel-provider-study",
        "0.4",
        "Machine-Native-Experimental-Learning",
        "3a44380c56ded6a1fae1aa7a6a908f28ad1dd953",
        "schemas/mnel-provider-study.schema.json",
        "sha256:77dc97a8207e48fa83db537599b9ff1d7a2a432170d6751a910d9145d37cba0a",
        "compat/mnel/provider-portfolio-0.4.json",
        "adapters.mnel.from_provider_study_record",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("source_record_family",),
    ),
    _c(
        "mnel:calibration:0.4",
        "mnel",
        "mnel-calibration-record",
        "mnel-calibration-record/0.4",
        "Machine-Native-Experimental-Learning",
        "3a44380c56ded6a1fae1aa7a6a908f28ad1dd953",
        "schemas/mnel-calibration.schema.json",
        "sha256:62078745b8766a00ad8848c605bc4749ad583c5360ef8ade4986f53027c3aca9",
        "compat/mnel/calibration-0.4.json",
        "adapters.mnel.from_provider_study_record",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "ravel:development-record:0.6",
        "ravel",
        "ravel-development-record",
        "ravel-development-record/0.6-preregistration",
        "RAVEL",
        "4b7c3c5503ec6bd11a7ffb96cbb32599cd1f342c",
        "ravel_versions/0.6/ravel-0.6-development-record.json",
        "sha256:45c6cf730df5a8f8da09923bf114f2f5fe0b51d71e7fdeafbcc2c5ac493d4839",
        "compat/ravel/ravel-0.6-development-record.json",
        "adapters.ravel.knowledge_view",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("promotion_authority", "learning_disposition"),
    ),
    _c(
        "ravel:matched-compute:0.6",
        "ravel",
        "ravel-matched-compute",
        "0.1",
        "RAVEL",
        "4b7c3c5503ec6bd11a7ffb96cbb32599cd1f342c",
        "ravel_versions/0.6/ravel-0.6-matched-compute.schema.json",
        "sha256:5da7b39b3faa61985bdc4c1403752d2e3f55db293186e14f9a19e5ef9f9cd5b2",
        "compat/ravel/matched-compute-0.6.json",
        "adapters.ravel.from_development_record",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("comparator_result",),
    ),
    _c(
        "ravel:transaction:0.6",
        "ravel",
        "ravel-transaction",
        "0.1",
        "RAVEL",
        "4b7c3c5503ec6bd11a7ffb96cbb32599cd1f342c",
        "ravel_versions/0.6/ravel-0.6-transaction.schema.json",
        "sha256:ffc6b887e95ff4ad2c0ace210cb775f80343f0da9ad7a90896333263d517ecc4",
        "compat/ravel/transaction-0.6.json",
        "adapters.ravel.from_development_record",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("authority",),
    ),
    _c(
        "mncs:gate-result:0.2",
        "mncs",
        "mncs-gate-result",
        "0.2",
        "machine-native-complexity-standard",
        "49400a41f3b7b36de8a25e6cac1141d3980878be",
        "schemas/mncs-gate-result.schema.json",
        "sha256:324bac4cab9521eb1a9e34e352287be2c0c1ba1e0335b5f2da0b6beaf6817588",
        None,
        "adapters.mncs.from_mncs_result",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("producer_result_fixture",),
    ),
    _c(
        "mncs:execution-receipt:0.1-experimental",
        "mncs",
        "mncs-execution-receipt",
        "0.1-experimental",
        "machine-native-complexity-standard",
        "49400a41f3b7b36de8a25e6cac1141d3980878be",
        "schemas/mncs-execution-receipt-0.1.schema.json",
        "sha256:f2e1860405052a40b100bead7c27dbe0cc3ac11d03dccca3fcb643b350ecab6e",
        "compat/mncs/execution-receipt-0.1.json",
        "adapters.mncs.from_mncs_execution_receipt",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "mncs:execution-bundle:0.1-experimental",
        "mncs",
        "mncs-execution-bundle",
        "0.1-experimental",
        "machine-native-complexity-standard",
        "49400a41f3b7b36de8a25e6cac1141d3980878be",
        "schemas/mncs-execution-bundle-0.1.schema.json",
        "sha256:4c90c6351dc0cb434761437c479028c359023493b5281a6a43a7e36b1537fc21",
        "compat/mncs/execution-bundle-0.1.json",
        "adapters.mncs.from_mncs_execution_bundle",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "mncs:execution-placement:0.1-experimental",
        "mncs",
        "mncs-execution-placement",
        "0.1-experimental",
        "machine-native-complexity-standard",
        "49400a41f3b7b36de8a25e6cac1141d3980878be",
        "schemas/mncs-execution-placement-evidence.schema.json",
        "sha256:6da5b4ba11a95385d758cbc114fb25fe0f8153034153aa4e3f4560e5af77af24",
        "compat/mncs/execution-placement-0.1.json",
        "adapters.mncs.from_mncs_execution_placement",
        CompatibilityStatus.COMPATIBLE,
    ),
    _c(
        "mncs-language:semantic-identities:0.1",
        "mncs-language",
        "semantic-identities",
        "0.1",
        "mncs-language",
        "26cd7f015cb857abe3f0601780de096e04dea7b4",
        "crates/mncs-model/src/identity.rs",
        "sha256:8fd43741728c7879fa2b7717e1d762787521af7ef80b2f4f18803b06dbe464f2",
        "compat/mncs-language/semantic-identity-boundary.json",
        "adapters.language.from_language_identity",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("semantic_graph_payload",),
    ),
    _c(
        "mncs-language:executable-body:0.2",
        "mncs-language",
        "executable-semantic-body",
        "0.2",
        "mncs-language",
        "26cd7f015cb857abe3f0601780de096e04dea7b4",
        "crates/mncs-model/src/body.rs",
        "sha256:29863bd69f45fe1c177585e55269b51aeda617e8dd952abd513b139142ce3179",
        "compat/mncs-language/executable-body-0.2.json",
        "adapters.language.from_executable_artifact",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("semantic_graph_payload",),
    ),
    _c(
        "mncs-language:verifier-artifact:0.2",
        "mncs-language",
        "verifier-artifact",
        "0.2",
        "mncs-language",
        "26cd7f015cb857abe3f0601780de096e04dea7b4",
        "crates/mncs-model/src/verifier.rs",
        "sha256:bcadbba5859cca67a02ff18dc0206104b4b1abc55dfaeaa9c6e0b150590f9de4",
        "compat/mncs-language/verifier-result-0.2.json",
        "adapters.language.from_verifier_artifact",
        CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        ("current_semantic_identities",),
    ),
    _c(
        "mncs-validator-rs:conformance-corpus:l5",
        "mncs-validator-rs",
        "conformance-corpus",
        "fixture-l5-pass",
        "mncs-validator-rs",
        "4c050b77b8cef10128c61adb009d20683643af5c",
        "fixtures/conformance-corpus/valid/l5-pass/manifest.json",
        "sha256:cc16ac61c294ee224e7d20198a26014326960a0f6b7611005d5fd77037b3831f",
        None,
        None,
        CompatibilityStatus.UNKNOWN,
        ("validator_output_contract",),
    ),
)


def contracts() -> tuple[ProducerContract, ...]:
    return _CONTRACTS


def contracts_for(producer: str) -> tuple[ProducerContract, ...]:
    return tuple(item for item in _CONTRACTS if item.producer == producer)


def contract_for(
    producer: str,
    *,
    record_type: str | None = None,
    schema_version: str | None = None,
    contract_id: str | None = None,
) -> ProducerContract | None:
    """Resolve exactly one contract; ambiguous producer-only lookup fails closed."""

    matches = [item for item in _CONTRACTS if item.producer == producer]
    if contract_id is not None:
        matches = [item for item in matches if item.contract_id == contract_id]
    if record_type is not None:
        matches = [item for item in matches if item.record_type == record_type]
    if schema_version is not None:
        matches = [item for item in matches if item.schema_version == schema_version]
    if len(matches) > 1:
        raise ValueError(
            "AMBIGUOUS_PRODUCER_CONTRACT: "
            + producer
            + ":"
            + ",".join(item.contract_id for item in matches)
        )
    return matches[0] if matches else None


def resolve_contract(record: Mapping[str, object]) -> ContractResolution:
    """Resolve a producer record using explicit family/version fields."""

    producer = record.get("producer") or record.get("producer_type")
    record_type = record.get("record_type") or record.get("recordType")
    schema_version = record.get("schema_version") or record.get("schema")
    if not isinstance(producer, str) or not producer:
        return ContractResolution(
            None,
            (Diagnostic("UNKNOWN_PRODUCER", "producer", "producer identity is required"),),
        )
    try:
        contract = contract_for(
            producer,
            record_type=str(record_type) if record_type else None,
            schema_version=str(schema_version) if schema_version else None,
        )
    except ValueError as exc:
        return ContractResolution(
            None,
            (Diagnostic("AMBIGUOUS_PRODUCER_CONTRACT", "record", str(exc)),),
        )
    if contract is None:
        code = "UNKNOWN_RECORD_TYPE" if record_type else "UNSUPPORTED_SOURCE_VERSION"
        return ContractResolution(
            None,
            (
                Diagnostic(
                    code, "record_type" if record_type else "schema_version", "no contract matches"
                ),
            ),
        )
    return ContractResolution(contract)


def _read_bounded(path: Path) -> bytes:
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError(f"source file exceeds {MAX_SOURCE_BYTES} bytes")
    return path.read_bytes()


def _git_head(repo: Path) -> str | None:
    git = repo / ".git"
    if git.is_file():
        text = _read_bounded(git).decode("utf-8", errors="replace").strip()
        if text.startswith("gitdir:"):
            git = (repo / text.split(":", 1)[1].strip()).resolve()
    head_path = git / "HEAD"
    if not head_path.is_file():
        return None
    head = _read_bounded(head_path).decode("utf-8", errors="replace").strip()
    if not head.startswith("ref: "):
        return head or None
    ref = head[5:]
    ref_path = git / ref
    if ref_path.is_file():
        return _read_bounded(ref_path).decode("utf-8", errors="replace").strip() or None
    packed = git / "packed-refs"
    if packed.is_file():
        for line in _read_bounded(packed).decode("utf-8", errors="replace").splitlines():
            if line and not line.startswith("#") and " " in line:
                commit, packed_ref = line.split(" ", 1)
                if packed_ref == ref:
                    return commit
    return None


def check_local(contract: ProducerContract, repo: Path) -> CompatibilityAssessment:
    """Inspect a local producer checkout without invoking Git or modifying it."""

    try:
        resolved_repo = repo.expanduser().resolve(strict=True)
    except OSError as exc:
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.UNKNOWN,
            diagnostics=(
                Diagnostic("SOURCE_REPOSITORY_UNAVAILABLE", "sourceRepository", str(exc)),
            ),
        )
    if not resolved_repo.is_dir():
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.UNKNOWN,
            diagnostics=(
                Diagnostic(
                    "SOURCE_REPOSITORY_UNAVAILABLE",
                    "sourceRepository",
                    "producer checkout is not a directory",
                ),
            ),
        )
    observed_commit = _git_head(resolved_repo)
    if contract.source_path is None or contract.source_fingerprint is None:
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.UNKNOWN,
            observed_commit=observed_commit,
            diagnostics=(
                Diagnostic(
                    "SOURCE_CONTRACT_UNAVAILABLE",
                    "sourcePath",
                    "no frozen source schema fingerprint is available",
                ),
            ),
        )
    source_path = (resolved_repo / contract.source_path).resolve()
    try:
        source_path.relative_to(resolved_repo)
    except ValueError:
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.UNKNOWN,
            observed_commit=observed_commit,
            diagnostics=(Diagnostic("SOURCE_PATH_INVALID", "sourcePath", "path escapes checkout"),),
        )
    if not source_path.is_file():
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.UNKNOWN,
            observed_commit=observed_commit,
            diagnostics=(
                Diagnostic("SOURCE_SCHEMA_UNAVAILABLE", "sourcePath", "source path is absent"),
            ),
        )
    observed_fingerprint = "sha256:" + hashlib.sha256(_read_bounded(source_path)).hexdigest()
    if observed_fingerprint != contract.source_fingerprint:
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.DRIFTED,
            observed_commit=observed_commit,
            observed_fingerprint=observed_fingerprint,
            diagnostics=(
                Diagnostic(
                    "SOURCE_SCHEMA_DRIFT",
                    "sourceFingerprint",
                    "source content differs from the frozen compatibility contract",
                ),
            ),
        )
    diagnostics: list[Diagnostic] = []
    status = contract.expected_status
    if contract.source_commit and observed_commit and observed_commit != contract.source_commit:
        diagnostics.append(
            Diagnostic(
                "SOURCE_COMMIT_MOVED",
                "sourceCommit",
                "source commit changed while the locked source fingerprint still matches",
                severity="warning",
            )
        )
        if status == CompatibilityStatus.EXACT:
            status = CompatibilityStatus.COMPATIBLE
    return CompatibilityAssessment(
        contract, status, observed_commit, observed_fingerprint, tuple(diagnostics)
    )


def compatibility_report(repositories: Mapping[str, Path]) -> list[CompatibilityAssessment]:
    """Assess every registered contract; omitted repositories remain UNKNOWN."""

    report: list[CompatibilityAssessment] = []
    for contract in _CONTRACTS:
        repository = repositories.get(contract.producer)
        if repository is None:
            report.append(
                CompatibilityAssessment(
                    contract,
                    CompatibilityStatus.UNKNOWN,
                    diagnostics=(
                        Diagnostic(
                            "SOURCE_REPOSITORY_UNAVAILABLE",
                            "sourceRepository",
                            "no local checkout was supplied",
                        ),
                    ),
                )
            )
        else:
            report.append(check_local(contract, repository))
    return report
