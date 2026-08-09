"""Transport-neutral Agent Exchange profile for Commons v0alpha1 records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .canonical import canonical_json
from .models import API_VERSION, Diagnostic, RecordKind
from .operations import operations
from .validation import validate_record
from .vocabulary import vocabulary

EXCHANGE_VERSION = "commons.mncs.dev/exchange/v0alpha1"
MAX_RECORD_BYTES = 1 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_QUERY_RESULTS = 1_000
MAX_SYNC_ENTRIES = 1_000
MAX_CONVERSATION_NODES = 1_000


class ExchangeError(ValueError):
    """A stable, machine-readable exchange boundary error."""

    def __init__(self, code: str, message: str, *, diagnostics: tuple[Diagnostic, ...] = ()):
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics

    def as_dict(self) -> dict[str, object]:
        return {
            "exchangeVersion": EXCHANGE_VERSION,
            "error": self.code,
            "message": self.message,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ParticipantDescriptor:
    """Self-asserted participant metadata; it is not authentication."""

    participant_id: str
    implementation: str
    software_version: str | None = None
    model_provider: str | None = None
    instance_id: str | None = None
    capabilities: tuple[str, ...] = ()
    namespace: str | None = None

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "participantId": self.participant_id,
            "implementation": self.implementation,
            "identityAssurance": "SELF_ASSERTED",
            "capabilities": sorted(set(self.capabilities)),
        }
        for key, item in (
            ("softwareVersion", self.software_version),
            ("modelProvider", self.model_provider),
            ("instanceId", self.instance_id),
            ("namespace", self.namespace),
        ):
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True, slots=True)
class ExchangePolicy:
    name: str = "local"
    public: bool = False
    allow_write: bool = True
    allow_lifecycle_events: bool = False
    max_record_bytes: int = MAX_RECORD_BYTES
    max_query_results: int = MAX_QUERY_RESULTS
    max_sync_entries: int = MAX_SYNC_ENTRIES
    max_conversation_nodes: int = MAX_CONVERSATION_NODES
    max_relationships: int = 256
    max_evidence: int = 256

    @classmethod
    def public_profile(cls) -> "ExchangePolicy":
        return cls(name="public-contribution", public=True, allow_lifecycle_events=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "public": self.public,
            "allowWrite": self.allow_write,
            "allowLifecycleEvents": self.allow_lifecycle_events,
            "metadataOnlyDisclosure": self.public,
            "sensitiveRecords": "rejected" if self.public else "policy-controlled",
        }


@dataclass(frozen=True, slots=True)
class ExchangeDescriptor:
    domain: str
    implementation_name: str
    implementation_version: str
    policy: ExchangePolicy = field(default_factory=ExchangePolicy)

    def as_dict(self) -> dict[str, object]:
        return {
            "exchangeVersion": EXCHANGE_VERSION,
            "recordVersions": [API_VERSION],
            "implementation": {
                "name": self.implementation_name,
                "version": self.implementation_version,
            },
            "domain": self.domain,
            "operations": [item.as_dict() for item in operations()],
            "recordKinds": sorted(item.value for item in RecordKind),
            "relationshipVocabulary": vocabulary()["relationships"],
            "limits": {
                "maxRecordBytes": self.policy.max_record_bytes,
                "maxQueryResults": self.policy.max_query_results,
                "maxSyncEntries": self.policy.max_sync_entries,
                "maxConversationNodes": self.policy.max_conversation_nodes,
                "maxResponseBytes": MAX_RESPONSE_BYTES,
            },
            "features": {
                "commonsBundles": True,
                "incrementalSync": True,
                "conversationGraph": True,
                "pushSubscriptions": False,
                "remoteTransport": False,
            },
            "securityProfile": {
                "identityAssertion": "self-asserted",
                "authenticatedTransport": "not-provided",
                "technicalAuthority": "not-granted",
                "instructionsAreUntrusted": True,
                "publicPolicy": self.policy.as_dict(),
            },
            "transport": {"binding": "local-application", "network": False},
            "vocabularyVersion": vocabulary()["vocabularyVersion"],
        }


@dataclass(frozen=True, slots=True)
class IngestionReceipt:
    status: str
    content_digest: str
    logical_record_id: str
    domain: str
    cursor: Mapping[str, object]
    participant: Mapping[str, object] | None
    diagnostics: tuple[Diagnostic, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "exchangeVersion": EXCHANGE_VERSION,
            "deliveryStatus": self.status,
            "validationStatus": "VALID",
            "storageStatus": "ALREADY_PRESENT" if self.status == "DUPLICATE" else "STORED",
            "acceptanceStatus": "UNCHANGED",
            "technicalAuthority": "NONE_GRANTED",
            "contentDigest": self.content_digest,
            "logicalRecordId": self.logical_record_id,
            "domain": self.domain,
            "cursor": dict(self.cursor),
            "participant": self.participant,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


def validate_participant(participant: ParticipantDescriptor | None) -> None:
    if participant is None:
        return
    for name, value in (
        ("participantId", participant.participant_id),
        ("implementation", participant.implementation),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ExchangeError("INVALID_PARTICIPANT", f"{name} must be a bounded non-empty string")


def validate_for_exchange(
    value: Mapping[str, Any], policy: ExchangePolicy | None = None
) -> None:
    policy = policy or ExchangePolicy()
    try:
        encoded = canonical_json(value)
    except (TypeError, ValueError) as error:
        raise ExchangeError("INVALID_RECORD", f"record is not canonicalizable: {error}") from error
    if len(encoded) > policy.max_record_bytes:
        raise ExchangeError("RECORD_TOO_LARGE", "record exceeds the exchange record-size limit")
    if value.get("kind") not in {item.value for item in RecordKind}:
        raise ExchangeError("UNSUPPORTED_RECORD_VERSION", "only Commons records can be published")
    report = validate_record(value)
    if not report.valid:
        code = (
            "SEMANTIC_RECORD_ERROR"
            if any(item.code == "DIGEST_MISMATCH" for item in report.diagnostics)
            else "INVALID_RECORD"
        )
        raise ExchangeError(
            code,
            "record failed Commons validation",
            diagnostics=report.diagnostics,
        )
    relationships = value.get("relationships", [])
    evidence = value.get("evidence", [])
    if len(relationships) > policy.max_relationships:
        raise ExchangeError("RECORD_TOO_LARGE", "record has too many relationships")
    if len(evidence) > policy.max_evidence:
        raise ExchangeError("RECORD_TOO_LARGE", "record has too many evidence references")
    security = value.get("security", {})
    if policy.public:
        if security.get("sensitivity") != "public":
            raise ExchangeError(
                "PUBLIC_POLICY_REJECTED", "public profile accepts public records only"
            )
        if security.get("executableAttachments") is not False:
            raise ExchangeError(
                "PUBLIC_POLICY_REJECTED", "public profile rejects executable attachments"
            )
        if security.get("instructionsAreUntrusted") is not True:
            raise ExchangeError(
                "PUBLIC_POLICY_REJECTED", "untrusted instruction marker is required"
            )


def descriptor(
    *, domain: str = "local", policy: ExchangePolicy | None = None
) -> dict[str, object]:
    from . import __version__

    return ExchangeDescriptor(
        domain, "mncs-commons", __version__, policy or ExchangePolicy()
    ).as_dict()
