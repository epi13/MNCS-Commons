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


def seed_work(path: Path, domain: str = "local") -> dict[str, object]:
    """Seed a small, idempotent MNCS-family backlog for lane-aware workers."""

    store = CommonsStore(path)
    store.init()
    application = CommonsApplication(store)
    submitter = {"type": "operator", "id": "urn:mncs:commons:work-seed"}
    project = {"id": "mncs-family", "revision": "2026-08"}
    requests = [
        {
            "workId": "work:seed-commons-lane-docs",
            "lane": "DOCUMENTATION",
            "repository": "MNCS-Commons",
            "task": (
                "Document the five-lane model, claim lifecycle, and shared-core escalation "
                "in Commons."
            ),
            "priority": 10,
        },
        {
            "workId": "work:seed-commons-boundary-docs",
            "lane": "DOCUMENTATION",
            "repository": "MNCS-Commons",
            "task": (
                "Synchronize the Commons, Fabric, Harness, Forge, and Git "
                "authority-boundary documentation."
            ),
            "priority": 20,
        },
        {
            "workId": "work:seed-tui-conversion-map",
            "lane": "CONVERSION_PREP",
            "repository": "mncs-tui",
            "task": (
                "Prepare a conversion map and bounded geometry fixtures for the existing "
                "mncs-tui layout examples."
            ),
            "capabilityRequirements": ["mncs-language:source-fixtures"],
            "priority": 20,
        },
        {
            "workId": "work:seed-mnel-corpus-map",
            "lane": "CONVERSION_PREP",
            "repository": "Machine-Native-Experimental-Learning",
            "task": (
                "Map the MNEL training differential corpus to conversion-ready semantic units "
                "and record unsupported constructs."
            ),
            "capabilityRequirements": ["mncs-language:source-fixtures"],
            "priority": 30,
        },
        {
            "workId": "work:seed-ravel-knowledge-scaffold",
            "lane": "CONVERSION_PREP",
            "repository": "RAVEL",
            "task": (
                "Scaffold a repo-local MNCS module for the existing RAVEL knowledge fixture "
                "without changing shared semantics."
            ),
            "priority": 40,
        },
        {
            "workId": "work:seed-lineage-corpus-verification",
            "lane": "VERIFICATION",
            "repository": "mncs-lineage",
            "task": (
                "Run the sealed lineage corpus and publish a reproducibility snapshot "
                "with explicit UNKNOWN cases."
            ),
            "priority": 20,
        },
        {
            "workId": "work:seed-forge-commons-compat",
            "lane": "VERIFICATION",
            "repository": "mncs-forge-mcp",
            "task": (
                "Add a compatibility verification fixture for Commons work-request and "
                "completion-evidence records."
            ),
            "priority": 30,
        },
        {
            "workId": "work:seed-language-service-regression",
            "lane": "VERIFICATION",
            "repository": "mncs-language-service",
            "task": (
                "Capture a regression fixture for the current language-service pin and "
                "its stale-capability diagnostic."
            ),
            "priority": 40,
        },
        {
            "workId": "work:seed-tui-layout-local",
            "lane": "REPO_LOCAL",
            "repository": "mncs-tui",
            "task": (
                "Implement the next repository-local layout fixture using only currently "
                "supported MNCS capabilities."
            ),
            "priority": 50,
        },
        {
            "workId": "work:seed-mnel-repo-local",
            "lane": "REPO_LOCAL",
            "repository": "Machine-Native-Experimental-Learning",
            "task": (
                "Improve repo-local differential-run reporting while preserving the working "
                "reference implementation."
            ),
            "priority": 60,
        },
        {
            "workId": "work:seed-shared-vector-reduce",
            "lane": "SHARED_CORE",
            "repository": "mncs-language",
            "task": (
                "Evaluate and, if accepted by the shared-core owner, specify numeric.vector.reduce "
                "for MNEL conversion pressure."
            ),
            "sharedCoreImpact": True,
            "capability": "numeric.vector.reduce",
            "reason": "native MNEL training-loss calculation needs a bounded reduction primitive.",
            "expectedSemantics": (
                "Deterministic reduction over a numeric vector with explicit empty-input behavior."
            ),
            "blockingWorkIds": ["work:seed-mnel-corpus-map"],
            "evidenceLinks": [
                "mncs://Machine-Native-Experimental-Learning/tools/run_mncs_differential.py"
            ],
            "priority": 70,
            "createdFrom": ["work:seed-mnel-corpus-map"],
        },
        {
            "workId": "work:seed-family-registry-reconcile",
            "lane": "REPO_HYGIENE",
            "repository": "machine-native-complexity-standard",
            "task": (
                "Reconcile the central family registry and repository manifests with the "
                "canonical 17-project roster, preserving component authority."
            ),
            "evidenceLinks": [
                "family/mncs-family.v0.1.json",
                "https://github.com/epi13/mncs-atlas/blob/main/atlas.json",
            ],
            "priority": 15,
        },
        {
            "workId": "work:seed-rights-ci-hygiene",
            "lane": "REPO_HYGIENE",
            "repository": "mncs-rights-provenance",
            "task": (
                "Repair the current default-branch CI failure while preserving rights and "
                "provenance semantics; classify any remaining toolchain gap explicitly."
            ),
            "evidenceLinks": ["GitHub Actions default-branch run 32841046979"],
            "priority": 20,
        },
        {
            "workId": "work:seed-forge-ci-hygiene",
            "lane": "REPO_HYGIENE",
            "repository": "mncs-forge-mcp",
            "task": (
                "Reconcile current cross-platform CI failures and stale compatibility evidence "
                "without weakening platform assertions or Forge authority boundaries."
            ),
            "evidenceLinks": ["GitHub Actions default-branch run 32843005064"],
            "priority": 25,
        },
        {
            "workId": "work:seed-mnel-ci-hygiene",
            "lane": "REPO_HYGIENE",
            "repository": "Machine-Native-Experimental-Learning",
            "task": (
                "Repair the current MNEL CI environment and fixture failures, including the "
                "Rust provider fixture and unavailable integration expectation, without "
                "weakening tests or changing intended behavior."
            ),
            "evidenceLinks": ["GitHub Actions default-branch run 33026287027"],
            "priority": 20,
        },
        {
            "workId": "work:seed-atlas-registry-alignment",
            "lane": "DOCUMENTATION",
            "repository": "mncs-atlas",
            "task": (
                "Align Atlas descriptive project orientation with the Commons active-family "
                "registry, retaining Atlas as non-normative and non-scheduling."
            ),
            "evidenceLinks": ["atlas.json", "commons.mncs.dev/family-registry/v0alpha1"],
            "priority": 30,
        },
    ]
    seeded = []
    for item in requests:
        seeded.append(
            application.submit_work(
                {
                    **item,
                    "submittingConsumer": submitter,
                    "project": project,
                    "constraints": [
                        "Commons records are inert; execution requires external authority",
                        f"seed domain: {domain}",
                    ],
                }
            )
        )
    return {
        "seeded": seeded,
        "count": len(seeded),
        "lanes": sorted({str(item["lane"]) for item in requests}),
        "authority": "seeded records are opportunities, not commands",
    }
