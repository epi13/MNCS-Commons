"""Small application services; protocol semantics remain in pure core modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..adapters.contracts import AdapterResult
from ..bundle import create_bundle, import_bundle, verify_bundle
from ..canonical import canonical_digest, canonical_json
from ..compatibility import (
    CompatibilityStatus,
    check_local,
    compatibility_report,
    contract_for,
    contracts,
    resolve_contract,
)
from ..evidence import evidence_lineage
from ..exchange import (
    ExchangeError,
    ExchangePolicy,
    IngestionReceipt,
    ParticipantDescriptor,
    descriptor,
    validate_for_exchange,
    validate_participant,
)
from ..family_registry import (
    canonical_project_identity,
    family_coverage,
    family_registry,
    validate_family_sources,
)
from ..health import (
    health_observation_record,
    parse_health_instant,
)
from ..lane_policy import LANES, lane_policy, scope_decision
from ..models import EVENT_KIND
from ..query import (
    QueryFilter,
    bounded_graph,
    concept_experiment_graph,
    development_lineage,
    replication_correlation,
)
from ..store import CommonsStore, StoreError
from ..validation import validate_event, validate_record
from ..work import (
    WorkProtocolError,
    capability_overlap,
    coordination_state,
    list_work,
    new_work_record,
    next_work,
    normalize_capability,
    project_work_history,
    revised_work_record,
)


class CommonsApplication:
    """Canonical use cases for local interfaces."""

    def __init__(self, store: CommonsStore | None = None) -> None:
        self.store = store

    @staticmethod
    def validate(value: Mapping[str, Any]) -> dict[str, object]:
        return (
            validate_event(value) if value.get("kind") == EVENT_KIND else validate_record(value)
        ).as_dict()

    @staticmethod
    def canonicalize(value: Mapping[str, Any]) -> bytes:
        return canonical_json(value)

    @staticmethod
    def identity(value: Mapping[str, Any]) -> str:
        return canonical_digest(value)

    def require_store(self) -> CommonsStore:
        if self.store is None:
            raise ValueError("this operation requires a configured Commons store")
        return self.store

    def add(self, value: Mapping[str, Any]) -> RecordIdentity:
        store = self.require_store()
        if value.get("kind") == EVENT_KIND:
            event = store.add_event(value)
            return RecordIdentity(event.event_digest, EVENT_KIND)
        record = store.add_record(value)
        return RecordIdentity(record.content_digest, str(record.data.get("kind")))

    def verify_store(self) -> dict[str, object]:
        return self.require_store().verify().as_dict()

    def diagnose_store(self) -> dict[str, object]:
        return self.require_store().diagnose().as_dict()

    def recover_store(self) -> dict[str, object]:
        return self.require_store().recover().as_dict()

    def local_status(self, *, domain: str = "local") -> dict[str, object]:
        """Return operator-facing facts without treating them as authentication."""

        store = self.require_store()
        root = store.root.resolve()
        initialized = (
            store.records_path.is_dir()
            and store.events_path.is_dir()
            and store.transactions_path.is_dir()
            and store.ledger_path.exists()
        )
        result: dict[str, object] = {
            "nodeProfile": "commons.mncs.dev/node/local-agent/v0alpha1",
            "storePath": str(root),
            "storeExists": root.exists(),
            "initialized": initialized,
            "protocolVersion": "commons.mncs.dev/v0alpha1",
            "exchangeVersion": "commons.mncs.dev/exchange/v0alpha1",
            "trustDomain": domain,
            "executionAuthority": "none",
            "networkExposure": "none-by-default",
            "interfaces": descriptor(domain=domain)["interfaces"],
        }
        if not initialized:
            result.update(
                {
                    "verification": {"valid": False, "diagnostics": []},
                    "recoveryRequired": False,
                    "writable": False,
                }
            )
            return result
        verification = store.verify().as_dict()
        result["verification"] = verification
        diagnostics = verification.get("diagnostics", [])
        result["recoveryRequired"] = isinstance(diagnostics, list) and any(
            isinstance(item, Mapping) and item.get("code") == "PENDING_TRANSACTION"
            for item in diagnostics
        )
        result["writable"] = root.is_dir() and root.stat().st_mode & 0o222 != 0
        try:
            result["usage"] = store.storage_usage()
        except (OSError, StoreError) as error:
            result["usageDiagnostics"] = [{"code": "USAGE_FAILED", "message": str(error)}]
        return result

    def local_doctor(self, *, domain: str = "local") -> dict[str, object]:
        status = self.local_status(domain=domain)
        verification = status.get("verification", {})
        checks = {
            "storeExists": status.get("storeExists") is True,
            "initialized": status.get("initialized") is True,
            "verifies": isinstance(verification, Mapping) and verification.get("valid") is True,
            "writable": status.get("writable") is True,
            "recoveryRequired": status.get("recoveryRequired") is False,
            "protocolVersion": status.get("protocolVersion") == "commons.mncs.dev/v0alpha1",
            "exchangeVersion": status.get("exchangeVersion")
            == "commons.mncs.dev/exchange/v0alpha1",
        }
        return {
            **status,
            "checks": checks,
            "valid": all(checks.values()),
            "authority": "diagnostic facts only; no authentication or execution authority",
        }

    def query(self, filters: QueryFilter) -> list[Mapping[str, Any]]:
        return self.require_store().query(filters)

    def list_records(self) -> list[Mapping[str, Any]]:
        return self.require_store().records()

    def lifecycle(self, digest: str, domain: str | None = None) -> dict[str, object]:
        return self.require_store().lifecycle(digest, domain=domain).as_dict()

    def domain_views(self, digest: str) -> dict[str, dict[str, object]]:
        views = self.require_store().domain_views(digest)
        return {key: value.as_dict() for key, value in views.items()}

    def related(self, digest: str, *, depth: int, max_nodes: int) -> dict[str, object]:
        return dict(
            bounded_graph(
                self.require_store().records(), [digest], max_depth=depth, max_nodes=max_nodes
            ).as_dict()
        )

    def experiment(
        self, experiment_id: str, *, depth: int = 3, max_nodes: int = 1_000
    ) -> dict[str, object]:
        return concept_experiment_graph(
            self.require_store().records(),
            experiment_id,
            max_depth=depth,
            max_nodes=max_nodes,
        )

    def replications(self, target: str) -> dict[str, object]:
        return dict(replication_correlation(self.require_store().records(), target).as_dict())

    def development_record(
        self, record_ref: str, *, depth: int = 3, max_nodes: int = 1_000
    ) -> dict[str, object]:
        return development_lineage(
            self.require_store().records(),
            record_ref,
            max_depth=depth,
            max_nodes=max_nodes,
        )

    def trace_evidence(
        self, root: str, *, depth: int = 3, max_nodes: int = 1_000
    ) -> dict[str, object]:
        return evidence_lineage(
            self.require_store().records(), [root], max_depth=depth, max_nodes=max_nodes
        ).as_dict()

    def get_record(self, digest: str) -> Mapping[str, Any] | None:
        return self.require_store().get(digest)

    def retention_status(self) -> dict[str, object]:
        from ..retention import RetentionController

        return RetentionController(self.require_store()).status()

    def retention_plan(self, *, now: str | None = None) -> dict[str, object]:
        from ..retention import RetentionController

        return RetentionController(self.require_store()).plan(now=now)

    def compact_store(
        self, *, confirm: bool = False, dry_run: bool = True, now: str | None = None
    ) -> dict[str, object]:
        from ..retention import RetentionController

        return RetentionController(self.require_store()).compact(
            confirm=confirm, dry_run=dry_run, now=now
        )

    def pin_record(self, digest: str, *, reason: str) -> dict[str, object]:
        from ..retention import RetentionController

        return RetentionController(self.require_store()).pin(digest, reason=reason)

    def unpin_record(self, digest: str) -> dict[str, object]:
        from ..retention import RetentionController

        return RetentionController(self.require_store()).unpin(digest)

    def list_archives(self) -> list[dict[str, object]]:
        from ..archive import list_archives

        return list_archives(self.require_store())

    def verify_archive(self, archive_id: str) -> dict[str, object]:
        from ..archive import verify_archive

        return verify_archive(self.require_store(), archive_id)

    def inspect_archive(self, archive_id: str) -> dict[str, object]:
        from ..archive import inspect_archive

        return inspect_archive(self.require_store(), archive_id)

    @staticmethod
    def describe(
        *,
        domain: str = "local",
        policy: ExchangePolicy | None = None,
        binding: str = "python-api",
        profile: str = "commons.mncs.dev/node/local-agent/v0alpha1",
    ) -> dict[str, object]:
        return descriptor(domain=domain, policy=policy, binding=binding, profile=profile)

    def publish(
        self,
        value: Mapping[str, Any],
        *,
        participant: ParticipantDescriptor | None = None,
        policy: ExchangePolicy | None = None,
        domain: str = "local",
    ) -> dict[str, object]:
        policy = policy or ExchangePolicy()
        if not policy.allow_write:
            raise ExchangeError("PUBLIC_POLICY_REJECTED", "this exchange profile is read-only")
        validate_participant(participant)
        validate_for_exchange(value, policy)
        store = self.require_store()
        digest = str(value.get("contentDigest", canonical_digest(value)))
        duplicate = store.get(digest) is not None
        added = self.add(value)
        cursor = store.current_cursor()
        return IngestionReceipt(
            "DUPLICATE" if duplicate else "INGESTED",
            added.digest,
            str(value.get("metadata", {}).get("recordId", added.digest)),
            domain,
            cursor,
            participant.as_dict() if participant else None,
        ).as_dict()

    def sync(
        self,
        cursor: Mapping[str, Any] | None = None,
        *,
        limit: int = 1000,
        kind: str | None = None,
    ) -> dict[str, object]:
        try:
            return self.require_store().sync_since(cursor, limit=limit, kind=kind)
        except StoreError as error:
            message = str(error)
            code = "STALE_CURSOR" if message.startswith("STALE_CURSOR") else "INVALID_CURSOR"
            raise ExchangeError(code, message) from error

    def ingest_adapter_result(
        self,
        result: AdapterResult,
        *,
        publish: bool = False,
        participant: ParticipantDescriptor | None = None,
        policy: ExchangePolicy | None = None,
        domain: str = "local",
    ) -> dict[str, object]:
        """Validate an explicit adapter result and optionally publish its inert record."""

        record = result.record
        if not result.recognized or not result.valid:
            return {
                "translated": result.as_dict(),
                "published": False,
                "authorityBoundary": "external outcome is not Commons verification",
            }
        if not isinstance(record, Mapping):
            raise ExchangeError(
                "INVALID_EXTERNAL_RECORD", "adapter result did not contain a record"
            )
        validation = self.validate(record)
        response: dict[str, object] = {
            "translated": result.as_dict(),
            "commonsValidation": validation,
            "published": False,
            "authorityBoundary": "external outcome is not Commons verification",
        }
        if publish:
            response["receipt"] = self.publish(
                record,
                participant=participant,
                policy=policy,
                domain=domain,
            )
            response["published"] = True
        return response

    def conversation(
        self, root: str, *, depth: int = 2, max_nodes: int = 1000
    ) -> dict[str, object]:
        graph = self.related(root, depth=depth, max_nodes=max_nodes)
        records = graph.get("records", [])
        if isinstance(records, list):
            records.sort(
                key=lambda item: (
                    str(item.get("metadata", {}).get("createdAt", "")),
                    str(item.get("contentDigest", "")),
                )
            )
        return {
            "exchangeVersion": "commons.mncs.dev/exchange/v0alpha1",
            "root": root,
            "canonicalRepresentation": "typed-record-graph",
            "records": records,
            "edges": graph.get("edges", []),
            "unresolved": graph.get("unresolved", []),
            "truncated": graph.get("truncated", False),
            "authority": "presentation view; graph records remain authoritative",
        }

    def work_queue(
        self, *, limit: int = 100, now=None, domain: str | None = None
    ) -> dict[str, object]:
        values = self.query(QueryFilter(open_work_requests=True, now=now, domain=domain))[
            : max(1, min(limit, 1000))
        ]
        return {
            "records": values,
            "truncated": len(values) >= max(1, min(limit, 1000)),
            "authority": "opportunity list, not commands or permissions",
        }

    def submit_work(self, request: Mapping[str, Any]) -> dict[str, object]:
        """Persist an inert work request; this never dispatches or accepts execution."""

        record = new_work_record(request)
        store = self.require_store()
        work_id = str(record["details"]["workId"])

        def prior_submission() -> Mapping[str, Any] | None:
            return next(
                (
                    item
                    for item in store.records()
                    if item.get("metadata", {}).get("revision") == 1
                    and item.get("details", {}).get("workId") == work_id
                ),
                None,
            )

        def duplicate_ack(prior: Mapping[str, Any]) -> dict[str, object]:
            prior_details = prior.get("details", {})
            requested_details = record["details"]
            immutable = (
                "workId",
                "objective",
                "submittingConsumer",
                "project",
                "repository",
                "constraints",
                "parentWorkId",
                "attempt",
                "routing",
            )
            if not isinstance(prior_details, Mapping) or any(
                prior_details.get(field) != requested_details.get(field) for field in immutable
            ):
                raise WorkProtocolError(
                    "WORK_CONFLICT", "workId is already bound to a different submission"
                )
            status = self.work_status(work_id)
            history = status.get("history", [])
            return {
                "persisted": True,
                "duplicate": True,
                "workId": work_id,
                "state": status["state"],
                "currentDigest": status["currentDigest"],
                "executionAccepted": any(
                    isinstance(item, Mapping) and item.get("state") == "accepted"
                    for item in history
                ),
                "contentTrust": "UNTRUSTED",
                "executionAuthority": "none",
            }

        prior = prior_submission()
        if prior is not None:
            return duplicate_ack(prior)
        try:
            added = store.add_record(record)
        except StoreError:
            # A competing first writer may have committed after the read. Only
            # treat it as an idempotent retry when the immutable submission matches.
            prior = prior_submission()
            if prior is not None:
                return duplicate_ack(prior)
            raise
        details = added.data["details"]
        return {
            "persisted": True,
            "duplicate": False,
            "workId": details["workId"],
            "state": details["state"],
            "currentDigest": added.content_digest,
            "executionAccepted": False,
            "contentTrust": "UNTRUSTED",
            "executionAuthority": "none",
        }

    def transition_work(self, work_id: str, transition: Mapping[str, Any]) -> dict[str, object]:
        """Append one state revision with optimistic lineage protection."""

        current = self.work_status(work_id)["current"]
        if not isinstance(current, Mapping):
            raise WorkProtocolError("WORK_HISTORY_INVALID", "current work record is malformed")
        revised = revised_work_record(current, transition)
        try:
            added = self.require_store().add_record(revised)
        except StoreError as error:
            if "next revision and previousDigest" in str(error):
                raise WorkProtocolError(
                    "WORK_CONFLICT", "work changed before the transition was persisted"
                ) from error
            raise
        details = added.data["details"]
        return {
            "persisted": True,
            "workId": work_id,
            "state": details["state"],
            "currentDigest": added.content_digest,
            "executionAuthority": "none",
        }

    def work_status(self, work_id: str) -> dict[str, Any]:
        return project_work_history(self.require_store().records(), work_id)

    def work_list(
        self,
        *,
        states: set[str] | None = None,
        lanes: set[str] | None = None,
        coordination_states: set[str] | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        values = list_work(
            self.require_store().records(),
            states,
            lanes=lanes,
            coordination_states=coordination_states,
        )
        bounded = max(1, min(limit, 1000))
        return {
            "work": values[:bounded],
            "truncated": len(values) > bounded,
            "contentTrust": "UNTRUSTED",
            "executionAuthority": "none",
        }

    def work_next(
        self,
        *,
        lane: str | None = None,
        repository: str | None = None,
        capabilities: set[str] | None = None,
        limit: int = 1,
    ) -> dict[str, object]:
        values = next_work(
            self.require_store().records(),
            lane=lane,
            repository=repository,
            capabilities=capabilities,
            limit=limit,
        )
        return {
            "work": values,
            "truncated": len(values) >= max(1, min(limit, 1000)),
            "authority": "opportunity list, not commands or permissions",
            "selection": (
                "priority ascending, dependency-unblocking value descending, quiet-project "
                "coverage boost, creation time, then workId; explicit high-priority blockers "
                "remain first"
            ),
        }

    @staticmethod
    def work_policy(lane: str | None = None) -> dict[str, object]:
        selected = sorted(LANES) if lane is None else [lane]
        return {
            "lanes": [lane_policy(item).as_dict() for item in selected],
            "authority": "policy hint; Harness and repository authorization remain external",
        }

    @staticmethod
    def work_scope_check(
        lane: str,
        path: str,
        *,
        repository: str | None = None,
        allowed_write_scope: list[str] | None = None,
    ) -> dict[str, object]:
        return scope_decision(
            lane,
            path,
            assigned_repository=repository,
            allowed_write_scope=allowed_write_scope,
        )

    @staticmethod
    def family_registry() -> dict[str, object]:
        return family_registry()

    def family_coverage(self) -> dict[str, object]:
        return family_coverage(self.require_store().records())

    @staticmethod
    def family_consistency(
        standard: Mapping[str, Any], atlas: Mapping[str, Any]
    ) -> dict[str, object]:
        return validate_family_sources(standard, atlas)

    def propose_work(self, proposal: Mapping[str, Any]) -> dict[str, object]:
        """Classify a bounded worker discovery before exposing it as AVAILABLE work."""

        candidate = dict(proposal)
        # Classification owns these fields; strip any caller-supplied injection
        candidate.pop("proposalStatus", None)
        candidate.pop("coordinationState", None)
        candidate.pop("proposalReason", None)
        candidate.pop("canonicalRepository", None)
        candidate.pop("canonicalAffectedRepositories", None)
        candidate.pop("deduplication", None)
        source = candidate.pop("source", None) or candidate.get("proposalSource")
        source_resolved = isinstance(source, str) and bool(source.strip())
        if not isinstance(source, str) or not source.strip():
            source = "worker-discovery"
        candidate["proposalSource"] = source
        lane = candidate.get("lane")
        repository = candidate.get("repository")
        all_work = list_work(self.require_store().records())
        current = [
            item
            for item in all_work
            if item.get("coordinationState")
            in {
                "AVAILABLE",
                "CLAIMED",
                "IN_PROGRESS",
                "BLOCKED",
                "VERIFYING",
                "NEEDS_RECONCILIATION",
            }
        ]
        reasons: list[str] = []
        if lane not in LANES:
            reasons.append("lane is unresolved")
        canonical_repo = None
        if not isinstance(repository, str) or not repository.strip():
            reasons.append("repository is unresolved")
        else:
            canonical_repo = canonical_project_identity(repository)
            if canonical_repo is None:
                reasons.append("repository is outside the canonical family")
            else:
                # Preserve submitted spelling as provenance, store canonical for matching
                candidate["canonicalRepository"] = canonical_repo["repository"]
                # Normalize affectedRepositories to canonical if it contains the repo
                affected = candidate.get("affectedRepositories", [])
                if isinstance(affected, list):
                    normalized_affected: list[str] = []
                    for item in affected:
                        ident = canonical_project_identity(item)
                        if ident is not None:
                            normalized_affected.append(ident["repository"])
                        elif isinstance(item, str) and item.strip():
                            normalized_affected.append(item.strip())
                    # Ensure canonical repo is included
                    if canonical_repo["repository"] not in normalized_affected:
                        normalized_affected.append(canonical_repo["repository"])
                    candidate["canonicalAffectedRepositories"] = normalized_affected
                else:
                    candidate["canonicalAffectedRepositories"] = [canonical_repo["repository"]]
        if not source_resolved:
            reasons.append("proposal source is unresolved")
        if not candidate.get("evidenceLinks"):
            reasons.append("proposal requires an evidence/source link")
        dependencies = candidate.get("dependencies", [])
        known_work_ids = {item["workId"] for item in all_work}
        if isinstance(dependencies, list) and any(
            str(item).startswith("work:") and str(item) not in known_work_ids
            for item in dependencies
        ):
            reasons.append("one or more work dependencies are unresolved")
        if lane == "SHARED_CORE" and not candidate.get("capability"):
            reasons.append("shared-core proposals require a capability identity")
        capability = candidate.get("capability")
        duplicate = None
        ambiguous: list[str] = []
        finding_identity = candidate.get("findingIdentity")

        # Build canonical repository surface for the candidate:
        # primary + all canonical affected repositories.
        def _candidate_repo_set() -> set[str]:
            # Prefer canonical fields if present
            canon_primary = candidate.get("canonicalRepository")
            canon_affected = candidate.get("canonicalAffectedRepositories")
            s: set[str] = set()
            if isinstance(canon_primary, str) and canon_primary.strip():
                s.add(canon_primary.strip())
            if isinstance(canon_affected, list):
                for v in canon_affected:
                    if isinstance(v, str) and v.strip():
                        s.add(v.strip())
            if s:
                return s
            # Legacy fallback: resolve submitted strings via canonical identity
            fallback: set[str] = set()
            if isinstance(repository, str) and repository.strip():
                ident = canonical_project_identity(repository)
                fallback.add(ident["repository"] if ident else repository.strip())
            for v in candidate.get("affectedRepositories", []) or []:
                if isinstance(v, str) and v.strip():
                    ident = canonical_project_identity(v)
                    fallback.add(ident["repository"] if ident else v.strip())
            return fallback

        candidate_repo_set = _candidate_repo_set()

        def _existing_repo_set(details: Mapping[str, Any]) -> set[str]:
            canon_primary = details.get("canonicalRepository")
            canon_affected = details.get("canonicalAffectedRepositories")
            s: set[str] = set()
            if isinstance(canon_primary, str) and canon_primary.strip():
                s.add(canon_primary.strip())
            if isinstance(canon_affected, list):
                for v in canon_affected:
                    if isinstance(v, str) and v.strip():
                        s.add(v.strip())
            if s:
                return s
            # Legacy fallback
            fallback: set[str] = set()
            legacy_primary = details.get("repository")
            if isinstance(legacy_primary, str) and legacy_primary.strip():
                ident = canonical_project_identity(legacy_primary)
                fallback.add(ident["repository"] if ident else legacy_primary.strip())
            for v in details.get("affectedRepositories", []) or []:
                if isinstance(v, str) and v.strip():
                    ident = canonical_project_identity(v)
                    fallback.add(ident["repository"] if ident else v.strip())
            return fallback

        for item in current:
            details = item["current"].get("details", {})
            if not isinstance(details, Mapping):
                continue
            # Repository overlap is any intersection of the two canonical surfaces
            existing_repo_set = _existing_repo_set(details)
            same_repo = bool(
                candidate_repo_set & existing_repo_set
            ) if candidate_repo_set and existing_repo_set else False
            same_finding = finding_identity and details.get("findingIdentity") == finding_identity
            existing_capability = details.get("capability")
            same_core = lane == "SHARED_CORE" and details.get("lane") == "SHARED_CORE"
            if same_finding and same_repo and details.get("lane") == lane:
                duplicate = item
                break
            if capability and existing_capability and (same_core or same_repo):
                comparison = capability_overlap(capability, existing_capability)
                if comparison == "exact":
                    duplicate = item
                    break
                if comparison == "ambiguous":
                    # Only consider AVAILABLE work for ambiguous pressure; NEEDS_RECONCILIATION
                    # work is not claimable and should not block distinct proposals
                    if item.get("coordinationState") == "AVAILABLE":
                        ambiguous.append(item["workId"])
        # Exact duplicates only attach if the proposal is otherwise valid;
        # invalid proposals must fail closed to NEEDS_RECONCILIATION
        if duplicate is not None and not reasons and not ambiguous:
            existing_details = duplicate["current"].get("details", {})
            attachments = list(existing_details.get("attachments", []))
            attachments.append(
                {
                    "type": "proposal-attachment",
                    "consumer": candidate.get("submittingConsumer"),
                    "evidenceLinks": candidate.get("evidenceLinks", []),
                    "dependencies": candidate.get("dependencies", []),
                    "capability": normalize_capability(capability) if capability else None,
                    "source": source,
                }
            )
            attached = self.transition_work(
                duplicate["workId"],
                {
                    "actor": candidate.get("submittingConsumer"),
                    "expectedPreviousDigest": duplicate["currentDigest"],
                    "attachments": attachments,
                    "reason": "proposal attached to an existing bounded opportunity",
                },
            )
            return {
                "persisted": True,
                "proposal": "ATTACHED",
                "workId": duplicate["workId"],
                "currentDigest": attached["currentDigest"],
                "deduplication": "exact capability or finding identity",
                "executionAuthority": "none",
            }
        if ambiguous:
            reasons.append("capability overlap is plausible but not proven")
        if reasons:
            # Classification owns these fields; force reconciliation regardless of caller
            candidate["proposalStatus"] = "NEEDS_RECONCILIATION"
            candidate["coordinationState"] = "NEEDS_RECONCILIATION"
            candidate["proposalReason"] = "; ".join(reasons)
            candidate["deduplication"] = {
                "status": "NEEDS_RECONCILIATION",
                "candidateWorkIds": ambiguous,
            }
            result = self.submit_work(candidate)
            return {
                **result,
                "proposal": "NEEDS_RECONCILIATION",
                "deduplication": candidate["deduplication"],
                "executionAuthority": "none",
            }
        # Fully resolved: classification grants AVAILABLE
        candidate["proposalStatus"] = "ACCEPTED"
        candidate["coordinationState"] = "AVAILABLE"
        result = self.submit_work(candidate)
        return {**result, "proposal": "ACCEPTED", "executionAuthority": "none"}

    def family_health_sweep(
        self, observations: list[Mapping[str, Any]], *, actor: Mapping[str, Any] | None = None
    ) -> dict[str, object]:
        """Ingest scanner observations and reconcile only their hygiene opportunities."""

        # Bound total observation count, but allow multiple distinct findings per
        # canonical repository (keyed by canonical repository + findingIdentity)
        if not isinstance(observations, list) or len(observations) > 64:
            raise WorkProtocolError(
                "HEALTH_SWEEP_INVALID", "observations must contain at most 64 entries"
            )
        writer = actor or {"type": "operator", "id": "urn:mncs:commons:family-health"}
        observed: list[dict[str, object]] = []
        proposals: list[dict[str, object]] = []
        superseded: list[dict[str, object]] = []
        seen_keys: set[tuple[str, str]] = set()
        # Pre-resolve canonical repositories for supersession matching
        for raw in observations:
            # Validate shape early for precise error, but canonical check happens below
            if not isinstance(raw, Mapping):
                raise WorkProtocolError(
                    "HEALTH_SWEEP_INVALID", "each observation must be an object"
                )
        for raw in observations:
            record, normalized = health_observation_record(raw)
            # Health observations are normalized to UTC instants at intake;
            # repository identity must be canonical
            canonical = canonical_project_identity(normalized["repository"])
            if canonical is None:
                raise WorkProtocolError(
                    "HEALTH_SWEEP_INVALID",
                    "observation repository is outside the canonical family",
                )
            # Enrich normalized with canonical for supersession and proposal
            normalized["canonicalRepository"] = canonical["repository"]
            # Also enrich record for coverage health matching
            record["details"]["canonicalHealthRepository"] = canonical["repository"]
            record["subject"]["identity"] = canonical["repository"]
            record["scope"]["context"]["repository"] = canonical["repository"]
            key = (canonical["repository"], normalized["findingIdentity"])
            if key in seen_keys:
                raise WorkProtocolError(
                    "HEALTH_SWEEP_INVALID",
                    "health sweep accepts at most one observation per "
                    "(repository, findingIdentity)",
                )
            seen_keys.add(key)
            receipt = self.publish(record, domain="local")
            observation_id = str(receipt["logicalRecordId"])
            observed.append({"recordId": observation_id, **normalized})
            if normalized["outcome"] == "FAIL":
                proposal = self.propose_work(
                    {
                        "submittingConsumer": writer,
                        "project": {"id": "mncs-family", "revision": "2026-08"},
                        # Keep original repository spelling; propose_work will canonicalize
                        "repository": normalized["repository"],
                        "affectedRepositories": [normalized["repository"]],
                        "task": normalized["finding"]
                        or f"Repair the observed health failure in {normalized['repository']}",
                        "lane": "REPO_HYGIENE",
                        "priority": 20,
                        "evidenceLinks": [observation_id, normalized["sourceIdentity"]],
                        "proposalSource": normalized["source"],
                        "observationTimestamp": normalized["observedAt"],
                        "findingIdentity": normalized["findingIdentity"],
                        "healthStatus": normalized["outcome"],
                    }
                )
                proposals.append(proposal)
            elif normalized["outcome"] == "PASS":
                # PASS supersession must be repository-scoped and strictly newer
                # than the *latest* FAIL evidence for that (repo, findingIdentity),
                # not merely the original WorkRequest observationTimestamp.
                try:
                    pass_instant = parse_health_instant(normalized["observedAt"])
                except ValueError:
                    continue
                # Build canonical set for the PASS observation (single repo)
                pass_repo_set = {normalized["canonicalRepository"]}
                for item in list_work(
                    self.require_store().records(),
                    coordination_states={"AVAILABLE"},
                ):
                    details = item["current"].get("details", {})
                    if details.get("lane") != "REPO_HYGIENE":
                        continue
                    if details.get("findingIdentity") != normalized["findingIdentity"]:
                        continue
                    # Health reconciliation identity must include canonical repository
                    # Compare canonical sets: primary + all canonical affected
                    def _work_repo_set(d: Mapping[str, Any]) -> set[str]:
                        canon_primary = d.get("canonicalRepository")
                        canon_affected = d.get("canonicalAffectedRepositories")
                        s: set[str] = set()
                        if isinstance(canon_primary, str) and canon_primary.strip():
                            s.add(canon_primary.strip())
                        if isinstance(canon_affected, list):
                            for v in canon_affected:
                                if isinstance(v, str) and v.strip():
                                    s.add(v.strip())
                        if s:
                            return s
                        # Legacy fallback
                        fallback: set[str] = set()
                        legacy_primary = d.get("repository")
                        if isinstance(legacy_primary, str) and legacy_primary.strip():
                            ident = canonical_project_identity(legacy_primary)
                            fallback.add(
                                ident["repository"] if ident else legacy_primary.strip()
                            )
                        for v in d.get("affectedRepositories", []) or []:
                            if isinstance(v, str) and v.strip():
                                ident = canonical_project_identity(v)
                                fallback.add(ident["repository"] if ident else v.strip())
                        return fallback

                    work_repo_set = _work_repo_set(details)
                    if not work_repo_set or not (pass_repo_set & work_repo_set):
                        continue
                    # Determine current failure freshness from durable health evidence/history
                    # Look at all health Observation records for this (repo, finding) with FAIL
                    latest_fail_instant = None
                    work_finding = details.get("findingIdentity")
                    # Scan all health observations (append-only) for latest FAIL
                    for rec in self.require_store().records():
                        if rec.get("kind") != "Observation":
                            continue
                        rec_details = rec.get("details", {})
                        if not isinstance(rec_details, Mapping):
                            continue
                        if rec_details.get("observationType") != "family-health":
                            continue
                        if rec_details.get("outcome") != "FAIL":
                            continue
                        if rec_details.get("findingIdentity") != work_finding:
                            continue
                        # Match canonical repository via set intersection
                        rec_canon = rec_details.get("canonicalHealthRepository")
                        rec_health_repo = rec_details.get("healthRepository")
                        rec_repo_set: set[str] = set()
                        if isinstance(rec_canon, str) and rec_canon.strip():
                            rec_repo_set.add(rec_canon.strip())
                        elif isinstance(rec_health_repo, str) and rec_health_repo.strip():
                            ident = canonical_project_identity(rec_health_repo)
                            rec_repo_set.add(
                                ident["repository"] if ident else rec_health_repo.strip()
                            )
                        if not rec_repo_set or not (rec_repo_set & work_repo_set):
                            continue
                        observed_at = rec_details.get("observedAt")
                        if not isinstance(observed_at, str):
                            continue
                        try:
                            instant = parse_health_instant(observed_at)
                        except ValueError:
                            continue
                        if latest_fail_instant is None or instant > latest_fail_instant:
                            latest_fail_instant = instant
                    # Fallback to work's own observationTimestamp if no health history found
                    if latest_fail_instant is None:
                        work_timestamp = details.get("observationTimestamp")
                        if not isinstance(work_timestamp, str):
                            continue
                        try:
                            latest_fail_instant = parse_health_instant(work_timestamp)
                        except ValueError:
                            continue
                    # Equal-time PASS does not silently override without explicit policy
                    if pass_instant <= latest_fail_instant:
                        continue
                    superseded.append(
                        self.transition_work(
                            item["workId"],
                            {
                                "state": "cancelled",
                                "coordinationState": "SUPERSEDED",
                                "actor": writer,
                                "expectedPreviousDigest": item["currentDigest"],
                                "reason": (
                                    "fresh PASS health observation superseded the hygiene "
                                    "opportunity"
                                ),
                                "result": {
                                    "terminalOutcome": "SUPERSEDED",
                                    "evidence": [{"id": observation_id, "status": "PASS"}],
                                },
                            },
                        )
                    )
        return {
            "observations": observed,
            "proposals": proposals,
            "superseded": superseded,
            "repositoryCount": len({item["repository"] for item in observed}),
            "authority": (
                "scanner observations are inert; Commons records and reconciles opportunities "
                "only"
            ),
            "executionAuthority": "none",
        }

    def claim_work(
        self,
        work_id: str,
        *,
        actor: Mapping[str, Any],
        expected_previous_digest: str,
        session_id: str | None = None,
        lane: str | None = None,
    ) -> dict[str, object]:
        """Claim one AVAILABLE task using the same optimistic revision path as transitions."""

        status = self.work_status(work_id)
        current = status.get("current")
        if not isinstance(current, Mapping):
            raise WorkProtocolError("WORK_HISTORY_INVALID", "current work record is malformed")
        details = current.get("details")
        if not isinstance(details, Mapping):
            raise WorkProtocolError("WORK_HISTORY_INVALID", "current work details are malformed")
        current_lane = details.get("lane")
        if lane is not None and current_lane != lane:
            raise WorkProtocolError("WORK_LANE_MISMATCH", "task is outside the requested lane")
        if coordination_state(details) not in {"AVAILABLE", "BLOCKED"}:
            raise WorkProtocolError("WORK_NOT_AVAILABLE", "task is not claimable")
        actor_type = actor.get("type") if isinstance(actor, Mapping) else None
        actor_id = actor.get("id") if isinstance(actor, Mapping) else None
        if (
            not isinstance(actor_type, str)
            or not actor_type.strip()
            or not isinstance(actor_id, str)
            or not actor_id.strip()
        ):
            raise WorkProtocolError("WORK_ACTOR_REQUIRED", "claim actor type and id are required")
        actor_value = {"type": actor_type.strip(), "id": actor_id.strip()}
        active = list_work(
            self.require_store().records(),
            coordination_states={"CLAIMED", "IN_PROGRESS", "VERIFYING"},
        )
        if current_lane == "SHARED_CORE" and any(
            item["current"].get("details", {}).get("lane") == "SHARED_CORE" for item in active
        ):
            raise WorkProtocolError(
                "WORK_SHARED_CORE_BUSY",
                "SHARED_CORE is single-writer while another core task is active",
            )

        def owned_by_actor(item: Mapping[str, Any]) -> bool:
            item_details = item["current"].get("details", {})
            claim_value = item_details.get("claim") if isinstance(item_details, Mapping) else None
            return (
                item["workId"] != work_id
                and isinstance(claim_value, Mapping)
                and claim_value.get("actor") == actor_value
            )

        if any(owned_by_actor(item) for item in active):
            raise WorkProtocolError(
                "WORK_ACTIVE_CLAIM_LIMIT",
                "worker already holds an active substantive claim",
            )
        claim: dict[str, Any] = {
            "actor": actor_value,
            "claimedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if session_id is not None:
            claim["sessionId"] = session_id
        return self.transition_work(
            work_id,
            {
                "state": "assigned",
                "coordinationState": "CLAIMED",
                "claim": claim,
                "actor": actor_value,
                "expectedPreviousDigest": expected_previous_digest,
                "reason": "worker claimed a lane-scoped Commons opportunity",
            },
        )

    def create_bundle(
        self, output: str | Path, *, roots: list[str] | None = None, max_depth: int = 2
    ) -> dict[str, object]:
        return dict(create_bundle(self.require_store(), output, roots=roots, max_depth=max_depth))

    @staticmethod
    def verify_bundle(path: str | Path) -> dict[str, object]:
        return verify_bundle(path).as_dict()

    @staticmethod
    def import_bundle(path: str | Path, store: CommonsStore) -> dict[str, object]:
        return import_bundle(path, store).as_dict()


class CompatibilityApplication:
    """Read-only producer registry and local drift inspection."""

    @staticmethod
    def list_contracts() -> list[dict[str, object]]:
        return [item.as_dict() for item in contracts()]

    @staticmethod
    def contract(
        producer: str,
        *,
        record_type: str | None = None,
        schema_version: str | None = None,
        contract_id: str | None = None,
    ):
        return contract_for(
            producer,
            record_type=record_type,
            schema_version=schema_version,
            contract_id=contract_id,
        )

    @staticmethod
    def check(
        producer: str,
        repository: Path,
        *,
        record_type: str | None = None,
        schema_version: str | None = None,
        contract_id: str | None = None,
    ) -> dict[str, object]:
        contract = CompatibilityApplication.contract(
            producer,
            record_type=record_type,
            schema_version=schema_version,
            contract_id=contract_id,
        )
        if contract is None:
            return {
                "status": CompatibilityStatus.UNKNOWN.value,
                "diagnostics": [
                    {
                        "code": "UNKNOWN_PRODUCER",
                        "path": "producer",
                        "message": "producer is not registered",
                        "severity": "error",
                    }
                ],
            }
        return check_local(contract, repository).as_dict()

    @staticmethod
    def resolve(record: Mapping[str, object]) -> dict[str, object]:
        resolution = resolve_contract(record)
        return {
            "contract": resolution.contract.as_dict() if resolution.contract else None,
            "diagnostics": [item.as_dict() for item in resolution.diagnostics],
            "resolved": resolution.contract is not None and not resolution.diagnostics,
        }

    @staticmethod
    def report(repositories: Mapping[str, Path]) -> list[dict[str, object]]:
        return [item.as_dict() for item in compatibility_report(repositories)]


class RecordIdentity:
    def __init__(self, digest: str, kind: str) -> None:
        self.digest = digest
        self.kind = kind
