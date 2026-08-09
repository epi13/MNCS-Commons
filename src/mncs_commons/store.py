"""Small append-only, content-addressed local reference store.

The store provides local consistency and recoverability.  It does not provide
authentication, protected custody, or authority to execute record contents.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .canonical import canonical_digest, canonical_json
from .lifecycle import LifecycleView, derive_lifecycle, domain_views, validate_transition
from .models import Diagnostic, LifecycleEvent, Record
from .query import QueryFilter, record_matches, review_required, state_matches
from .semantic import record_semantic_diagnostics
from .validation import validate_event, validate_record

MAX_LEDGER_LINE_BYTES = 8 * 1024 * 1024
MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_LEDGER_ROWS = 100_000
MAX_TRANSACTION_BYTES = 16 * 1024 * 1024
TRANSACTION_VERSION = 1


class StoreError(RuntimeError):
    """A fail-closed local persistence error."""


@dataclass(frozen=True, slots=True)
class StoreVerification:
    valid: bool
    diagnostics: tuple[Diagnostic, ...]

    def as_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "diagnostics": [item.as_dict() for item in self.diagnostics]}


@dataclass(frozen=True, slots=True)
class _LedgerTail:
    sequence: int
    entry_digest: str | None
    ledger_bytes: int


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_DIRECTORY)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            return
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Serialize writers with an advisory lock on POSIX and Windows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 30.0
    while True:
        try:
            handle = path.open("a+b")
            break
        except PermissionError:
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
    with handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
            try:
                yield
            finally:
                # Windows releases the region when this handle closes. Explicit
                # LK_UNLCK is unreliable on the hosted Windows runner.
                handle.flush()
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


class CommonsStore:
    """Filesystem store with recoverable append transactions."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.records_path = self.root / "records"
        self.events_path = self.root / "events"
        self.ledger_path = self.root / "ledger.jsonl"
        self.transactions_path = self.root / ".transactions"
        self.lock_path = self.root / ".writer.lock"
        self.tail_path = self.root / ".ledger-tail.json"

    def init(self) -> None:
        self.records_path.mkdir(parents=True, exist_ok=True)
        self.events_path.mkdir(parents=True, exist_ok=True)
        self.transactions_path.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            _atomic_write(self.ledger_path, b"")
        if not self.tail_path.exists():
            _atomic_write(
                self.tail_path,
                canonical_json({"sequence": 0, "entryDigest": None, "ledgerBytes": 0}),
            )

    def _require_initialized(self) -> None:
        if (
            not self.records_path.is_dir()
            or not self.events_path.is_dir()
            or not self.transactions_path.is_dir()
            or not self.ledger_path.exists()
        ):
            raise StoreError("store is not initialized")

    def _pending_transactions(self) -> list[Path]:
        if not self.transactions_path.exists():
            return []
        return sorted(
            (item for item in self.transactions_path.iterdir() if item.is_dir()),
            key=lambda item: item.name,
        )

    def _require_no_pending(self) -> None:
        pending = self._pending_transactions()
        if pending:
            raise StoreError("pending transaction requires explicit store recover")

    def _rows(self) -> list[dict[str, Any]]:
        self._require_initialized()
        rows: list[dict[str, Any]] = []
        total_bytes = 0
        with self.ledger_path.open("rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                total_bytes += len(raw)
                if total_bytes > MAX_LEDGER_BYTES or line_number > MAX_LEDGER_ROWS:
                    raise StoreError("ledger exceeds bounded storage read limit")
                if len(raw) > MAX_LEDGER_LINE_BYTES:
                    raise StoreError(f"ledger line {line_number} exceeds bounded read limit")
                if not raw.strip():
                    raise StoreError(f"ledger line {line_number} is blank")
                try:
                    row = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise StoreError(f"ledger line {line_number} is invalid JSON") from error
                if not isinstance(row, dict):
                    raise StoreError(f"ledger line {line_number} is not an object")
                rows.append(row)
        return rows

    def _tail_from_rows(self, rows: list[dict[str, Any]]) -> _LedgerTail:
        return _LedgerTail(
            sequence=len(rows),
            entry_digest=str(rows[-1].get("entryDigest")) if rows else None,
            ledger_bytes=self.ledger_path.stat().st_size,
        )

    def _load_tail_locked(self) -> _LedgerTail:
        self._require_initialized()
        size = self.ledger_path.stat().st_size
        if self.tail_path.exists():
            try:
                raw = self.tail_path.read_bytes()
                if len(raw) <= MAX_TRANSACTION_BYTES:
                    value = json.loads(raw.decode("utf-8"))
                    tail = _LedgerTail(
                        int(value["sequence"]),
                        value.get("entryDigest"),
                        int(value["ledgerBytes"]),
                    )
                    if tail.ledger_bytes == size and tail.sequence >= 0:
                        if tail.sequence == 0 and tail.entry_digest is None:
                            return tail
                        with self.ledger_path.open("rb") as handle:
                            handle.seek(max(0, size - MAX_LEDGER_LINE_BYTES))
                            lines = handle.read().splitlines()
                        if lines:
                            last = json.loads(lines[-1].decode("utf-8"))
                            if (
                                isinstance(last, dict)
                                and last.get("sequence") == tail.sequence
                                and last.get("entryDigest") == tail.entry_digest
                            ):
                                return tail
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass
        rows = self._rows()
        tail = self._tail_from_rows(rows)
        _atomic_write(
            self.tail_path,
            canonical_json(
                {
                    "sequence": tail.sequence,
                    "entryDigest": tail.entry_digest,
                    "ledgerBytes": tail.ledger_bytes,
                }
            ),
        )
        return tail

    @staticmethod
    def _with_digest(value: Mapping[str, Any]) -> dict[str, Any]:
        result = json.loads(canonical_json(value).decode("utf-8"))
        result["contentDigest"] = canonical_digest(result)
        return json.loads(canonical_json(result).decode("utf-8"))

    def _content_path(self, entry_type: str, digest: str) -> Path:
        directory = self.records_path if entry_type == "record" else self.events_path
        return directory / f"{digest.removeprefix('sha256:')}.json"

    def _make_ledger_row(
        self, entry_type: str, payload: Mapping[str, Any], tail: _LedgerTail
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "sequence": tail.sequence + 1,
            "entryType": entry_type,
            "previousDigest": tail.entry_digest,
            "payload": dict(payload),
        }
        return {**body, "entryDigest": canonical_digest(body, projected=False)}

    def _stage_transaction(
        self,
        entry_type: str,
        payload: Mapping[str, Any],
        content_path: Path,
        row: Mapping[str, Any],
        tail: _LedgerTail,
    ) -> Path:
        transaction = Path(tempfile.mkdtemp(prefix="txn-", dir=self.transactions_path))
        content = canonical_json(payload)
        encoded_row = canonical_json(row) + b"\n"
        journal = {
            "version": TRANSACTION_VERSION,
            "entryType": entry_type,
            "contentDigest": payload.get("contentDigest"),
            "contentPath": str(content_path.relative_to(self.root)),
            "content": content.decode("utf-8"),
            "ledgerRow": dict(row),
            "ledgerRowBytesDigest": canonical_digest(row, projected=False),
            "previousEntryDigest": tail.entry_digest,
            "sequence": tail.sequence + 1,
            "ledgerBytesAfter": self.ledger_path.stat().st_size + len(encoded_row),
        }
        encoded_journal = canonical_json(journal)
        if len(encoded_journal) > MAX_TRANSACTION_BYTES:
            shutil.rmtree(transaction)
            raise StoreError("transaction exceeds bounded journal size")
        _atomic_write(transaction / "journal.json", encoded_journal)
        _atomic_write(transaction / "content.json", content)
        return transaction

    def _append_row(self, row: Mapping[str, Any]) -> None:
        encoded = canonical_json(row) + b"\n"
        with self.ledger_path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    def _finish_transaction(self, transaction: Path, row: Mapping[str, Any]) -> None:
        journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
        content = (transaction / "content.json").read_bytes()
        content_path = self.root / str(journal["contentPath"])
        if content_path.exists() and content_path.read_bytes() != content:
            raise StoreError(f"content path collision for {journal['contentDigest']}")
        if not content_path.exists():
            _atomic_write(content_path, content)
        self._append_row(row)
        tail = {
            "sequence": row["sequence"],
            "entryDigest": row["entryDigest"],
            "ledgerBytes": self.ledger_path.stat().st_size,
        }
        _atomic_write(self.tail_path, canonical_json(tail))
        shutil.rmtree(transaction)

    def _commit(self, entry_type: str, payload: Mapping[str, Any]) -> None:
        tail = self._load_tail_locked()
        row = self._make_ledger_row(entry_type, payload, tail)
        transaction = self._stage_transaction(
            entry_type,
            payload,
            self._content_path(entry_type, str(payload["contentDigest"])),
            row,
            tail,
        )
        try:
            self._finish_transaction(transaction, row)
        except Exception:
            raise

    def _payloads_from_rows(
        self, rows: Sequence[Mapping[str, Any]], entry_type: str
    ) -> list[Mapping[str, Any]]:
        return [
            row["payload"]
            for row in rows
            if row.get("entryType") == entry_type and isinstance(row.get("payload"), dict)
        ]

    def add_record(self, value: Mapping[str, Any]) -> Record:
        self._require_initialized()
        with _file_lock(self.lock_path):
            self._require_no_pending()
            candidate = self._with_digest(value) if "contentDigest" not in value else dict(value)
            report = validate_record(candidate)
            if not report.valid:
                raise StoreError(
                    "record rejected: " + "; ".join(item.message for item in report.diagnostics)
                )
            digest = str(candidate["contentDigest"])
            path = self._content_path("record", digest)
            encoded = canonical_json(candidate)
            if path.exists() and path.read_bytes() != encoded:
                raise StoreError(f"record path collision for {digest}")
            rows = self._rows()
            existing_records = self._payloads_from_rows(rows, "record")
            semantic = record_semantic_diagnostics(candidate, existing_records)
            if semantic:
                raise StoreError("record rejected: " + "; ".join(item.message for item in semantic))
            if any(
                row.get("entryType") == "record"
                and row.get("payload", {}).get("contentDigest") == digest
                for row in rows
            ):
                return Record(candidate, digest)
            self._commit("record", candidate)
            return Record(candidate, digest)

    def add_event(self, value: Mapping[str, Any]) -> LifecycleEvent:
        self._require_initialized()
        with _file_lock(self.lock_path):
            self._require_no_pending()
            candidate = self._with_digest(value) if "contentDigest" not in value else dict(value)
            report = validate_event(candidate)
            if not report.valid:
                raise StoreError(
                    "event rejected: " + "; ".join(item.message for item in report.diagnostics)
                )
            digest = str(candidate["contentDigest"])
            rows = self._rows()
            if any(
                row.get("entryType") == "event"
                and row.get("payload", {}).get("contentDigest") == digest
                for row in rows
            ):
                return LifecycleEvent(candidate, digest)
            target_digest = str(candidate["target"]["contentDigest"])
            target = next(
                (
                    item
                    for item in self._payloads_from_rows(rows, "record")
                    if item.get("contentDigest") == target_digest
                ),
                None,
            )
            if target is None:
                raise StoreError("lifecycle event target is not present locally")
            authority = candidate.get("authority", {})
            domain = str(authority.get("domain", "")) if isinstance(authority, Mapping) else ""
            current = derive_lifecycle(
                target, self._payloads_from_rows(rows, "event"), domain=domain
            )
            transition = candidate["transition"]
            transition_report = validate_transition(
                current.transition_state, str(transition["to"]), candidate
            )
            if not transition_report.valid:
                raise StoreError(
                    "event transition rejected: "
                    + "; ".join(item.message for item in transition_report.diagnostics)
                )
            self._commit("event", candidate)
            return LifecycleEvent(candidate, digest)

    def _rows_for_read(self) -> list[dict[str, Any]]:
        return self._rows()

    def records(self) -> list[Mapping[str, Any]]:
        return list(self._payloads_from_rows(self._rows_for_read(), "record"))

    def events(self) -> list[Mapping[str, Any]]:
        return list(self._payloads_from_rows(self._rows_for_read(), "event"))

    def get(self, digest: str) -> Mapping[str, Any] | None:
        for item in (*self.records(), *self.events()):
            if item.get("contentDigest") == digest:
                return item
        return None

    def lifecycle(self, digest: str, domain: str | None = None) -> LifecycleView:
        record = next(
            (item for item in self.records() if item.get("contentDigest") == digest), None
        )
        if record is None:
            raise StoreError(f"record not found: {digest}")
        return derive_lifecycle(record, self.events(), domain=domain)

    def domain_views(self, digest: str) -> dict[str, LifecycleView]:
        record = next(
            (item for item in self.records() if item.get("contentDigest") == digest), None
        )
        if record is None:
            raise StoreError(f"record not found: {digest}")
        return domain_views(record, self.events())

    def query(self, query: QueryFilter) -> list[Mapping[str, Any]]:
        result: list[Mapping[str, Any]] = []
        for record in self.records():
            digest = str(record.get("contentDigest"))
            view = self.lifecycle(digest, domain=query.domain)
            domain_state_map = dict(view.domain_states)
            match_state = (
                query.state
                if query.state and not query.domain and query.state in domain_state_map.values()
                else view.current_state
            )
            if record_matches(record, query, match_state) and state_matches(
                view.current_state, query, domain_state_map
            ):
                if query.needs_review and not review_required(record, now=query.now):
                    continue
                result.append(record)
        return sorted(
            result,
            key=lambda item: (
                str(item.get("metadata", {}).get("createdAt", "")),
                str(item.get("contentDigest", "")),
            ),
        )

    def _verify_journal(self, transaction: Path) -> dict[str, Any]:
        journal_path = transaction / "journal.json"
        raw = journal_path.read_bytes()
        if len(raw) > MAX_TRANSACTION_BYTES:
            raise StoreError(f"transaction journal exceeds bounded read limit: {transaction.name}")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict) or value.get("version") != TRANSACTION_VERSION:
            raise StoreError(f"unsupported transaction journal: {transaction.name}")
        required = {"entryType", "contentDigest", "contentPath", "content", "ledgerRow"}
        if not required <= set(value):
            raise StoreError(f"incomplete transaction journal: {transaction.name}")
        content = value["content"].encode("utf-8")
        payload = json.loads(content.decode("utf-8"))
        row = value["ledgerRow"]
        if not isinstance(payload, dict) or not isinstance(row, dict):
            raise StoreError(f"invalid transaction payload: {transaction.name}")
        if value["entryType"] not in {"record", "event"}:
            raise StoreError(f"invalid transaction entry type: {transaction.name}")
        relative_path = Path(str(value["contentPath"]))
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.parts[:1] not in {("records",), ("events",)}
        ):
            raise StoreError(f"unsafe transaction content path: {transaction.name}")
        expected_path = self._content_path(str(value["entryType"]), str(value["contentDigest"]))
        if relative_path != expected_path.relative_to(self.root):
            raise StoreError(f"transaction content path mismatch: {transaction.name}")
        if (
            canonical_json(payload) != content
            or payload.get("contentDigest") != value["contentDigest"]
        ):
            raise StoreError(f"transaction content identity mismatch: {transaction.name}")
        if canonical_digest(payload) != value["contentDigest"]:
            raise StoreError(f"transaction content digest mismatch: {transaction.name}")
        if canonical_digest(row, projected=False) != value.get("ledgerRowBytesDigest"):
            raise StoreError(f"transaction ledger identity mismatch: {transaction.name}")
        if row.get("entryType") != value["entryType"] or row.get("payload") != payload:
            raise StoreError(f"transaction ledger payload mismatch: {transaction.name}")
        return value

    def _recover_one_locked(self, transaction: Path) -> None:
        journal = self._verify_journal(transaction)
        rows = self._rows()
        row = journal["ledgerRow"]
        matching = [item for item in rows if item.get("entryDigest") == row.get("entryDigest")]
        if matching:
            if matching[0] != row:
                raise StoreError(f"transaction conflicts with committed ledger: {transaction.name}")
        else:
            previous = rows[-1].get("entryDigest") if rows else None
            if (
                previous != journal.get("previousEntryDigest")
                or row.get("sequence") != len(rows) + 1
            ):
                raise StoreError(f"transaction cannot be safely recovered: {transaction.name}")
            content_path = self.root / str(journal["contentPath"])
            content = journal["content"].encode("utf-8")
            if content_path.exists() and content_path.read_bytes() != content:
                raise StoreError(f"transaction content collision: {transaction.name}")
            if not content_path.exists():
                _atomic_write(content_path, content)
            self._append_row(row)
            _atomic_write(
                self.tail_path,
                canonical_json(
                    {
                        "sequence": row["sequence"],
                        "entryDigest": row["entryDigest"],
                        "ledgerBytes": self.ledger_path.stat().st_size,
                    }
                ),
            )
        content_path = self.root / str(journal["contentPath"])
        if (
            not content_path.exists()
            or content_path.read_bytes() != journal["content"].encode("utf-8")
        ):
            raise StoreError(f"transaction content is not committed: {transaction.name}")
        shutil.rmtree(transaction)

    def recover(self) -> StoreVerification:
        self._require_initialized()
        with _file_lock(self.lock_path):
            diagnostics: list[Diagnostic] = []
            for transaction in self._pending_transactions():
                try:
                    self._recover_one_locked(transaction)
                except (OSError, StoreError, ValueError, json.JSONDecodeError) as error:
                    diagnostics.append(Diagnostic("RECOVERY_FAILED", transaction.name, str(error)))
                    break
            if diagnostics:
                return StoreVerification(False, tuple(diagnostics))
        return self.verify()

    def diagnose(self) -> StoreVerification:
        return self.verify()

    def verify(self) -> StoreVerification:
        diagnostics: list[Diagnostic] = []
        try:
            rows = self._rows()
        except StoreError as error:
            return StoreVerification(
                False, (Diagnostic("LEDGER_READ_FAILED", "ledger.jsonl", str(error)),)
            )
        for transaction in self._pending_transactions():
            diagnostics.append(
                Diagnostic(
                    "PENDING_TRANSACTION",
                    transaction.name,
                    "transaction is recoverable or must be inspected explicitly",
                )
            )
        previous: str | None = None
        referenced_records: set[str] = set()
        referenced_events: set[str] = set()
        for expected_sequence, row in enumerate(rows, 1):
            path = f"ledger.jsonl[{expected_sequence}]"
            if row.get("sequence") != expected_sequence:
                diagnostics.append(
                    Diagnostic("SEQUENCE_MISMATCH", path, "ledger sequence is not contiguous")
                )
            if row.get("previousDigest") != previous:
                diagnostics.append(
                    Diagnostic("PREVIOUS_DIGEST_MISMATCH", path, "ledger hash link is broken")
                )
            body = {
                key: row.get(key) for key in ("sequence", "entryType", "previousDigest", "payload")
            }
            expected_entry = canonical_digest(body, projected=False)
            if row.get("entryDigest") != expected_entry:
                diagnostics.append(
                    Diagnostic("ENTRY_DIGEST_MISMATCH", path, f"expected {expected_entry}")
                )
            previous = row.get("entryDigest")
            entry_type = row.get("entryType")
            payload = row.get("payload")
            if not isinstance(payload, dict):
                diagnostics.append(
                    Diagnostic("PAYLOAD_INVALID", path, "ledger payload must be an object")
                )
                continue
            if entry_type == "record":
                report = validate_record(payload)
                digest = payload.get("contentDigest")
                referenced_records.add(str(digest))
            elif entry_type == "event":
                report = validate_event(payload)
                digest = payload.get("contentDigest")
                referenced_events.add(str(digest))
            else:
                diagnostics.append(
                    Diagnostic("UNKNOWN_ENTRY_TYPE", path, "entry type must be record or event")
                )
                continue
            file_path = self._content_path(str(entry_type), str(digest))
            if not report.valid:
                diagnostics.extend(
                    Diagnostic(item.code, f"{path}.{item.path}", item.message)
                    for item in report.diagnostics
                )
            if isinstance(digest, str) and canonical_digest(payload) != digest:
                diagnostics.append(
                    Diagnostic(
                        "CONTENT_DIGEST_MISMATCH",
                        path,
                        f"content digest for {entry_type} is wrong",
                    )
                )
            if not file_path.exists():
                diagnostics.append(Diagnostic("CONTENT_FILE_MISSING", path, str(file_path)))
            elif file_path.read_bytes() != canonical_json(payload):
                diagnostics.append(Diagnostic("CONTENT_FILE_MISMATCH", path, str(file_path)))
        if self.records_path.exists():
            for content_path in self.records_path.glob("*.json"):
                digest = "sha256:" + content_path.stem
                if digest not in referenced_records:
                    diagnostics.append(
                        Diagnostic(
                            "ORPHAN_RECORD",
                            str(content_path),
                            "content file is not linked from ledger",
                        )
                    )
        if self.events_path.exists():
            for content_path in self.events_path.glob("*.json"):
                digest = "sha256:" + content_path.stem
                if digest not in referenced_events:
                    diagnostics.append(
                        Diagnostic(
                            "ORPHAN_EVENT",
                            str(content_path),
                            "content file is not linked from ledger",
                        )
                    )
        return StoreVerification(not diagnostics, tuple(diagnostics))
