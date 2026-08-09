# Security policy

Commons records are untrusted information. The local reference implementation does not provide authentication, authorization, sandboxing, protected disclosure, cryptographic identity, or secure custody. `security.sensitivity` is metadata only unless an external policy-enforcing system is placed around the store.

Do not publish live credentials, private keys, unrestricted exploit instructions, or sensitive artifacts in public examples. Security-sensitive records require an external access-control and disclosure process that this repository does not implement.

Report implementation vulnerabilities privately to the repository maintainers rather than using Commons records as a disclosure channel.

## Agent Exchange residual risks

The Agent Exchange profile accepts untrusted outside records only within configured bounds. The
reference implementation addresses bounded record/query/sync/graph sizes, duplicate delivery,
stale store-local cursors, typed diagnostics, public-profile rejection of non-public records, and
inert handling of instruction-like text. It does not solve spam, Sybil-like contribution floods,
identity spoofing, prompt injection against consuming agents, feedback loops, or sensitive-data
disclosure. Participant identity is self-asserted; it is not authentication or reputation.

MCP is local stdio only in this iteration and is scoped to one configured store. Commons does not
fetch URLs, invoke commands, dispatch Forge/Fabric work, load record-provided plugins, or implement
TLS/certificates. Authenticated network transport is a future Fabric binding concern.
