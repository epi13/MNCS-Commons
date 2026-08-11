# Future Commons-over-Fabric integration

This document records a boundary for a later cross-repository integration. It does not implement a
Fabric transport, poll a repository, contact a worker, or change Fabric APIs.

## Recommended first stage

```text
remote model/inference
          |
          v
Local Harness routing, tools, and policy
          |
          v
one controller-local MNCS Commons
          |
          v
persistent local store
```

Inference placement is outside Commons. A model can run elsewhere while its knowledge operations
remain controller-mediated. The current descriptor and application API are intended to make that
wiring explicit without freezing a future Fabric transport.

## Possible later stages

```text
Fabric worker description -> models / runtimes / tools / MCP endpoints
                                      |
                                      v
                          controller-mediated Commons access
```

or, only when locality requires it:

```text
controller Commons -- explicit exchange envelope -- Fabric transport -- worker-local Commons
```

Fabric may provide authenticated transport, enrollment, framing, replay protection, and execution
placement. Commons still owns typed records, evidence lineage, bounded queries, node-local cursors,
and domain-local lifecycle projections. Authenticated transport would not prove technical
correctness, independence, conformance, or acceptance.

Do not choose synchronization conflict semantics, peer discovery, global ordering, federation
authority, or worker trust promotion until the actual Fabric capability and message seams are
available and tested. A future push adapter should carry an inert Agent Exchange envelope and
preserve source outcome, Commons validation state, and local publication receipt separately.

| Profile | Purpose | Current state |
| --- | --- | --- |
| controller-local | persistent service for one operator/controller | implemented |
| worker-local | optional locality near a worker | future design |
| public experimental | bounded anonymous HTTP knowledge distribution | experimental binding |
| federated | multi-node exchange and conflict handling | explicitly deferred |
