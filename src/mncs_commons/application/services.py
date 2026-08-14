"""Small application services; protocol semantics remain in pure core modules."""

from __future__ import annotations

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
from ..models import EVENT_KIND
from ..query import QueryFilter, bounded_graph, replication_correlation
from ..store import CommonsStore, StoreError
from ..validation import validate_event, validate_record
from ..work import (
    WorkProtocolError,
    list_work,
    new_work_record,
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

    def replications(self, target: str) -> dict[str, object]:
        return dict(replication_correlation(self.require_store().records(), target).as_dict())

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

    def compact_store(self, *, confirm: bool = False, dry_run: bool = True, now: str | None = None) -> dict[str, object]:
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
        values = self.query(
            QueryFilter(open_work_requests=True, now=now, domain=domain)
        )[: max(1, min(limit, 1000))]
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

    def transition_work(
        self, work_id: str, transition: Mapping[str, Any]
    ) -> dict[str, object]:
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

    def work_list(self, *, states: set[str] | None = None, limit: int = 100) -> dict[str, object]:
        values = list_work(self.require_store().records(), states)
        bounded = max(1, min(limit, 1000))
        return {
            "work": values[:bounded],
            "truncated": len(values) > bounded,
            "contentTrust": "UNTRUSTED",
            "executionAuthority": "none",
        }

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
