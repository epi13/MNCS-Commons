"""MNCS Commons 0.3 local executable reference implementation."""

from .application import CommonsApplication, CompatibilityApplication
from .canonical import canonical_digest, canonical_json, identity_projection
from .compatibility import CompatibilityStatus, ProducerContract, contracts
from .lifecycle import derive_lifecycle, validate_transition
from .models import LifecycleState, RecordKind, RelationType, ResultStatus, WorkRequestState
from .query import ScopeAssessment, assess_scope, unresolved_relationships
from .store import CommonsStore
from .validation import ValidationReport, validate_event, validate_record

__all__ = [
    "CommonsStore",
    "CommonsApplication",
    "CompatibilityApplication",
    "CompatibilityStatus",
    "LifecycleState",
    "RecordKind",
    "RelationType",
    "ResultStatus",
    "WorkRequestState",
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
]
