"""Content-addressed evidence references with explicit availability.

A Commons record carries knowledge identity; possession of the supporting
evidence is a separate, explicitly tracked fact.  An ``EvidenceReference``
describes one evidence blob independently of whether this node holds it:

.. code-block:: text

    knowledge identity  !=  evidence possession

Availability vocabulary (``AVAILABILITY_VERSION``):

- ``LOCAL`` -- this node holds the bytes in its local CAS.
- ``SOURCE_AVAILABLE`` -- the originator asserts the bytes remain fetchable.
- ``MIRRORED`` -- some non-origin node holds a copy.
- ``DURABLE`` -- pinned/archived copy with a retention commitment.
- ``CANONICAL`` -- canonical, governance-pinned copy.
- ``UNAVAILABLE`` -- no known live copy; the record stays auditable anyway.

Records may annotate ``evidence[]`` entries with the optional inert keys
``availability``, ``sizeBytes``, and ``mediaType``.  Older readers ignore
unknown keys, so the annotation never changes a v0alpha1 content digest …
unless it is added to the record itself, in which case it is simply part of
the hashed content like any other field.  The mesh-level availability *view*
(a node's local knowledge about where evidence lives) is kept out of the
record in the node's mesh state, never as silent record mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .errors import MeshError

AVAILABILITY_VERSION = "commons.mncs.dev/availability/v0alpha1"

MAX_DIGEST_LENGTH = 256
MAX_MEDIA_TYPE_LENGTH = 128
MAX_PROVENANCE_LENGTH = 512
MAX_EVIDENCE_BYTES = 1024 * 1024 * 1024


class EvidenceAvailability(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    SOURCE_AVAILABLE = "SOURCE_AVAILABLE"
    LOCAL = "LOCAL"
    MIRRORED = "MIRRORED"
    DURABLE = "DURABLE"
    CANONICAL = "CANONICAL"


# Deterministic retention priority: higher survives budget pressure longer.
# LOCAL outranks SOURCE_AVAILABLE because possession is certain; named
# replicated tiers outrank local possession because they carry commitments.
RETENTION_PRIORITY = {
    EvidenceAvailability.UNAVAILABLE: 0,
    EvidenceAvailability.SOURCE_AVAILABLE: 1,
    EvidenceAvailability.LOCAL: 2,
    EvidenceAvailability.MIRRORED: 3,
    EvidenceAvailability.DURABLE: 4,
    EvidenceAvailability.CANONICAL: 5,
}


def _bounded_text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise MeshError("INVALID_EVIDENCE_REFERENCE", f"{name} must be a bounded string")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A machine-readable pointer to evidence, independent of possession."""

    digest: str
    availability: EvidenceAvailability = EvidenceAvailability.UNAVAILABLE
    media_type: str | None = None
    size_bytes: int | None = None
    provenance: str | None = None

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "digest": self.digest,
            "availability": self.availability.value,
        }
        if self.media_type is not None:
            value["mediaType"] = self.media_type
        if self.size_bytes is not None:
            value["sizeBytes"] = self.size_bytes
        if self.provenance is not None:
            value["provenance"] = self.provenance
        return value

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceReference":
        if not isinstance(value, Mapping):
            raise MeshError("INVALID_EVIDENCE_REFERENCE", "evidence reference must be an object")
        digest = _bounded_text(value.get("digest"), "digest", MAX_DIGEST_LENGTH)
        raw_availability = value.get("availability", EvidenceAvailability.UNAVAILABLE.value)
        try:
            availability = EvidenceAvailability(str(raw_availability))
        except ValueError:
            raise MeshError(
                "UNKNOWN_AVAILABILITY",
                f"availability {raw_availability!r} is not supported; known: "
                + ",".join(item.value for item in EvidenceAvailability),
            ) from None
        media_type = value.get("mediaType")
        if media_type is not None:
            media_type = _bounded_text(media_type, "mediaType", MAX_MEDIA_TYPE_LENGTH)
        size_bytes = value.get("sizeBytes")
        if size_bytes is not None and (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
            or size_bytes > MAX_EVIDENCE_BYTES
        ):
            raise MeshError("INVALID_EVIDENCE_REFERENCE", "sizeBytes must be a bounded integer")
        provenance = value.get("provenance")
        if provenance is not None:
            provenance = _bounded_text(provenance, "provenance", MAX_PROVENANCE_LENGTH)
        return cls(
            digest=digest,
            availability=availability,
            media_type=media_type,
            size_bytes=size_bytes,
            provenance=provenance,
        )


def merge_availability(
    first: EvidenceAvailability, second: EvidenceAvailability
) -> EvidenceAvailability:
    """Deterministic knowledge merge: keep the stronger retention tier."""
    if RETENTION_PRIORITY[first] >= RETENTION_PRIORITY[second]:
        return first
    return second


def annotation_from_evidence_entry(entry: Mapping[str, Any]) -> EvidenceReference | None:
    """Read the optional inert availability annotation off an evidence entry.

    Returns ``None`` when the entry carries no mesh annotation, so callers
    can distinguish "no information" from an explicit ``UNAVAILABLE`` claim.
    Unknown availability tokens are inert (``None``), never executable.
    """

    if not isinstance(entry, Mapping):
        return None
    if "availability" not in entry and "sizeBytes" not in entry and "mediaType" not in entry:
        return None
    raw = entry.get("availability", EvidenceAvailability.UNAVAILABLE.value)
    try:
        availability = EvidenceAvailability(str(raw))
    except ValueError:
        return None
    size_bytes = entry.get("sizeBytes")
    if size_bytes is not None and (
        not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0
    ):
        return None
    media_type = entry.get("mediaType")
    if media_type is not None and not isinstance(media_type, str):
        return None
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        return None
    return EvidenceReference(
        digest=entry_id,
        availability=availability,
        media_type=media_type,
        size_bytes=size_bytes,
    )
