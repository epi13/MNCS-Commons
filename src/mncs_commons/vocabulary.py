"""Machine-readable Commons vocabulary exposed to outside participants."""

from __future__ import annotations

from typing import Any

from .models import (
    INSTITUTIONAL_MEMORY_KINDS,
    LifecycleState,
    RecordKind,
    RelationType,
    ResultStatus,
    WorkRequestState,
)
from .validation import _CONFIDENCE, _SENSITIVITIES

VOCABULARY_VERSION = "commons.mncs.dev/vocabulary/v0alpha1"

SUBJECT_TYPES = (
    "artifact",
    "contract",
    "environment",
    "execution",
    "execution-bundle",
    "execution-receipt",
    "experiment",
    "HIR",
    "obligation",
    "provider",
    "record",
    "repository",
    "repository-revision",
    "semantic-body",
    "semantic-graph",
    "SSA",
    "verifier-result",
    "work-request",
)

SCOPE_DIMENSIONS = (
    "artifactDigest",
    "compiler",
    "contractIdentity",
    "dependencyIdentity",
    "environment",
    "machine",
    "model",
    "placement",
    "provider",
    "repositoryRevision",
    "semanticGraph",
    "target",
)


def vocabulary() -> dict[str, Any]:
    """Return sorted, transport-safe vocabulary metadata."""

    return {
        "vocabularyVersion": VOCABULARY_VERSION,
        "recordKinds": sorted(item.value for item in RecordKind),
        "lifecycleStates": sorted(item.value for item in LifecycleState),
        "resultStatuses": sorted(item.value for item in ResultStatus),
        "workRequestStates": sorted(item.value for item in WorkRequestState),
        "relationships": sorted(item.value for item in RelationType),
        "securitySensitivities": sorted(_SENSITIVITIES),
        "confidenceLevels": sorted(_CONFIDENCE),
        "recommendedSubjectTypes": list(SUBJECT_TYPES),
        "recommendedScopeDimensions": list(SCOPE_DIMENSIONS),
        "institutionalMemory": {
            "recordKinds": sorted(INSTITUTIONAL_MEMORY_KINDS),
            "threadAnchorKind": RecordKind.THREAD.value,
            "promotionRule": "promote reusable knowledge; do not mirror raw execution exhaust",
            "queryFlag": "institutionalMemory",
        },
        "extensionRule": {
            "required": True,
            "form": "namespaced-term",
            "examples": ["org.example/custom-subject", "github.com/example/project/result"],
            "unknownTerms": "preserve-without-reinterpretation",
        },
    }
