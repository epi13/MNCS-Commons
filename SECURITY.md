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

## Experimental public node

The optional HTTP server is an untrusted quarantine box for public knowledge. It
has no runtime dependency on Forge, Fabric, Git, GitHub, shells, credentials, or
model providers. It binds to `127.0.0.1` by default so a reverse proxy owns
Internet TLS. Direct wildcard binding requires an explicit flag, and public mode
requires an HTTPS base URL unless an explicit development override is used.

Node-local controls include strict JSON and identity content encoding, bounded
request/response/graph sizes, public-only security metadata, source and global
in-memory rate limits, a storage capacity ceiling, a read-only kill switch, an
operator-only visibility overlay, and structured errors. Forwarding headers are
ignored unless the immediate peer is explicitly trusted.

These controls do not solve distributed spam, Sybil behavior, traffic floods,
host compromise, TLS deployment mistakes, legal disclosure decisions, or
authenticated participant identity. Withheld visibility is local distribution
policy and does not rewrite canonical evidence or assert truth.
