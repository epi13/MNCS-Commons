"""Fail-closed structural validation for the v0alpha1 protocol."""

from __future__ import annotations

from datetime import datetime
from string import hexdigits
from typing import Any, Mapping, TypeGuard

from .canonical import canonical_digest
from .diagnostics import ValidationReport
from .models import (
    API_VERSION,
    EVENT_KIND,
    Diagnostic,
    LifecycleState,
    RecordKind,
    RelationType,
    ResultStatus,
    WorkRequestState,
)
from .protocol import protocol_spec
from .work import validate_work_record

_RECORD_KEYS = {
    "apiVersion",
    "kind",
    "contentDigest",
    "metadata",
    "subject",
    "scope",
    "statement",
    "evidence",
    "reproduction",
    "dependencies",
    "affectedContracts",
    "provenance",
    "confidence",
    "security",
    "lifecycle",
    "relationships",
    "details",
    "extensions",
}
_EVENT_KEYS = {
    "apiVersion",
    "kind",
    "contentDigest",
    "metadata",
    "target",
    "transition",
    "authority",
    "evidence",
    "extensions",
}
_SENSITIVITIES = {"public", "restricted", "sensitive", "security-sensitive"}
_CONFIDENCE = {"low", "medium", "high", "unreported"}
_REQUIRED_DETAILS = {
    RecordKind.OBSERVATION.value: {"outcome"},
    RecordKind.CLAIM.value: {"outcome", "falsifier"},
    RecordKind.WORK_REQUEST.value: {"objective", "requestedKind", "authorityBoundary"},
    RecordKind.REPLICATION.value: {"targetRecord", "outcome", "independence"},
    RecordKind.ADVISORY.value: {"severity", "concern"},
    RecordKind.DECISION.value: {"domain", "rationale", "authorityScope"},
}


def _error(code: str, path: str, message: str) -> Diagnostic:
    return Diagnostic(code, path, message)


