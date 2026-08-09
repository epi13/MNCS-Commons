"""Deterministic operator-run bootstrap records for an empty public node."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .application import CommonsApplication
from .exchange import ExchangePolicy
from .store import CommonsStore


def _request(record_id: str, summary: str, domain: str) -> dict[str, Any]:
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "WorkRequest",
        "metadata": {
            "recordId": record_id,
            "createdAt": "2026-01-01T00:00:00Z",
            "author": {"id": "urn:mncs:commons:bootstrap", "type": "operator"},
        },
        "subject": {"type": "work-request", "identity": record_id},
        "scope": {
            "context": {"domain": domain},
            "limitations": ["request carries no execution authority"],
        },
        "statement": {
            "summary": summary,
            "details": "A response is optional and remains untrusted evidence.",
        },
        "evidence": [],
        "reproduction": {
            "prerequisites": ["read the public exchange descriptor"],
            "procedure": [
                {
                    "command": "use an independently authorized client",
                    "authorityRequired": "none from Commons",
                }
            ],
            "expected": ["publish PASS, FAIL, or UNKNOWN with limitations"],
        },
        "dependencies": [],
        "affectedContracts": [],
        "relationships": [],
        "provenance": {
            "producer": {"type": "operator", "id": "urn:mncs:commons:bootstrap"},
            "sourceRecords": [],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "a request is not evidence of the requested result",
        },
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": True,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": ["operator review"]},
        "details": {
            "objective": "independent interoperability report",
            "requestedKind": "Replication",
            "authorityBoundary": "Commons does not dispatch commands or grant permissions",
            "requestState": "open",
        },
    }


def seed_public(path: Path, domain: str = "public") -> dict[str, object]:
    store = CommonsStore(path)
    store.init()
    application = CommonsApplication(store)
    records = [
        _request(
            "bootstrap-interoperability",
            "Implement the documented Commons describe, publish, query, and sync lifecycle "
            "and report PASS/FAIL/UNKNOWN.",
            domain,
        ),
        _request(
            "bootstrap-ambiguity-review",
            "Review the exchange profile and report any field whose semantics required guessing.",
            domain,
        ),
        _request(
            "bootstrap-non-python-client",
            "Implement the smallest client in another language or agent framework and "
            "report compatibility and limitations.",
            domain,
        ),
    ]
    receipts = [
        application.publish(record, policy=ExchangePolicy.public_profile(), domain=domain)
        for record in records
    ]
    return {
        "seeded": receipts,
        "count": len(receipts),
        "authority": "requests are opportunities, not commands",
    }
