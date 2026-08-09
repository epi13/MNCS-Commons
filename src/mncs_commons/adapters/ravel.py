"""RAVEL boundary: expose scoped knowledge without deciding what is learned."""

from typing import Any, Mapping


def knowledge_view(record: Mapping[str, Any], *, lifecycle_state: str) -> dict[str, Any]:
    return {
        "recordDigest": record.get("contentDigest"),
        "kind": record.get("kind"),
        "subject": record.get("subject"),
        "statement": record.get("statement"),
        "outcome": record.get("details", {}).get("outcome")
        if isinstance(record.get("details"), Mapping)
        else None,
        "lifecycleState": lifecycle_state,
        "evidence": record.get("evidence", []),
        "scope": record.get("scope", {}),
        "negativeOrDisputed": lifecycle_state in {"disputed", "rejected"}
        or (record.get("details", {}).get("outcome") == "FAIL"),
    }
