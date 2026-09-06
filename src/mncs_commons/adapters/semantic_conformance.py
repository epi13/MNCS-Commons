"""Semantic-conformance adapter: ingest MNCS conformance evidence inertly.

A ``mncs.conformance-report/1`` document claims: independent system W
executed contract X against implementation Y under environment Z and
observed behavior satisfying (or violating) the declared semantics. This
adapter preserves that claim as an inert Observation without re-running
anything and without promoting local verification authority:

- the report's own verdict (from its summary counts) becomes the
  observation outcome;
- ``independentVerificationStatus`` stays UNKNOWN: Commons confirmation is
  material, not a flag — several observations with distinct worker
  identities over the same subject fingerprint are what independent
  confirmation is built from, and no parallel consensus mechanism is
  invented here;
- content addressing is preserved: the subject fingerprint and the
  per-predicate semantic identities travel verbatim into details.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

REPORT_SCHEMA = "mncs.conformance-report/1"


def _conformance_observation(
    value: Mapping[str, Any],
    *,
    source_identity: str | None,
    subject_identity: str,
    summary: str,
    created_at: str | None,
    outcome: str,
    details: Mapping[str, Any],
    unresolved_fields: list[str] | None = None,
) -> AdapterResult:
    return observation_from_external(
        producer_type="mncs-conformance",
        producer_id="mncs-conformance",
        source_identity=source_identity,
        subject_type="semantic-contract",
        subject_identity=subject_identity,
        summary=summary,
        evidence_ids=[source_identity] if source_identity else [],
        scope_context={
            "reportSchemaVersion": value.get("schema_version"),
            "subjectModule": value.get("subject_module"),
            "seed": value.get("seed"),
        },
        created_at=created_at,
        source_version=str(value.get("generator")) if value.get("generator") else None,
        unresolved_fields=unresolved_fields,
        details={"outcome": outcome, **dict(details)},
    )


def conformance_report_summary(value: Mapping[str, Any]) -> dict[str, int]:
    """Project a report summary to its verdict-relevant counts."""
    summary = value.get("summary")
    if not isinstance(summary, dict):
        return {"pass": 0, "fail": 0, "unknown": 0, "unsupported": 0}
    counts = {}
    for key in ("pass", "fail", "unknown", "unsupported"):
        count = summary.get(key)
        counts[key] = count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0
    return counts


def from_conformance_report(
    value: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Ingest one conformance report as an inert Observation."""
    if not isinstance(value, Mapping) or value.get("schema_version") != REPORT_SCHEMA:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNKNOWN_CONFORMANCE_SCHEMA_VERSION",
                    "schema_version",
                    "conformance report schema is not mncs.conformance-report/1; no verdict was inferred",
                ),
            ),
            str(value.get("schema_version")) if isinstance(value, Mapping) and value.get("schema_version") else None,
            recognized=True,
            unresolved_fields=("schema_version",),
        )
    summary = value.get("summary")
    predicates = value.get("predicates")
    if not isinstance(summary, Mapping) or not isinstance(predicates, list):
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "MALFORMED_CONFORMANCE_REPORT",
                    "summary",
                    "conformance report has no summary/predicates; it establishes no claim",
                ),
            ),
            REPORT_SCHEMA,
            recognized=True,
            unresolved_fields=("summary", "predicates"),
        )
    counts = conformance_report_summary(value)
    tested = sum(1 for entry in predicates if isinstance(entry, Mapping) and entry.get("status") == "tested")
    backends = sorted(
        {
            observation.get("backend")
            for entry in predicates
            if isinstance(entry, Mapping)
            for case in (entry.get("cases") or [])
            if isinstance(case, Mapping)
            for observation in (case.get("backends") or [])
            if isinstance(observation, Mapping) and observation.get("backend")
        }
    )
    worker = value.get("worker") if isinstance(value.get("worker"), Mapping) else {}
    predicate_identities = [
        entry.get("predicate_identity")
        for entry in predicates
        if isinstance(entry, Mapping) and entry.get("predicate_identity")
    ]
    if tested == 0:
        outcome = ResultStatus.UNKNOWN.value
        summary_text = "Conformance report with no tested predicates establishes no claim."
    elif counts["fail"] > 0:
        outcome = ResultStatus.FAIL.value
        summary_text = (
            f"Conformance observed contract violations: fail={counts['fail']} "
            f"pass={counts['pass']} unknown={counts['unknown']} unsupported={counts['unsupported']}."
        )
    elif counts["unknown"] > 0:
        outcome = ResultStatus.UNKNOWN.value
        summary_text = (
            f"Conformance inconclusive: unknown={counts['unknown']} "
            f"pass={counts['pass']} unsupported={counts['unsupported']}."
        )
    else:
        outcome = ResultStatus.PASS.value
        summary_text = (
            f"Conformance observed declared semantics: pass={counts['pass']} "
            f"unsupported={counts['unsupported']}."
        )
    fingerprint = value.get("subject_fingerprint")
    return _conformance_observation(
        value,
        source_identity=fingerprint if isinstance(fingerprint, str) and fingerprint else None,
        subject_identity=subject_identity,
        summary=summary_text,
        created_at=created_at,
        outcome=outcome,
        details={
            "conformanceSummary": counts,
            "testedPredicates": tested,
            "backendsExercised": backends,
            "worker": dict(worker),
            "seed": value.get("seed"),
            "subjectModule": value.get("subject_module"),
            "subjectFingerprint": fingerprint,
            "predicateIdentities": predicate_identities,
            "independentVerificationStatus": ResultStatus.UNKNOWN.value,
            "conformanceReport": dict(value),
        },
        unresolved_fields=[] if fingerprint else ["subject_fingerprint"],
    )
