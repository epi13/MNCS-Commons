"""Small CLI over reusable Commons services."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .application import CommonsApplication, CompatibilityApplication
from .io import load_document
from .models import RecordKind
from .query import QueryFilter
from .store import CommonsStore, StoreError


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
    query.add_argument("--domain")
    query.add_argument("--open-work-requests", action="store_true")
    query.add_argument("--needs-review", action="store_true")
    query.add_argument("--now")
    related = commands.add_parser("related")
    related.add_argument("path")
    related.add_argument("digest")
    related.add_argument("--depth", type=int, default=2)
    related.add_argument("--max-nodes", type=int, default=1000)
    replications = commands.add_parser("replications")
    replications.add_argument("path")
    replications.add_argument("target")
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
    return parser


def _repositories(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        producer, separator, path = value.partition("=")
        if not separator or not producer or not path or producer in result:
            raise ValueError("--repo must use one unique PRODUCER=PATH value")
        result[producer] = Path(path)
    return result


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
            if args.store_command == "verify":
                verification = application.verify_store()
                _print(verification)
                return 0 if verification["valid"] else 2
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
        if args.command in {"show", "lifecycle", "related", "replications", "query"}:
            application = CommonsApplication(CommonsStore(args.path))
        if args.command == "show":
            shown = application.require_store().get(args.digest)
            if shown is None:
                raise StoreError(f"not found: {args.digest}")
            _print(shown)
        elif args.command == "lifecycle":
            _print(application.lifecycle(args.digest, domain=args.domain))
        elif args.command == "related":
            _print(
                application.related(args.digest, depth=args.depth, max_nodes=args.max_nodes)
            )
        elif args.command == "replications":
            _print(application.replications(args.target))
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
                    needs_review=args.needs_review,
                    now=query_now,
                )
            )
            _print(query_records)
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
                _print(CompatibilityApplication.check(args.producer, Path(args.repo)))
        return 0
    except (OSError, ValueError, StoreError) as error:
        print(json.dumps({"valid": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
