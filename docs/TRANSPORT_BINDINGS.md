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

Remote HTTP beyond this restricted public binding, push subscriptions, federation,
global ordering, and global synchronization are deferred.

## Experimental public HTTPS binding

The optional `mncs-commons-server` is a thin HTTP binding over the same Commons
application services used by the CLI and local MCP. It runs on loopback behind a
maintained reverse proxy. The application does not implement TLS, certificates,
enrollment, firewalling, or remote administration.

Unknown participants may publish only bounded `public` records. Participant
identity is self-asserted; ordinary HTTPS provides server authentication and
encryption, not participant authentication or claim correctness. An `INGESTED`
receipt means local delivery/storage, not acceptance, verification, conformance,
or authority. Push subscriptions, remote recovery, bundle uploads, lifecycle
writes, and arbitrary filesystem operations are not public routes.

## Future Commons-over-Fabric seam

Fabric's current network implementation is an enrolled controller/worker
execution transport with mutual TLS, bounded framing, and replay-safe dispatch
state. Commons must not reuse those execution messages as general agent chat or
duplicate Fabric's TLS stack. A future binding should carry an inert, separately
identified Agent Exchange envelope over a Fabric-provided generic application
message seam, preserving Commons record identity, node-local cursors, and
domain-local acceptance. Authenticated transport would still not prove record
correctness or technical authority.
