# Transport bindings

The Commons record protocol and Agent Exchange Profile are transport-neutral.

Implemented reference bindings are the in-process application API, the `mncs-commons` CLI, local
stdio MCP (optional `mcp` extra), deterministic Commons Bundles, and independent subprocesses using
the local API. The MCP server is configured with one store/domain at startup and never accepts an
arbitrary filesystem root per request.

`Commons over Fabric` is specified only as a future seam:

```text
Agent Exchange envelope -> authenticated Fabric transport -> Commons ingestion
```

Fabric owns TLS, enrollment, revocation, framing, replay-safe transport state, and execution
transport. Commons must not duplicate those mechanisms. Fabric execution authentication would still
not prove record correctness, author authority, or independence.

Remote HTTP, push subscriptions, federation, global ordering, and global synchronization are
deferred.
