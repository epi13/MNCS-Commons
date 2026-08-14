# ADR 0013: Promote reusable knowledge above execution exhaust

## Decision

Commons will distinguish raw execution/evidence records from deliberately promoted institutional
memory. The core vocabulary adds `Finding`, `Question`, `Hypothesis`, `FailedApproach`, `Handoff`,
`ArtifactReference`, and `Thread`; the existing `Decision` remains part of institutional memory.
Consumers may request this layer with the `institutionalMemory` structured query flag.

A `Thread` is a typed graph anchor, not a free-form message primitive. Individual memory records are
linked with typed relationships and remain independently scoped, attributable, and immutable.

## Context

The persistent controller-local Commons proved that Fabric execution evidence and detached durable
work survive client boundaries. Live inspection also showed that nearly all accumulated records were
execution observations, while useful model reasoning remained embedded in stdout. Scaling that shape
to sustained autonomous compute would optimize for audit volume rather than reusable knowledge.

## Consequences

- agents have a stable protocol for preserving findings, open questions, hypotheses, failures,
  decisions, handoffs, artifact identities, and topic continuity;
- raw observations can remain short-lived or archive-managed without losing promoted conclusions;
- promoted knowledge receives canonical retention, while artifact references are evidence-class;
- Commons still does not become an unrestricted chat room, command bus, or artifact store;
- conversation remains a derived graph projection over immutable typed records;
- open-work discovery must use the latest revision of revisioned WorkRequests so historical states do
  not masquerade as current opportunities.
