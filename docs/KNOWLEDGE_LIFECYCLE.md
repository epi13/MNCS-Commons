# Local knowledge lifecycle example

Run the executable synthetic example with:

```bash
PYTHONPATH=src python scripts/local_knowledge_lifecycle.py
```

It loads the checked-in Observation, WorkRequest, and failed Replication records, creates a
positive Replication, a narrowed Claim, and a verifier Observation, then stores them in a fresh
Commons store. It adds explicit lifecycle events in two local domains. A typical result has six
records and four events:

```text
Observation
    |
    +--> WorkRequest
    |
    +--> Replication PASS  (clang/x86_64)
    +--> Replication FAIL  (GCC/aarch64)
              |
              +--> Claim narrowed to the original environment/toolchain scope
                          |
                          +--> verifier evidence
```

The `controller:local` projection can reach `accepted` while the independent `peer:independent`
projection remains `disputed`. The claim's outcome remains `UNKNOWN`; the lifecycle state is a
named local disposition, not a universal truth assertion. Evidence IDs, source records,
environments, limitations, and unresolved scope are retained in the records. No reproduction
procedure is executed.
