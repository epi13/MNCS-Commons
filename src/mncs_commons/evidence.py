"""Bounded evidence-lineage views over immutable Commons records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .models import Diagnostic
from .query import bounded_graph


@dataclass(frozen=True, slots=True)
class EvidenceTrace:
    """A deterministic, bounded view; it never infers truth from graph shape."""

    records: tuple[Mapping[str, Any], ...]
    edges: tuple[Mapping[str, str], ...]
    unresolved: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "records": list(self.records),
            "edges": list(self.edges),
            "unresolved": list(self.unresolved),
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "truncated": self.truncated,
            "authority": "information-only; no technical truth or command authority inferred",
        }


def _references(record: Mapping[str, Any]) -> dict[str, set[str]]:
    """Extract only stable, known execution identities from adapter details."""

    details = record.get("details")
    if not isinstance(details, Mapping):
        return {}
    references: dict[str, set[str]] = {}

    def add(family: str, value: Any) -> None:
        if isinstance(value, str) and value:
            references.setdefault(family, set()).add(value)

    receipt = details.get("executionReceipt")
    if isinstance(receipt, Mapping):
        bundle = receipt.get("bundle")
        add("bundle", bundle.get("test_bundle_identity") if isinstance(bundle, Mapping) else None)
        add("candidate", receipt.get("candidate_identity"))
        add("environment", receipt.get("environment_identity"))
    bundle = details.get("executionBundle")
    if isinstance(bundle, Mapping):
        add("bundle", bundle.get("bundle_identity"))
        add("candidate", bundle.get("input_snapshot_identity"))
    fabric = details.get("fabricExecution")
    if isinstance(fabric, Mapping):
        add("artifact", fabric.get("artifact_manifest_identity"))
        add("candidate", fabric.get("candidate_identity"))
        node = fabric.get("node")
        add("environment", node.get("environment_identity") if isinstance(node, Mapping) else None)
    return references


def _identity_aliases(record: Mapping[str, Any]) -> set[str]:
    aliases = {str(record.get("contentDigest"))}
    metadata = record.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("recordId"):
        aliases.add(str(metadata["recordId"]))
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        source_records = provenance.get("sourceRecords")
        if isinstance(source_records, list):
            aliases.update(str(item) for item in source_records if item)
    return aliases


def evidence_lineage(
    records: Iterable[Mapping[str, Any]],
    roots: Iterable[str],
    *,
    max_depth: int = 3,
    max_nodes: int = 1000,
) -> EvidenceTrace:
    """Trace typed relationships and report bounded execution-binding problems."""

    traversal = bounded_graph(records, roots, max_depth=max_depth, max_nodes=max_nodes)
    aliases: dict[str, Mapping[str, Any]] = {}
    for record in traversal.records:
        for alias in _identity_aliases(record):
            aliases[alias] = record

    unresolved = set(traversal.unresolved)
    diagnostics: list[Diagnostic] = []
    for record in traversal.records:
        for family, values in _references(record).items():
            for value in values:
                if value not in aliases:
                    unresolved.add(value)
                    diagnostics.append(
                        Diagnostic(
                            "UNRESOLVED_EVIDENCE_REFERENCE",
                            f"details.{family}",
                            f"{family} identity is not present in the bounded local trace",
                            severity="warning",
                        )
                    )

    # A receipt and bundle are compatible only when the receipt's declared
    # bundle identity resolves to the bundle record in this trace.
    bundle_aliases = {
        alias
        for alias, record in aliases.items()
        if record.get("subject", {}).get("type") == "execution-bundle"
        or isinstance(record.get("details"), Mapping)
        and "executionBundle" in record["details"]
    }
    for record in traversal.records:
        refs = _references(record).get("bundle", set())
        if refs and bundle_aliases and refs.isdisjoint(bundle_aliases):
            diagnostics.append(
                Diagnostic(
                    "INCOMPATIBLE_EVIDENCE_BINDING",
                    "details.executionReceipt.bundle",
                    "receipt bundle identity does not resolve to a bundle in the trace",
                )
            )

    return EvidenceTrace(
        traversal.records,
        traversal.edges,
        tuple(sorted(unresolved)),
        tuple(sorted(diagnostics, key=lambda item: (item.code, item.path, item.message))),
        traversal.truncated,
    )
