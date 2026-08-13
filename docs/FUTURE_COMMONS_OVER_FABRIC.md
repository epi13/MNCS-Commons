# Future Commons-over-Fabric integration

This document records the implemented first-stage boundary and the explicitly deferred
federation boundary. Commons itself does not poll Fabric, contact workers, or acquire execution
authority.

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

Inference placement is outside Commons. In the Local Harness 0.5.0 integration a model can run on
an enrolled Fabric worker while its Commons operations remain controller-mediated through the
persistent local consumer socket. The worker receives tool schemas and bounded results, never the
Commons store path, operator socket, service lifecycle, controller filesystem, credentials, or a
direct Commons channel. Fixed stdio MCP remains an explicit compatibility binding.

Fabric execution records may be translated with `from_fabric_execution` and optionally published
as inert Commons Observations. A source execution outcome such as `PASS` remains an observed
Fabric outcome; `details.claimVerificationStatus` remains `UNKNOWN`. Commons validation and a
local ingestion receipt do not promote that outcome to verified truth.

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
| controller-local | persistent service for one operator/controller | implemented and Harness-integrated |
| worker-local | optional locality near a worker | future design |
| public experimental | bounded anonymous HTTP knowledge distribution | experimental binding |
| federated | multi-node exchange and conflict handling | explicitly deferred |
