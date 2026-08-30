"""Small, transport-independent protocol types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

API_VERSION = "commons.mncs.dev/v0alpha1"
EVENT_KIND = "LifecycleEvent"


class RecordKind(StrEnum):
    CONCEPT_EXPERIMENT = "ConceptExperiment"
    FAILURE_CLASSIFICATION = "FailureClassification"
    OBSERVATION = "Observation"
    CLAIM = "Claim"
    FINDING = "Finding"
    QUESTION = "Question"
    HYPOTHESIS = "Hypothesis"
    FAILED_APPROACH = "FailedApproach"
    HANDOFF = "Handoff"
    ARTIFACT_REFERENCE = "ArtifactReference"
    THREAD = "Thread"
    WORK_REQUEST = "WorkRequest"
    REPLICATION = "Replication"
    DEVELOPMENT_RECORD = "DevelopmentRecord"
    ADVISORY = "Advisory"
    DECISION = "Decision"
    EPOCH = "Epoch"
    EPOCH_SUMMARY = "EpochSummary"
    REPLICATION_SERIES = "ReplicationSeries"
    OBSERVATION_SERIES = "ObservationSeries"


INSTITUTIONAL_MEMORY_KINDS = frozenset(
    {
        RecordKind.FINDING.value,
        RecordKind.QUESTION.value,
        RecordKind.HYPOTHESIS.value,
        RecordKind.FAILED_APPROACH.value,
        RecordKind.HANDOFF.value,
        RecordKind.ARTIFACT_REFERENCE.value,
        RecordKind.THREAD.value,
        RecordKind.DECISION.value,
    }
)


class LifecycleState(StrEnum):
    PROPOSED = "proposed"
    REPRODUCED = "reproduced"
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class WorkRequestState(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    RESPONDED = "responded"
    COMPLETED = "completed"
    UNABLE_TO_COMPLETE = "unable_to_complete"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class WorkCoordinationState(StrEnum):
    AVAILABLE = "AVAILABLE"
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    ABANDONED = "ABANDONED"
    SUPERSEDED = "SUPERSEDED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"


class RelationType(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REPLICATES = "replicates"
    FAILED_TO_REPLICATE = "failed_to_replicate"
    SUPERSEDES = "supersedes"
    NARROWS = "narrows"
    DEPENDS_ON = "depends_on"
    DERIVED_FROM = "derived_from"
    REQUESTS = "requests"
    RESPONDS_TO = "responds_to"
    ANSWERS = "answers"
    CONTRIBUTES_TO = "contributes_to"
    EXPLORES = "explores"
    ATTEMPTS = "attempts"
    HANDS_OFF = "hands_off"
    FOLLOWS_UP = "follows_up"
    VERIFIES = "verifies"
    DISPUTES = "disputes"
    AFFECTS_CONTRACT = "affects_contract"
    REFERENCES_ARTIFACT = "references_artifact"
    RERUN_OF = "rerun_of"
    PREDECESSOR = "predecessor"
    EVALUATES = "evaluates"
    EXECUTES = "executes"
    COMPILED_FROM = "compiled_from"
    PRODUCED = "produced"


@dataclass(frozen=True, slots=True)
class Record:
    """An immutable view over a validated record mapping."""

    data: Mapping[str, Any]
    content_digest: str

    @property
    def kind(self) -> str:
        return str(self.data["kind"])

    @property
    def record_id(self) -> str:
        return str(self.data["metadata"].get("recordId", self.content_digest))


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    data: Mapping[str, Any]
    event_digest: str

    @property
    def target_digest(self) -> str:
        return str(self.data["target"]["contentDigest"])


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    path: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }
