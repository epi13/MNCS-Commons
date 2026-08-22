"""Small CLI over reusable Commons services."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .application import CommonsApplication, CompatibilityApplication
from .exchange import ExchangePolicy, ParticipantDescriptor
from .io import load_document
from .models import RecordKind
from .query import QueryFilter
from .remote import RemoteClient
from .store import CommonsStore, StoreError
from .visibility import VisibilityPolicy


def _read(path: str) -> Mapping[str, Any]:
    value = load_document(Path(path))
    if not isinstance(value, Mapping):
        raise ValueError("document root must be an object")
    return value


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mncs-commons", description="MNCS Commons local reference CLI"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("validate", "canonicalize", "id"):
        command = commands.add_parser(name)
        command.add_argument("record")

    store = commands.add_parser("store")
    store_commands = store.add_subparsers(dest="store_command", required=True)
    init = store_commands.add_parser("init")
    init.add_argument("path")
    add = store_commands.add_parser("add")
    add.add_argument("path")
    add.add_argument("record")
    store_commands.add_parser("verify").add_argument("path")
    store_commands.add_parser("diagnose").add_argument("path")
    store_commands.add_parser("recover").add_argument("path")
    store_commands.add_parser("list").add_argument("path")
    store_commands.add_parser("stats").add_argument("path")
    store_commands.add_parser("retention-status").add_argument("path")
    store_commands.add_parser("retention-plan").add_argument("path")
    compact = store_commands.add_parser("compact")
    compact.add_argument("path")
    compact.add_argument("--dry-run", action="store_true")
    compact.add_argument("--confirm", action="store_true")
    compact.add_argument("--now")
    store_commands.add_parser("archives").add_argument("path")
    archive_verify = store_commands.add_parser("archive-verify")
    archive_verify.add_argument("path")
    archive_verify.add_argument("archive_id")
    archive_inspect = store_commands.add_parser("archive-inspect")
    archive_inspect.add_argument("path")
    archive_inspect.add_argument("archive_id")
    pin = store_commands.add_parser("pin")
    pin.add_argument("path")
    pin.add_argument("digest")
    pin.add_argument("--reason", required=True)
    unpin = store_commands.add_parser("unpin")
    unpin.add_argument("path")
    unpin.add_argument("digest")
    seed = store_commands.add_parser("seed-public")
    seed.add_argument("path")
    seed.add_argument("--domain", default="public")

    local = commands.add_parser("local", help="operate a controller-local Commons node")
    local_commands = local.add_subparsers(dest="local_command", required=True)
    local_init = local_commands.add_parser("init")
    local_init.add_argument("path")
    local_status = local_commands.add_parser("status")
    local_status.add_argument("path")
    local_status.add_argument("--domain", default="local")
    local_doctor = local_commands.add_parser("doctor")
    local_doctor.add_argument("path")
    local_doctor.add_argument("--domain", default="local")

    visibility = commands.add_parser("visibility")
    visibility_commands = visibility.add_subparsers(dest="visibility_command", required=True)
    visibility_set = visibility_commands.add_parser("set")
    visibility_set.add_argument("policy")
    visibility_set.add_argument("digest")
    visibility_set.add_argument("--reason", required=True)
    visibility_clear = visibility_commands.add_parser("clear")
    visibility_clear.add_argument("policy")
    visibility_clear.add_argument("digest")
    visibility_commands.add_parser("list").add_argument("policy")

    show = commands.add_parser("show")
    show.add_argument("path")
    show.add_argument("digest")
    query = commands.add_parser("query")
    query.add_argument("path")
    query.add_argument("--kind", choices=[item.value for item in RecordKind])
    query.add_argument("--state")
    query.add_argument("--subject")
    query.add_argument("--contract")
    query.add_argument("--artifact")
    query.add_argument("--related")
    query.add_argument("--institutional-memory", action="store_true")
    query.add_argument("--domain")
    query.add_argument("--open-work-requests", action="store_true")
    query.add_argument("--needs-review", action="store_true")
    query.add_argument("--now")
    query.add_argument("--concept")
    query.add_argument("--language-profile")
    query.add_argument("--backend")
    query.add_argument("--participant")
    query.add_argument("--failure-classification")
    query.add_argument("--experiment-status")
    experiment = commands.add_parser("experiment")
    experiment.add_argument("path")
    experiment.add_argument("experiment_id")
    experiment.add_argument("--depth", type=int, default=3)
    experiment.add_argument("--max-nodes", type=int, default=1000)
    related = commands.add_parser("related")
    related.add_argument("path")
    related.add_argument("digest")
    related.add_argument("--depth", type=int, default=2)
    related.add_argument("--max-nodes", type=int, default=1000)
    replications = commands.add_parser("replications")
    replications.add_argument("path")
    replications.add_argument("target")
    evidence = commands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    trace = evidence_commands.add_parser("trace")
    trace.add_argument("path")
    trace.add_argument("root")
    trace.add_argument("--depth", type=int, default=3)
    trace.add_argument("--max-nodes", type=int, default=1000)
    lifecycle = commands.add_parser("lifecycle")
    lifecycle.add_argument("path")
    lifecycle.add_argument("digest")
    lifecycle.add_argument("--domain")
    bundle = commands.add_parser("bundle")
    bundle_commands = bundle.add_subparsers(dest="bundle_command", required=True)
    create = bundle_commands.add_parser("create")
    create.add_argument("path")
    create.add_argument("output")
    create.add_argument("--root", action="append")
    create.add_argument("--depth", type=int, default=2)
    for name in ("verify", "inspect"):
        bundle_commands.add_parser(name).add_argument("bundle")
    bundle_import = bundle_commands.add_parser("import")
    bundle_import.add_argument("bundle")
    bundle_import.add_argument("path")

    compat = commands.add_parser("compat")
    compat_commands = compat.add_subparsers(dest="compat_command", required=True)
    compat_commands.add_parser("list")
    report = compat_commands.add_parser("report")
    report.add_argument("--repo", action="append", default=[], metavar="PRODUCER=PATH")
    check = compat_commands.add_parser("check-local")
    check.add_argument("--producer", required=True)
    check.add_argument("--repo", required=True)
    for command in (check,):
        command.add_argument("--record-type")
        command.add_argument("--schema-version")
        command.add_argument("--contract-id")

    exchange = commands.add_parser("exchange")
    exchange_commands = exchange.add_subparsers(dest="exchange_command", required=True)
    describe = exchange_commands.add_parser("describe")
    describe.add_argument("--domain", default="local")
    describe.add_argument("--public", action="store_true")
    publish = exchange_commands.add_parser("publish")
    publish.add_argument("path")
    publish.add_argument("record")
    publish.add_argument("--domain", default="local")
    publish.add_argument("--public", action="store_true")
    publish.add_argument("--participant-id")
    publish.add_argument("--implementation", default="unknown-participant")
    publish.add_argument("--software-version")
    publish.add_argument("--model-provider")
    publish.add_argument("--instance-id")
    publish.add_argument("--namespace")
    publish.add_argument("--model-identity")
    publish.add_argument("--session-id")
    publish.add_argument("--producer-identity")
    publish.add_argument("--environment-identity")
    sync = exchange_commands.add_parser("sync")
    sync.add_argument("path")
    sync.add_argument("--cursor")
    sync.add_argument("--limit", type=int, default=1000)
    sync.add_argument("--kind")
    conversation = exchange_commands.add_parser("conversation")
    conversation.add_argument("path")
    conversation.add_argument("root")
    conversation.add_argument("--depth", type=int, default=2)
    conversation.add_argument("--max-nodes", type=int, default=1000)
    work = exchange_commands.add_parser("work-list")
    work.add_argument("path")
    work.add_argument("--limit", type=int, default=100)
    work.add_argument("--domain")
    ingest = exchange_commands.add_parser("ingest-fabric-execution")
    ingest.add_argument("path")
    ingest.add_argument("record")
    ingest.add_argument("--subject-identity", required=True)
    ingest.add_argument("--created-at")
    ingest.add_argument("--publish", action="store_true")
    ingest.add_argument("--domain", default="local")
    ingest.add_argument("--participant-id")
    ingest.add_argument("--implementation", default="unknown-participant")
    ingest.add_argument("--software-version")
    ingest.add_argument("--model-provider")
    ingest.add_argument("--instance-id")
    ingest.add_argument("--namespace")
    ingest.add_argument("--model-identity")
    ingest.add_argument("--session-id")
    ingest.add_argument("--producer-identity")
    ingest.add_argument("--environment-identity")

    server = commands.add_parser("serve")
    server.add_argument("--server-args", nargs=argparse.REMAINDER)

    remote = commands.add_parser("remote")
    remote_commands = remote.add_subparsers(dest="remote_command", required=True)
    remote_commands.add_parser("describe").add_argument("url")
    remote_commands.add_parser("work").add_argument("url")
    remote_get = remote_commands.add_parser("get")
    remote_get.add_argument("url")
    remote_get.add_argument("digest")
    remote_validate = remote_commands.add_parser("validate")
    remote_validate.add_argument("url")
    remote_validate.add_argument("record")
    remote_publish = remote_commands.add_parser("publish")
    remote_publish.add_argument("url")
    remote_publish.add_argument("record")
    remote_sync = remote_commands.add_parser("sync")
    remote_sync.add_argument("url")
    remote_sync.add_argument("--cursor")
    remote_sync.add_argument("--limit", type=int, default=100)
    for command in remote_commands.choices.values():
        command.add_argument("--allow-http", action="store_true")
    return parser


def _repositories(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        producer, separator, path = value.partition("=")
        if not separator or not producer or not path or producer in result:
            raise ValueError("--repo must use one unique PRODUCER=PATH value")
        result[producer] = Path(path)
    return result


def _cursor(value: str | None) -> Mapping[str, Any] | None:
    if value is None:
        return None
    candidate = value
    path = Path(value)
    if path.exists():
        candidate = path.read_text(encoding="utf-8")
    parsed = json.loads(candidate)
    if not isinstance(parsed, Mapping):
        raise ValueError("cursor must be a JSON object")
    return parsed


def _participant(args: argparse.Namespace) -> ParticipantDescriptor | None:
    if not args.participant_id:
        return None
    return ParticipantDescriptor(
        args.participant_id,
        args.implementation,
        args.software_version,
        args.model_provider,
        args.instance_id,
        (),
        args.namespace,
        args.model_identity,
        args.session_id,
        args.producer_identity,
        args.environment_identity,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"validate", "canonicalize", "id"}:
            value = _read(args.record)
            application = CommonsApplication()
            if args.command == "validate":
                result = application.validate(value)
                _print(result)
                return 0 if result["valid"] else 2
            if args.command == "id":
                print(application.identity(value))
                return 0
            normalized = json.loads(application.canonicalize(value).decode("utf-8"))
            if "contentDigest" not in normalized:
                normalized["contentDigest"] = application.identity(normalized)
            print(application.canonicalize(normalized).decode("utf-8"))
            return 0
        if args.command == "store":
            application = CommonsApplication(CommonsStore(args.path))
            if args.store_command == "init":
                application.require_store().init()
                _print({"initialized": str(application.require_store().root)})
                return 0
            if args.store_command == "add":
                value = _read(args.record)
                added = application.add(value)
                _print({"contentDigest": added.digest})
                return 0
            if args.store_command == "seed-public":
                from .bootstrap import seed_public

                _print(seed_public(Path(args.path), args.domain))
                return 0
            if args.store_command == "verify":
                verification = application.verify_store()
                _print(verification)
                return 0 if verification["valid"] else 2
            if args.store_command == "stats":
                records = application.list_records()
                by_kind: dict[str, int] = {}
                for record in records:
                    kind = str(record.get("kind", "UNKNOWN"))
                    by_kind[kind] = by_kind.get(kind, 0) + 1
                work_records = application.work_queue(limit=1000).get("records", [])
                _print(
                    {
                        "usage": application.require_store().storage_usage(),
                        "recordsByKind": dict(sorted(by_kind.items())),
                        "openWorkRequests": len(work_records)
                        if isinstance(work_records, list)
                        else 0,
                    }
                )
                return 0
            if args.store_command == "retention-status":
                _print(application.retention_status())
                return 0
            if args.store_command == "retention-plan":
                _print(application.retention_plan())
                return 0
            if args.store_command == "compact":
                result = application.compact_store(
                    confirm=args.confirm,
                    dry_run=args.dry_run or not args.confirm,
                    now=args.now,
                )
                _print(result)
                return 0
            if args.store_command == "archives":
                _print(application.list_archives())
                return 0
            if args.store_command == "archive-verify":
                _print(application.verify_archive(args.archive_id))
                return 0
            if args.store_command == "archive-inspect":
                _print(application.inspect_archive(args.archive_id))
                return 0
            if args.store_command == "pin":
                _print(application.pin_record(args.digest, reason=args.reason))
                return 0
            if args.store_command == "unpin":
                _print(application.unpin_record(args.digest))
                return 0
            if args.store_command == "diagnose":
                diagnostic = application.diagnose_store()
                _print(diagnostic)
                return 0 if diagnostic["valid"] else 2
            if args.store_command == "recover":
                recovery = application.recover_store()
                _print(recovery)
                return 0 if recovery["valid"] else 2
            records = application.list_records()
            _print(
                [
                    {
                        "contentDigest": item.get("contentDigest"),
                        "kind": item.get("kind"),
                        "subject": item.get("subject"),
                    }
                    for item in records
                ]
            )
            return 0
        if args.command == "local":
            store = CommonsStore(args.path)
            application = CommonsApplication(store)
            if args.local_command == "init":
                store.init()
                _print(application.local_status())
                return 0
            if args.local_command == "status":
                _print(application.local_status(domain=args.domain))
                return 0
            result = application.local_doctor(domain=args.domain)
            _print(result)
            return 0 if result["valid"] else 2
        if args.command == "visibility":
            visibility_policy = VisibilityPolicy(Path(args.policy))
            if args.visibility_command == "set":
                visibility_policy.set_withheld(args.digest, args.reason)
            elif args.visibility_command == "clear":
                visibility_policy.clear(args.digest)
            _print(visibility_policy.entries())
            return 0
        if args.command == "serve":
            from .http_server import server_main

            return server_main(args.server_args or [])
        if args.command == "remote":
            client = RemoteClient(args.url, allow_http=args.allow_http)
            if args.remote_command == "describe":
                _print(client.describe())
            elif args.remote_command == "work":
                _print(client.work())
            elif args.remote_command == "get":
                _print(client.get(args.digest))
            elif args.remote_command == "validate":
                _print(client.validate(_read(args.record)))
            elif args.remote_command == "publish":
                _print(client.publish(_read(args.record)))
            else:
                _print(client.sync(_cursor(args.cursor), args.limit))
            return 0
        if args.command in {
            "show",
            "lifecycle",
            "related",
            "replications",
            "query",
            "evidence",
            "experiment",
        }:
            application = CommonsApplication(CommonsStore(args.path))
        if args.command == "exchange":
            if args.exchange_command == "describe":
                policy = ExchangePolicy.public_profile() if args.public else ExchangePolicy()
                _print(
                    CommonsApplication.describe(
                        domain=args.domain, policy=policy, binding="cli"
                    )
                )
                return 0
            application = CommonsApplication(CommonsStore(args.path))
            if args.exchange_command == "publish":
                participant = _participant(args)
                policy = ExchangePolicy.public_profile() if args.public else ExchangePolicy()
                _print(
                    application.publish(
                        _read(args.record),
                        participant=participant,
                        policy=policy,
                        domain=args.domain,
                    )
                )
                return 0
            if args.exchange_command == "ingest-fabric-execution":
                from .adapters.fabric import from_fabric_execution

                translated = from_fabric_execution(
                    _read(args.record),
                    subject_identity=args.subject_identity,
                    created_at=args.created_at,
                )
                _print(
                    application.ingest_adapter_result(
                        translated,
                        publish=args.publish,
                        participant=_participant(args),
                        domain=args.domain,
                    )
                )
                return 0 if translated.valid else 2
            if args.exchange_command == "sync":
                _print(application.sync(_cursor(args.cursor), limit=args.limit, kind=args.kind))
                return 0
            if args.exchange_command == "conversation":
                _print(
                    application.conversation(args.root, depth=args.depth, max_nodes=args.max_nodes)
                )
                return 0
            _print(application.work_queue(limit=args.limit, domain=args.domain))
            return 0
        if args.command == "show":
            shown = application.require_store().get(args.digest)
            if shown is None:
                raise StoreError(f"not found: {args.digest}")
            _print(shown)
        elif args.command == "lifecycle":
            _print(application.lifecycle(args.digest, domain=args.domain))
        elif args.command == "related":
            _print(application.related(args.digest, depth=args.depth, max_nodes=args.max_nodes))
        elif args.command == "replications":
            _print(application.replications(args.target))
        elif args.command == "evidence":
            _print(
                application.trace_evidence(args.root, depth=args.depth, max_nodes=args.max_nodes)
            )
        elif args.command == "query":
            query_now = None
            if args.now:
                query_now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            elif args.needs_review:
                query_now = datetime.now(timezone.utc)
            query_records = application.query(
                QueryFilter(
                    kind=args.kind,
                    state=args.state,
                    subject=args.subject,
                    contract=args.contract,
                    artifact=args.artifact,
                    related=args.related,
                    domain=args.domain,
                    open_work_requests=args.open_work_requests,
                    institutional_memory=args.institutional_memory,
                    needs_review=args.needs_review,
                    now=query_now,
                    concept=args.concept,
                    language_profile=args.language_profile,
                    backend=args.backend,
                    participant=args.participant,
                    failure_classification=args.failure_classification,
                    experiment_status=args.experiment_status,
                )
            )
            _print(query_records)
        elif args.command == "experiment":
            _print(
                application.experiment(
                    args.experiment_id, depth=args.depth, max_nodes=args.max_nodes
                )
            )
        elif args.command == "bundle":
            if args.bundle_command == "create":
                manifest = CommonsApplication(CommonsStore(args.path)).create_bundle(
                    args.output, roots=args.root, max_depth=args.depth
                )
                _print(manifest)
            elif args.bundle_command in {"verify", "inspect"}:
                bundle_verification = CommonsApplication.verify_bundle(args.bundle)
                _print(bundle_verification)
                return 0 if bundle_verification["valid"] else 2
            else:
                bundle_verification = CommonsApplication.import_bundle(
                    args.bundle, CommonsStore(args.path)
                )
                _print(bundle_verification)
                return 0 if bundle_verification["valid"] else 2
        elif args.command == "compat":
            if args.compat_command == "list":
                _print(CompatibilityApplication.list_contracts())
            elif args.compat_command == "report":
                _print(CompatibilityApplication.report(_repositories(args.repo)))
            else:
                _print(
                    CompatibilityApplication.check(
                        args.producer,
                        Path(args.repo),
                        record_type=args.record_type,
                        schema_version=args.schema_version,
                        contract_id=args.contract_id,
                    )
                )
        return 0
    except (OSError, ValueError, StoreError) as error:
        print(json.dumps({"valid": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
