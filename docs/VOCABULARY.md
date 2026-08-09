# Commons vocabulary

The machine-readable vocabulary is available from `mncs-commons exchange describe` and the optional
MCP `mncs-commons://vocabulary` resource. The exchange exposes record kinds, lifecycle states,
`PASS`/`FAIL`/`UNKNOWN`, WorkRequest states, relationship types, sensitivity, confidence levels,
recommended subject types, and recommended scope dimensions.

External terms must use a namespaced form such as `org.example/custom-result`. Unknown namespaced
terms remain preserved data. They do not silently become core terms and do not grant authority.

The canonical speech acts are `Observation`, `Claim`, `WorkRequest`, `Replication`, `Advisory`, and
`Decision`; `LifecycleEvent` is history, not a conversational message. Conversation operations are
views over typed relationships, not a new free-form `Message` primitive.
