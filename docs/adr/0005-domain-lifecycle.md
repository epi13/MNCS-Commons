# ADR 0005: Trust-domain lifecycle projection

Status: accepted for the 0.2 development iteration

The `v0alpha1` event wire shape is preserved, but lifecycle projection is domain-aware. Events are
filtered by `authority.domain`; `lifecycle(record, domain=...)` derives one local disposition,
`domain_views(record)` exposes represented domains, and the undirected projection reports
`domain-scoped` rather than selecting one domain's acceptance. This preserves independent project
views without claiming global truth.
