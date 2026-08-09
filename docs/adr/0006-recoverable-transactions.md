# ADR 0006: Recoverable local append transactions

Status: accepted for the 0.2 development iteration

The filesystem store uses a writer lock, a bounded transaction journal, staged canonical bytes, and a
hash-linked ledger row. A crash may leave an inspectable pending transaction, but recovery only
commits bytes whose content digest, ledger identity, predecessor, sequence, and expected content
path verify. The tail metadata is a disposable append acceleration; the ledger remains authoritative
and `verify` never silently repairs it.
