"""MNCS Commons 0.5 local agent knowledge service reference implementation."""

__version__ = "0.5.0.dev1"

from .application import CommonsApplication, CompatibilityApplication
from .canonical import canonical_digest, canonical_json, identity_projection
from .compatibility import CompatibilityStatus, ProducerContract, contracts
from .exchange import ExchangeError, ExchangePolicy, ParticipantDescriptor
from .family import (
    FamilyRecordError,
    make_concept_experiment_record,
    make_development_record_record,
    make_failure_classification_record,
    make_replication_record,
    normalize_producer_reference,
    producer_reference,
    reference_identity,
)
from .family_registry import CoverageState, family_coverage, family_registry
from .lane_policy import LANES, SAFE_LANES, LanePolicy, WorkLane, lane_policy, scope_decision
from .lifecycle import derive_lifecycle, validate_transition
from .local_service import CommonsAdminClient, CommonsClient
from .models import (
    LifecycleState,
    RecordKind,
    RelationType,
    ResultStatus,
    WorkCoordinationState,
    WorkRequestState,
)
from .query import ScopeAssessment, assess_scope, unresolved_relationships
from .remote import RemoteClient
from .store import CommonsStore
from .validation import ValidationReport, validate_event, validate_record

__all__ = [
    "CommonsStore",
    "CommonsApplication",
    "CommonsAdminClient",
    "CommonsClient",
    "CompatibilityApplication",
    "CompatibilityStatus",
    "LifecycleState",
    "RecordKind",
    "RelationType",
    "ResultStatus",
    "WorkRequestState",
    "WorkCoordinationState",
    "CoverageState",
    "family_registry",
    "family_coverage",
    "LANES",
    "SAFE_LANES",
    "LanePolicy",
    "WorkLane",
    "lane_policy",
    "scope_decision",
    "ScopeAssessment",
    "ValidationReport",
    "ProducerContract",
    "assess_scope",
    "canonical_digest",
    "canonical_json",
    "derive_lifecycle",
    "identity_projection",
    "validate_event",
    "validate_record",
    "validate_transition",
    "unresolved_relationships",
    "contracts",
    "ExchangeError",
    "ExchangePolicy",
    "ParticipantDescriptor",
    "RemoteClient",
    "FamilyRecordError",
    "producer_reference",
    "normalize_producer_reference",
    "reference_identity",
    "make_concept_experiment_record",
    "make_development_record_record",
    "make_failure_classification_record",
    "make_replication_record",
]
