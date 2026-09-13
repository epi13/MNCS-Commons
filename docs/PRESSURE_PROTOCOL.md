# MNCS family pressure protocol

`mncs-commons` is the coordination exchange for constraints discovered while
building the MNCS family. A pressure is an observed engineering limitation,
not a feature wishlist and not permission to run a suggested command. The
canonical data lives in `pressures/`; Markdown ledgers in consumer repositories
remain historical source material until explicitly migrated.

## Source of truth

The exchange has four append-only surfaces:

| Surface | Contents | Merge behavior |
| --- | --- | --- |
| `pressures/records/<id>.json` | One stable pressure declaration | One file per pressure |
| `pressures/observations/<pressure>--OBS-<hash>.json` | Reporter, reproduction, evidence, workaround and verification observations | One file per contribution |
| `pressures/events/EVT-<hash>.json` | Lifecycle transitions and typed pressure relationships | One file per event; stale heads fail validation |
| `pressures/views/*.json` | Generated query projections | Never edit by hand |

The declaration contains the stable identity and the initial `discovered`
state. The materialized status, affected repositories, evidence, verification
summary, implementation metadata and relationships are derived from the
append-only documents. A projection is invalid if its event history has two
heads, a dangling target, a bad digest, or a forbidden transition.

The JSON Schema is [`schemas/mncs-family-pressure-v1.schema.json`](../schemas/mncs-family-pressure-v1.schema.json).
The Python validator adds cross-document and evidence-gated invariants that a
structural schema cannot express.

## Global identities

An id is generated from the stable tuple
`target + domain + capability + reproducer.signature`, then rendered as:

```text
MNCS-LANG-<12 uppercase hex digits>
MNCS-COMPILER-<12 uppercase hex digits>
MNCS-TOOLING-<12 uppercase hex digits>
```

There is no central counter. Two agents can create records concurrently and
will either derive the same identity (a candidate to inspect and reuse) or
different identities (distinct provenance). `legacyIds` preserves local names
such as `mncs-store:P1-003`. An id is intentionally stable across repository
moves and wording edits because those fields are outside the identity tuple.

## Lifecycle

The canonical lifecycle is:

```text
discovered -> confirmed -> accepted -> implementing -> available
                                                     |
                                                     v
                                                  verifying -> resolved
```

`available` means the owning language/compiler/runtime capability has landed
with implementation evidence. It does not mean any downstream consumer has
removed its workaround. `resolved` requires PASS verification from every
affected repository and either `workaround.removed: true` or
`workaround.removed: "not_needed"`.

Side paths are explicit: `duplicate`, `rejected`, `superseded`, `deferred`,
and `obsolete`. A failed or unknown verification returns an available pressure
to the `available` state; it never upgrades to resolution. PASS, FAIL, and
UNKNOWN are never collapsed into one confidence score.

Transitions are append-only and carry `from`, `to`, `previousEvent`, actor,
reason, and evidence references. The validator rejects direct
`discovered -> resolved`, missing implementation evidence for `available`,
missing duplicate/supersession relationships, stale heads, and partial
resolution.

## Standard agent protocol

When a consumer agent encounters a limitation that forces a workaround, a Rust
fallback, a semantic compromise, a parity gap, a correctness/performance
regression, or an impossible architecture:

1. Query the registry for exact and likely candidates.
2. If a matching pressure exists, attach an observation from the current
   repository. Preserve the local reproducer and evidence; do not overwrite
   another report.
3. If no matching pressure exists, add a new pressure with a stable
   `reproducer.signature`, source reference, and at least an honest
   PASS/FAIL/UNKNOWN reproduction result.
4. Keep the workaround associated with the observation. A workaround is not a
   resolution.
5. When the owning capability lands, move the pressure to `available` with an
   implementation reference and profile/toolchain metadata.
6. Re-run the original consumer. Add a verification observation even when it
   fails or remains unknown. Only then may an authorized consumer transition
   the pressure to `resolved`.

Suggested first commands from a checkout of Commons:

```bash
mncs-commons pressure validate pressures
mncs-commons pressure list pressures --target language --unresolved
mncs-commons pressure candidates pressures \
  --target language --domain io.filesystem --capability atomic_publish
mncs-commons pressure show pressures MNCS-LANG-<id>
```

The machine-readable `list` result is deterministic and suitable for an agent
or CI. Add `--format text` for a compact human view.

