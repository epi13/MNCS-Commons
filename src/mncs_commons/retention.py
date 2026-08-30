"""Operator retention policy: classify, protect, and plan compaction.

Execution exhaust is disposable until promotion. This module never grants
execution authority and never deletes because a consumer asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .canonical import canonical_json
from .models import RecordKind
from .store import CommonsStore, StoreError, _atomic_write

RETENTION_POLICY_SCHEMA = "commons.mncs.dev/retention-policy/v0alpha1"
RETENTION_PINS_SCHEMA = "commons.mncs.dev/retention-pins/v0alpha1"
RETENTION_CLASSES = ("canonical", "evidence", "diagnostic", "ephemeral")
PROTECTED_KINDS = {
    RecordKind.CONCEPT_EXPERIMENT.value,
    RecordKind.FAILURE_CLASSIFICATION.value,
    RecordKind.CLAIM.value,
    RecordKind.DECISION.value,
    RecordKind.FINDING.value,
    RecordKind.QUESTION.value,
    RecordKind.HYPOTHESIS.value,
    RecordKind.FAILED_APPROACH.value,
    RecordKind.HANDOFF.value,
    RecordKind.THREAD.value,
    "Epoch",
    "EpochSummary",
    "ReplicationSeries",
    "ObservationSeries",
}
DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": RETENTION_POLICY_SCHEMA,
    "soft_ledger_bytes": 32 * 1024 * 1024,
    "archive_pressure_bytes": 40 * 1024 * 1024,
    "emergency_ledger_bytes": 56 * 1024 * 1024,
    "hot_record_target": 4000,
    "ephemeral_ttl_days": 7,
    "diagnostic_ttl_days": 60,
    "evidence_archive": True,
    "canonical_permanent": True,
}


def _now(value: str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _created_at(record: Mapping[str, Any]) -> datetime | None:
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    raw = metadata.get("createdAt")
    if not isinstance(raw, str):
        return None
    try:
        return _now(raw)
    except ValueError:
        return None


def classify_record(record: Mapping[str, Any]) -> str:
    """Assign a retention class. Promotion happens by kind and references."""

    kind = str(record.get("kind") or "")
    if kind in PROTECTED_KINDS:
        return "canonical"
    details_value = record.get("details")
    details: Mapping[str, Any] = details_value if isinstance(details_value, Mapping) else {}
    if kind == RecordKind.WORK_REQUEST.value:
        state = str(details.get("requestState") or "open")
        if state in {"open", "claimed", "responded"}:
            return "canonical"
        return "diagnostic"
    if kind == RecordKind.ADVISORY.value:
        return "diagnostic"
    if kind == RecordKind.ARTIFACT_REFERENCE.value:
        return "evidence"
    if kind == RecordKind.REPLICATION.value:
        outcome = str(details.get("outcome") or "")
        if outcome == "FAIL":
            return "evidence"
        return "ephemeral"
    if kind == RecordKind.OBSERVATION.value:
        outcome = str(details.get("outcome") or "")
        if outcome in {"FAIL", "UNKNOWN"}:
            return "diagnostic"
        labels = (
            (record.get("metadata") or {}).get("labels")
            if isinstance(record.get("metadata"), Mapping)
            else []
        )
        if isinstance(labels, list) and "canonical" in labels:
            return "canonical"
        if isinstance(labels, list) and "evidence" in labels:
            return "evidence"
        return "ephemeral"
    return "diagnostic"


def referenced_digests(record: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    for key in ("contentDigest",):
        value = record.get(key)
        if isinstance(value, str) and value.startswith("sha256:"):
            found.add(value)
    provenance_value = record.get("provenance")
    provenance: Mapping[str, Any] = (
        provenance_value if isinstance(provenance_value, Mapping) else {}
    )
    for item in provenance.get("sourceRecords") or []:
        if isinstance(item, str) and item.startswith("sha256:"):
            found.add(item)
    for relation in record.get("relationships") or []:
        if isinstance(relation, Mapping):
            target = relation.get("target")
            if isinstance(target, str) and target.startswith("sha256:"):
                found.add(target)
            digest = relation.get("contentDigest")
            if isinstance(digest, str) and digest.startswith("sha256:"):
                found.add(digest)
    details_value = record.get("details")
    details: Mapping[str, Any] = details_value if isinstance(details_value, Mapping) else {}
    for key in (
        "targetRecord",
        "epochId",
        "sourceIdentities",
        "representativeEvidence",
        "notableFailures",
    ):
        value = details.get(key)
        if isinstance(value, str) and value.startswith("sha256:"):
            found.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith("sha256:"):
                    found.add(item)
    evidence_value = record.get("evidence")
    evidence: list[Any] = evidence_value if isinstance(evidence_value, list) else []
    for item in evidence:
        if isinstance(item, Mapping):
            for key in ("id", "contentDigest"):
                value = item.get(key)
                if isinstance(value, str) and value.startswith("sha256:"):
                    found.add(value)
    return found


def protection_graph(records: Iterable[Mapping[str, Any]]) -> set[str]:
    """Digests that must remain retrievable because a live knowledge object names them."""

    records = list(records)
    by_digest = {
        str(item.get("contentDigest")): item
        for item in records
        if isinstance(item.get("contentDigest"), str)
    }
    roots = {
        digest
        for digest, record in by_digest.items()
        if classify_record(record) == "canonical"
        or str(record.get("kind")) in PROTECTED_KINDS
    }
    protected = set(roots)
    stack = list(roots)
    while stack:
        current = stack.pop()
        record = by_digest.get(current)
        if record is None:
            continue
        for related in referenced_digests(record):
            if related not in protected:
                protected.add(related)
                stack.append(related)
    return protected


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    soft_ledger_bytes: int = DEFAULT_POLICY["soft_ledger_bytes"]
    archive_pressure_bytes: int = DEFAULT_POLICY["archive_pressure_bytes"]
    emergency_ledger_bytes: int = DEFAULT_POLICY["emergency_ledger_bytes"]
    hot_record_target: int = DEFAULT_POLICY["hot_record_target"]
    ephemeral_ttl_days: int = DEFAULT_POLICY["ephemeral_ttl_days"]
    diagnostic_ttl_days: int = DEFAULT_POLICY["diagnostic_ttl_days"]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "RetentionPolicy":
        raw = dict(DEFAULT_POLICY)
        if value:
            raw.update(value)
        return cls(
            soft_ledger_bytes=int(raw["soft_ledger_bytes"]),
            archive_pressure_bytes=int(raw["archive_pressure_bytes"]),
            emergency_ledger_bytes=int(raw["emergency_ledger_bytes"]),
            hot_record_target=int(raw["hot_record_target"]),
            ephemeral_ttl_days=int(raw["ephemeral_ttl_days"]),
            diagnostic_ttl_days=int(raw["diagnostic_ttl_days"]),
        )


class RetentionController:
    """Store-local operator policy. Models cannot authorize destruction."""

    def __init__(self, store: CommonsStore) -> None:
        self.store = store
        self.policy_path = store.root / "retention-policy.json"
        self.pins_path = store.root / "retention-pins.json"

    def policy(self) -> RetentionPolicy:
        if not self.policy_path.exists():
            return RetentionPolicy()
        import json

        value = json.loads(self.policy_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise StoreError("retention policy is not an object")
        return RetentionPolicy.from_mapping(value)

    def write_policy(self, value: Mapping[str, Any]) -> None:
        payload = {**DEFAULT_POLICY, **dict(value), "schema_version": RETENTION_POLICY_SCHEMA}
        _atomic_write(self.policy_path, canonical_json(payload))

    def pins(self) -> dict[str, dict[str, str]]:
        if not self.pins_path.exists():
            return {}
        import json

        value = json.loads(self.pins_path.read_text(encoding="utf-8"))
        pins = value.get("pins") if isinstance(value, dict) else None
        if not isinstance(pins, dict):
            return {}
        return {
            str(digest): dict(meta)
            for digest, meta in pins.items()
            if isinstance(meta, dict)
        }

    def pin(self, digest: str, *, reason: str, now: str | None = None) -> dict[str, Any]:
        if not digest.startswith("sha256:"):
            raise StoreError("pin target must be a content digest")
        pins = self.pins()
        pins[digest] = {
            "pinnedAt": (now or _now().isoformat().replace("+00:00", "Z")),
            "reason": reason,
        }
        _atomic_write(
            self.pins_path,
            canonical_json({"schema_version": RETENTION_PINS_SCHEMA, "pins": pins}),
        )
        return {"pinned": digest, "reason": reason}

    def unpin(self, digest: str) -> dict[str, Any]:
        pins = self.pins()
        pins.pop(digest, None)
        _atomic_write(
            self.pins_path,
            canonical_json({"schema_version": RETENTION_PINS_SCHEMA, "pins": pins}),
        )
        return {"unpinned": digest}

    def status(self) -> dict[str, Any]:
        usage = self.store.storage_usage()
        records = list(self.store.records())
        policy = self.policy()
        classes: dict[str, int] = {name: 0 for name in RETENTION_CLASSES}
        for record in records:
            classes[classify_record(record)] = classes.get(classify_record(record), 0) + 1
        protected = protection_graph(records) | set(self.pins())
        ledger_bytes = int(usage["ledgerBytes"])
        pressure = "normal"
        if ledger_bytes >= policy.emergency_ledger_bytes:
            pressure = "emergency"
        elif ledger_bytes >= policy.archive_pressure_bytes:
            pressure = "archive"
        elif ledger_bytes >= policy.soft_ledger_bytes:
            pressure = "soft"
        return {
            "usage": usage,
            "pressure": pressure,
            "policy": {
                "softLedgerBytes": policy.soft_ledger_bytes,
                "archivePressureBytes": policy.archive_pressure_bytes,
                "emergencyLedgerBytes": policy.emergency_ledger_bytes,
                "hotRecordTarget": policy.hot_record_target,
                "ephemeralTtlDays": policy.ephemeral_ttl_days,
                "diagnosticTtlDays": policy.diagnostic_ttl_days,
            },
            "recordsByClass": classes,
            "pinned": sorted(self.pins()),
            "protectedCount": len(protected),
            "executionAuthority": "none",
        }

    def plan(self, *, now: str | None = None) -> dict[str, Any]:
        policy = self.policy()
        records = list(self.store.records())
        protected = protection_graph(records) | set(self.pins())
        current = _now(now)
        candidates: list[dict[str, Any]] = []
        reclaimable = 0
        for record in records:
            digest = str(record.get("contentDigest") or "")
            retention = classify_record(record)
            created = _created_at(record)
            age_days = (current - created).days if created is not None else 0
            eligible = False
            reason = "protected"
            if digest in protected:
                reason = "referenced-or-canonical"
            elif retention == "ephemeral" and age_days >= policy.ephemeral_ttl_days:
                eligible = True
                reason = "ephemeral-ttl"
            elif retention == "diagnostic" and age_days >= policy.diagnostic_ttl_days:
                eligible = True
                reason = "diagnostic-ttl"
            elif retention == "evidence" and policy:
                eligible = False
                reason = "evidence-archive-only"
            encoded = canonical_json(record)
            if eligible:
                reclaimable += len(encoded)
                candidates.append(
                    {
                        "contentDigest": digest,
                        "kind": record.get("kind"),
                        "class": retention,
                        "reason": reason,
                        "bytes": len(encoded),
                    }
                )
        usage = self.store.storage_usage()
        return {
            "usage": usage,
            "protectedCount": len(protected),
            "candidateCount": len(candidates),
            "reclaimableBytes": reclaimable,
            "candidates": candidates[:200],
            "blocked": []
            if candidates
            else ["no TTL-eligible unreferenced records"],
            "executionAuthority": "none",
        }

    def compact(
        self, *, confirm: bool = False, dry_run: bool = True, now: str | None = None
    ) -> dict[str, Any]:
        plan = self.plan(now=now)
        if dry_run or not confirm:
            return {**plan, "action": "dry-run", "applied": False}
        from .archive import create_archive, verify_archive
        from .store import _file_lock

        records = list(self.store.records())
        events = list(self.store.events())
        candidate_ids = {item["contentDigest"] for item in self._all_candidates(records, now=now)}
        if not candidate_ids:
            return {**plan, "action": "blocked", "applied": False}
        archive = create_archive(self.store, records=records, events=events, now=now)
        verification = verify_archive(self.store, str(archive["archiveId"]))
        keep = [item for item in records if item.get("contentDigest") not in candidate_ids]
        keep_ids = {str(item.get("contentDigest")) for item in keep}
        keep_events = [
            item
            for item in events
            if str((item.get("target") or {}).get("contentDigest")) in keep_ids
        ]
        staging = self.store.root / ".compaction-staging"
        if staging.exists():
            import shutil

            shutil.rmtree(staging)
        replacement = type(self.store)(staging)
        replacement.init()
        replacement.add_snapshot(
            {
                "schema_version": "commons.mncs.dev/store-snapshot/v0alpha1",
                "archiveId": archive["archiveId"],
                "archiveIdentity": archive["bundleDigest"],
                "archivedThroughSequence": self.store.storage_usage()["ledgerEntries"],
                "hotRecordCount": len(keep),
                "createdAt": now or _now().isoformat().replace("+00:00", "Z"),
                "authority": "operator-compaction",
                "executionAuthority": "none",
            }
        )
        for record in keep:
            replacement.add_record(dict(record))
        for event in keep_events:
            replacement.add_event(dict(event))
        if not replacement.verify().valid:
            raise StoreError("compaction staging store failed verification")
        with _file_lock(self.store.lock_path):
            self.store.install_generation(staging)
        return {
            **plan,
            "action": "compacted",
            "applied": True,
            "archive": archive,
            "archiveVerification": verification,
            "hotRecords": len(keep),
            "removedFromHot": len(candidate_ids),
        }

    def _all_candidates(
        self, records: list[Mapping[str, Any]], *, now: str | None
    ) -> list[dict[str, Any]]:
        policy = self.policy()
        protected = protection_graph(records) | set(self.pins())
        current = _now(now)
        selected: list[dict[str, Any]] = []
        for record in records:
            digest = str(record.get("contentDigest") or "")
            retention = classify_record(record)
            created = _created_at(record)
            age_days = (current - created).days if created is not None else 0
            if digest in protected:
                continue
            if retention == "ephemeral" and age_days >= policy.ephemeral_ttl_days:
                selected.append({"contentDigest": digest, "class": retention})
            elif retention == "diagnostic" and age_days >= policy.diagnostic_ttl_days:
                selected.append({"contentDigest": digest, "class": retention})
        return selected
