# Semantic family graph

Repository owners keep `family-semantic-contracts-v1.json` next to the
implementation it describes.  A consuming entry may also name a
`verification` identity and its command-free
`family-verification-checks-v1.json` surface. A verification surface names
the trusted runner kind (`declaration` or `mncs-test`) and, for behavioral
checks, a bounded manifest, compiler inventory identity, and exact test
identities. It never carries a shell command. Commons binds the content
digests of both files into the generated graph; changing either file makes
the checked-in graph stale. An unknown runner, unsafe selector path, missing
inventory identity, duplicate test identity, or executable field is rejected
before graph generation.

The cheap local check is:

```text
python scripts/validate_semantic_declaration.py --root <repository>
```

The synchronization check obtains the registered family checkouts and runs:

```text
python scripts/reconcile_semantic_edges.py --workspace <family-root> --check
```

Commons CI performs that reconciliation against current `main` checkouts.
The local service exposes the already checked-in graph through
`family.graph`; it never regenerates or executes repositories.  Consumers can
use the returned `graph_identity` as a bounded cache key and select exact edge
fingerprints without rediscovering sibling repositories.

`graph.complete` means topology is complete among repositories explicitly
classified as semantic-graph participants. The separate `coverage` projection
reports registered family projects, explicit nonparticipants, and
unclassified projects. A selected-repository proof must not describe the
participant count as the total family size; incomplete registry coverage keeps
full consumer closure UNKNOWN while still allowing a bounded known-edge proof.

## Runtime contract-edge audit

`repository_contracts()` reads both repository manifests and validated explicit
semantic declarations. Bare manifest exports are qualified by their declared
repository identity; consumes edges stay exact. Environment uses this structural
reader for architectural consumer discovery. Language Service impact is observed
semantic evidence and does not manufacture declarations or repair authority.

For the demonstrated stdlib ownership migration, validate provider-indexed native
runtime imports with:

```bash
python3 scripts/audit_repository_dependencies.py --workspace <family-root> \
  --stdlib <selected-stdlib> --repository mncs-store --repository mncs-test
```

The audit verifies the selected provider's module content index, inspects native
source evidence named by provides declarations, excludes dev/test/example trees,
and reports missing consumes edges (exit 5), unavailable/stale evidence (exit 2),
or a complete selected audit (exit 0). It does not write manifests. This is a
validation command, not a source scan on every coordination pass. It proves only
the bounded selected provider/consumer closure; it is not a universal import graph.
