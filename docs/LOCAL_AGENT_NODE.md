# Controller-local Commons Agent Node

Commons can run as a persistent local knowledge and coordination service for a controller without
requiring Fabric or a network listener:

```text
agent/model -> controller policy and tools -> CommonsApplication
                                      ├── local filesystem store
                                      ├── CLI
                                      └── optional stdio MCP
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
is active and whether each optional interface is installed. MCP is a thin local stdio binding for
bounded knowledge operations. It has no arbitrary path, filesystem, subprocess, URL, recovery,
Forge, Fabric, or remote dispatch tool.

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
