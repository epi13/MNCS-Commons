"""Bounded controller-local service and public clients for MNCS Commons.

The local protocol is deliberately separate from the record/exchange protocols.
It exposes one read-only consumer socket and one operator socket.  Records and
WorkRequests remain inert data; no operation in this module executes content.
"""

from __future__ import annotations

import errno
import importlib
import json
import os
import re
import socket
import stat
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Self

try:
    fcntl: Any = importlib.import_module("fcntl")
except ImportError:  # pragma: no cover - the service itself requires POSIX.
    fcntl = None

from . import __version__
from .application import CommonsApplication
from .canonical import canonical_json
from .exchange import ExchangeError, ExchangePolicy, ParticipantDescriptor
from .query import QueryFilter
from .store import CommonsStore, StoreError
from .work import WORK_STATES, WorkProtocolError

SERVICE_PROTOCOL = "commons.mncs.dev/local-service/v0alpha1"
SERVICE_REQUEST = "commons.mncs.dev/local-service-request/v0alpha1"
SERVICE_RESPONSE = "commons.mncs.dev/local-service-response/v0alpha1"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ARGUMENTS_BYTES = 768 * 1024
MAX_TEXT = 4096
MAX_CURSOR_BYTES = 64 * 1024
MAX_LIMIT = 1000
MAX_CONNECTIONS = 32
REQUEST_TTL_SECONDS = 30.0

