"""Small append-only, content-addressed local reference store."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_digest, canonical_json
from .lifecycle import LifecycleView, derive_lifecycle, validate_transition
from .models import Diagnostic, LifecycleEvent, Record
from .query import QueryFilter, record_matches
from .validation import validate_event, validate_record

MAX_LEDGER_LINE_BYTES = 8 * 1024 * 1024
MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_LEDGER_ROWS = 100_000


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoreVerification:
    valid: bool
    diagnostics: tuple[Diagnostic, ...]

    def as_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "diagnostics": [item.as_dict() for item in self.diagnostics]}


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
            directory = os.open(path.parent, os.O_DIRECTORY)
        except (AttributeError, OSError):
            return
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class CommonsStore:
    """Filesystem store; it is local consistency, not custody or authentication."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.records_path = self.root / "records"
        self.events_path = self.root / "events"
        self.ledger_path = self.root / "ledger.jsonl"

    def init(self) -> None:
        self.records_path.mkdir(parents=True, exist_ok=True)
        self.events_path.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            _atomic_write(self.ledger_path, b"")

    def _require_initialized(self) -> None:
        if (
            not self.records_path.is_dir()
            or not self.events_path.is_dir()
            or not self.ledger_path.exists()
        ):
            raise StoreError("store is not initialized")

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

    def _append_ledger(self, entry_type: str, payload: Mapping[str, Any]) -> None:
        rows = self._rows()
        previous = rows[-1]["entryDigest"] if rows else None
        body: dict[str, Any] = {
            "sequence": len(rows) + 1,
            "entryType": entry_type,
            "previousDigest": previous,
            "payload": dict(payload),
        }
        row = {**body, "entryDigest": canonical_digest(body, projected=False)}
        encoded = canonical_json(row) + b"\n"
        with self.ledger_path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _with_digest(value: Mapping[str, Any]) -> dict[str, Any]:
        result = json.loads(canonical_json(value).decode("utf-8"))
        result["contentDigest"] = canonical_digest(result)
        return json.loads(canonical_json(result).decode("utf-8"))

    def add_record(self, value: Mapping[str, Any]) -> Record:
        self._require_initialized()
        candidate = self._with_digest(value) if "contentDigest" not in value else dict(value)
        report = validate_record(candidate)
        if not report.valid:
            raise StoreError(
                "record rejected: " + "; ".join(item.message for item in report.diagnostics)
            )
        digest = str(candidate["contentDigest"])
        path = self.records_path / f"{digest.removeprefix('sha256:')}.json"
        encoded = canonical_json(candidate)
        if path.exists() and path.read_bytes() != encoded:
            raise StoreError(f"record path collision for {digest}")
        rows = self._rows()
        if any(
            row.get("entryType") == "record"
            and row.get("payload", {}).get("contentDigest") == digest
            for row in rows
        ):
            return Record(candidate, digest)
        if not path.exists():
            _atomic_write(path, encoded)
        self._append_ledger("record", candidate)
        return Record(candidate, digest)

    def add_event(self, value: Mapping[str, Any]) -> LifecycleEvent:
        self._require_initialized()
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
        target = self.get(target_digest)
        if target is None:
            raise StoreError("lifecycle event target is not present locally")
        current = self.lifecycle(target_digest)
        transition = candidate["transition"]
        transition_report = validate_transition(
            current.current_state, str(transition["to"]), candidate
        )
        if not transition_report.valid:
            raise StoreError(
                "event transition rejected: "
                + "; ".join(item.message for item in transition_report.diagnostics)
            )
        path = self.events_path / f"{digest.removeprefix('sha256:')}.json"
        encoded = canonical_json(candidate)
        if path.exists() and path.read_bytes() != encoded:
            raise StoreError(f"event path collision for {digest}")
        if not path.exists():
            _atomic_write(path, encoded)
        self._append_ledger("event", candidate)
        return LifecycleEvent(candidate, digest)

    def _payloads(self, entry_type: str) -> list[Mapping[str, Any]]:
        return [
            row["payload"]
            for row in self._rows()
            if row.get("entryType") == entry_type and isinstance(row.get("payload"), dict)
        ]

    def records(self) -> list[Mapping[str, Any]]:
        return list(self._payloads("record"))

    def events(self) -> list[Mapping[str, Any]]:
        return list(self._payloads("event"))

    def get(self, digest: str) -> Mapping[str, Any] | None:
        for record in self.records():
            if record.get("contentDigest") == digest:
                return record
        for event in self.events():
            if event.get("contentDigest") == digest:
                return event
        return None

    def lifecycle(self, digest: str) -> LifecycleView:
        record = next(
            (item for item in self.records() if item.get("contentDigest") == digest), None
        )
        if record is None:
            raise StoreError(f"record not found: {digest}")
        return derive_lifecycle(record, self.events())

    def query(self, query: QueryFilter) -> list[Mapping[str, Any]]:
        result: list[Mapping[str, Any]] = []
        for record in self.records():
            digest = str(record.get("contentDigest"))
            state = self.lifecycle(digest).current_state
            if record_matches(record, query, state):
                if query.needs_review and not record.get("scope", {}).get("reviewAt"):
                    continue
                result.append(record)
        return sorted(
            result,
            key=lambda item: (
                str(item.get("metadata", {}).get("createdAt", "")),
                str(item.get("contentDigest", "")),
            ),
        )

    def verify(self) -> StoreVerification:
        diagnostics: list[Diagnostic] = []
        try:
            rows = self._rows()
        except StoreError as error:
            return StoreVerification(
                False, (Diagnostic("LEDGER_READ_FAILED", "ledger.jsonl", str(error)),)
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
                file_path = self.records_path / f"{str(digest).removeprefix('sha256:')}.json"
            elif entry_type == "event":
                report = validate_event(payload)
                digest = payload.get("contentDigest")
                referenced_events.add(str(digest))
                file_path = self.events_path / f"{str(digest).removeprefix('sha256:')}.json"
            else:
                diagnostics.append(
                    Diagnostic("UNKNOWN_ENTRY_TYPE", path, "entry type must be record or event")
                )
                continue
            if not report.valid:
                diagnostics.extend(
                    Diagnostic(item.code, f"{path}.{item.path}", item.message)
                    for item in report.diagnostics
                )
            if isinstance(digest, str) and canonical_digest(payload) != digest:
                diagnostics.append(
                    Diagnostic(
                        "CONTENT_DIGEST_MISMATCH", path, f"content digest for {entry_type} is wrong"
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
