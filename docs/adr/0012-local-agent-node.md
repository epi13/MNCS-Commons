# ADR 0012: Local Commons Agent Node is the controller-local default

## Decision

Define `commons.mncs.dev/node/local-agent/v0alpha1` as the deployment profile for a persistent
Commons store owned by one operator or controller machine. The profile has no network listener by
default and exposes the Python application API, CLI, and optional local stdio MCP binding over one
application-service implementation. A loopback HTTP listener, when explicitly configured, is a
separate binding and does not change the profile's authority boundary.

The machine-readable service descriptor is additive to the Agent Exchange profile. It identifies
the record and exchange versions, active binding, supported operations, limits, optional interface
availability, trust-domain label, and the fact that Commons has no execution authority. Its package
version is independent of both wire versions.

## Rationale

The later Local Harness integration needs a durable controller-local knowledge service without
requiring Fabric, remote inference, authentication, or a network service. Keeping the application
services canonical lets local interfaces remain semantically aligned while leaving transport and
policy decisions to their owners.

## Consequences

`local status` and `local doctor` report store existence, initialization, verification, recovery,
writability, and interface availability. These are operator diagnostics, not proof of
authentication, protected custody, correctness, conformance, or global trust. The local node does
not execute work requests, reproduction procedures, URLs, attachments, or suggested commands.

The experimental public node remains a distinct operator-configured HTTP profile. Worker-local or
federated Commons instances, synchronization conflict semantics, and Commons-over-Fabric transport
remain future integration work.