CONSUMER_OPERATIONS = frozenset(
    {
        "service.status",
        "service.doctor",
        "service.descriptor",
        "commons.describe",
        "commons.validate",
        "commons.get",
        "commons.query",
        "commons.sync",
        "commons.conversation",
        "commons.experiment",
        "commons.work",
        "commons.evidence",
        "work.status",
        "work.list",
        "store.retention",
    }
)
OPERATOR_OPERATIONS = frozenset(
    {
        "commons.publish",
        "store.recover",
        "store.compact",
        "store.pin",
        "store.unpin",
        "work.submit",
        "work.transition",
    }
)
ALL_OPERATIONS = CONSUMER_OPERATIONS | OPERATOR_OPERATIONS
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class CommonsServiceError(RuntimeError):
    """A bounded local-service error with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def default_service_root() -> Path:
    root = os.environ.get("XDG_STATE_HOME")
    return (
        Path(root) / "mncs-commons"
        if root
        else Path.home() / ".local" / "state" / "mncs-commons"
    )


def _current_uid() -> int:
    getuid = getattr(os, "getuid", None)
    if not callable(getuid):
        raise CommonsServiceError(
            "TRANSPORT_UNSUPPORTED", "local service requires POSIX user identities"
        )
    return int(getuid())


def _af_unix() -> int:
    value = getattr(socket, "AF_UNIX", None)
    if not isinstance(value, int):
        raise CommonsServiceError(
            "TRANSPORT_UNSUPPORTED", "local service requires POSIX AF_UNIX"
        )
    return value


@dataclass(frozen=True, slots=True)
class CommonsServiceConfig:
    store_path: Path
    consumer_socket: Path
    operator_socket: Path
    domain: str = "local"
    request_timeout_seconds: float = 10.0
    max_connections: int = MAX_CONNECTIONS

    def __post_init__(self) -> None:
        if not self.domain or len(self.domain) > 256 or "\x00" in self.domain:
            raise CommonsServiceError("CONFIG_INVALID", "domain must be bounded text")
        if not 0.1 <= self.request_timeout_seconds <= 30.0:
            raise CommonsServiceError("CONFIG_INVALID", "request timeout is outside bounds")
        if not 1 <= self.max_connections <= MAX_CONNECTIONS:
            raise CommonsServiceError("CONFIG_INVALID", "connection bound is invalid")
        if self.consumer_socket == self.operator_socket:
            raise CommonsServiceError("CONFIG_INVALID", "consumer and operator sockets must differ")

    @classmethod
    def default(cls) -> CommonsServiceConfig:
        root = default_service_root()
        return cls(root / "store", root / "commons.sock", root / "commons-operator.sock")


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise CommonsServiceError("PROTOCOL_INVALID", f"{field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CommonsServiceError("PROTOCOL_INVALID", f"{field} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommonsServiceError("PROTOCOL_INVALID", f"{field} requires a timezone")
    return parsed.astimezone(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_exact(stream: socket.socket, size: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise CommonsServiceError("TRANSPORT_TIMEOUT", "service request timed out")
        stream.settimeout(timeout)
        chunk = stream.recv(remaining)
        if not chunk:
            raise CommonsServiceError("FRAME_TRUNCATED", "service frame was truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _receive_frame(stream: socket.socket, *, maximum: int, deadline: float) -> dict[str, Any]:
    header = _read_exact(stream, 4, deadline)
    size = struct.unpack("!I", header)[0]
    if size < 2 or size > maximum:
        raise CommonsServiceError("FRAME_INVALID", "service frame size is invalid")
    raw = _read_exact(stream, size, deadline)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CommonsServiceError("FRAME_INVALID", "service frame is not valid JSON") from error
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise CommonsServiceError("FRAME_INVALID", "service frame must be a canonical object")
    return value


def _send_frame(stream: socket.socket, value: Mapping[str, Any], *, maximum: int) -> None:
    raw = canonical_json(value)
    if len(raw) > maximum:
        raise CommonsServiceError("RESPONSE_LIMIT_EXCEEDED", "service response exceeds its bound")
    stream.sendall(struct.pack("!I", len(raw)) + raw)


def _request(operation: str, arguments: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    created = datetime.now(timezone.utc)
    return {
        "schemaVersion": SERVICE_REQUEST,
        "requestId": f"request:{uuid.uuid4().hex}",
        "operation": operation,
        "arguments": dict(arguments),
        "createdAt": created.isoformat().replace("+00:00", "Z"),
        "expiresAt": (created + timedelta(seconds=min(timeout, REQUEST_TTL_SECONDS)))
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _validate_request(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schemaVersion",
        "requestId",
        "operation",
        "arguments",
        "createdAt",
        "expiresAt",
    }
    if set(value) != expected or value.get("schemaVersion") != SERVICE_REQUEST:
        raise CommonsServiceError("PROTOCOL_UNSUPPORTED", "request schema is unsupported")
    request_id = value.get("requestId")
    operation = value.get("operation")
    arguments = value.get("arguments")
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise CommonsServiceError("PROTOCOL_INVALID", "request identity is invalid")
    if not isinstance(operation, str) or operation not in ALL_OPERATIONS:
        raise CommonsServiceError("OPERATION_UNSUPPORTED", "operation is unsupported")
    if not isinstance(arguments, dict) or len(arguments) > 32:
        raise CommonsServiceError("PROTOCOL_INVALID", "arguments must be a bounded object")
    if len(canonical_json(arguments)) > MAX_ARGUMENTS_BYTES:
        raise CommonsServiceError("REQUEST_LIMIT_EXCEEDED", "arguments exceed their bound")
    created = _timestamp(value.get("createdAt"), "createdAt")
    expires = _timestamp(value.get("expiresAt"), "expiresAt")
    if expires < created or expires - created > timedelta(seconds=REQUEST_TTL_SECONDS):
        raise CommonsServiceError("PROTOCOL_INVALID", "request expiry is invalid")
    return dict(value)


def _response(
    request_id: str,
    *,
    result: Mapping[str, Any] | None = None,
    error: CommonsServiceError | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SERVICE_RESPONSE,
        "requestId": request_id,
        "ok": error is None,
        "result": dict(result or {}),
        "error": {"code": error.code, "message": error.message} if error else None,
        "servedAt": _now(),
    }


def _safe_socket_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = os.lstat(path.parent)
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise CommonsServiceError("SOCKET_PATH_UNSAFE", "socket parent is not a real directory")
    if parent.st_uid != _current_uid():
        raise CommonsServiceError("SOCKET_PATH_UNSAFE", "socket parent owner is unsafe")
    os.chmod(path.parent, 0o700)
    parent = os.lstat(path.parent)
    if parent.st_mode & 0o077:
        raise CommonsServiceError("SOCKET_PATH_UNSAFE", "socket parent permissions are unsafe")
    if path.exists() or path.is_symlink():
        entry = os.lstat(path)
        if not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != _current_uid():
            raise CommonsServiceError("SOCKET_PATH_UNSAFE", "socket path is not an owned socket")


def _socket_ready(path: Path) -> bool:
    try:
        entry = os.lstat(path)
    except OSError:
        return False
    return (
        stat.S_ISSOCK(entry.st_mode)
        and entry.st_uid == _current_uid()
        and stat.S_IMODE(entry.st_mode) == 0o600
    )


def _bounded_text(value: object, field: str, *, allow_none: bool = True) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT or "\x00" in value:
        raise CommonsServiceError("INVALID_ARGUMENTS", f"{field} must be bounded text")
    return value


def _limit(value: object, default: int) -> int:
    result = default if value is None else value
    if isinstance(result, bool) or not isinstance(result, int):
        raise CommonsServiceError("INVALID_ARGUMENTS", "limit must be an integer")
    if not 1 <= result <= MAX_LIMIT:
        raise CommonsServiceError("INVALID_ARGUMENTS", f"limit must be between 1 and {MAX_LIMIT}")
    return result


def _boolean(value: object, field: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise CommonsServiceError("INVALID_ARGUMENTS", f"{field} must be a boolean")
    return value


def _bounded_integer(value: object, field: str, default: int, maximum: int) -> int:
    result = default if value is None else value
    if isinstance(result, bool) or not isinstance(result, int) or not 0 <= result <= maximum:
        raise CommonsServiceError(
            "INVALID_ARGUMENTS", f"{field} must be an integer between 0 and {maximum}"
        )
    return result


def _only(arguments: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(arguments) - allowed
    if unknown:
        raise CommonsServiceError("INVALID_ARGUMENTS", "unexpected arguments")


def _tool_schema(
    name: str,
    description: str,
    properties: Mapping[str, Any],
    *,
    capability: str = "consumer-read",
    authority: str = "consumer",
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": dict(properties)},
        },
        "mncs_commons": {
            "capability": capability,
            "authority": authority,
            "executionAuthority": "none",
        },
    }


def service_tool_schemas() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return consumer and operator model-tool projections for service clients."""

    consumer = [
        _tool_schema("commons_describe", "Describe this Commons service.", {}),
        _tool_schema(
            "commons_validate_record",
            "Validate an inert Commons record without storing it.",
            {"record": {"type": "object"}},
        ),
        _tool_schema(
            "commons_get_record",
            "Get one Commons record by digest.",
            {"digest": {"type": "string"}},
        ),
        _tool_schema(
            "commons_query",
            "Run a bounded structured Commons query.",
            {
                "kind": {"type": "string"},
                "state": {"type": "string"},
                "subject": {"type": "string"},
                "contract": {"type": "string"},
                "artifact": {"type": "string"},
                "related": {"type": "string"},
                "domain": {"type": "string"},
                "openWorkRequests": {"type": "boolean"},
                "institutionalMemory": {"type": "boolean"},
                "needsReview": {"type": "boolean"},
                "concept": {"type": "string"},
                "languageProfile": {"type": "string"},
                "backend": {"type": "string"},
                "participant": {"type": "string"},
                "failureClassification": {"type": "string"},
                "experimentStatus": {"type": "string"},
                "now": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
            },
        ),
        _tool_schema(
            "commons_sync",
            "Read a bounded ordered ledger slice.",
            {
                "cursor": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                "kind": {"type": "string"},
            },
        ),
        _tool_schema(
            "commons_conversation",
            "Project a bounded typed record graph.",
            {
                "root": {"type": "string"},
                "depth": {"type": "integer", "minimum": 0, "maximum": 8},
                "maxNodes": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
            },
        ),
        _tool_schema(
            "commons_work_list",
            "List work opportunities as inert data, never commands.",
            {
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                "domain": {"type": "string"},
            },
        ),
        _tool_schema(
            "commons_evidence_trace",
            "Trace bounded evidence lineage without inferring truth.",
            {
                "root": {"type": "string"},
                "depth": {"type": "integer", "minimum": 0, "maximum": 8},
                "maxNodes": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
            },
        ),
        _tool_schema(
            "commons_experiment",
            "Project a bounded Concept Experiment graph without changing producer semantics.",
            {
                "experimentId": {"type": "string"},
                "depth": {"type": "integer", "minimum": 0, "maximum": 8},
                "maxNodes": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
            },
        ),
        _tool_schema(
            "commons_work_status",
            "Read durable, untrusted work state and append-only revision history.",
            {"workId": {"type": "string"}},
        ),
        _tool_schema(
            "commons_durable_work_list",
            "List durable work records as inert state assertions.",
            {
                "states": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
            },
        ),
    ]
    operator = [
        _tool_schema(
            "commons_publish_record",
            "Publish one record; delivery grants no acceptance or authority.",
            {"record": {"type": "object"}, "participant": {"type": "object"}},
            capability="model-publication",
            authority="operator",
        ),
        _tool_schema(
            "commons_submit_work_record",
            "Persist an inert work request without accepting or dispatching execution.",
            {"request": {"type": "object"}},
            capability="model-publication",
            authority="operator",
        ),
        _tool_schema(
            "commons_transition_work_record",
            "Append an untrusted work-state revision with optimistic lineage checks.",
            {"workId": {"type": "string"}, "transition": {"type": "object"}},
            capability="model-publication",
            authority="operator",
        ),
        _tool_schema(
            "commons_retention_status",
            "Inspect Commons hot-store retention pressure. Grants no deletion authority.",
            {},
            capability="operator-admin",
            authority="operator",
        ),
        _tool_schema(
            "commons_compact_store",
            "Operator compaction. Destructive replacement requires confirm=true.",
            {
                "confirm": {"type": "boolean"},
                "dryRun": {"type": "boolean"},
                "now": {"type": "string"},
            },
            capability="operator-admin",
            authority="operator",
        ),
    ]
    return consumer, operator


