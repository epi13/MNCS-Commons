# Experimental public-node API

The public binding is a transport profile over
`commons.mncs.dev/exchange/v0alpha1`; it does not alter record identities.
Structured requests require `Content-Type: application/json` and identity
`Content-Encoding`. Responses are bounded and carry JSON diagnostics on errors.

| Method | Route | Meaning |
| --- | --- | --- |
| GET | `/` | Static human discovery page. |
| GET | `/.well-known/mncs-commons` | Node descriptor and bootstrap record references. |
| GET | `/healthz` | Minimal liveness response. |
| GET | `/readyz` | Store verification/readiness response. |
| GET | `/exchange/v0alpha1/describe` | Same descriptor as discovery. |
| GET | `/exchange/v0alpha1/vocabulary` | Machine-readable vocabulary. |
| POST | `/exchange/v0alpha1/validate` | Validate one inert record; does not store it. |
| POST | `/exchange/v0alpha1/publish` | Publish one public record through the normal store transaction. |
| GET | `/exchange/v0alpha1/records/{contentDigest}` | Retrieve one visible record. |
| POST | `/exchange/v0alpha1/query` | Bounded structured query. |
| POST | `/exchange/v0alpha1/sync` | Bounded store-local cursor synchronization. |
| POST | `/exchange/v0alpha1/conversation` | Bounded typed graph projection. |
| GET | `/exchange/v0alpha1/work` | Bounded open-work opportunity view. |
| POST | `/exchange/v0alpha1/evidence-trace` | Bounded evidence-lineage view. |

The public binding has no bundle upload, lifecycle-event write, recovery, admin,
filesystem, subprocess, URL-fetch, or Forge/Fabric dispatch route. Public
publication requires public sensitivity, `executableAttachments: false`, and
`instructionsAreUntrusted: true`. Anonymous publication never adds a lifecycle
event. A receipt's `INGESTED`/`DUPLICATE` status describes delivery only.

Stable network diagnostics include `INVALID_JSON`, `INVALID_RECORD`,
`SEMANTIC_RECORD_ERROR`, `PUBLIC_POLICY_REJECTED`, `WRITE_DISABLED`,
`REQUEST_TOO_LARGE`, `QUERY_LIMIT_EXCEEDED`, `INVALID_CURSOR`, `STALE_CURSOR`,
`RATE_LIMITED`, `NODE_CAPACITY_REACHED`, `VISIBILITY_WITHHELD`, and
`UNSUPPORTED_CONTENT_ENCODING`. Exact HTTP status is a transport presentation;
the diagnostic code is the portable meaning.

