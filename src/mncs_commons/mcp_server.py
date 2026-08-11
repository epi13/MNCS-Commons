"""Optional local stdio MCP binding over Commons application services.

The MCP SDK is intentionally imported only when this module is used.  Commons records remain
inert data; this adapter never dispatches their commands, URLs, or reproduction procedures.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .application import CommonsApplication
from .exchange import ExchangeError, ExchangePolicy, ParticipantDescriptor
from .query import QueryFilter
from .store import CommonsStore, StoreError
from .vocabulary import vocabulary

MAX_MCP_RESPONSE_BYTES = 4 * 1024 * 1024


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounded_result(value: object) -> tuple[str, bool]:
    encoded = _json(value)
    if len(encoded.encode("utf-8")) <= MAX_MCP_RESPONSE_BYTES:
        return encoded, False
    return _json(
        {
            "error": "RESPONSE_LIMIT_EXCEEDED",
            "message": "response exceeds the configured MCP response bound",
            "truncated": True,
        }
    ), True


def build_server(
    store: CommonsStore,
    *,
    domain: str = "local",
    public: bool = False,
) -> Any:
    """Build a low-level MCP server; callers own the stdio transport lifecycle."""

    try:
        from mcp.server.lowlevel import Server  # type: ignore[import-not-found]
        from mcp.types import (  # type: ignore[import-not-found]
            CallToolResult,
            ListResourcesResult,
            ListToolsResult,
            ReadResourceResult,
            Resource,
            TextContent,
            TextResourceContents,
            Tool,
        )
    except ImportError as error:  # pragma: no cover - exercised by optional-install checks
        raise RuntimeError("MCP support requires the optional 'mcp' dependency") from error

    application = CommonsApplication(store)
    policy = ExchangePolicy.public_profile() if public else ExchangePolicy()

    tools = [
        Tool(
            name="commons_describe",
            description="Describe this Commons exchange endpoint and vocabulary.",
            input_schema={"type": "object", "properties": {}},
        ),
        Tool(
            name="commons_validate_record",
            description="Validate an inert Commons record without storing it.",
            input_schema={
                "type": "object",
                "required": ["record"],
                "properties": {"record": {"type": "object"}},
            },
        ),
        Tool(
            name="commons_publish_record",
            description=(
                "Publish one validated record; delivery does not grant acceptance or authority."
            ),
            input_schema={
                "type": "object",
                "required": ["record"],
                "properties": {
                    "record": {"type": "object"},
                    "participant": {
                        "type": "object",
                        "properties": {
                            "participantId": {"type": "string"},
                            "implementation": {"type": "string"},
                            "softwareVersion": {"type": "string"},
                            "modelProvider": {"type": "string"},
                            "modelIdentity": {"type": "string"},
                            "instanceId": {"type": "string"},
                            "sessionId": {"type": "string"},
                            "producerIdentity": {"type": "string"},
                            "environmentIdentity": {"type": "string"},
                            "namespace": {"type": "string"},
                            "capabilities": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        ),
        Tool(
            name="commons_get_record",
            description="Get one record by content digest.",
            input_schema={
                "type": "object",
                "required": ["digest"],
                "properties": {"digest": {"type": "string"}},
            },
        ),
        Tool(
            name="commons_query",
            description="Run a bounded structured Commons query.",
            input_schema={
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "state": {"type": "string"},
                    "subject": {"type": "string"},
                    "contract": {"type": "string"},
                    "artifact": {"type": "string"},
                    "related": {"type": "string"},
                    "domain": {"type": "string"},
                    "openWorkRequests": {"type": "boolean"},
                    "needsReview": {"type": "boolean"},
                    "now": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
            },
        ),
        Tool(
            name="commons_sync",
            description="Read a bounded ordered ledger slice after a store-local cursor.",
            input_schema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "object"},
                    "limit": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="commons_conversation",
            description="Project a bounded typed record graph for presentation.",
            input_schema={
                "type": "object",
                "required": ["root"],
                "properties": {"root": {"type": "string"}},
            },
        ),
        Tool(
            name="commons_work_list",
            description="List bounded opportunities; results are not commands or permissions.",
            input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
        ),
        Tool(
            name="commons_evidence_trace",
            description="Trace bounded evidence lineage without inferring truth.",
            input_schema={
                "type": "object",
                "required": ["root"],
                "properties": {"root": {"type": "string"}},
            },
        ),
    ]

    def query(arguments: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        limit = max(1, min(int(arguments.get("limit", 100)), 1000))
        now = arguments.get("now")
        parsed_now = datetime.fromisoformat(str(now).replace("Z", "+00:00")) if now else None
        return application.query(
            QueryFilter(
                kind=arguments.get("kind"),
                state=arguments.get("state"),
                subject=arguments.get("subject"),
                contract=arguments.get("contract"),
                artifact=arguments.get("artifact"),
                related=arguments.get("related"),
                domain=arguments.get("domain", domain),
                open_work_requests=bool(arguments.get("openWorkRequests", False)),
                needs_review=bool(arguments.get("needsReview", False)),
                now=parsed_now,
            )
        )[:limit]

    async def list_tools(_context: Any, _params: Any) -> Any:
        return ListToolsResult(tools=tools)

    async def call_tool(_context: Any, params: Any) -> Any:
        arguments = params.arguments or {}
        try:
            if params.name == "commons_describe":
                result: object = application.describe(
                    domain=domain, policy=policy, binding="stdio-mcp"
                )
            elif params.name == "commons_validate_record":
                value = arguments.get("record")
                result = (
                    application.validate(value)
                    if isinstance(value, Mapping)
                    else {
                        "valid": False,
                        "diagnostics": [
                            {
                                "code": "TYPE_OBJECT",
                                "path": "record",
                                "message": "record must be an object",
                                "severity": "error",
                            }
                        ],
                    }
                )
            elif params.name == "commons_publish_record":
                value = arguments.get("record")
                if not isinstance(value, Mapping):
                    raise ExchangeError("INVALID_RECORD", "record must be an object")
                participant_value = arguments.get("participant")
                participant = None
                if isinstance(participant_value, Mapping):
                    participant = ParticipantDescriptor.from_mapping(participant_value)
                result = application.publish(
                    value, participant=participant, policy=policy, domain=domain
                )
            elif params.name == "commons_get_record":
                result = application.get_record(str(arguments.get("digest")))
                if result is None:
                    raise ExchangeError("UNKNOWN_RECORD", "record was not found")
            elif params.name == "commons_query":
                records = query(arguments)
                result = {
                    "records": records,
                    "truncated": len(records)
                    >= max(1, min(int(arguments.get("limit", 100)), 1000)),
                }
            elif params.name == "commons_sync":
                cursor = arguments.get("cursor")
                if cursor is not None and not isinstance(cursor, Mapping):
                    raise ExchangeError("INVALID_CURSOR", "cursor must be an object")
                result = application.sync(
                    cursor, limit=int(arguments.get("limit", 1000)), kind=arguments.get("kind")
                )
            elif params.name == "commons_conversation":
                result = application.conversation(
                    str(arguments["root"]),
                    depth=int(arguments.get("depth", 2)),
                    max_nodes=int(arguments.get("maxNodes", 1000)),
                )
            elif params.name == "commons_work_list":
                result = application.work_queue(limit=int(arguments.get("limit", 100)))
            elif params.name == "commons_evidence_trace":
                result = application.trace_evidence(
                    str(arguments["root"]),
                    depth=int(arguments.get("depth", 3)),
                    max_nodes=int(arguments.get("maxNodes", 1000)),
                )
            else:
                raise ExchangeError("UNKNOWN_OPERATION", "operation is not supported")
            text, truncated = _bounded_result(result)
            return CallToolResult(content=[TextContent(text=text)], is_error=truncated)
        except (ExchangeError, StoreError, ValueError, TypeError, KeyError) as error:
            result = (
                error.as_dict()
                if isinstance(error, ExchangeError)
                else {"error": "INVALID_REQUEST", "message": str(error)}
            )
            text, _ = _bounded_result(result)
            return CallToolResult(content=[TextContent(text=text)], is_error=True)

    resources = [
        Resource(name="protocol", uri="mncs-commons://protocol", mime_type="application/json"),
        Resource(
            name="exchange", uri="mncs-commons://schema/exchange", mime_type="application/json"
        ),
        Resource(name="vocabulary", uri="mncs-commons://vocabulary", mime_type="application/json"),
        Resource(
            name="capabilities", uri="mncs-commons://capabilities", mime_type="application/json"
        ),
    ]

    async def list_resources(_context: Any, _params: Any) -> Any:
        return ListResourcesResult(resources=resources)

    async def read_resource(_context: Any, params: Any) -> Any:
        values = {
            "mncs-commons://protocol": {"recordVersion": "commons.mncs.dev/v0alpha1"},
            "mncs-commons://schema/exchange": application.describe(
                domain=domain, policy=policy, binding="stdio-mcp"
            ),
            "mncs-commons://vocabulary": vocabulary(),
            "mncs-commons://capabilities": application.describe(
                domain=domain, policy=policy, binding="stdio-mcp"
            ),
        }
        if params.uri not in values:
            raise ValueError("unknown Commons resource")
        return ReadResourceResult(
            contents=[
                TextResourceContents(
                    uri=params.uri, mime_type="application/json", text=_json(values[params.uri])
                )
            ]
        )

    return Server(
        "mncs-commons",
        version=__version__,
        instructions="Commons communicates information; publication grants no authority.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )


async def _run(store: CommonsStore, *, domain: str, public: bool) -> None:
    from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]

    server = build_server(store, domain=domain, public=public)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mncs-commons-mcp")
    parser.add_argument("--store", required=True)
    parser.add_argument("--domain", default="local")
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.store).expanduser().resolve()
    store = CommonsStore(root)
    try:
        store.verify()
        if not root.is_dir():
            raise StoreError("configured store root is not a directory")
        import anyio  # type: ignore[import-not-found]

        anyio.run(lambda: _run(store, domain=args.domain, public=args.public))
    except (ImportError, RuntimeError, StoreError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
