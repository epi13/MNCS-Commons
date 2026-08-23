"""Immutable cold archives for Commons generations.

Archives are lossless tar.zst bundles with a verified manifest. An LLM
summary is never the sole surviving representation.
"""

from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from compression import zstd  # type: ignore[import-not-found,no-redef]
except ModuleNotFoundError:  # Python < 3.14
    import zstandard as _zstandard

    class _ZstdModule:
        @staticmethod
        def compress(data: bytes) -> bytes:
            return _zstandard.ZstdCompressor().compress(data)

        @staticmethod
        def decompress(data: bytes) -> bytes:
            return _zstandard.ZstdDecompressor().decompress(data)

    zstd = _ZstdModule()  # type: ignore[assignment,misc]

from .canonical import canonical_digest, canonical_json
from .store import CommonsStore, StoreError, _atomic_write

ARCHIVE_SCHEMA = "commons.mncs.dev/archive-manifest/v0alpha1"
POINTER_SCHEMA = "commons.mncs.dev/archived-pointer/v0alpha1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_week(now: str | None = None) -> tuple[int, int]:
    current = datetime.fromisoformat((now or _utc_now()).replace("Z", "+00:00"))
    iso = current.isocalendar()
    return iso.year, iso.week


def archive_root(store: CommonsStore) -> Path:
    path = store.root / "archive"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bundle_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, payload in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return zstd.compress(buffer.getvalue())


def _extract_bundle(data: bytes) -> dict[str, bytes]:
    raw = zstd.decompress(data)
    members: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as archive:
        for member in archive.getmembers():
            if not member.isfile() or member.name.startswith("/") or ".." in member.name:
                raise StoreError("archive member path is unsafe")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise StoreError(f"archive member missing: {member.name}")
            members[member.name] = extracted.read()
    return members


def create_archive(
    store: CommonsStore,
    *,
    records: list[Mapping[str, Any]],
    events: list[Mapping[str, Any]],
    now: str | None = None,
) -> dict[str, Any]:
    """Package the current ledger generation plus selected payloads."""

    year, week = _iso_week(now)
    members = {
        "ledger.jsonl": store.ledger_path.read_bytes() if store.ledger_path.exists() else b"",
        "manifest-placeholder": b"",
    }
    identities: list[str] = []
    for record in records:
        digest = str(record.get("contentDigest"))
        identities.append(digest)
        members[f"records/{digest.removeprefix('sha256:')}.json"] = canonical_json(record)
    for event in events:
        digest = str(event.get("contentDigest"))
        members[f"events/{digest.removeprefix('sha256:')}.json"] = canonical_json(event)
    members.pop("manifest-placeholder")
    bundle = _bundle_bytes(members)
    bundle_digest = "sha256:" + __import__("hashlib").sha256(bundle).hexdigest()
    usage = store.storage_usage()
    material = {
        "schema_version": ARCHIVE_SCHEMA,
        "createdAt": now or _utc_now(),
        "storeIdentity": store._store_identity(),
        "ledgerEntries": usage["ledgerEntries"],
        "ledgerBytes": usage["ledgerBytes"],
        "recordCount": len(records),
        "eventCount": len(events),
        "recordIdentities": identities,
        "bundleBytes": len(bundle),
        "bundleDigest": bundle_digest,
        "compression": "zstd",
        "format": "tar.zst",
        "authority": "operator-archive",
        "executionAuthority": "none",
    }
    archive_id = canonical_digest(material)
    material["archiveId"] = archive_id
    destination = (
        archive_root(store)
        / str(year)
        / f"week-{week:02d}"
        / archive_id.removeprefix("sha256:")
    )
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_write(destination / "bundle.tar.zst", bundle)
    _atomic_write(destination / "manifest.json", canonical_json(material))
    return material


def list_archives(store: CommonsStore) -> list[dict[str, Any]]:
    root = archive_root(store)
    found: list[dict[str, Any]] = []
    for manifest in sorted(root.rglob("manifest.json")):
        value = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value["path"] = str(manifest.parent)
            found.append(value)
    return found


def _archive_dir(store: CommonsStore, archive_id: str) -> Path:
    suffix = archive_id.removeprefix("sha256:")
    matches = list(archive_root(store).rglob(suffix))
    if not matches:
        raise StoreError(f"archive not found: {archive_id}")
    return matches[0]


def verify_archive(store: CommonsStore, archive_id: str) -> dict[str, Any]:
    directory = _archive_dir(store, archive_id)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    bundle = (directory / "bundle.tar.zst").read_bytes()
    digest = "sha256:" + __import__("hashlib").sha256(bundle).hexdigest()
    if digest != manifest.get("bundleDigest"):
        raise StoreError("ARCHIVE_CORRUPT: bundle digest does not match manifest")
    members = _extract_bundle(bundle)
    if "ledger.jsonl" not in members:
        raise StoreError("ARCHIVE_CORRUPT: ledger is missing")
    expected = set(manifest.get("recordIdentities") or [])
    present = {
        "sha256:" + Path(name).stem
        for name in members
        if name.startswith("records/") and name.endswith(".json")
    }
    if not expected.issubset(present):
        raise StoreError("ARCHIVE_CORRUPT: archived record set is incomplete")
    return {
        "valid": True,
        "archiveId": manifest.get("archiveId"),
        "bundleDigest": digest,
        "recordCount": len(present),
        "bundleBytes": len(bundle),
    }


def inspect_archive(store: CommonsStore, archive_id: str) -> dict[str, Any]:
    directory = _archive_dir(store, archive_id)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["path"] = str(directory)
    return manifest


def load_archived_record(store: CommonsStore, digest: str) -> dict[str, Any] | None:
    for archive in list_archives(store):
        identities = archive.get("recordIdentities") or []
        if digest not in identities:
            continue
        directory = Path(str(archive["path"]))
        members = _extract_bundle((directory / "bundle.tar.zst").read_bytes())
        payload = members.get(f"records/{digest.removeprefix('sha256:')}.json")
        if payload is None:
            continue
        value = json.loads(payload.decode("utf-8"))
        if isinstance(value, dict):
            return value
    return None


def restore_archive(store: CommonsStore, archive_id: str, destination: Path) -> dict[str, Any]:
    """Materialize an archive into a new store directory without mutating the hot store."""

    verify_archive(store, archive_id)
    directory = _archive_dir(store, archive_id)
    members = _extract_bundle((directory / "bundle.tar.zst").read_bytes())
    restored = CommonsStore(destination)
    restored.init()
    _atomic_write(restored.ledger_path, members["ledger.jsonl"])
    for name, payload in members.items():
        if name.startswith("records/") and name.endswith(".json"):
            _atomic_write(restored.records_path / Path(name).name, payload)
        elif name.startswith("events/") and name.endswith(".json"):
            _atomic_write(restored.events_path / Path(name).name, payload)
    restored.rebuild_tail()
    verification = restored.verify()
    if not verification.valid:
        raise StoreError("restored archive failed ledger verification")
    return {"restored": str(destination), "valid": True, "archiveId": archive_id}
