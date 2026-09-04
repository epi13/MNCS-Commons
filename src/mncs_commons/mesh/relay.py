"""Optional Commons Relay: bounded reference infrastructure, zero authority.

A relay retains node descriptors, record identities, compact canonical
records, availability locations, graph relationships, and synchronization
frontier information.  It never requires all evidence, all execution
artifacts, private records, global authority, or promotion authority, and
it never issues lifecycle events.

Multiple relays may exist (language/compiler knowledge, Rights &
Provenance, GPU/PTX ecosystem, broad public graph).  Partial relays are
normal.  Loss of any relay destroys nothing: local nodes keep functioning
and direct or alternate synchronization remains possible.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from ..canonical import canonical_json
from .errors import MeshError
from .interest import InterestFilter, matches

RELAY_VERSION = "commons.mncs.dev/relay/v0alpha1"

MAX_DESCRIPTORS = 512
MAX_CAPSULES = 10_000
MAX_LOCATIONS_PER_DIGEST = 64


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class CommonsRelay:
    """A bounded, file-backed reference relay with no trust authority."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._descriptors_path = self.root / "descriptors.json"
        self._records_path = self.root / "records.json"
        self._capsules_path = self.root / "capsules.json"
        self._locations_path = self.root / "locations.json"

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self._descriptors_path,
            self._records_path,
            self._capsules_path,
            self._locations_path,
        ):
            if not path.exists():
                path.write_text("{}", encoding="utf-8")

    def _load(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise MeshError("RELAY_UNREADABLE", f"relay state unreadable: {error}") from error
        if not isinstance(value, dict):
            raise MeshError("RELAY_INVALID", "relay state must be an object")
        return value

    def _save(self, path: Path, value: Mapping[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(canonical_json(dict(value)))
        temporary.replace(path)

    # -- node descriptors ----------------------------------------------
    def advertise(self, descriptor: Mapping[str, Any]) -> dict[str, object]:
        if not isinstance(descriptor, Mapping):
            raise MeshError("INVALID_DESCRIPTOR", "node descriptor must be an object")
        node_id = descriptor.get("nodeId")
        if not isinstance(node_id, str) or not node_id or len(node_id) > 256:
            raise MeshError("INVALID_DESCRIPTOR", "descriptor needs a bounded nodeId")
        descriptors = self._load(self._descriptors_path)
        if node_id not in descriptors and len(descriptors) >= MAX_DESCRIPTORS:
            raise MeshError("RELAY_FULL", "relay descriptor table is at its bound")
        descriptors[node_id] = {"descriptor": dict(descriptor), "advertisedAt": _now()}
        self._save(self._descriptors_path, descriptors)
        return {"relayVersion": RELAY_VERSION, "advertised": node_id}

    def descriptors(self) -> dict[str, Any]:
        return self._load(self._descriptors_path)

    # -- compact canonical records -----------------------------------------
    def offer_record(self, record: Mapping[str, Any]) -> dict[str, object]:
        """Retain one compact canonical record; validated, never authorized.

        Oversize records are refused (discoverable via capsule instead);
        lifecycle events are refused (a relay holds no trust authority).
        """
        from ..exchange import validate_for_exchange
        from ..models import EVENT_KIND as _EVENT_KIND

        if not isinstance(record, Mapping):
            raise MeshError("INVALID_RECORD", "record must be an object")
        if record.get("kind") == _EVENT_KIND:
            raise MeshError("RELAY_NO_AUTHORITY", "relay never retains lifecycle events")
        try:
            validate_for_exchange(record)
        except Exception as error:
            raise MeshError("INVALID_RECORD", f"relay refuses invalid record: {error}") from error
        identity = record.get("contentDigest")
        if not isinstance(identity, str) or not identity:
            raise MeshError("INVALID_RECORD", "record needs a contentDigest")
        try:
            encoded = canonical_json(dict(record))
        except (TypeError, ValueError) as error:
            raise MeshError("INVALID_RECORD", f"record is not encodable: {error}") from error
        if len(encoded) > 256 * 1024:
            raise MeshError(
                "RECORD_TOO_LARGE",
                "relay retains compact records only; use a capsule for discovery",
            )
        records = self._load(self._records_path)
        if identity not in records and len(records) >= MAX_CAPSULES:
            raise MeshError("RELAY_FULL", "relay record table is at its bound")
        records[identity] = {"record": dict(record), "offeredAt": _now()}
        self._save(self._records_path, records)
        return {"relayVersion": RELAY_VERSION, "retained": identity}

    # -- capsules (discovery envelopes) --------------------------------------
    def publish_capsule(
        self, capsule: Mapping[str, Any], *, locations: Mapping[str, str] | None = None
    ) -> dict[str, object]:
        """Retain a compact capsule; capsules never carry lifecycle authority."""
        if not isinstance(capsule, Mapping):
            raise MeshError("INVALID_CAPSULE", "capsule must be an object")
        identity = capsule.get("identity")
        if not isinstance(identity, str) or not identity:
            raise MeshError("INVALID_CAPSULE", "capsule needs an identity")
        try:
            encoded = canonical_json(dict(capsule))
        except (TypeError, ValueError) as error:
            raise MeshError("INVALID_CAPSULE", f"capsule is not encodable: {error}") from error
        if len(encoded) > 256 * 1024:
            raise MeshError("CAPSULE_TOO_LARGE", "relay retains compact capsules only")
        capsules = self._load(self._capsules_path)
        if identity not in capsules and len(capsules) >= MAX_CAPSULES:
            raise MeshError("RELAY_FULL", "relay capsule table is at its bound")
        capsules[identity] = {"capsule": dict(capsule), "publishedAt": _now()}
        self._save(self._capsules_path, capsules)
        if locations:
            known = self._load(self._locations_path)
            entry = known.get(identity)
            if not isinstance(entry, dict):
                entry = {}
            for evidence_id, location in locations.items():
                if isinstance(evidence_id, str) and isinstance(location, str):
                    entry[evidence_id] = location[:256]
            known[identity] = dict(list(entry.items())[:MAX_LOCATIONS_PER_DIGEST])
            self._save(self._locations_path, known)
        return {"relayVersion": RELAY_VERSION, "retained": identity}

    def locate(self, digest: str) -> dict[str, object]:
        capsules = self._load(self._capsules_path)
        locations = self._load(self._locations_path)
        entry = locations.get(digest)
        return {
            "relayVersion": RELAY_VERSION,
            "identity": digest,
            "retained": digest in capsules,
            "evidenceLocations": dict(entry) if isinstance(entry, dict) else {},
            "authority": "location-hint only; availability is a claim, not custody",
        }

    def frontier(self) -> frozenset[str]:
        records = self._load(self._records_path)
        capsules = self._load(self._capsules_path)
        return frozenset((*records.keys(), *capsules.keys()))

    def fetch(self, digests: list[str], *, limit: int = 1_000) -> list[Mapping[str, Any]]:
        records = self._load(self._records_path)
        wanted = set(digests[:limit])
        found: list[Mapping[str, Any]] = []
        for digest in sorted(wanted):
            entry = records.get(digest)
            if isinstance(entry, dict) and isinstance(entry.get("record"), dict):
                found.append(dict(entry["record"]))
        return found[:limit]

    def pull(
        self, interest: InterestFilter | None = None, *, limit: int = 1_000
    ) -> list[Mapping[str, Any]]:
        """Pull capsules matching an interest projection (bounded)."""
        capsules = self._load(self._capsules_path)
        selected: list[Mapping[str, Any]] = []
        for digest in sorted(capsules):
            entry = capsules[digest]
            if not isinstance(entry, dict) or not isinstance(entry.get("capsule"), dict):
                continue
            capsule = entry["capsule"]
            if interest is not None:
                pseudo = {
                    "kind": capsule.get("recordKind"),
                    "contentDigest": digest,
                    "scope": capsule.get("scope", {}),
                    "subject": capsule.get("subject", {}),
                    "affectedContracts": [],
                    "provenance": {"producer": capsule.get("producer", {})},
                    "evidence": [],
                    "relationships": capsule.get("relationships", []),
                    "metadata": {"labels": []},
                }
                if not matches(pseudo, interest):
                    continue
            selected.append(dict(capsule))
            if len(selected) >= limit:
                break
        return selected
