# Forge repository identity

The canonical Forge repository is now:

```text
mncs-forge
epi13/mncs-forge
```

Commons uses `mncs-forge` in its family registry, semantic graph, pressure
views, work routing, and generated evidence. The former `mncs-forge-mcp` name
is retained only as a bounded input alias so old observations and external
callers can be normalized without rewriting append-only historical provenance.

The alias is not a repository identity, checkout requirement, provider ID, or
execution path. New records, evidence, docs, and automation must use the
canonical name. Rename revalidation observations were added to the affected
resolved pressure records rather than creating duplicate pressures.
