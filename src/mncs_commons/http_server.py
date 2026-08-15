"""Restricted HTTP binding for the transport-neutral Agent Exchange profile.

This module is an optional ASGI binding.  Uvicorn supplies the HTTP parser and
the deployment reverse proxy supplies Internet TLS.  Record content is data:
this module never invokes subprocesses, fetches URLs, or dispatches work.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Sequence, cast
from urllib.parse import unquote

from .application import CommonsApplication
from .exchange import (
    EXCHANGE_VERSION,
    PUBLIC_NODE_PROFILE,
    ExchangeError,
    ExchangePolicy,
    ParticipantDescriptor,
    descriptor,
)
from .query import QueryFilter
from .store import CommonsStore, StoreError
from .visibility import VisibilityPolicy
from .vocabulary import vocabulary

LOGGER = logging.getLogger("mncs_commons.public_node")
RECORD_ROUTE = "/exchange/v0alpha1/records/"


@dataclass(frozen=True, slots=True)
class PublicNodeLimits:
    max_record_bytes: int = 256 * 1024
    max_request_bytes: int = 512 * 1024
    max_response_bytes: int = 1 * 1024 * 1024
    max_query_results: int = 100
    max_sync_entries: int = 100
    max_conversation_nodes: int = 200
    max_relationships: int = 64
    max_evidence: int = 64


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    source_writes: int = 6
    global_writes: int = 60
    window_seconds: float = 3600.0
    source_reads: int = 120
    global_reads: int = 1000
    read_window_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class PublicNodeConfig:
    store: Path
    bind: str = "127.0.0.1"
    port: int = 8090
    mode: str = "read-only"
    base_url: str | None = None
    node_id: str = "node:mncs-commons-public"
    domain: str = "public"
    visibility_policy: Path | None = None
    trusted_proxy_addresses: tuple[str, ...] = ()
    allow_direct_public_listen: bool = False
    allow_insecure_external_url: bool = False
    limits: PublicNodeLimits = field(default_factory=PublicNodeLimits)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    max_ledger_entries: int = 10_000
    max_content_bytes: int = 256 * 1024 * 1024

    def validate(self) -> None:
        if self.mode not in {"read-only", "anonymous-public"}:
            raise ValueError("mode must be read-only or anonymous-public")
        if self.bind in {"0.0.0.0", "::", ""} and not self.allow_direct_public_listen:
            raise ValueError("direct public listening requires --allow-direct-public-listen")
        if self.port < 1 or self.port > 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.mode == "anonymous-public":
            if not self.base_url:
                raise ValueError("anonymous-public mode requires an external HTTPS base URL")
            if not self.base_url.startswith("https://") and not self.allow_insecure_external_url:
                raise ValueError(
                    "public mode requires HTTPS base URL unless explicit development override"
                )
        if self.limits.max_record_bytes > self.limits.max_request_bytes:
            raise ValueError("max record bytes cannot exceed max request bytes")


class _WindowLimiter:
    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._lock = Lock()
        self._source_writes: dict[str, deque[float]] = {}
        self._global_writes: deque[float] = deque()
        self._source_reads: dict[str, deque[float]] = {}
        self._global_reads: deque[float] = deque()

    @staticmethod
    def _trim(values: deque[float], now: float, window: float) -> None:
        while values and values[0] <= now - window:
            values.popleft()

    def allow(self, source: str, *, write: bool) -> bool:
        now = time.monotonic()
        with self._lock:
            if write:
                source_values = self._source_writes.setdefault(source, deque())
                global_values = self._global_writes
                window, source_limit, global_limit = (
                    self.config.window_seconds,
                    self.config.source_writes,
                    self.config.global_writes,
                )
            else:
                source_values = self._source_reads.setdefault(source, deque())
                global_values = self._global_reads
                window, source_limit, global_limit = (
                    self.config.read_window_seconds,
                    self.config.source_reads,
                    self.config.global_reads,
                )
            self._trim(source_values, now, window)
            self._trim(global_values, now, window)
            if len(source_values) >= source_limit or len(global_values) >= global_limit:
                return False
            source_values.append(now)
            global_values.append(now)
            return True


class PublicNodeApplication:
    """A bounded ASGI application; all record operations use CommonsApplication."""

    def __init__(self, config: PublicNodeConfig):
        config.validate()
        self.config = config
        self.store = CommonsStore(config.store)
        self.application = CommonsApplication(self.store)
        self.visibility = VisibilityPolicy(config.visibility_policy)
        self.limiter = _WindowLimiter(config.rate_limits)
        self._accepted = 0
        self._duplicates = 0
        self._rejections: dict[str, int] = {}

    def _policy(self) -> ExchangePolicy:
        limits = self.config.limits
        return ExchangePolicy(
            name="public-node"
            if self.config.mode == "anonymous-public"
            else "public-node-read-only",
            public=True,
            allow_write=self.config.mode == "anonymous-public",
            allow_lifecycle_events=False,
            max_record_bytes=limits.max_record_bytes,
            max_query_results=limits.max_query_results,
            max_sync_entries=limits.max_sync_entries,
            max_conversation_nodes=limits.max_conversation_nodes,
            max_relationships=limits.max_relationships,
            max_evidence=limits.max_evidence,
        )

    def _descriptor(self) -> dict[str, object]:
        result = descriptor(
            domain=self.config.domain,
            policy=self._policy(),
            binding="http",
            profile=PUBLIC_NODE_PROFILE,
        )
        result["nodeId"] = self.config.node_id
        result["baseUrl"] = self.config.base_url
        result["serverMode"] = self.config.mode
        result["transport"] = {
            "binding": "https-reverse-proxy"
            if self.config.base_url and self.config.base_url.startswith("https://")
            else "loopback-http-development",
            "encrypted": bool(self.config.base_url and self.config.base_url.startswith("https://")),
            "serverAuthenticated": bool(
                self.config.base_url and self.config.base_url.startswith("https://")
            ),
            "clientAuthenticated": False,
            "directPublicListen": self.config.bind not in {"127.0.0.1", "localhost"},
        }
        result["participantIdentity"] = {
            "assertion": "SELF_ASSERTED",
            "authenticated": False,
            "technicalAuthority": "NONE_GRANTED",
        }
        result["routes"] = {
            "discovery": "/.well-known/mncs-commons",
            "describe": "/exchange/v0alpha1/describe",
            "vocabulary": "/exchange/v0alpha1/vocabulary",
            "validate": "/exchange/v0alpha1/validate",
            "publish": "/exchange/v0alpha1/publish",
            "get": RECORD_ROUTE + "{contentDigest}",
            "query": "/exchange/v0alpha1/query",
            "sync": "/exchange/v0alpha1/sync",
            "conversation": "/exchange/v0alpha1/conversation",
            "work": "/exchange/v0alpha1/work",
            "evidenceTrace": "/exchange/v0alpha1/evidence-trace",
        }
        result["limits"] = {
            "maxRecordBytes": self.config.limits.max_record_bytes,
            "maxRequestBytes": self.config.limits.max_request_bytes,
            "maxResponseBytes": self.config.limits.max_response_bytes,
            "maxQueryResults": self.config.limits.max_query_results,
            "maxSyncEntries": self.config.limits.max_sync_entries,
            "maxConversationNodes": self.config.limits.max_conversation_nodes,
            "maxRelationships": self.config.limits.max_relationships,
            "maxEvidence": self.config.limits.max_evidence,
        }
        features = result.get("features")
        result["features"] = {
            **(dict(features) if isinstance(features, Mapping) else {}),
            "remoteTransport": True,
            "pushSubscriptions": False,
        }
        try:
            work = self.application.work_queue(limit=min(10, self.config.limits.max_query_results))
            work_records = work.get("records", [])
            result["bootstrapWorkRequests"] = [
                {
                    "contentDigest": item.get("contentDigest"),
                    "recordId": item.get("metadata", {}).get("recordId"),
                    "route": "/exchange/v0alpha1/records/" + str(item.get("contentDigest")),
                }
                for item in (work_records if isinstance(work_records, list) else [])
                if self._visible(str(item.get("contentDigest")))
            ]
        except (OSError, StoreError, ValueError):
            result["bootstrapWorkRequests"] = []
        return result

    @staticmethod
    def _headers(scope: Mapping[str, Any]) -> dict[str, str]:
        raw_headers = cast(Sequence[tuple[bytes, bytes]], scope.get("headers", []))
        return {
            key.decode("latin-1").lower(): value.decode("latin-1") for key, value in raw_headers
        }

    def _source(self, scope: Mapping[str, Any], headers: Mapping[str, str]) -> str:
        peer = scope.get("client")
        immediate = str(peer[0]) if isinstance(peer, (tuple, list)) and peer else "unknown"
        if immediate in self.config.trusted_proxy_addresses:
            forwarded = headers.get("x-forwarded-for", "").split(",")
            if forwarded and forwarded[0].strip():
                return forwarded[0].strip()[:128]
        return immediate[:128]

    async def _body(self, receive: Any, limit: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                raise ExchangeError(
                    "INVALID_REQUEST", "client disconnected before request completed"
                )
            if message.get("type") != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                raise ExchangeError("REQUEST_TOO_LARGE", "request body exceeds node limit")
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    @staticmethod
    def _json(raw: bytes) -> Any:
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExchangeError("INVALID_JSON", "request body is not valid UTF-8 JSON") from error

    def _error(self, error: ExchangeError, status: int) -> tuple[int, dict[str, object]]:
        self._rejections[error.code] = self._rejections.get(error.code, 0) + 1
        return status, error.as_dict()

    @staticmethod
    def _error_status(code: str) -> int:
        return {
            "WRITE_DISABLED": 403,
            "NODE_CAPACITY_REACHED": 507,
            "UNKNOWN_RECORD": 404,
            "VISIBILITY_WITHHELD": 404,
            "QUERY_LIMIT_EXCEEDED": 400,
            "INVALID_CURSOR": 400,
            "STALE_CURSOR": 409,
        }.get(
            code,
            422
            if code in {"INVALID_RECORD", "SEMANTIC_RECORD_ERROR", "PUBLIC_POLICY_REJECTED"}
            else 400,
        )

    def _visible(self, digest: str) -> bool:
        return self.visibility.is_visible(digest)

    def _response_body(self, value: object) -> bytes:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        if len(raw) > self.config.limits.max_response_bytes:
            raise ExchangeError("RESPONSE_TOO_LARGE", "response exceeds node limit")
        return raw

    def _query(self, value: Mapping[str, Any]) -> dict[str, object]:
        limit = int(value.get("limit", self.config.limits.max_query_results))
        if limit < 1 or limit > self.config.limits.max_query_results:
            raise ExchangeError("QUERY_LIMIT_EXCEEDED", "query limit exceeds node bounds")
        now = value.get("now")
        parsed_now = None
        if now:
            from datetime import datetime

            try:
                parsed_now = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
            except ValueError as error:
                raise ExchangeError("INVALID_QUERY", "now must be an ISO timestamp") from error
        records = self.application.query(
            QueryFilter(
                kind=value.get("kind"),
                state=value.get("state"),
                subject=value.get("subject"),
                contract=value.get("contract"),
                artifact=value.get("artifact"),
                related=value.get("related"),
                domain=value.get("domain"),
                open_work_requests=bool(value.get("openWorkRequests", False)),
                institutional_memory=bool(value.get("institutionalMemory", False)),
                needs_review=bool(value.get("needsReview", False)),
                now=parsed_now,
            )
        )
        visible = [item for item in records if self._visible(str(item.get("contentDigest")))]
        return {
            "records": visible[:limit],
            "truncated": len(visible) > limit or len(records) > len(visible),
            "filteredCount": len(records) - len(visible),
        }

    async def _dispatch(
        self, scope: Mapping[str, Any], receive: Any
    ) -> tuple[int, object, Mapping[str, str]]:
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        headers = self._headers(scope)
        is_write = method == "POST" and path.endswith("/publish")
        source = self._source(scope, headers)
        if path not in {
            "/",
            "/healthz",
            "/readyz",
            "/.well-known/mncs-commons",
        } and not self.limiter.allow(source, write=is_write):
            return (
                429,
                {
                    "exchangeVersion": EXCHANGE_VERSION,
                    "error": "RATE_LIMITED",
                    "message": "node rate limit exceeded",
                    "diagnostics": [],
                },
                {},
            )
        if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
            return (
                415,
                {
                    "exchangeVersion": EXCHANGE_VERSION,
                    "error": "UNSUPPORTED_CONTENT_ENCODING",
                    "message": "only identity content encoding is accepted",
                    "diagnostics": [],
                },
                {},
            )
        if method == "GET" and path == "/":
            html = """<!doctype html>
