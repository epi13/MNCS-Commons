# Semantic family graph

Repository owners keep `family-semantic-contracts-v1.json` next to the
implementation it describes.  A consuming entry may also name a
`verification` identity and its command-free
`family-verification-checks-v1.json` surface.  Commons binds the content
digests of both files into the generated graph; changing either file makes
the checked-in graph stale.

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
