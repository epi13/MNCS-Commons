"""Command-line lifecycle for the persistent controller-local Commons service."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

from .local_service import (
    CommonsAdminClient,
    CommonsClient,
    CommonsService,
    CommonsServiceConfig,
    CommonsServiceError,
    CommonsServiceServer,
    default_service_root,
)
from .store import CommonsStore, StoreError


def _parser() -> argparse.ArgumentParser:
    root = default_service_root()
    parser = argparse.ArgumentParser(prog="mncs-commons-service")
    parser.add_argument("--store", type=Path, default=root / "store")
    parser.add_argument("--socket", type=Path, default=root / "commons.sock")
    parser.add_argument(
        "--operator-socket", type=Path, default=root / "commons-operator.sock"
    )
    parser.add_argument("--domain", default="local")
    parser.add_argument("--timeout", type=float, default=5.0)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    commands.add_parser("status")
    commands.add_parser("doctor")
    commands.add_parser("descriptor")
    commands.add_parser("recover")
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _config(args: argparse.Namespace) -> CommonsServiceConfig:
    return CommonsServiceConfig(
        args.store.expanduser().resolve(),
        args.socket.expanduser().resolve(),
        args.operator_socket.expanduser().resolve(),
        domain=args.domain,
        request_timeout_seconds=args.timeout,
    )


def _run(config: CommonsServiceConfig) -> int:
    store = CommonsStore(config.store_path)
    if not config.store_path.exists():
        store.init()
    # Invalid state remains untouched. The service stays inspectable through
    # status/doctor/recover while ordinary record operations fail closed.
    try:
        store.verify()
    except (OSError, StoreError):
        pass
    server = CommonsServiceServer(CommonsService(config))
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.start()
    try:
        while not stopped.wait(0.5):
            pass
    finally:
        server.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = _config(args)
        if args.command == "run":
            return _run(config)
        if args.command == "recover":
            admin_client = CommonsAdminClient.connect(
                config.operator_socket, timeout=config.request_timeout_seconds
            )
            _print(admin_client.recover())
            return 0
        consumer_client = CommonsClient.connect(
            config.consumer_socket, timeout=config.request_timeout_seconds
        )
        if args.command == "status":
            _print(consumer_client.status())
        elif args.command == "doctor":
            result = consumer_client.doctor()
            _print(result)
            checks = result.get("checks", {})
            return 0 if isinstance(checks, dict) and all(checks.values()) else 2
        else:
            _print(consumer_client.descriptor())
        return 0
    except CommonsServiceError as error:
        print(json.dumps({"error": error.code, "message": error.message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
