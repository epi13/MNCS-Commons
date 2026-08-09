"""Explicit, read-only producer compatibility contracts and drift inspection."""

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


_CONTRACTS = (
    ProducerContract(
        producer="forge",
        record_type="forge-cell-execution",
        schema_version="0.1",
        source_repository="mncs-forge-mcp",
        source_commit="bc9388d0ad8e8be554791def5d8aa6ff2f44d72d",
        source_path="examples/forge-cell/execution-record.json",
        source_fingerprint="sha256:5c9982b94cd7f443ac45445e95ca94b3032712babcdf71e62e5fa0489eef9fbc",
        fixture_path="compat/forge/forge-cell-execution-0.1.json",
        adapter="adapters.forge.from_forge_result",
        expected_status=CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        known_unresolved_fields=("result_identity",),
    ),
    ProducerContract(
        producer="fabric",
        record_type="fabric-execution",
        schema_version="UNKNOWN",
        source_repository="mncs-fabric",
        source_commit=None,
        source_path=None,
        source_fingerprint=None,
        fixture_path=None,
        adapter="adapters.fabric.from_fabric_execution",
        expected_status=CompatibilityStatus.UNKNOWN,
        known_unresolved_fields=("source_schema", "source_commit"),
    ),
    ProducerContract(
        producer="mnel",
        record_type="mnel-ledger-record",
        schema_version="mnel-ledger-record/0.1",
        source_repository="Machine-Native-Experimental-Learning",
        source_commit="7e11fbd15680a034a27e14db32762451c2bd7d17",
        source_path="schemas/mnel-records.schema.json",
        source_fingerprint="sha256:b45e609ddc64c2dd4859c3824048c39516f381e6036e9a3b047ce58b09088d90",
        fixture_path="compat/mnel/mnel-episode-0.1.json",
        adapter="adapters.mnel.from_mnel_observation",
        expected_status=CompatibilityStatus.COMPATIBLE,
    ),
    ProducerContract(
        producer="ravel",
        record_type="ravel-development-record",
        schema_version="ravel-development-record/0.6-preregistration",
        source_repository="RAVEL",
        source_commit="2bc3003f5195fc2d9abbce576615cec5d4279337",
        source_path="ravel_versions/0.6/ravel-0.6-development-record.json",
        source_fingerprint="sha256:45c6cf730df5a8f8da09923bf114f2f5fe0b51d71e7fdeafbcc2c5ac493d4839",
        fixture_path="compat/ravel/ravel-0.6-development-record.json",
        adapter="adapters.ravel.knowledge_view",
        expected_status=CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        known_unresolved_fields=("promotion_authority", "learning_disposition"),
    ),
    ProducerContract(
        producer="mncs-language",
        record_type="semantic-identities",
        schema_version="0.1",
        source_repository="mncs-language",
        source_commit="bbc3cef7142844443a5f75e8be01f4a148572fa8",
        source_path="crates/mncs-model/src/identity.rs",
        source_fingerprint="sha256:8fd43741728c7879fa2b7717e1d762787521af7ef80b2f4f18803b06dbe464f2",
        fixture_path="compat/mncs-language/semantic-identity-boundary.json",
        adapter="adapters.language.from_language_identity",
        expected_status=CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        known_unresolved_fields=("semantic_graph_payload",),
    ),
    ProducerContract(
        producer="mncs",
        record_type="mncs-gate-result",
        schema_version="0.2",
        source_repository="machine-native-complexity-standard",
        source_commit="160358365c4bec8c2c0038e2e2e69da7c4b06911",
        source_path="schemas/mncs-gate-result.schema.json",
        source_fingerprint="sha256:324bac4cab9521eb1a9e34e352287be2c0c1ba1e0335b5f2da0b6beaf6817588",
        fixture_path=None,
        adapter="adapters.mncs.from_mncs_result",
        expected_status=CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
        known_unresolved_fields=("producer_result_fixture",),
    ),
    ProducerContract(
        producer="mncs-validator-rs",
        record_type="conformance-corpus",
        schema_version="fixture-l5-pass",
        source_repository="mncs-validator-rs",
        source_commit="4c050b77b8cef10128c61adb009d20683643af5c",
        source_path="fixtures/conformance-corpus/valid/l5-pass/manifest.json",
        source_fingerprint="sha256:cc16ac61c294ee224e7d20198a26014326960a0f6b7611005d5fd77037b3831f",
        fixture_path=None,
        adapter=None,
        expected_status=CompatibilityStatus.UNKNOWN,
        known_unresolved_fields=("validator_output_contract",),
    ),
)


def contracts() -> tuple[ProducerContract, ...]:
    """Return the frozen in-code registry; callers cannot mutate it."""

    return _CONTRACTS


def contracts_for(producer: str) -> tuple[ProducerContract, ...]:
    return tuple(item for item in _CONTRACTS if item.producer == producer)


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

    diagnostics: list[Diagnostic] = []
    try:
        resolved_repo = repo.expanduser().resolve(strict=True)
    except OSError as exc:
        return CompatibilityAssessment(
            contract,
            CompatibilityStatus.UNKNOWN,
            diagnostics=(
                Diagnostic(
                    "SOURCE_REPOSITORY_UNAVAILABLE",
                    "sourceRepository",
                    str(exc),
                ),
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
        contract,
        status,
        observed_commit=observed_commit,
        observed_fingerprint=observed_fingerprint,
        diagnostics=tuple(diagnostics),
    )


def compatibility_report(repositories: Mapping[str, Path]) -> list[CompatibilityAssessment]:
    """Assess every registered producer; omitted repositories remain UNKNOWN."""

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
