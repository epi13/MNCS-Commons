# ADR 0011: MCP is an optional thin binding

## Decision

Provide an optional local stdio MCP adapter over Commons application services. The core has no MCP or
Forge runtime dependency, and the server is scoped to one configured store.

## Rationale

MCP gives existing agent systems a useful local interface without making MCP the semantic protocol or
duplicating CLI logic. Remote authentication and network transport are not ready for this repository.

## Consequences

Tools return bounded structured outcomes and inert records. Recovery, arbitrary filesystem access,
URL fetching, command execution, and automatic Forge/Fabric dispatch remain unavailable.
