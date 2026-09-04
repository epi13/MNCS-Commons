"""Disposable derived views: storage/exchange separated from presentation.

A searchable global Commons interface is a *view*, not Commons itself.  A
view ingests records a node already possesses and derives projections:

- ``open-work`` -- open work requests with their coordination state.
- ``verification-status`` -- replication correlation per target record.
- ``topic-index`` -- records grouped by thread topic / labels.
- ``promotion-candidates`` -- reproduced/verified/accepted records plus
  their replication outcomes, for the governance layer to evaluate.

Views are rebuildable at any time, own no canonical record, and grant no
authority.  Every view names the digests it was built from.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..query import replication_correlation
from .errors import MeshError

VIEW_VERSION = "commons.mncs.dev/view/v0alpha1"
VIEW_KINDS = ("open-work", "verification-status", "topic-index", "promotion-candidates")
MAX_VIEW_ROWS = 5_000


def build_view(
    records: list[Mapping[str, Any]],
    view_kind: str,
    *,
    lifecycle_of: Any = None,
    domain: str = "local",
) -> dict[str, object]:
    """Derive a disposable projection over already-possessed records."""

    if view_kind not in VIEW_KINDS:
        raise MeshError("UNKNOWN_VIEW", f"view {view_kind!r} is not supported")
    if len(records) > MAX_VIEW_ROWS * 2:
        raise MeshError("VIEW_TOO_LARGE", "view input exceeds its bound")

    def _state(digest: str | None) -> str | None:
        if digest is None or lifecycle_of is None:
            return None
        try:
            return str(lifecycle_of(digest, domain))
        except Exception:
            return None

    built_from = sorted(
        {str(item.get("contentDigest")) for item in records if item.get("contentDigest")}
    )
    rows: list[dict[str, object]] = []
    truncated = False
    if view_kind == "open-work":
        for item in records:
            if item.get("kind") != "WorkRequest":
                continue
            details = item.get("details")
            state = details.get("requestState", "open") if isinstance(details, Mapping) else "open"
            if state != "open":
                continue
            rows.append(
                {
                    "identity": item.get("contentDigest"),
                    "objective": details.get("objective") if isinstance(details, Mapping) else None,
                    "requestedKind": details.get("requestedKind")
                    if isinstance(details, Mapping)
                    else None,
                    "lifecycle": _state(str(item.get("contentDigest"))),
                }
            )
    elif view_kind == "verification-status":
        correlation_targets = sorted(
            {
                str(item["details"].get("targetRecord"))
                for item in records
                if item.get("kind") == "Replication"
                and isinstance(item.get("details"), Mapping)
                and isinstance(item["details"].get("targetRecord"), str)
            }
        )
        for target in correlation_targets[:MAX_VIEW_ROWS]:
            correlation = replication_correlation(records, target)
            rows.append(
                {
                    "target": target,
                    "outcomes": dict(correlation.outcomes),
                    "replications": len(correlation.replications),
                }
            )
    elif view_kind == "topic-index":
        for item in records:
            topics: list[str] = []
            if item.get("kind") == "Thread" and isinstance(item.get("details"), Mapping):
                topic = item["details"].get("topic")
                if isinstance(topic, str):
                    topics.append(topic)
            metadata = item.get("metadata")
            if isinstance(metadata, Mapping) and isinstance(metadata.get("labels"), list):
                topics.extend(str(label) for label in metadata["labels"] if label)
            if topics:
                rows.append(
                    {
                        "identity": item.get("contentDigest"),
                        "kind": item.get("kind"),
                        "topics": topics[:8],
                    }
                )
    elif view_kind == "promotion-candidates":
        for item in records:
            digest = str(item.get("contentDigest", ""))
            state = _state(digest or None)
            if state in ("reproduced", "verified", "accepted"):
                correlation = replication_correlation(records, digest)
                rows.append(
                    {
                        "identity": digest,
                        "kind": item.get("kind"),
                        "lifecycle": state,
                        "replicationOutcomes": dict(correlation.outcomes),
                    }
                )
    if len(rows) > MAX_VIEW_ROWS:
        rows = rows[:MAX_VIEW_ROWS]
        truncated = True
    return {
        "viewVersion": VIEW_VERSION,
        "viewKind": view_kind,
        "builtFrom": built_from,
        "rows": rows,
        "truncated": truncated,
        "disposable": True,
        "authority": "derived projection only; owns no record, grants no promotion",
    }
