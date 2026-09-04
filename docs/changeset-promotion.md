# ChangeSet promotion profile

Status: coordination profile (non-normative for producer semantics).

A cross-repository ChangeSet that reaches an MNCS promotion boundary
carries, by reference, the machine-readable contracts owned elsewhere.
Commons does not redefine them; this profile names the edges so every
affected repository assembles the same relationship graph.

## Carried references

| ChangeSet element              | Owning contract                                              | Edge            |
| ------------------------------ | ------------------------------------------------------------ | --------------- |
| ChangeSet identity             | MNCDS ChangeSet (`development-pressure-protocol.md`)         | self            |
| affected repositories/revisions| exact base revisions in the ChangeSet                        | self            |
| MNCDS development record       | `mncds-development-record` check (MNCDS check catalog)       | `supported_by`  |
| rights/lineage references      | `mncs-rights-provenance` lineage record                      | `supported_by`  |
| Commons coordination relation  | this profile                                                 | `groups_with`   |
| pressure/capability gaps       | `mncds-obligation-record/0.1` (projected pressure)           | `supports_pressure` |
| evidence per affected repo     | each repository's `check-result/1` claims                    | `supported_by`  |
| unresolved obligations         | `mncds-obligations` check `unresolved` entries               | `contradicts` (blocks) or `groups_with` (tolerated) |
| eventual promotion evaluation  | `promotion-boundary` check (MNCS boundary evaluation)        | `promotes`      |

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
