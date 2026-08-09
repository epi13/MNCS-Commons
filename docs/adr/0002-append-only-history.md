# ADR 0002: Immutable records and append-only events

Status: accepted for v0.1

Original evidence is never rewritten to represent a dispute, replication, acceptance, expiration, or supersession. A typed `LifecycleEvent` references the original content digest and an explicit local authority domain. Current state is a deterministic projection of the original record plus ordered events.
