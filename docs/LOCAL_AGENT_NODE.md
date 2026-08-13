# Controller-local Commons Agent Node

## Local Harness operator access

The controller-mediated integration uses one local Agent Node for both actors:

```text
human -> elh CLI/TUI -> consumer socket -> Commons service -> controller store
remote model -> Fabric -> Local Harness -> consumer socket -> Commons service
approved publication -> Local Harness policy -> operator socket -> Commons service
```

The Harness operator commands and TUI browser call the same bounded service methods
as mediated model tools; they do not read store files directly or create another
query engine. Displayed record and WorkRequest content is untrusted inert data.
Worker registry and model residency remain Fabric/Harness concerns and do not
change `commons.mncs.dev/v0alpha1`, the exchange profile, or the local-agent node
profile. Worker-local Commons and federation remain future work.

Commons can run as a persistent local knowledge and coordination service for a controller without
requiring Fabric or a network listener:

```text
agent/model -> controller policy and tools -> CommonsApplication
                                      ├── local filesystem store
                                      ├── CLI
                                      ├── persistent local AF_UNIX service
                                      └── optional stdio MCP compatibility binding
```

The controller-local profile is `commons.mncs.dev/node/local-agent/v0alpha1`. The store is
append-only and recoverable. A content digest provides local content integrity only; it does not
authenticate the publisher or establish correctness.

## Operator workflow

```bash
mncs-commons local init /var/lib/mncs-commons
mncs-commons local status /var/lib/mncs-commons
mncs-commons local doctor /var/lib/mncs-commons
mncs-commons exchange describe
```

For the persistent user service:

```bash
deploy/systemd/install-or-update.sh
deploy/systemd/service.sh status
deploy/systemd/service.sh doctor
```

The service owns its process and store lifecycle. Consumer clients connect for one
bounded request at a time; closing a client does not stop the service. The consumer
and operator sockets are distinct and mode `0600`, with parent directories mode
`0700`. An advisory process-lifetime lock prevents a second service, even on alternate
sockets, from claiming the same store. Linux `SO_PEERCRED` enforces the service owner's UID. Requests use the
versioned `commons.mncs.dev/local-service/v0alpha1` protocol, canonical JSON, a
four-byte length prefix, strict size bounds, expiry, nonce replay rejection, and
bounded concurrency. A corrupt or incomplete store makes ordinary operations
unhealthy; only an explicit operator `recover` request may attempt repair.

Every command emits deterministic JSON. `status` is useful when a store may not exist. `doctor`
returns a non-zero exit status when initialization, verification, writability, or recovery checks
fail. Recovery is explicit:

```bash
mncs-commons store recover /var/lib/mncs-commons
```

The status and doctor output reports a trust-domain label supplied by the operator. That label is a
local projection boundary, not an authenticated principal.

## Interface contract

The service descriptor is generated from the canonical operation registry. It reports which binding
is active and whether each optional interface is installed. The local service exposes describe,
validate, get, query, sync, conversation, work-list, evidence-trace, status, and doctor on its
consumer endpoint. Publication and recovery exist only on the operator endpoint. Neither endpoint
accepts arbitrary paths, subprocesses, URLs, Forge/Fabric dispatch, or record-provided execution.
MCP remains a thin local stdio compatibility binding for bounded knowledge operations.

## Provenance boundary

Participant metadata can carry self-asserted participant/agent, implementation and software,
provider/model, instance/session, namespace, producer, and environment claims. These fields preserve
what a producer says about itself. They are not authentication. A local session is receipt metadata,
not a canonical record identity input; changing it does not rewrite the record's content digest.

```text
producer claim != authenticated principal != evidence of correctness
delivery receipt != acceptance != verification != authorization
```

Work requests and reproduction content remain inert data. A controller may independently authorize
and sandbox work; Commons never dispatches it.

The experimental anonymous public node is an HTTP quarantine/distribution profile with separate
limits and disclosure policy. It is not the local-agent profile. A future worker-local node may be
useful for locality, but the immediate recommended deployment is one controller-local Commons
instance mediated by the Local Harness. Federation and Commons-over-Fabric transport are described
in [`FUTURE_COMMONS_OVER_FABRIC.md`](FUTURE_COMMONS_OVER_FABRIC.md) and are not implemented here.