## Reporting, evidence and verification

Create a declaration from a JSON object or file:

```bash
mncs-commons pressure add pressures pressure.json
```

The object must include `title`, `target`, `domain`, `capability`, `summary`,
`requiredBehavior`, `reproducer.signature`, `severity`, and `discoveredBy`.
The optional `observation` object is written as a separate immutable document.

Attach another repository's evidence without changing the canonical
declaration:

```bash
mncs-commons pressure observe pressures MNCS-LANG-<id> observation.json
```

An observation carries repository, commit/branch/path/run provenance, active
profile/compiler, reproduction status, evidence entries, and workaround
metadata. Evidence entries have an id, reference, summary, and one of PASS,
FAIL, or UNKNOWN. URLs and source text are retained as inert data.

Record consumer verification explicitly:

```bash
mncs-commons pressure verify pressures MNCS-LANG-<id> \
  --repository mncs-store --status PASS \
  --workaround-removed true --evidence evidence.json \
  --source-ref verification-ref.json
```

Use `--status FAIL` or `--status UNKNOWN` when that is what the evidence says.
For three affected repositories, all three must contribute PASS verification
before `resolved` is accepted.

## Relationships and deduplication

Use candidates as an aid, not an auto-merge mechanism. After comparing
reproducers and root causes, record a deliberate relationship:

```bash
mncs-commons pressure relate pressures MNCS-LANG-B duplicate_of MNCS-LANG-A \
  --actor mncs-commons
mncs-commons pressure transition pressures MNCS-LANG-B duplicate \
  --actor mncs-commons --reason "same reproducer and root cause"
```

`duplicate_of`, `same_root_cause`, `parent_of`, `child_of`, `blocked_by`,
`supersedes`, `implements`, `reframes`, and `related_to` preserve different
engineering meanings. The original declaration, observations, aliases and
source references remain intact.

## Workaround markers and Doctor

Small source comments are enough to make future migration discoverable:

```text
// mncs-pressure: MNCS-LANG-ABCDEF012345
```

They are inert markers. `mncs-commons pressure markers path/to/source.mncs`
extracts ids but does not open files named by a record or execute a suggested
action. A future `mncs-doctor` can combine the marker with an active workaround
observation, `available` implementation metadata, and a consumer verification
recipe to propose a migration. Commons does not perform that migration.

## Migration from local ledgers

Import a local Markdown pressure directory conservatively:

```bash
mncs-commons pressure migrate pressures \
  --repository mncs-store /path/to/mncs-store/pressure --dry-run
mncs-commons pressure migrate pressures \
  --repository mncs-store /path/to/mncs-store/pressure
```

The importer creates one canonical record per source document, preserves the
full original Markdown, source path, source digest, local id and historical
status, and begins the Commons lifecycle at `discovered` with UNKNOWN
reproduction. It never infers that a local word such as “resolved” is current
consumer verification. A later reconciliation can add explicit evidence,
aliases and typed relationships. A full multi-repository migration should be a
separate campaign so unreviewed local claims are not silently merged.
The compatibility `--refresh` flag never deletes or rewrites an existing
record; changed source material must be attached as a new observation by an
authorized migration rather than erasing the original snapshot.

## Language campaign interface

The complete unresolved language set is:

```bash
mncs-commons pressure validate pressures
mncs-commons pressure list pressures \
  --target language --unresolved --format json
```

The result includes status, severity, capability, domain, affected
repositories, reporter count, verification counts, and validity. A campaign
can rank by raw signals—severity, repository breadth, Rust fallback, native
conversion blockage, correctness/performance impact—without treating an
automated score as truth. `pressures/views/unresolved-language.json` is the
generated checked-in projection for review and CI. The generated set also
includes blocking, by-repository, by-domain, multi-repository,
awaiting-verification, recently-resolved, and rust-fallback views.

## Git and schema discipline

Do not hand-edit generated views. Each new observation/event is its own file;
canonical arrays are sorted during projection. A transition contains the head
it was based on. If two branches update the same pressure, validation reports
`CONCURRENT_TRANSITIONS` and the losing branch must be rebased or deliberately
reconciled. No event is silently discarded.

Schema changes increment the exchange version and require a migration. Readers
must reject unknown versions rather than guessing. Historical source snapshots
remain data under `legacy`; they are not executable instructions or authority.
