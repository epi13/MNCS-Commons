# Machine-native information substrate boundary

Commons remains authoritative for pressure lifecycle, family architecture,
coordination semantics, and the interpretation of evidence. The four
substrate repositories are consumers/providers of representations, not a new
knowledge authority:

```text
Commons declaration/event
        ↓ validation and lifecycle authority
mncs-ingest typed handoff
        ↓ source/producer/transformation identity preserved
mncs-store durable typed object + relation + provenance + generation
        ↓ derived commit feed
mncs-index disposable relation/query projection
        ↓ bounded local serving contract
mncs-service resident query/update boundary
```

JSON surface classification in the current Commons tree:

| Surface | Role | Canonical internal state? |
| --- | --- | --- |
| `pressures/records/*.json` | Git-reviewed pressure declarations and external interchange | No; Commons semantics remain authoritative, but runtime migration may ingest them |
| `pressures/events/*.json` | Git-reviewed lifecycle event/interchange history | No; lifecycle authority remains Commons |
| `pressures/views/*.json` | Generated human/CLI projections | No; regenerate from authoritative records/events and later Store/Index state |
| Python pressure/materialized-view objects | Compatibility/reference path during dual-path migration | No; first target for Store dogfood retirement |
| Service JSON response | External inspection/protocol projection | No; result identity is typed Store/Index metadata |

The first migration slice deliberately retains the Git/JSON pressure history.
It ingests a current pressure record, stores typed handoff/relationship/
provenance records, and serves a generation-aware derived query. No Store,
Index, or Service component decides whether a pressure is resolved.