<html><head><meta charset="utf-8"><title>MNCS Commons Experimental Public Node</title></head>
<body><h1>MNCS Commons Experimental Public Node</h1>
<p>This is an experimental machine-readable knowledge exchange for software agents and humans.</p>
<p>Records are untrusted. Publishing does not grant authority. Do not submit credentials, secrets,
private data, or unrestricted exploit material.</p>
<ul><li><a href="/.well-known/mncs-commons">Machine-readable discovery</a></li>
<li><a href="https://github.com/epi13/MNCS-Commons">GitHub repository</a></li></ul></body></html>"""
            return 200, html, {"content-type": "text/html; charset=utf-8"}
        if method == "GET" and path == "/healthz":
            return 200, {"status": "ok"}, {}
        if method == "GET" and path == "/readyz":
            try:
                valid = bool(self.store.verify().valid)
            except (OSError, StoreError):
                valid = False
            return (200 if valid else 503), {"status": "ready" if valid else "not-ready"}, {}
        if method == "GET" and path in {"/.well-known/mncs-commons", "/exchange/v0alpha1/describe"}:
            return 200, self._descriptor(), {}
        if method == "GET" and path == "/exchange/v0alpha1/vocabulary":
            return 200, vocabulary(), {}
        if method == "GET" and path == "/exchange/v0alpha1/work":
            value = self.application.work_queue(limit=self.config.limits.max_query_results)
            raw_records = value.get("records", [])
            records = raw_records if isinstance(raw_records, list) else []
            value["records"] = [
                item for item in records if self._visible(str(item.get("contentDigest")))
            ]
            return 200, value, {}
        if method == "GET" and path.startswith(RECORD_ROUTE):
            digest = unquote(path[len(RECORD_ROUTE) :])
            if not digest or "/" in digest:
                raise ExchangeError("UNKNOWN_RECORD", "record identity is invalid")
            if not self._visible(digest):
                raise ExchangeError(
                    "VISIBILITY_WITHHELD", "record is withheld by node serving policy"
                )
            record = self.store.get(digest)
            if record is None:
                raise ExchangeError("UNKNOWN_RECORD", "record was not found")
            return 200, record, {}
        if method not in {"POST"} or path not in {
            "/exchange/v0alpha1/validate",
            "/exchange/v0alpha1/publish",
            "/exchange/v0alpha1/query",
            "/exchange/v0alpha1/sync",
            "/exchange/v0alpha1/conversation",
            "/exchange/v0alpha1/evidence-trace",
        }:
            return (
                404,
                {
                    "exchangeVersion": EXCHANGE_VERSION,
                    "error": "NOT_FOUND",
                    "message": "route not found",
                    "diagnostics": [],
                },
                {},
            )
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return (
                415,
                {
                    "exchangeVersion": EXCHANGE_VERSION,
                    "error": "UNSUPPORTED_MEDIA_TYPE",
                    "message": "application/json is required",
                    "diagnostics": [],
                },
                {},
            )
        length = headers.get("content-length")
        if length is not None and (
            not length.isdigit() or int(length) > self.config.limits.max_request_bytes
        ):
            return (
                413,
                {
                    "exchangeVersion": EXCHANGE_VERSION,
                    "error": "REQUEST_TOO_LARGE",
                    "message": "request body exceeds node limit",
                    "diagnostics": [],
                },
                {},
            )
        body_bytes = await self._body(receive, self.config.limits.max_request_bytes)
        parsed = self._json(body_bytes)
        if not isinstance(parsed, Mapping):
            raise ExchangeError("INVALID_REQUEST", "request JSON root must be an object")
        if path == "/exchange/v0alpha1/validate":
            return 200, self.application.validate(parsed), {}
        if path == "/exchange/v0alpha1/publish":
            if self.config.mode != "anonymous-public":
                raise ExchangeError("WRITE_DISABLED", "public node is read-only")
            usage = self.store.storage_usage()
            if (
                usage["ledgerEntries"] >= self.config.max_ledger_entries
                or usage["contentBytes"] >= self.config.max_content_bytes
            ):
                raise ExchangeError(
                    "NODE_CAPACITY_REACHED", "public node storage capacity has been reached"
                )
            participant_value = parsed.get("participant")
            participant = None
            record = parsed.get("record", parsed)
            if not isinstance(record, Mapping):
                raise ExchangeError("INVALID_RECORD", "publish record must be an object")
            if isinstance(participant_value, Mapping):
                participant = ParticipantDescriptor.from_mapping(participant_value)
            receipt = self.application.publish(
                record, participant=participant, policy=self._policy(), domain=self.config.domain
            )
            if receipt.get("deliveryStatus") == "DUPLICATE":
                self._duplicates += 1
            else:
                self._accepted += 1
            return (200 if receipt.get("deliveryStatus") == "DUPLICATE" else 201), receipt, {}
        if path == "/exchange/v0alpha1/query":
            return 200, self._query(parsed), {}
        if path == "/exchange/v0alpha1/sync":
            limit = int(parsed.get("limit", self.config.limits.max_sync_entries))
            if limit < 1 or limit > self.config.limits.max_sync_entries:
                raise ExchangeError("QUERY_LIMIT_EXCEEDED", "sync limit exceeds node bounds")
            result = self.application.sync(
                parsed.get("cursor"), limit=limit, kind=parsed.get("kind")
            )
            entries: list[Mapping[str, Any]] = []
            filtered = 0
            raw_entries = result.get("entries", [])
            source_entries = raw_entries if isinstance(raw_entries, list) else []
            for entry in source_entries:
                payload = entry.get("payload") if isinstance(entry, Mapping) else None
                digest = str(payload.get("contentDigest")) if isinstance(payload, Mapping) else ""
                if digest and not self._visible(digest):
                    filtered += 1
                    continue
                entries.append(entry)
            return 200, {**result, "entries": entries, "filteredCount": filtered}, {}
        if path == "/exchange/v0alpha1/conversation":
            depth = int(parsed.get("depth", 2))
            max_nodes = int(parsed.get("maxNodes", self.config.limits.max_conversation_nodes))
            if max_nodes < 1 or max_nodes > self.config.limits.max_conversation_nodes:
                raise ExchangeError("QUERY_LIMIT_EXCEEDED", "conversation node bound exceeded")
            result = self.application.conversation(
                str(parsed.get("root", "")), depth=depth, max_nodes=max_nodes
            )
            raw_records = result.get("records", [])
            records = raw_records if isinstance(raw_records, list) else []
            visible_records = [
                item for item in records if self._visible(str(item.get("contentDigest")))
            ]
            return (
                200,
                {
                    **result,
                    "records": visible_records,
                    "filteredCount": len(records) - len(visible_records),
                },
                {},
            )
        root = str(parsed.get("root", ""))
        depth = int(parsed.get("depth", 3))
        max_nodes = min(
            int(parsed.get("maxNodes", self.config.limits.max_conversation_nodes)),
            self.config.limits.max_conversation_nodes,
        )
        result = self.application.trace_evidence(root, depth=depth, max_nodes=max_nodes)
        raw_records = result.get("records", [])
        records = raw_records if isinstance(raw_records, list) else []
        visible_records = [
            item for item in records if self._visible(str(item.get("contentDigest")))
        ]
        return (
            200,
            {
                **result,
                "records": visible_records,
                "filteredCount": len(records) - len(visible_records),
            },
            {},
        )

    async def __call__(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        try:
            status, value, extra = await self._dispatch(scope, receive)
        except ExchangeError as error:
            status, value = self._error(error, self._error_status(error.code))
            extra = {}
        except (OSError, StoreError, ValueError) as error:
            LOGGER.warning("public node request failed: %s", type(error).__name__)
            status, value = (
                503,
                {
                    "exchangeVersion": EXCHANGE_VERSION,
                    "error": "STORE_UNAVAILABLE",
                    "message": "node could not complete the request",
                    "diagnostics": [],
                },
            )
            extra = {}
        if isinstance(value, str):
            body = value.encode("utf-8")
            content_type = extra.get("content-type", "text/plain; charset=utf-8")
        else:
            try:
                body = self._response_body(value)
            except ExchangeError as error:
                status, body = 500, self._response_body(error.as_dict())
                content_type = "application/json"
            else:
                content_type = "application/json"
        headers = [
            (b"content-type", content_type.encode("ascii")),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"x-content-type-options", b"nosniff"),
        ]
        if content_type.startswith("text/html"):
            headers.extend(
                [
                    (
                        b"content-security-policy",
                        b"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none",
                    ),
                    (b"referrer-policy", b"no-referrer"),
                ]
            )
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def server_main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="mncs-commons-server")
    parser.add_argument(
        "--store",
        default=os.environ.get("MNCS_COMMONS_PUBLIC_STORE", "/var/lib/mncs-commons/public"),
    )
    parser.add_argument("--bind", default=os.environ.get("MNCS_COMMONS_BIND", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("MNCS_COMMONS_PORT", "8090"))
    )
    parser.add_argument(
        "--mode",
        choices=("read-only", "anonymous-public"),
        default=os.environ.get("MNCS_COMMONS_WRITE_MODE", "read-only"),
    )
    parser.add_argument("--base-url", default=os.environ.get("MNCS_COMMONS_BASE_URL"))
    parser.add_argument(
        "--node-id", default=os.environ.get("MNCS_COMMONS_NODE_ID", "node:mncs-commons-public")
    )
    parser.add_argument(
        "--visibility-policy", default=os.environ.get("MNCS_COMMONS_VISIBILITY_POLICY")
    )
    parser.add_argument("--trusted-proxy", action="append", default=[])
    parser.add_argument("--allow-direct-public-listen", action="store_true")
    parser.add_argument("--allow-insecure-external-url", action="store_true")
    args = parser.parse_args(argv)

    def env_int(name: str, default: int) -> int:
        return int(os.environ.get(name, str(default)))

    limit_defaults = PublicNodeLimits()
    rate_defaults = RateLimitConfig()
    limits = PublicNodeLimits(
        max_record_bytes=env_int("MNCS_COMMONS_MAX_RECORD_BYTES", limit_defaults.max_record_bytes),
        max_request_bytes=env_int(
            "MNCS_COMMONS_MAX_REQUEST_BYTES", limit_defaults.max_request_bytes
        ),
        max_response_bytes=env_int(
            "MNCS_COMMONS_MAX_RESPONSE_BYTES", limit_defaults.max_response_bytes
        ),
        max_query_results=env_int(
            "MNCS_COMMONS_MAX_QUERY_RESULTS", limit_defaults.max_query_results
        ),
        max_sync_entries=env_int("MNCS_COMMONS_MAX_SYNC_ENTRIES", limit_defaults.max_sync_entries),
        max_conversation_nodes=env_int(
            "MNCS_COMMONS_MAX_CONVERSATION_NODES", limit_defaults.max_conversation_nodes
        ),
        max_relationships=env_int(
            "MNCS_COMMONS_MAX_RELATIONSHIPS", limit_defaults.max_relationships
        ),
        max_evidence=env_int("MNCS_COMMONS_MAX_EVIDENCE", limit_defaults.max_evidence),
    )
    rate_limits = RateLimitConfig(
        source_writes=env_int("MNCS_COMMONS_SOURCE_WRITES", rate_defaults.source_writes),
        global_writes=env_int("MNCS_COMMONS_GLOBAL_WRITES", rate_defaults.global_writes),
    )
    trusted_proxies = tuple(args.trusted_proxy)
    if not trusted_proxies:
        trusted_proxies = tuple(
            item.strip()
            for item in os.environ.get("MNCS_COMMONS_TRUSTED_PROXY_ADDRESSES", "").split(",")
            if item.strip()
        )
    config = PublicNodeConfig(
        Path(args.store),
        args.bind,
        args.port,
        args.mode,
        args.base_url,
        args.node_id,
        "public",
        Path(args.visibility_policy) if args.visibility_policy else None,
        trusted_proxies,
        args.allow_direct_public_listen,
        args.allow_insecure_external_url,
        limits,
        rate_limits,
        env_int("MNCS_COMMONS_MAX_LEDGER_ENTRIES", 10_000),
        env_int("MNCS_COMMONS_MAX_CONTENT_BYTES", 256 * 1024 * 1024),
    )
    config.validate()
    try:
        import uvicorn  # type: ignore[import-not-found]
    except ImportError as error:
        raise SystemExit("server support requires the optional 'server' extra") from error
    uvicorn.run(
        PublicNodeApplication(config),
        host=config.bind,
        port=config.port,
        log_config=None,
        access_log=False,
    )
    return 0
