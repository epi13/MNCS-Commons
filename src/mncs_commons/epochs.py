"""Bounded compute-epoch records.

An epoch is a named work window, not a scheduler. Cron, systemd, Fabric
ticks, or a later orchestrator can open and close epochs. Commons stores
the resulting knowledge; it does not authorize execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .canonical import canonical_digest

EPOCH_SCHEMA = "commons.mncs.dev/epoch/v0alpha1"
EPOCH_SUMMARY_SCHEMA = "commons.mncs.dev/epoch-summary/v0alpha1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def epoch_identity(material: Mapping[str, Any]) -> str:
    return canonical_digest(dict(material))


def make_epoch_record(
    *,
    started_at: str,
    ended_at: str | None = None,
    participants: list[str] | None = None,
    workers: list[str] | None = None,
    models: list[str] | None = None,
    projects: list[str] | None = None,
    predecessor: str | None = None,
    fabric_version: str | None = None,
    controller_version: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    details = {
        "schema": EPOCH_SCHEMA,
        "windowStart": started_at,
        "windowEnd": ended_at,
        "participants": list(participants or []),
        "workers": list(workers or []),
        "models": list(models or []),
        "projects": list(projects or []),
        "predecessor": predecessor,
        "fabricVersion": fabric_version,
        "controllerVersion": controller_version,
        "workAttempted": [],
        "completed": [],
        "failed": [],
        "blocked": [],
    }
    stamp = created_at or started_at or _utc_now()
    identity = epoch_identity(
        {"started_at": started_at, "participants": details["participants"], "workers": details["workers"]}
    )
    return _knowledge_record(
        "Epoch",
        record_id=f"epoch:{identity.removeprefix('sha256:')[:16]}",
        summary=f"Compute epoch {started_at}",
        details=details,
        created_at=stamp,
        labels=["epoch"],
    )


def make_epoch_summary(
    epoch: Mapping[str, Any],
    *,
    attempted: list[str],
    changed: list[str],
    discoveries: list[str],
    failures: list[str],
    claims: list[str],
    unresolved: list[str],
    continuation: list[str],
    source_identities: list[str],
    created_at: str | None = None,
) -> dict[str, Any]:
    epoch_digest = str(epoch.get("contentDigest") or "")
    details = {
        "schema": EPOCH_SUMMARY_SCHEMA,
        "epochId": epoch_digest,
        "attempted": list(attempted),
        "changed": list(changed),
        "discoveries": list(discoveries),
        "meaningfulFailures": list(failures),
        "claims": list(claims),
        "unresolved": list(unresolved),
        "recommendedContinuation": list(continuation),
        "sourceIdentities": list(source_identities),
    }
    return _knowledge_record(
        "EpochSummary",
        record_id=f"epoch-summary:{epoch_digest.removeprefix('sha256:')[:16]}",
        summary="Structured summary of a completed compute epoch.",
        details=details,
        created_at=created_at or _utc_now(),
        labels=["epoch", "canonical"],
        relationships=[{"type": "derived_from", "target": epoch_digest}] if epoch_digest else [],
    )


def make_replication_series(
    *,
    target: str,
    passes: int,
    failures: int,
    workers: list[str],
    models: list[str],
    first_observed: str,
    last_observed: str,
    source_identities: list[str],
    notable_failures: list[str],
    created_at: str | None = None,
) -> dict[str, Any]:
    details = {
        "target": target,
        "passes": int(passes),
        "failures": int(failures),
        "workers": list(workers),
        "models": list(models),
        "firstObserved": first_observed,
        "lastObserved": last_observed,
        "sourceIdentities": list(source_identities),
        "notableFailures": list(notable_failures),
        "representativeEvidence": list(source_identities[:3]),
    }
    return _knowledge_record(
        "ReplicationSeries",
        record_id=f"replication-series:{target.removeprefix('sha256:')[:16]}",
        summary=f"Aggregated replications of {target}: {passes} pass, {failures} fail.",
        details=details,
        created_at=created_at or _utc_now(),
        labels=["aggregate", "canonical"],
        relationships=[{"type": "derived_from", "target": item} for item in source_identities[:16]],
    )


def _knowledge_record(
    kind: str,
    *,
    record_id: str,
    summary: str,
    details: Mapping[str, Any],
    created_at: str,
    labels: list[str],
    relationships: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": kind,
        "metadata": {
            "recordId": record_id,
            "createdAt": created_at,
            "author": {"type": "operator", "id": "mncs:information-lifecycle"},
            "labels": labels,
        },
        "subject": {"type": "work-request", "identity": record_id},
        "scope": {
            "context": {"lifecycle": "information"},
            "limitations": ["coordination memory only; no execution authority"],
        },
        "statement": {"summary": summary, "details": "Structured epoch/retention knowledge."},
        "evidence": [],
        "reproduction": {"prerequisites": [], "procedure": [], "expected": []},
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "operator", "id": "mncs:information-lifecycle"},
            "sourceRecords": list(details.get("sourceIdentities") or []),
        },
        "confidence": {"level": "medium", "rationale": "operator-authored structured summary"},
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": False,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": ["epoch continuation"]},
        "relationships": list(relationships or []),
        "details": dict(details),
    }
