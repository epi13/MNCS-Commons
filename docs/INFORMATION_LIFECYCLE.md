# MNCS information lifecycle

Execution produces disposable data by default. Promotion makes it knowledge.

```text
  Fabric / Harness / Control execution
           │  stdout, bundles, transcripts, retries
           ▼
     ephemeral exhaust  ──TTL──►  archive or delete
           │
           │  unusual failure, useful diagnostic
           ▼
     diagnostic evidence  ──TTL──►  archive
           │
           │  referenced by Forge/Commons conclusions
           ▼
     durable evidence  ──archive indefinitely──►  cold tar.zst
           │
           │  Claim / Decision / EpochSummary / Series
           ▼
     canonical knowledge   (hot, protected)
```

## Ownership

| Substrate | Owns | Does not own |
|---|---|---|
| Fabric | execution, receipts, bundle cache GC | project conclusions |
| Commons | coordination records, epoch summaries, archives | command authority |
| Forge | evaluation, claims, scoring | dispatch |
| Control / Harness | bounded operator/agent surfaces | silent deletion |

Commons records remain inert. Reading an EpochSummary is not permission to run anything.

## Retention classes

- **canonical** — Claims, Decisions, Epochs, summaries, aggregates, open work
- **evidence** — failed replications and labeled evidence; archive, do not expire
- **diagnostic** — advisories and unknown/fail observations; TTL (default 60 days)
- **ephemeral** — routine passing replications/observations; TTL (default 7 days)

Pins and reference protection override TTL. A digest named by an active Claim, Decision, EpochSummary, series, or open WorkRequest stays retrievable.

## Epochs

An epoch is a bounded compute window, not a scheduler:

`Epoch` → work attempted during a window  
`EpochSummary` → structured close-out referencing source identities  
`ReplicationSeries` / `ObservationSeries` → auditable aggregates

Any orchestrator (systemd, cron, Fabric `schedule.tick`, a later RAVEL/MNEL consumer) can open/close epochs.

## Archives

Hot compaction:

1. classify and plan (dry-run by default)
2. write `archive/YYYY/week-WW/<id>/{manifest.json,bundle.tar.zst}`
3. verify bundle digest and record set
4. install a new hot generation that starts with a snapshot row
5. keep resolving archived digests through `store.get()`

The append-only history of a generation is preserved in the archive. The hot ledger is a new hash chain. Cursors from a previous generation are stale.

## Operator commands

```bash
mncs-commons store retention-status PATH
mncs-commons store retention-plan PATH
mncs-commons store compact PATH --dry-run
mncs-commons store compact PATH --confirm --now 2026-08-13T00:00:00Z
mncs-commons store archives PATH
mncs-commons store archive-verify PATH ARCHIVE_ID
mncs-commons store archive-inspect PATH ARCHIVE_ID
mncs-commons store pin PATH DIGEST --reason "keep for claim"
mncs-commons store unpin PATH DIGEST

mncs-fabric cache status
mncs-fabric cache gc --dry-run
mncs-fabric cache gc --confirm
```

A model cannot compact or evict by asking. `--confirm` is required.

## Recovery

```bash
# verify then materialize an archive into a new store directory
python -c 'from mncs_commons.archive import restore_archive; ...'
```

If compaction is interrupted, the staging directory `.compaction-staging` is discarded and the previous hot store remains.

## Why this exists

A fleet that can deliver hundreds of compute-hours per week will emit far more stdout than knowledge. Hot memory must stay small, useful, and auditable. Full evidence remains content-addressed in cold archives.
