# ChangeSet promotion profile

Status: coordination profile (non-normative for producer semantics).

A cross-repository ChangeSet that reaches an MNCS promotion boundary
carries, by reference, the machine-readable contracts owned elsewhere.
Commons does not redefine them; this profile names the edges so every
affected repository assembles the same relationship graph.

## Carried references

| ChangeSet element              | Owning contract                                              | Mechanical edge              |
| ------------------------------ | ------------------------------------------------------------ | ---------------------------- |
| ChangeSet identity             | MNCDS ChangeSet (`development-pressure-protocol.md`)         | self                         |
| affected repositories/revisions| exact `baseRevisions` in the ChangeSet record                | self                         |
| MNCDS development record       | `mncds-development-record` check (MNCDS check catalog)       | `supports`                   |
| rights/lineage references      | `mncs-rights-provenance` lineage record                      | `supports`                   |
| pressure/capability gaps       | `mncds-obligation-record/0.2` (projected pressure)           | `pressure/supports-pressure` |
| evidence per affected repo     | each repository's `check-result/1` claims                    | `supports`                   |
| unresolved obligations         | `mncds-obligations` check `unresolved` entries               | `contradicts` (blocks)       |
| eventual promotion evaluation  | `promotion-boundary` check (MNCS boundary evaluation)        | `promotion/promotes`         |

The `supports`/`contradicts` edges use the shared Commons relationship
vocabulary; `pressure/supports-pressure` and `promotion/promotes` are
namespaced coordination extensions owned by this profile. Machine form:
`make_changeset_record` in `src/mncs_commons/family.py` (kind
`ChangeSet`), fixture `tests/fixtures/changeset-promotion-graph.json`,
tests in `tests/test_changeset_promotion.py`.

## Rules

1. The ChangeSet identity is the correlation key: every carried claim
   must be bound (by subject stamp or digest reference) to a revision
   the ChangeSet names. Evidence for another revision is not evidence
   for this ChangeSet.
2. `promotes` edges originate only from an MNCS promotion-boundary
   evaluation result, never from transport aggregation or from a
   component-level PASS. System-level PASS is never inferred from
   component records alone.
3. Unresolved obligations that block promotion are carried as
   `contradicts` edges against the promotion claim; obligations the
   boundary explicitly tolerates are `groups_with`. Silence is not
   tolerance.
4. Convergent pressures link (`groups_with`), never silently merge; the
   MNCDS `supersedes` chain on obligation records is preserved verbatim.
5. Amendments (new results, replications, disagreements, invalidations)
   are append-only linked records, never edits of the carried claims.

## Minimal shape

A coordination record needs no new schema to use this profile: it is a
set of typed edges over existing producer records plus the ChangeSet's
own base-revision pins. Producers keep their native stores; Commons
keeps the graph.

## Mechanical enforcement

`make_changeset_record` enforces what the rules above declare:

- rule 2: a `promotes` entry must be `recordKind: check-result` from
  producer `mncs-promotion-boundary`. Anything else -- a component PASS,
  a development record, a lineage entry -- is rejected, as is a second
  promotion result.
- rule 1: a reference carrying `scope.repository`/`scope.commit`
  correlation-claims its revision and must name one of the ChangeSet's
  base revisions exactly (40-hex, no moving refs). Evidence for another
  revision is rejected. Scopeless references stay allowed: Commons
  cannot demand correlation metadata a producer never carried.

Enforcement is covered by `tests/test_changeset_promotion_evidence.py`,
including a full tranche that relates genuine promotion-shaped evidence
(candidate revisions, boundary, evidence, obligations, claim, digests)
over real merged base revisions with recomputed digests.

## Publication

An accepted family graph's ChangeSet is published by committing the
bundle bytes verbatim to `family/changesets/<changeset-id>.json`
through a reviewed Commons PR (staged from mncs-actions with
`family_proof.py publish-commons`, which re-derives the owner content
digest and refuses overwrites). Publication is append-only and decides
nothing: merging records that Commons relates this constellation, with
exactly one `promotes` edge and a `predecessorGraph` chain link.
`tests/test_published_family_changesets.py` revalidates every published
record with the owner validator, so publication stays self-checking.
