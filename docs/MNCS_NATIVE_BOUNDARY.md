# Commons MNCS-native boundary

Commons is intentionally not a second generic utility repository. Its
family-wide contract is the pressure exchange and the coordination metadata
around it. The implementation therefore has two explicit layers.

## Native semantic kernel

The normative pressure kernel is
`src/mncs_commons/mesh/mncs/commons/pressure/lifecycle.mncs`. It owns pure,
deterministic rules for:

- lifecycle transition legality;
- unresolved versus terminal classification;
- evidence-gated resolution readiness;
- `incomplete`, `ready`, `failed`, and `unknown` verification state;
- an available capability awaiting consumer validation; and
- an unresolved record that needs a current-language revalidation.

The Python mirror is tested against
`pressure-lifecycle-corpus.json` and `pressure-projection-corpus.json`.
`mncs-research-bytecode` and `portable-wasm` execute the same corpus through
the normal toolchain interop lane. Numeric discriminants are an intentionally
small ABI: JSON field names, filesystem authority, and untrusted text do not
enter the MNCS program.

## Host adapter boundary

Python remains for work that is currently an OS or transport boundary:

| Area | Why it remains host-side |
| --- | --- |
| JSON read/write and canonical digests | Dynamic documents, byte serialization, and filesystem publication are host effects. |
| Append-only files and stale-head checks | Git-friendly one-document-per-contribution storage needs filesystem inspection and atomic host writes. |
| Paths, repository manifests, and Git provenance | These are operating-system/process inputs, not pressure semantics. |
| Clock and run metadata | Wall-clock acquisition is an explicit host capability. |
| CLI and text-ledger migration | Argument parsing and inert Markdown ingestion are transport/adaptation. |
| Dynamic projection over records/observations/events | Current MNCS does not yet provide the unbounded maps/sets, dynamic text, JSON, and graph-folding surface needed to replace `PressureRegistry`. |

The last row is a real language pressure, not an unexplained implementation
preference: `MNCS-LANG-6643CDECCFEC` records the current reproducer, host
locus, Profile 0.16 review, Python fallback locations, and the recommended
direction. Existing related family evidence includes Store `P1-017`, Index
`PRESS-014`, and compiler `CP-0005`; their consumer reproductions remain
distinct and are linked rather than silently merged.

This boundary keeps the host code thin around the native laws. It also makes
future conversion measurable: when MNCS gains dynamic structured values,
bounded graph folds, or a suitable JSON/effect contract, a new observation can
close or narrow `MNCS-LANG-6643CDECC` after the host projection is actually
replaced and the generated views remain byte-for-byte deterministic.

## Trust boundary

Pressure descriptions, source snapshots, reproducer commands, workaround text,
and URLs remain inert data. Neither the native kernel nor the Python adapter
executes imported instructions. A future Doctor integration may read a
pressure marker and propose a migration, but separate authorization and
sandboxing remain required to apply it.
