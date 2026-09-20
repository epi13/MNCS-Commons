# MNCS family persistence census — 2026-09-20

This census is the first scope artifact for the `mncs-store` reuse campaign.
It is derived from the current Commons family registry at revision
`2026-09-15`, then checked against the checked-out family repositories. It is
an evidence-backed inventory, not a new semantic authority and not a claim
that every listed surface should migrate.

## Classification rule

Each persistence surface is classified as `SOURCE_DECLARATION`,
`EXTERNAL_INTERCHANGE`, `EPHEMERAL`, `DERIVED_CACHE`,
`DURABLE_APPLICATION_STATE`, `EVIDENCE_ARTIFACT`,
`PLATFORM_SECRET_OR_CREDENTIAL`, or `REFERENCE/HISTORICAL`.

The campaign acts only on durable application state, identity-bound evidence,
and rebuildable derivatives where Store reduces real duplication. Git source,
protocol files, process-local state, disposable indexes, and secrets remain in
their existing boundaries unless a later concrete requirement changes that
decision.

## Current result

The registry covers 25 family projects. The strongest duplicated persistence
machinery is:

| Project | Current private machinery | Classification | Campaign disposition |
|---|---|---|---|
| Forge | immutable record files, JSONL hash ledger, transaction journals, ledger index | durable state + evidence + derived cache | first migration candidate |
| Fabric | append-only controller/worker ledger, registries, desired state, bundle cache, receipts | durable state + cache + evidence + secrets | concurrency/recovery pressure candidate |
| RAVEL | candidate ledger, SQLite experience store, checkpoints, evidence files | durable state + historical formats | migrate persistence mechanics only |
| Commons | local record store for pressure/family semantics | durable state + evidence | retain authority; Store already proves a vertical |
| Doctor | `.mncs/doctor/inventory.json` | derived cache | local embedded Store experiment |
| Test / Debug / Actions | JSON result, trace, receipt, and evidence envelopes | external interchange + evidence | retain projections; share Store identities |
| Index | Store-feed/query projections | derived cache | delete and rebuild from Store |
| Language Service | resident analysis snapshots and indexes | ephemeral / optional derived cache | measure before persisting |
| MNEL | evidence ledger and snapshot/provider state | durable state + evidence | later pressure test |

The remaining registry participants are specification, orientation, transport,
or research surfaces without a current Store migration candidate. The complete
machine-readable matrix, including evidence paths and supplemental workspace
projects, is [persistence-census-2026-09.json](persistence-census-2026-09.json).

## Initial architecture decisions

1. Forge, Fabric, and RAVEL are migration candidates; none is declared
   migrated by this census.
2. Forge/Fabric/RAVEL domain semantics remain in those repositories. Store
   owns representation, identity, generations, integrity, recovery,
   provenance, and generic relations only.
3. JSON and JSONL remain valid external/import/export and historical formats;
   they are not canonical merely because they remain visible at boundaries.
4. Index remains disposable. A migrated consumer must rebuild it from Store.
5. Fabric secrets and trust material remain specialized security state; Store
   may eventually hold references/metadata, not private key bytes by default.
6. `mncs-memory` is explicitly outside this campaign.

The census is registry-coverage tested so adding a family participant creates a
review obligation instead of silently escaping the inventory.
