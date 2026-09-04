"""Storage economics: measure first, bound deterministically.

Storage must grow with important retained knowledge, not total agent
activity.  A ``StorageAccount`` measures one node along the axes the mesh
cares about; ``check_budgets`` turns a ``MeshPolicy`` into pass/fail facts.

.. code-block:: text

    routine execution exhaust   short TTL,        never exchanged
    diagnostic exhaust          TTL,              usually not exchanged
    Observation                 bounded,          selective metadata
    Finding / Claim             hot,              hot compact record
    Replication                 hot,              hot compact record
    full evidence               local CAS,        fetch on demand
    accepted knowledge          durable,          broadly replicated
    promotion-critical evidence durable,          intentionally mirrored
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .node import CommonsNode


@dataclass(frozen=True, slots=True)
class StorageAccount:
    ledger_entries: int
    content_bytes: int
    content_files: int
    ledger_bytes: int
    cas_blobs: int
    cas_bytes: int
    exchanged_bytes: int
    foreign_evidence_bytes: int
    records_by_kind: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ledgerEntries": self.ledger_entries,
            "contentBytes": self.content_bytes,
            "contentFiles": self.content_files,
            "ledgerBytes": self.ledger_bytes,
            "casBlobs": self.cas_blobs,
            "casBytes": self.cas_bytes,
            "exchangedBytes": self.exchanged_bytes,
            "foreignEvidenceBytes": self.foreign_evidence_bytes,
            "recordsByKind": dict(self.records_by_kind),
        }


def account_node(node: "CommonsNode", *, exchanged_bytes: int = 0) -> StorageAccount:
    """Measure a node's storage footprint deterministically."""

    usage = node.store.storage_usage()
    cas_blobs = 0
    cas_bytes = 0
    foreign_evidence_bytes = 0
    if node.cas_path.is_dir():
        for blob in sorted(node.cas_path.glob("*.blob")):
            try:
                size = blob.stat().st_size
            except OSError:
                continue
            cas_blobs += 1
            cas_bytes += size
    kinds: dict[str, int] = {}
    for record in node.store.records():
        kind = str(record.get("kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return StorageAccount(
        ledger_entries=int(usage.get("ledgerEntries", 0)),
        content_bytes=int(usage.get("contentBytes", 0)),
        content_files=int(usage.get("contentFiles", 0)),
        ledger_bytes=int(usage.get("ledgerBytes", 0)),
        cas_blobs=cas_blobs,
        cas_bytes=cas_bytes,
        exchanged_bytes=exchanged_bytes,
        foreign_evidence_bytes=foreign_evidence_bytes,
        records_by_kind=tuple(sorted(kinds.items())),
    )


def check_budgets(node: "CommonsNode", account: StorageAccount) -> dict[str, object]:
    """Evaluate the node's policy budgets against a measured account."""

    checks = {
        "hotByteBudget": account.content_bytes <= node.policy.hot_byte_budget,
        "foreignEvidenceBudget": account.foreign_evidence_bytes
        <= node.policy.foreign_evidence_budget,
    }
    return {
        "budgets": checks,
        "withinBudgets": all(checks.values()),
        "policy": node.policy.as_dict(),
        "account": account.as_dict(),
    }
