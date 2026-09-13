# Canonical pressure exchange

This directory is the machine-readable family-wide source of truth for MNCS
development pressures. Read [the pressure protocol](../docs/PRESSURE_PROTOCOL.md)
before adding a record.

The checked-in declarations, observations and events are append-only by
convention. Generated views under `views/` are projections and must be
regenerated with:

```bash
mncs-commons pressure validate pressures
mncs-commons pressure generate pressures
```

The exchange preserves evidence and provenance but grants no execution,
authentication, protected custody, consensus, or contract-change authority.