class CommonsService:
    """Own one Commons store independently of consumer process lifetimes."""

    def __init__(self, config: CommonsServiceConfig):
        self.config = config
        self.store = CommonsStore(config.store_path)
        self.application = CommonsApplication(self.store)
        self._recent_requests: deque[str] = deque(maxlen=4096)
        self._request_lock = threading.Lock()

    def _verification(self) -> dict[str, object]:
        try:
            return self.store.verify().as_dict()
        except (OSError, StoreError) as error:
            return {
                "valid": False,
                "diagnostics": [{"code": "STORE_UNREADABLE", "message": str(error)}],
            }

    def status(self) -> dict[str, object]:
        verification = self._verification()
        valid = verification.get("valid") is True
        diagnostics = verification.get("diagnostics", [])
        recovery_required = isinstance(diagnostics, list) and any(
            isinstance(item, Mapping) and item.get("code") == "PENDING_TRANSACTION"
            for item in diagnostics
        )
        record_count: int | None = None
        if valid:
            try:
                record_count = len(self.store.records())
            except (OSError, StoreError):
                valid = False
        consumer_socket_ready = _socket_ready(self.config.consumer_socket)
        operator_socket_ready = _socket_ready(self.config.operator_socket)
        return {
            "serviceProtocol": SERVICE_PROTOCOL,
            "packageVersion": __version__,
            "serviceOwner": "mncs-commons",
            "domain": self.config.domain,
            "storeHealthy": valid,
            "recoveryRequired": recovery_required,
            "recordCount": record_count,
            "consumerReadCapable": valid and consumer_socket_ready,
            "operatorPublicationCapable": valid and operator_socket_ready,
            "consumerSocketReady": consumer_socket_ready,
            "operatorSocketReady": operator_socket_ready,
            "contentTrust": "UNTRUSTED",
            "executionAuthority": "none",
        }

    def doctor(self) -> dict[str, object]:
        status = self.status()
        verification = self._verification()
        return {
            **status,
            "verification": verification,
            "checks": {
                "protocolCompatible": status["serviceProtocol"] == SERVICE_PROTOCOL,
                "storeHealthy": status["storeHealthy"],
                "recoveryNotRequired": status["recoveryRequired"] is False,
                "separateAuthoritySockets": self.config.consumer_socket
                != self.config.operator_socket,
                "consumerSocketOwnedAndPrivate": status["consumerSocketReady"],
                "operatorSocketOwnedAndPrivate": status["operatorSocketReady"],
            },
        }

    def descriptor(self) -> dict[str, object]:
        consumer_tools, operator_tools = service_tool_schemas()
        return {
            "serviceProtocol": SERVICE_PROTOCOL,
            "recordProtocol": "commons.mncs.dev/v0alpha1",
            "exchangeProtocol": "commons.mncs.dev/exchange/v0alpha1",
            "transport": "LOCAL_UNIX_SOCKET",
            "consumerOperations": sorted(CONSUMER_OPERATIONS),
            "operatorOperations": sorted(OPERATOR_OPERATIONS),
            "consumerTools": consumer_tools,
            "operatorTools": operator_tools,
            "toolCapabilities": {
                "consumer-read": "discover, read, and query inert Commons knowledge",
                "model-publication": "publish permitted inert records without execution authority",
                "operator-admin": "operator retention/compaction; never model-facing",
            },
            "publicationMeaning": "delivery-only",
            "contentTrust": "UNTRUSTED",
            "executionAuthority": "none",
        }

    def _require_healthy(self) -> None:
        if self.status()["storeHealthy"] is not True:
            raise CommonsServiceError("STORE_UNHEALTHY", "Commons store is not healthy")

    def handle(self, request_value: Mapping[str, Any], *, role: str) -> dict[str, Any]:
        request = _validate_request(request_value)
        request_id = str(request["requestId"])
        if _timestamp(request["expiresAt"], "expiresAt") <= datetime.now(timezone.utc):
            return _response(
                request_id,
                error=CommonsServiceError("REQUEST_EXPIRED", "request deadline expired"),
            )
        with self._request_lock:
            if request_id in self._recent_requests:
                return _response(
                    request_id,
                    error=CommonsServiceError("REQUEST_REPLAYED", "request was already served"),
                )
            self._recent_requests.append(request_id)
        operation = str(request["operation"])
        if role not in {"consumer", "operator"}:
            return _response(
                request_id,
                error=CommonsServiceError("AUTHORITY_DENIED", "service role is invalid"),
            )
        if operation in OPERATOR_OPERATIONS and role != "operator":
            return _response(
                request_id,
                error=CommonsServiceError(
                    "AUTHORITY_DENIED", "operation requires the operator socket"
                ),
            )
        arguments = request["arguments"]
        try:
            result = self._dispatch(operation, arguments)
            return _response(request_id, result=result)
        except CommonsServiceError as error:
            return _response(request_id, error=error)
        except WorkProtocolError as error:
            return _response(
                request_id,
                error=CommonsServiceError(error.code, error.message[:MAX_TEXT]),
            )
        except (ExchangeError, StoreError, OSError, ValueError, TypeError, KeyError) as error:
            return _response(
                request_id,
                error=CommonsServiceError("REQUEST_REJECTED", str(error)[:MAX_TEXT]),
            )

    def _dispatch(self, operation: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if operation == "service.status":
            _only(arguments, set())
            return self.status()
        if operation == "service.doctor":
            _only(arguments, set())
            return self.doctor()
        if operation == "service.descriptor":
            _only(arguments, set())
            return self.descriptor()
        if operation == "commons.describe":
            _only(arguments, set())
            return self.application.describe(
                domain=self.config.domain, binding="local-service"
            )
        if operation == "commons.validate":
            _only(arguments, {"record"})
            record = arguments.get("record")
            if not isinstance(record, Mapping):
                raise CommonsServiceError("INVALID_ARGUMENTS", "record must be an object")
            return self.application.validate(record)
        if operation == "store.recover":
            _only(arguments, set())
            return self.application.recover_store()
        if operation == "store.retention":
            _only(arguments, set())
            return self.application.retention_status()
        if operation == "store.compact":
            _only(arguments, {"confirm", "dryRun", "now"})
            return self.application.compact_store(
                confirm=arguments.get("confirm") is True,
                dry_run=arguments.get("dryRun") is not False,
                now=arguments.get("now") if isinstance(arguments.get("now"), str) else None,
            )
        if operation == "store.pin":
            _only(arguments, {"digest", "reason"})
            digest = _bounded_text(arguments.get("digest"), "digest", allow_none=False)
            reason = _bounded_text(arguments.get("reason"), "reason", allow_none=False)
            if digest is None or reason is None:
                raise CommonsServiceError("INVALID_ARGUMENTS", "pin requires digest and reason")
            return self.application.pin_record(digest, reason=reason)
        if operation == "store.unpin":
            _only(arguments, {"digest"})
            digest = _bounded_text(arguments.get("digest"), "digest", allow_none=False)
            if digest is None:
                raise CommonsServiceError("INVALID_ARGUMENTS", "unpin requires digest")
            return self.application.unpin_record(digest)
        self._require_healthy()
        if operation == "commons.get":
            _only(arguments, {"digest"})
            digest = _bounded_text(arguments.get("digest"), "digest", allow_none=False)
            if digest is None or not _DIGEST.fullmatch(digest):
                raise CommonsServiceError("INVALID_ARGUMENTS", "digest is malformed")
            record = self.application.get_record(digest)
            if record is None:
                raise CommonsServiceError("NOT_FOUND", "record was not found")
            return dict(record)
        if operation == "commons.query":
            allowed = {
                "kind",
                "state",
                "subject",
                "contract",
                "artifact",
                "related",
                "domain",
                "openWorkRequests",
                "institutionalMemory",
                "needsReview",
                "now",
                "limit",
                "concept",
                "languageProfile",
                "backend",
                "participant",
                "failureClassification",
                "experimentStatus",
            }
            _only(arguments, allowed)
            now_value = _bounded_text(arguments.get("now"), "now")
            now = _timestamp(now_value, "now") if now_value else None
            records = self.application.query(
                QueryFilter(
                    kind=_bounded_text(arguments.get("kind"), "kind"),
                    state=_bounded_text(arguments.get("state"), "state"),
                    subject=_bounded_text(arguments.get("subject"), "subject"),
                    contract=_bounded_text(arguments.get("contract"), "contract"),
                    artifact=_bounded_text(arguments.get("artifact"), "artifact"),
                    related=_bounded_text(arguments.get("related"), "related"),
                    domain=_bounded_text(arguments.get("domain"), "domain"),
                    open_work_requests=_boolean(
                        arguments.get("openWorkRequests"), "openWorkRequests"
                    ),
                    institutional_memory=_boolean(
                        arguments.get("institutionalMemory"), "institutionalMemory"
                    ),
                    needs_review=_boolean(arguments.get("needsReview"), "needsReview"),
                    now=now,
                    concept=_bounded_text(arguments.get("concept"), "concept"),
                    language_profile=_bounded_text(
                        arguments.get("languageProfile"), "languageProfile"
                    ),
                    backend=_bounded_text(arguments.get("backend"), "backend"),
                    participant=_bounded_text(arguments.get("participant"), "participant"),
                    failure_classification=_bounded_text(
                        arguments.get("failureClassification"), "failureClassification"
                    ),
                    experiment_status=_bounded_text(
                        arguments.get("experimentStatus"), "experimentStatus"
                    ),
                )
            )
            limit = _limit(arguments.get("limit"), 100)
            return {"records": records[:limit], "truncated": len(records) > limit}
        if operation == "commons.sync":
            _only(arguments, {"cursor", "limit", "kind"})
            cursor = arguments.get("cursor")
            if cursor is not None and not isinstance(cursor, Mapping):
                raise CommonsServiceError("INVALID_ARGUMENTS", "cursor must be an object")
            if cursor is not None and len(canonical_json(cursor)) > MAX_CURSOR_BYTES:
                raise CommonsServiceError("INVALID_ARGUMENTS", "cursor exceeds its bound")
            return self.application.sync(
                cursor,
                limit=_limit(arguments.get("limit"), 1000),
                kind=_bounded_text(arguments.get("kind"), "kind"),
            )
        if operation in {"commons.conversation", "commons.evidence"}:
            _only(arguments, {"root", "depth", "maxNodes"})
            root = _bounded_text(arguments.get("root"), "root", allow_none=False)
            depth = _bounded_integer(
                arguments.get("depth"),
                "depth",
                2 if operation.endswith("conversation") else 3,
                8,
            )
            max_nodes = _limit(arguments.get("maxNodes"), 1000)
            if operation == "commons.conversation":
                return self.application.conversation(root or "", depth=depth, max_nodes=max_nodes)
            return self.application.trace_evidence(root or "", depth=depth, max_nodes=max_nodes)
        if operation == "commons.experiment":
            _only(arguments, {"experimentId", "depth", "maxNodes"})
            experiment_id = _bounded_text(
                arguments.get("experimentId"), "experimentId", allow_none=False
            )
            return self.application.experiment(
                experiment_id or "",
                depth=_bounded_integer(arguments.get("depth"), "depth", 3, 8),
                max_nodes=_limit(arguments.get("maxNodes"), 1000),
            )
        if operation == "commons.work":
            _only(arguments, {"limit", "domain"})
            return self.application.work_queue(
                limit=_limit(arguments.get("limit"), 100),
                domain=_bounded_text(arguments.get("domain"), "domain") or self.config.domain,
            )
        if operation == "work.status":
            _only(arguments, {"workId"})
            work_id = _bounded_text(arguments.get("workId"), "workId", allow_none=False)
            return self.application.work_status(work_id or "")
        if operation == "work.list":
            _only(arguments, {"states", "limit"})
            states_value = arguments.get("states")
            states: set[str] | None = None
            if states_value is not None:
                if not isinstance(states_value, list) or len(states_value) > len(WORK_STATES):
                    raise CommonsServiceError("INVALID_ARGUMENTS", "states must be a bounded list")
                states = set()
                for item in states_value:
                    state = _bounded_text(item, "states[]", allow_none=False)
                    if state not in WORK_STATES:
                        raise CommonsServiceError("INVALID_ARGUMENTS", "work state is unsupported")
                    states.add(state)
            return self.application.work_list(
                states=states, limit=_limit(arguments.get("limit"), 100)
            )
        if operation == "commons.publish":
            _only(arguments, {"record", "participant"})
            record = arguments.get("record")
            if not isinstance(record, Mapping):
                raise CommonsServiceError("INVALID_ARGUMENTS", "record must be an object")
            participant_value = arguments.get("participant")
            participant = (
                ParticipantDescriptor.from_mapping(participant_value)
                if isinstance(participant_value, Mapping)
                else None
            )
            return self.application.publish(
                record,
                participant=participant,
                policy=ExchangePolicy(),
                domain=self.config.domain,
            )
        if operation == "work.submit":
            _only(arguments, {"request"})
            request = arguments.get("request")
            if not isinstance(request, Mapping):
                raise CommonsServiceError("INVALID_ARGUMENTS", "request must be an object")
            return self.application.submit_work(request)
        if operation == "work.transition":
            _only(arguments, {"workId", "transition"})
            work_id = _bounded_text(arguments.get("workId"), "workId", allow_none=False)
            transition = arguments.get("transition")
            if not isinstance(transition, Mapping):
                raise CommonsServiceError("INVALID_ARGUMENTS", "transition must be an object")
            return self.application.transition_work(work_id or "", transition)
        raise CommonsServiceError("OPERATION_UNSUPPORTED", "operation is unsupported")


class CommonsServiceServer:
    """One-request-per-connection AF_UNIX server for both authority surfaces."""

    def __init__(self, service: CommonsService):
        self.service = service
        self._stop = threading.Event()
        self._listeners: list[tuple[socket.socket, Path, tuple[int, int], str]] = []
        self._threads: list[threading.Thread] = []
        self._slots = threading.BoundedSemaphore(service.config.max_connections)
        self._ownership: Any = None

    def _acquire_ownership(self) -> None:
        if fcntl is None:
            raise CommonsServiceError(
                "TRANSPORT_UNSUPPORTED", "service ownership requires POSIX locking"
            )
        store = self.service.config.store_path.resolve()
        path = store.parent / f".{store.name}.service.lock"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise CommonsServiceError("SOCKET_PATH_UNSAFE", "service lock is a symlink")
        handle = path.open("a+b", buffering=0)
        try:
            os.chmod(path, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise CommonsServiceError(
                    "SERVICE_RUNNING", "Commons store is already owned by a service"
                ) from error
            raise
        self._ownership = handle

    def _release_ownership(self) -> None:
        if self._ownership is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._ownership.fileno(), fcntl.LOCK_UN)
        finally:
            self._ownership.close()
            self._ownership = None

    @staticmethod
    def _prepare(path: Path) -> None:
        _safe_socket_path(path)
        if not path.exists():
            return
        original = os.lstat(path)
        probe = socket.socket(_af_unix(), socket.SOCK_STREAM)
        try:
            probe.settimeout(0.1)
            probe.connect(str(path))
        except OSError:
            current = os.lstat(path)
            if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
                raise CommonsServiceError(
                    "SOCKET_PATH_UNSAFE", "socket changed during probe"
                ) from None
            path.unlink()
        else:
            raise CommonsServiceError("SERVICE_RUNNING", "service socket is already in use")
        finally:
            probe.close()

    def _bind(self, path: Path, role: str) -> None:
        if os.name != "posix" or not hasattr(socket, "AF_UNIX"):
            raise CommonsServiceError(
                "TRANSPORT_UNSUPPORTED", "local service requires POSIX AF_UNIX"
            )
        self._prepare(path)
        listener = socket.socket(_af_unix(), socket.SOCK_STREAM)
        try:
            listener.bind(str(path))
            os.chmod(path, 0o600)
            listener.listen(self.service.config.max_connections)
            listener.settimeout(0.2)
            entry = os.lstat(path)
            identity = (entry.st_dev, entry.st_ino)
            self._listeners.append((listener, path, identity, role))
        except BaseException:
            listener.close()
            raise

    def start(self) -> None:
        if self._listeners:
            raise CommonsServiceError("SERVICE_RUNNING", "service is already started")
        self._acquire_ownership()
        try:
            self._bind(self.service.config.consumer_socket, "consumer")
            self._bind(self.service.config.operator_socket, "operator")
        except BaseException:
            self.close()
            raise
        for listener, _path, _identity, role in self._listeners:
            thread = threading.Thread(
                target=self._accept_loop,
                args=(listener, role),
                daemon=True,
                name=f"mncs-commons-{role}",
            )
            self._threads.append(thread)
            thread.start()

    @staticmethod
    def _peer_allowed(stream: socket.socket) -> bool:
        if not hasattr(socket, "SO_PEERCRED"):
            return False
        raw = stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", raw)
        return uid == _current_uid()

    def _accept_loop(self, listener: socket.socket, role: str) -> None:
        while not self._stop.is_set():
            try:
                stream, _address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self._slots.acquire(blocking=False):
                stream.close()
                continue
            thread = threading.Thread(
                target=self._handle,
                args=(stream, role),
                daemon=True,
                name=f"mncs-commons-request-{role}",
            )
            self._threads.append(thread)
            thread.start()

    def _handle(self, stream: socket.socket, role: str) -> None:
        request: dict[str, Any] | None = None
        try:
            if not self._peer_allowed(stream):
                return
            deadline = time.monotonic() + self.service.config.request_timeout_seconds
            request = _receive_frame(stream, maximum=MAX_REQUEST_BYTES, deadline=deadline)
            response = self.service.handle(request, role=role)
            try:
                _send_frame(stream, response, maximum=MAX_RESPONSE_BYTES)
            except CommonsServiceError as error:
                _send_frame(
                    stream,
                    _response(str(request.get("requestId", "unknown")), error=error),
                    maximum=MAX_RESPONSE_BYTES,
                )
        except (CommonsServiceError, OSError):
            # Invalid pre-schema traffic receives no diagnostic. A structurally
            # valid request receives only a bounded generic rejection.
            if request is not None and isinstance(request.get("requestId"), str):
                try:
                    _send_frame(
                        stream,
                        _response(
                            str(request["requestId"]),
                            error=CommonsServiceError(
                                "REQUEST_REJECTED", "service request was rejected"
                            ),
                        ),
                        maximum=MAX_RESPONSE_BYTES,
                    )
                except (CommonsServiceError, OSError):
                    pass
        finally:
            try:
                stream.close()
            finally:
                self._slots.release()

    def serve_forever(self) -> None:
        self.start()
        try:
            while not self._stop.wait(0.5):
                pass
        finally:
            self.close()

    def close(self) -> None:
        self._stop.set()
        listeners = list(self._listeners)
        self._listeners.clear()
        for listener, _path, _identity, _role in listeners:
            try:
                listener.close()
            except OSError:
                pass
        for thread in list(self._threads):
            if thread is not threading.current_thread():
                thread.join(timeout=1.0)
        self._threads.clear()
        for _listener, path, identity, _role in listeners:
            try:
                entry = os.lstat(path)
                if (entry.st_dev, entry.st_ino) == identity and stat.S_ISSOCK(entry.st_mode):
                    path.unlink()
            except FileNotFoundError:
                pass
        self._release_ownership()


class CommonsClient:
    """Supported read-only client for a running controller-local service."""

    def __init__(self, socket_path: Path | str, *, timeout: float = 5.0):
        if os.name != "posix" or not hasattr(socket, "AF_UNIX"):
            raise CommonsServiceError(
                "TRANSPORT_UNSUPPORTED", "local service requires POSIX AF_UNIX"
            )
        if not 0.1 <= timeout <= 30.0:
            raise CommonsServiceError("CONFIG_INVALID", "client timeout is outside bounds")
        self.socket_path = Path(socket_path).expanduser()
        self.timeout = timeout

    @classmethod
    def connect(cls, socket_path: Path | str, *, timeout: float = 5.0) -> Self:
        return cls(socket_path, timeout=timeout)

    def close(self) -> None:
        """Close this stateless client; the service lifetime is unaffected."""

    def _call(self, operation: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if operation not in CONSUMER_OPERATIONS:
            raise CommonsServiceError("AUTHORITY_DENIED", "consumer operation is not allowed")
        return self._request(operation, arguments)

    def _request(
        self, operation: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        request = _request(operation, arguments or {}, self.timeout)
        deadline = time.monotonic() + self.timeout
        try:
            with socket.socket(_af_unix(), socket.SOCK_STREAM) as stream:
                stream.settimeout(self.timeout)
                stream.connect(str(self.socket_path))
                _send_frame(stream, request, maximum=MAX_REQUEST_BYTES)
                response = _receive_frame(
                    stream, maximum=MAX_RESPONSE_BYTES, deadline=deadline
                )
        except socket.timeout as exc:
            raise CommonsServiceError("TRANSPORT_TIMEOUT", "service request timed out") from exc
        except OSError as exc:
            raise CommonsServiceError("SERVICE_UNREACHABLE", str(exc)) from exc
        if (
            set(response)
            != {"schemaVersion", "requestId", "ok", "result", "error", "servedAt"}
            or response.get("schemaVersion") != SERVICE_RESPONSE
            or response.get("requestId") != request["requestId"]
            or not isinstance(response.get("result"), dict)
        ):
            raise CommonsServiceError("PROTOCOL_INVALID", "service response is invalid")
        _timestamp(response.get("servedAt"), "servedAt")
        if response.get("ok") is not True:
            response_error = response.get("error")
            if not isinstance(response_error, Mapping):
                raise CommonsServiceError("PROTOCOL_INVALID", "service error is invalid")
            raise CommonsServiceError(
                str(response_error.get("code", "REQUEST_REJECTED")),
                str(response_error.get("message", "service request was rejected")),
            )
        return dict(response["result"])

    def status(self) -> dict[str, Any]:
        return self._call("service.status")

    def doctor(self) -> dict[str, Any]:
        return self._call("service.doctor")

    def descriptor(self) -> dict[str, Any]:
        return self._call("service.descriptor")

    def describe(self) -> dict[str, Any]:
        return self._call("commons.describe")

    def validate(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("commons.validate", {"record": dict(record)})

    def get(self, digest: str) -> dict[str, Any]:
        return self._call("commons.get", {"digest": digest})

    def query(self, **filters: Any) -> dict[str, Any]:
        return self._call(
            "commons.query", {key: value for key, value in filters.items() if value is not None}
        )

    def sync(
        self,
        cursor: Mapping[str, Any] | None = None,
        *,
        limit: int = 1000,
        kind: str | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            arguments["cursor"] = dict(cursor)
        if kind is not None:
            arguments["kind"] = kind
        return self._call("commons.sync", arguments)

    def conversation(
        self, root: str, *, depth: int = 2, max_nodes: int = 1000
    ) -> dict[str, Any]:
        return self._call(
            "commons.conversation", {"root": root, "depth": depth, "maxNodes": max_nodes}
        )

    def experiment(
        self, experiment_id: str, *, depth: int = 3, max_nodes: int = 1000
    ) -> dict[str, Any]:
        return self._call(
            "commons.experiment",
            {"experimentId": experiment_id, "depth": depth, "maxNodes": max_nodes},
        )

    def work(self, *, limit: int = 100, domain: str | None = None) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": limit}
        if domain is not None:
            arguments["domain"] = domain
        return self._call("commons.work", arguments)

    def work_status(self, work_id: str) -> dict[str, Any]:
        return self._call("work.status", {"workId": work_id})

    def work_list(
        self, *, states: list[str] | None = None, limit: int = 100
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": limit}
        if states is not None:
            arguments["states"] = list(states)
        return self._call("work.list", arguments)

    def evidence(
        self, root: str, *, depth: int = 3, max_nodes: int = 1000
    ) -> dict[str, Any]:
        return self._call(
            "commons.evidence", {"root": root, "depth": depth, "maxNodes": max_nodes}
        )


class CommonsAdminClient(CommonsClient):
    """Explicit operator client; connect it only to the operator socket."""

    def _operator_call(
        self, operation: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        if operation not in OPERATOR_OPERATIONS:
            raise CommonsServiceError("AUTHORITY_DENIED", "operator operation is not allowed")
        return self._request(operation, arguments)

    def publish(
        self,
        record: Mapping[str, Any],
        *,
        participant: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"record": dict(record)}
        if participant is not None:
            arguments["participant"] = dict(participant)
        return self._operator_call("commons.publish", arguments)

    def recover(self) -> dict[str, Any]:
        return self._operator_call("store.recover")

    def submit_work(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._operator_call("work.submit", {"request": dict(request)})

    def transition_work(
        self, work_id: str, transition: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._operator_call(
            "work.transition", {"workId": work_id, "transition": dict(transition)}
        )


__all__ = [
    "ALL_OPERATIONS",
    "CONSUMER_OPERATIONS",
    "OPERATOR_OPERATIONS",
    "SERVICE_PROTOCOL",
    "CommonsAdminClient",
    "CommonsClient",
    "CommonsService",
    "CommonsServiceConfig",
    "CommonsServiceError",
    "CommonsServiceServer",
    "default_service_root",
    "service_tool_schemas",
]