def _require_object(
    value: Any, path: str, diagnostics: list[Diagnostic]
) -> TypeGuard[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        diagnostics.append(_error("TYPE_OBJECT", path, "must be an object"))
        return False
    return True


def _require_string(value: Any, path: str, diagnostics: list[Diagnostic]) -> bool:
    if not isinstance(value, str) or not value.strip():
        diagnostics.append(_error("TYPE_STRING", path, "must be a non-empty string"))
        return False
    return True


def _check_keys(
    value: Mapping[str, Any], allowed: set[str], path: str, diagnostics: list[Diagnostic]
) -> None:
    for key in value:
        if key not in allowed:
            diagnostics.append(
                _error("UNKNOWN_FIELD", f"{path}.{key}", "field is not defined by v0alpha1")
            )


def _check_timestamp(value: Any, path: str, diagnostics: list[Diagnostic]) -> None:
    if not _require_string(value, path, diagnostics):
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        diagnostics.append(
            _error("INVALID_TIMESTAMP", path, "must be an ISO-8601 timestamp with timezone")
        )


def _check_metadata(value: Any, diagnostics: list[Diagnostic]) -> None:
    if not _require_object(value, "metadata", diagnostics):
        return
    _check_keys(
        value,
        {"recordId", "createdAt", "author", "labels", "revision", "previousDigest"},
        "metadata",
        diagnostics,
    )
    _check_timestamp(value.get("createdAt"), "metadata.createdAt", diagnostics)
    author = value.get("author")
    if _require_object(author, "metadata.author", diagnostics):
        _require_string(author.get("type"), "metadata.author.type", diagnostics)
        _require_string(author.get("id"), "metadata.author.id", diagnostics)
    labels = value.get("labels", [])
    if not isinstance(labels, list) or not all(isinstance(item, str) for item in labels):
        diagnostics.append(_error("TYPE_LABELS", "metadata.labels", "must be a list of strings"))
    if "revision" in value and (
        not isinstance(value["revision"], int)
        or isinstance(value["revision"], bool)
        or value["revision"] < 1
    ):
        diagnostics.append(
            _error("INVALID_REVISION", "metadata.revision", "must be a positive integer")
        )
    if "previousDigest" in value and not _valid_digest(value["previousDigest"]):
        diagnostics.append(
            _error("INVALID_DIGEST", "metadata.previousDigest", "must be a sha256: digest")
        )


def _check_evidence(value: Any, path: str, diagnostics: list[Diagnostic]) -> None:
    if not isinstance(value, list):
        diagnostics.append(_error("TYPE_ARRAY", path, "must be a list"))
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if _require_object(item, item_path, diagnostics):
            _require_string(item.get("id"), f"{item_path}.id", diagnostics)
            if "status" in item and item["status"] not in {status.value for status in ResultStatus}:
                diagnostics.append(
                    _error(
                        "INVALID_STATUS", f"{item_path}.status", "must be PASS, FAIL, or UNKNOWN"
                    )
                )


def _check_relationships(value: Any, record_id: str | None, diagnostics: list[Diagnostic]) -> None:
    if not isinstance(value, list):
        diagnostics.append(_error("TYPE_ARRAY", "relationships", "must be a list"))
        return
    allowed = {item.value for item in RelationType}
    for index, item in enumerate(value):
        path = f"relationships[{index}]"
        if _require_object(item, path, diagnostics):
            relation = item.get("type")
            extension = isinstance(relation, str) and "/" in relation and relation.split("/", 1)[0]
            if relation not in allowed and not extension:
                diagnostics.append(
                    _error("INVALID_RELATION", f"{path}.type", "relationship type is not supported")
                )
            target = item.get("target")
            _require_string(target, f"{path}.target", diagnostics)
            if record_id and target == record_id:
                diagnostics.append(
                    _error("SELF_RELATION", path, "a record cannot relate to itself")
                )


def _common_record_checks(value: Mapping[str, Any], diagnostics: list[Diagnostic]) -> None:
    _check_metadata(value.get("metadata"), diagnostics)
    subject = value.get("subject")
    if _require_object(subject, "subject", diagnostics):
        _require_string(subject.get("type"), "subject.type", diagnostics)
        _require_string(subject.get("identity"), "subject.identity", diagnostics)
    scope = value.get("scope")
    if _require_object(scope, "scope", diagnostics):
        _check_keys(scope, {"context", "limitations", "reviewAt"}, "scope", diagnostics)
        context = scope.get("context", {})
        if not isinstance(context, Mapping):
            diagnostics.append(_error("TYPE_OBJECT", "scope.context", "must be an object"))
        if "limitations" in scope and (
            not isinstance(scope["limitations"], list)
            or not all(isinstance(x, str) for x in scope["limitations"])
        ):
            diagnostics.append(
                _error("TYPE_ARRAY_STRINGS", "scope.limitations", "must be a list of strings")
            )
        if "reviewAt" in scope:
            _check_timestamp(scope["reviewAt"], "scope.reviewAt", diagnostics)
    statement = value.get("statement")
    if _require_object(statement, "statement", diagnostics):
        _require_string(statement.get("summary"), "statement.summary", diagnostics)
    _check_evidence(value.get("evidence"), "evidence", diagnostics)
    for key in ("dependencies", "affectedContracts"):
        items = value.get(key)
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            diagnostics.append(_error("TYPE_ARRAY_STRINGS", key, "must be a list of strings"))
    provenance = value.get("provenance")
    if _require_object(provenance, "provenance", diagnostics):
        producer = provenance.get("producer")
        if _require_object(producer, "provenance.producer", diagnostics):
            _require_string(producer.get("type"), "provenance.producer.type", diagnostics)
            _require_string(producer.get("id"), "provenance.producer.id", diagnostics)
    confidence = value.get("confidence")
    if _require_object(confidence, "confidence", diagnostics):
        _check_keys(confidence, {"level", "rationale"}, "confidence", diagnostics)
        if confidence.get("level") not in _CONFIDENCE:
            diagnostics.append(
                _error("INVALID_CONFIDENCE", "confidence.level", "unsupported confidence level")
            )
        _require_string(confidence.get("rationale"), "confidence.rationale", diagnostics)
    security = value.get("security")
    if _require_object(security, "security", diagnostics):
        _check_keys(
            security,
            {
                "sensitivity",
                "executableAttachments",
                "instructionsAreUntrusted",
                "requiredExternalAuthority",
            },
            "security",
            diagnostics,
        )
        if security.get("sensitivity") not in _SENSITIVITIES:
            diagnostics.append(
                _error("INVALID_SENSITIVITY", "security.sensitivity", "unsupported sensitivity")
            )
        if not isinstance(security.get("executableAttachments"), bool):
            diagnostics.append(
                _error("TYPE_BOOLEAN", "security.executableAttachments", "must be boolean")
            )
        if security.get("instructionsAreUntrusted") is not True:
            diagnostics.append(
                _error(
                    "UNTRUSTED_BOUNDARY_REQUIRED",
                    "security.instructionsAreUntrusted",
                    "must be true",
                )
            )
    lifecycle = value.get("lifecycle")
    if _require_object(lifecycle, "lifecycle", diagnostics):
        _check_keys(lifecycle, {"initialState", "reviewWhen"}, "lifecycle", diagnostics)
        if lifecycle.get("initialState") != LifecycleState.PROPOSED.value:
            diagnostics.append(
                _error(
                    "INVALID_INITIAL_STATE", "lifecycle.initialState", "records must begin proposed"
                )
            )
        review_when = lifecycle.get("reviewWhen", [])
        if not isinstance(review_when, list) or not all(isinstance(x, str) for x in review_when):
            diagnostics.append(
                _error("TYPE_ARRAY_STRINGS", "lifecycle.reviewWhen", "must be a list of strings")
            )
    _check_relationships(
        value.get("relationships"),
        value.get("metadata", {}).get("recordId")
        if isinstance(value.get("metadata"), Mapping)
        else None,
        diagnostics,
    )
    reproduction = value.get("reproduction")
    if reproduction is not None and _require_object(reproduction, "reproduction", diagnostics):
        if not isinstance(reproduction.get("procedure", []), list):
            diagnostics.append(
                _error(
                    "TYPE_ARRAY", "reproduction.procedure", "must be a list; it remains inert data"
                )
            )


def validate_record(value: Any) -> ValidationReport:
    diagnostics: list[Diagnostic] = []
    if not _require_object(value, "<root>", diagnostics):
        return ValidationReport(tuple(diagnostics))
    _check_keys(value, _RECORD_KEYS, "<root>", diagnostics)
    if protocol_spec(value.get("apiVersion")) is None:
        diagnostics.append(
            _error("UNSUPPORTED_API_VERSION", "apiVersion", f"expected {API_VERSION}")
        )
    kind = value.get("kind")
    if kind not in {item.value for item in RecordKind}:
        diagnostics.append(_error("UNKNOWN_RECORD_KIND", "kind", "record kind is not supported"))
    digest = value.get("contentDigest")
    if digest is not None and not _valid_digest(digest):
        diagnostics.append(_error("INVALID_DIGEST", "contentDigest", "must be a sha256: digest"))
    for required in (
        "metadata",
        "subject",
        "scope",
        "statement",
        "evidence",
        "dependencies",
        "affectedContracts",
        "provenance",
        "confidence",
        "security",
        "lifecycle",
        "relationships",
        "details",
    ):
        if required not in value:
            diagnostics.append(_error("REQUIRED_FIELD", required, "field is required"))
    _common_record_checks(value, diagnostics)
    details = value.get("details")
    if _require_object(details, "details", diagnostics) and kind in _REQUIRED_DETAILS:
        for required in _REQUIRED_DETAILS[kind]:
            if required not in details:
                diagnostics.append(
                    _error("REQUIRED_DETAIL", f"details.{required}", f"required for {kind}")
                )
        if "outcome" in details and details["outcome"] not in {
            status.value for status in ResultStatus
        }:
            diagnostics.append(
                _error("INVALID_STATUS", "details.outcome", "must be PASS, FAIL, or UNKNOWN")
            )
        if kind == RecordKind.REPLICATION.value and not isinstance(
            details.get("independence"), Mapping
        ):
            diagnostics.append(
                _error("TYPE_OBJECT", "details.independence", "must preserve correlation metadata")
            )
        if kind == RecordKind.WORK_REQUEST.value and "requestState" in details:
            if details["requestState"] not in {item.value for item in WorkRequestState}:
                diagnostics.append(
                    _error(
                        "INVALID_WORK_REQUEST_STATE",
                        "details.requestState",
                        "unsupported WorkRequest coordination state",
                    )
                )
        if kind == RecordKind.WORK_REQUEST.value:
            diagnostics.extend(validate_work_record(value))
    if not diagnostics:
        expected = canonical_digest(value)
        if digest is not None and digest != expected:
            diagnostics.append(_error("DIGEST_MISMATCH", "contentDigest", f"expected {expected}"))
    return ValidationReport(tuple(diagnostics))


def validate_event(value: Any) -> ValidationReport:
    diagnostics: list[Diagnostic] = []
    if not _require_object(value, "<root>", diagnostics):
        return ValidationReport(tuple(diagnostics))
    _check_keys(value, _EVENT_KEYS, "<root>", diagnostics)
    if protocol_spec(value.get("apiVersion")) is None:
        diagnostics.append(
            _error("UNSUPPORTED_API_VERSION", "apiVersion", f"expected {API_VERSION}")
        )
    if value.get("kind") != EVENT_KIND:
        diagnostics.append(_error("INVALID_EVENT_KIND", "kind", f"expected {EVENT_KIND}"))
    for required in ("metadata", "target", "transition", "authority", "evidence"):
        if required not in value:
            diagnostics.append(_error("REQUIRED_FIELD", required, "field is required"))
    _check_metadata(value.get("metadata"), diagnostics)
    target = value.get("target")
    if _require_object(target, "target", diagnostics):
        _require_string(target.get("contentDigest"), "target.contentDigest", diagnostics)
        if not _valid_digest(target.get("contentDigest")):
            diagnostics.append(
                _error(
                    "INVALID_DIGEST",
                    "target.contentDigest",
                    "must be a sha256: digest",
                )
            )
    transition = value.get("transition")
    if _require_object(transition, "transition", diagnostics):
        if transition.get("from") not in {item.value for item in LifecycleState}:
            diagnostics.append(
                _error("INVALID_STATE", "transition.from", "unknown lifecycle state")
            )
        if transition.get("to") not in {item.value for item in LifecycleState}:
            diagnostics.append(_error("INVALID_STATE", "transition.to", "unknown lifecycle state"))
    authority = value.get("authority")
    if _require_object(authority, "authority", diagnostics):
        _require_string(authority.get("domain"), "authority.domain", diagnostics)
        _require_string(authority.get("actor"), "authority.actor", diagnostics)
        _require_string(authority.get("rationale"), "authority.rationale", diagnostics)
    _check_evidence(value.get("evidence"), "evidence", diagnostics)
    digest = value.get("contentDigest")
    if digest is not None and not _valid_digest(digest):
        diagnostics.append(_error("INVALID_DIGEST", "contentDigest", "must be a sha256: digest"))
    if not diagnostics:
        expected = canonical_digest(value)
        if digest is not None and digest != expected:
            diagnostics.append(_error("DIGEST_MISMATCH", "contentDigest", f"expected {expected}"))
    return ValidationReport(tuple(diagnostics))


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in hexdigits.lower() for character in value[7:])
    )
