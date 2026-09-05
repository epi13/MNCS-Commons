"""Commons Node: the first-class unit of the Commons Mesh.

Every participating MNCS environment owns a local Commons node.  The node is
authoritative only for its own possession and observations:

.. code-block:: text

    record identity != record possession != record delivery
        != transport authentication != producer identity
        != technical correctness != independent verification
        != MNCS conformance != MNCS promotion != governance acceptance

A node receiving a record learns that the record exists.  Nothing more.
Delivery never promotes into correctness: foreign records land as
``proposed`` with origin ``foreign:<source>``, lifecycle evaluation stays
per-domain, and no lifecycle event is ever synthesized on ingest.

Convergence (the precise invariant tested in ``tests/test_mesh_*.py``):

    Given two nodes with compatible policies, continued opportunity to
    exchange, and no permanent withholding of records matching the
    recipient's requested projection, both nodes eventually possess the
    same set of relevant immutable record identities.

Local trust, acceptance, retention, derived views, and evidence possession
may legitimately remain different after convergence.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .. import __version__ as _commons_version
from ..canonical import canonical_digest, canonical_json
from ..exchange import (
    EXCHANGE_VERSION,
    ExchangeError,
    ExchangePolicy,
    ParticipantDescriptor,
    validate_for_exchange,
)
from ..models import EVENT_KIND, RecordKind, RelationType
from ..store import CommonsStore
from ..vocabulary import vocabulary
from .availability import (
    AVAILABILITY_VERSION,
    EvidenceAvailability,
)
from .capsule import CAPSULE_VERSION
from .errors import MeshError
from .executor import MncsKernelExecutor, decide_membership
from .interest import INTEREST_VERSION, InterestFilter, matches

MESH_VERSION = "commons.mncs.dev/mesh/v0alpha1"
NODE_PROFILE = "commons.mncs.dev/node/mesh/v0alpha1"

# Sync modes a node may advertise.  Only "direct" and "bundle" are realized
# in-process; the rest are negotiated capabilities that require an explicit
# carrier at sync time and degrade to bounded errors when unavailable.
SYNC_MODES = ("direct", "bundle", "relay", "http", "fabric")
TRANSPORTS = ("local-ipc", "bundle-file", "http", "fabric", "direct-peer")

MAX_NODE_ID_LENGTH = 256
MAX_DOMAIN_LENGTH = 256
MAX_PEERS = 256
MAX_CAS_BLOB_BYTES = 64 * 1024 * 1024
MAX_SYNC_RECORDS = 1_000

_ORIGIN_LOCAL = "local"


def _bounded_id(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise MeshError("INVALID_NODE", f"{name} must be a bounded non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class MeshPolicy:
    """Local node policy: possession budgets, never foreign obligations."""

    max_record_bytes: int = 1024 * 1024
    max_sync_records: int = MAX_SYNC_RECORDS
    max_cas_blob_bytes: int = MAX_CAS_BLOB_BYTES
    max_relationships: int = 256
    max_evidence: int = 256
    hot_byte_budget: int = 256 * 1024 * 1024
    foreign_evidence_budget: int = 64 * 1024 * 1024

    def as_dict(self) -> dict[str, object]:
        return {
            "maxRecordBytes": self.max_record_bytes,
            "maxSyncRecords": self.max_sync_records,
            "maxCasBlobBytes": self.max_cas_blob_bytes,
            "maxRelationships": self.max_relationships,
            "maxEvidence": self.max_evidence,
            "hotByteBudget": self.hot_byte_budget,
            "foreignEvidenceBudget": self.foreign_evidence_budget,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "MeshPolicy":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise MeshError("INVALID_NODE", "mesh policy must be an object")
        result = {}
        for key, attr in (
            ("maxRecordBytes", "max_record_bytes"),
            ("maxSyncRecords", "max_sync_records"),
            ("maxCasBlobBytes", "max_cas_blob_bytes"),
            ("maxRelationships", "max_relationships"),
            ("maxEvidence", "max_evidence"),
            ("hotByteBudget", "hot_byte_budget"),
            ("foreignEvidenceBudget", "foreign_evidence_budget"),
        ):
            raw = value.get(key)
            if raw is None:
                continue
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
                raise MeshError("INVALID_NODE", f"{key} must be a positive integer")
            result[attr] = raw
        return cls(**result)


@dataclass(frozen=True, slots=True)
class NodeDescriptor:
    """Advertised mesh capabilities for protocol negotiation."""

    node_id: str
    domain: str = "local"
    implementation: str = "mncs-commons"
    implementation_version: str = _commons_version
    exchange_versions: tuple[str, ...] = (EXCHANGE_VERSION,)
    record_kinds: tuple[str, ...] = tuple(sorted(item.value for item in RecordKind))
    relationship_vocabulary: tuple[str, ...] = tuple(sorted(item.value for item in RelationType))
    sync_modes: tuple[str, ...] = ("direct", "bundle")
    transports: tuple[str, ...] = ("local-ipc", "bundle-file", "direct-peer")
    roles: tuple[str, ...] = ()
    identity_assurance: str = "SELF_ASSERTED"
    policy: MeshPolicy = field(default_factory=MeshPolicy)

    def as_dict(self) -> dict[str, object]:
        return {
            "nodeDescriptorVersion": MESH_VERSION,
            "nodeProfile": NODE_PROFILE,
            "nodeId": self.node_id,
            "domain": self.domain,
            "implementation": {
                "name": self.implementation,
                "version": self.implementation_version,
            },
            "exchangeVersions": list(self.exchange_versions),
            "meshVersion": MESH_VERSION,
            "interestVersion": INTEREST_VERSION,
            "availabilityVersion": AVAILABILITY_VERSION,
            "capsuleVersion": CAPSULE_VERSION,
            "recordKinds": list(self.record_kinds),
            "relationshipVocabulary": list(self.relationship_vocabulary),
            "vocabularyVersion": vocabulary()["vocabularyVersion"],
            "syncModes": list(self.sync_modes),
            "transports": list(self.transports),
            "roles": list(self.roles),
            "identityAssurance": self.identity_assurance,
            "retention": dict(self.policy.as_dict()),
            "contentLimits": {
                "maxRecordBytes": self.policy.max_record_bytes,
                "maxSyncRecords": self.policy.max_sync_records,
                "maxCasBlobBytes": self.policy.max_cas_blob_bytes,
            },
            "authority": "possession-only; no correctness, conformance, or promotion",
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NodeDescriptor":
        if not isinstance(value, Mapping):
            raise MeshError("INVALID_NODE", "node descriptor must be an object")
        node_id = _bounded_id(value.get("nodeId"), "nodeId", MAX_NODE_ID_LENGTH)
        domain = value.get("domain", "local")
        if not isinstance(domain, str) or len(domain) > MAX_DOMAIN_LENGTH:
            raise MeshError("INVALID_NODE", "domain must be a bounded string")

        def _string_list(key: str, allowed: tuple[str, ...] | None = None) -> tuple[str, ...]:
            raw = value.get(key, ())
            if raw is None:
                return ()
            if not isinstance(raw, (list, tuple)):
                raise MeshError("INVALID_NODE", f"{key} must be a list")
            items = tuple(str(item) for item in raw)
            if len(items) > 256 or any(len(item) > 256 or not item for item in items):
                raise MeshError("INVALID_NODE", f"{key} entries must be bounded strings")
            if allowed is not None:
                unknown = [item for item in items if item not in allowed]
                if unknown:
                    raise MeshError(
                        "UNKNOWN_NODE_VOCABULARY",
                        f"{key} carries unsupported entries: {','.join(sorted(unknown))}",
                    )
            return tuple(sorted(set(items)))

        return cls(
            node_id=node_id,
            domain=domain,
            implementation=str(value.get("implementation", {}).get("name", "unknown"))
            if isinstance(value.get("implementation"), Mapping)
            else "unknown",
            exchange_versions=_string_list("exchangeVersions") or (EXCHANGE_VERSION,),
            record_kinds=_string_list("recordKinds")
            or tuple(sorted(item.value for item in RecordKind)),
            relationship_vocabulary=_string_list("relationshipVocabulary")
            or tuple(sorted(item.value for item in RelationType)),
            sync_modes=_string_list("syncModes", SYNC_MODES) or ("direct",),
            transports=_string_list("transports", TRANSPORTS) or ("direct-peer",),
            roles=_string_list("roles"),
            identity_assurance=str(value.get("identityAssurance", "SELF_ASSERTED")),
            policy=MeshPolicy.from_mapping(value.get("retention")),
        )


def negotiate(local: NodeDescriptor, remote: Mapping[str, Any]) -> dict[str, object]:
    """Negotiate a bounded exchange agreement; unknown vocabulary stays inert.

    Returns the agreed sync modes (local preference order), the agreed
    record kinds, the binding content limit (minimum of both maxima), and
    version agreement flags.  Anything the local node does not understand
    is reported under ``inert`` and never acted on.
    """

    peer = NodeDescriptor.from_mapping(remote)
    agreed_modes = [mode for mode in local.sync_modes if mode in peer.sync_modes]
    agreed_kinds = sorted(set(local.record_kinds) & set(peer.record_kinds))
    inert_relationships = sorted(
        set(peer.relationship_vocabulary) - set(local.relationship_vocabulary)
    )
    return {
        "meshVersion": MESH_VERSION,
        "agreedSyncModes": agreed_modes,
        "agreedRecordKinds": agreed_kinds,
        "inertRelationships": inert_relationships,
        "bindingMaxRecordBytes": min(local.policy.max_record_bytes, peer.policy.max_record_bytes),
        "versions": {
            "interest": (INTEREST_VERSION, remote.get("interestVersion")),
            "availability": (AVAILABILITY_VERSION, remote.get("availabilityVersion")),
            "capsule": (CAPSULE_VERSION, remote.get("capsuleVersion")),
        },
        "canExchange": bool(agreed_modes and agreed_kinds),
    }


@dataclass(frozen=True, slots=True)
class PossessionReceipt:
    origin: str
    content_digest: str
    duplicate: bool
    domain: str

    def as_dict(self) -> dict[str, object]:
        return {
            "meshVersion": MESH_VERSION,
            "origin": self.origin,
            "contentDigest": self.content_digest,
            "duplicate": self.duplicate,
            "domain": self.domain,
            "acceptanceStatus": "UNCHANGED",
            "technicalAuthority": "NONE_GRANTED",
            "meaning": "this node knows the record exists; nothing more",
        }


@dataclass(frozen=True, slots=True)
class SyncReport:
    peer: str
    offered: int
    received: int
    sent: int
    duplicates: int
    skipped_by_interest: int
    skipped_by_policy: int
    bytes_received: int
    bytes_sent: int
    diagnostics: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "meshVersion": MESH_VERSION,
            "peer": self.peer,
            "offered": self.offered,
            "received": self.received,
            "sent": self.sent,
            "duplicates": self.duplicates,
            "skippedByInterest": self.skipped_by_interest,
            "skippedByPolicy": self.skipped_by_policy,
            "bytesReceived": self.bytes_received,
            "bytesSent": self.bytes_sent,
            "diagnostics": list(self.diagnostics),
        }


class CommonsNode:
    """A local Commons node: owns possession, cursors, CAS, and policy."""

    def __init__(
        self,
        root: Path | str,
        *,
        node_id: str,
        domain: str = "local",
        policy: MeshPolicy | None = None,
    ) -> None:
        self.root = Path(root)
        self.node_id = _bounded_id(node_id, "nodeId", MAX_NODE_ID_LENGTH)
        self.domain = _bounded_id(domain or "local", "domain", MAX_DOMAIN_LENGTH)
        self.policy = policy or MeshPolicy()
        self.store = CommonsStore(self.root / "store")
        self.cas_path = self.root / "cas"
        self._state_path = self.root / "mesh-state.json"

    # -- lifecycle ------------------------------------------------------
    def init(self) -> None:
        self.store.init()
        self.cas_path.mkdir(parents=True, exist_ok=True)
        if not self._state_path.exists():
            self._write_state({"nodeId": self.node_id, "peers": {}, "origins": {}})

    def _read_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise MeshError(
                "MESH_STATE_UNREADABLE", f"mesh state is unreadable: {error}"
            ) from error
        if not isinstance(state, dict):
            raise MeshError("MESH_STATE_INVALID", "mesh state must be an object")
        return state

    def _write_state(self, state: Mapping[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(self._state_path)

    def _mark_origin(self, digest: str, origin: str) -> None:
        state = self._read_state()
        origins = state.get("origins")
        if not isinstance(origins, dict):
            origins = {}
        origins[digest] = origin
        state["origins"] = origins
        self._write_state(state)

    def origin_of(self, digest: str) -> str | None:
        state = self._read_state()
        origins = state.get("origins")
        if isinstance(origins, dict):
            origin = origins.get(digest)
            return str(origin) if isinstance(origin, str) else None
        return None

    # -- identity -------------------------------------------------------
    def describe(self) -> dict[str, object]:
        return NodeDescriptor(
            node_id=self.node_id,
            domain=self.domain,
            policy=self.policy,
        ).as_dict()

    # -- publish / ingest -----------------------------------------------
    def publish_local(
        self,
        record: Mapping[str, Any],
        *,
        participant: ParticipantDescriptor | None = None,
    ) -> PossessionReceipt:
        """Validate and append a locally produced record (origin ``local``)."""
        policy = ExchangePolicy(
            max_record_bytes=self.policy.max_record_bytes,
            max_relationships=self.policy.max_relationships,
            max_evidence=self.policy.max_evidence,
        )
        try:
            validate_for_exchange(record, policy)
        except ExchangeError as error:
            raise MeshError(error.code, error.message) from error
        stored = self.store.add_record(dict(record))
        self._mark_origin(stored.content_digest, _ORIGIN_LOCAL)
        return PossessionReceipt(_ORIGIN_LOCAL, stored.content_digest, False, self.domain)

    def ingest_foreign(self, record: Mapping[str, Any], *, source: str) -> PossessionReceipt:
        """Ingest a foreign record as possession-only knowledge.

        The record is validated and stored when new.  No lifecycle event is
        created, no acceptance changes, and the origin marker records where
        the bytes were learned from.  Delivery is not correctness.
        """
        origin = f"foreign:{_bounded_id(source, 'source', MAX_NODE_ID_LENGTH)}"
        policy = ExchangePolicy(
            max_record_bytes=self.policy.max_record_bytes,
            max_relationships=self.policy.max_relationships,
            max_evidence=self.policy.max_evidence,
        )
        try:
            validate_for_exchange(record, policy)
        except ExchangeError as error:
            raise MeshError(error.code, error.message) from error
        digest = canonical_digest(record)
        if self.store.get(digest) is not None:
            return PossessionReceipt(origin, digest, True, self.domain)
        stored = self.store.add_record(dict(record))
        self._mark_origin(stored.content_digest, origin)
        return PossessionReceipt(origin, stored.content_digest, False, self.domain)

    # -- frontiers ------------------------------------------------------
    def frontier(self) -> frozenset[str]:
        """Local possession frontier: every immutable record/event identity."""
        digests = set()
        for item in (*self.store.records(), *self.store.events()):
            digest = item.get("contentDigest")
            if isinstance(digest, str) and digest:
                digests.add(digest)
        return frozenset(digests)

    def missing_against(self, remote_frontier: set[str] | frozenset[str]) -> list[str]:
        """Identities the remote holds that this node lacks (deterministic)."""
        return sorted(set(remote_frontier) - set(self.frontier()))

    def get_record(self, digest: str) -> Mapping[str, Any] | None:
        return self.store.get(digest)

    # -- local CAS (lazy evidence) --------------------------------------
    def cas_put(self, data: bytes, *, media_type: str = "application/octet-stream") -> str:
        if len(data) > self.policy.max_cas_blob_bytes:
            raise MeshError("EVIDENCE_TOO_LARGE", "evidence blob exceeds the node CAS limit")
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        path = self.cas_path / (digest.replace(":", "_") + ".blob")
        self.cas_path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        meta = path.with_suffix(".json")
        if not meta.exists():
            meta.write_text(
                json.dumps({"digest": digest, "mediaType": media_type, "bytes": len(data)}),
                encoding="utf-8",
            )
        return digest

    def cas_has(self, digest: str) -> bool:
        return (self.cas_path / (digest.replace(":", "_") + ".blob")).exists()

    def cas_get(self, digest: str) -> bytes | None:
        path = self.cas_path / (digest.replace(":", "_") + ".blob")
        try:
            return path.read_bytes()
        except OSError:
            return None

    def evidence_availability(self, evidence_id: str) -> EvidenceAvailability:
        if self.cas_has(evidence_id):
            return EvidenceAvailability.LOCAL
        return EvidenceAvailability.UNAVAILABLE

    # -- peer state ------------------------------------------------------
    def note_peer_frontier(self, peer_id: str, frontier_digests: set[str]) -> None:
        peer = _bounded_id(peer_id, "peerId", MAX_NODE_ID_LENGTH)
        state = self._read_state()
        peers = state.get("peers")
        if not isinstance(peers, dict):
            peers = {}
        if len(peers) >= MAX_PEERS and peer not in peers:
            raise MeshError("TOO_MANY_PEERS", "peer table is at its bound")
        peers[peer] = {
            "frontier": sorted(frontier_digests)[:10_000],
            "notedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        state["peers"] = peers
        self._write_state(state)

    # -- sync ------------------------------------------------------------
    def select_for_peer(
        self,
        remote_frontier: set[str] | frozenset[str],
        interest: InterestFilter,
        *,
        limit: int | None = None,
        executor: MncsKernelExecutor | None = None,
    ) -> list[Mapping[str, Any]]:
        """Records this node holds that the peer lacks, filtered by interest.

        With ``executor`` (and an available toolchain), membership runs
        batched through the normative ``candidate_matches_full`` kernel;
        otherwise the pinned Python mirror decides.  Both lanes implement
        the identical law.
        """
        bound = min(limit if limit is not None else self.policy.max_sync_records, MAX_SYNC_RECORDS)
        wanted = sorted(set(self.frontier()) - set(remote_frontier))
        candidates = []
        for digest in wanted:
            record = self.store.get(digest)
            if record is None or record.get("kind") == EVENT_KIND:
                continue
            state = None
            try:
                state = str(self.store.lifecycle(digest, self.domain).current_state)
            except Exception:
                state = None
            candidates.append((record, state))
        if executor is not None and executor.available:
            verdicts = decide_membership(
                executor, [(record, interest, state) for record, state in candidates]
            )
            return [record for (record, _), keep in zip(candidates, verdicts, strict=True) if keep][
                :bound
            ]
        selected = []
        for record, state in candidates:
            if matches(record, interest, lifecycle_state=state):
                selected.append(record)
            if len(selected) >= bound:
                break
        return selected

    def receive_records(
        self,
        records: list[Mapping[str, Any]],
        *,
        source: str,
        interest: InterestFilter | None = None,
        executor: MncsKernelExecutor | None = None,
    ) -> SyncReport:
        """Ingest an offered batch: interest-filtered, bounded, possession-only.

        With ``executor`` (and an available toolchain), the interest gate
        runs batched through the normative kernel; otherwise the pinned
        Python mirror decides.  Both lanes implement the identical law.
        """
        use_kernel = interest is not None and executor is not None and executor.available
        kernel_verdicts: dict[int, bool] = {}
        if use_kernel:
            assert interest is not None
            assert executor is not None
            # Non-mappings never reach the gate (policy-skipped first); they
            # still occupy a batch slot so verdict indices stay aligned.
            kernel_verdicts = dict(
                enumerate(
                    decide_membership(
                        executor,
                        [
                            (record if isinstance(record, Mapping) else {}, interest, None)
                            for record in records
                        ],
                    )
                )
            )
        received = 0
        duplicates = 0
        skipped_interest = 0
        skipped_policy = 0
        bytes_received = 0
        diagnostics: list[str] = []
        for index, record in enumerate(records[: self.policy.max_sync_records]):
            if not isinstance(record, Mapping):
                skipped_policy += 1
                diagnostics.append("NON_RECORD_SKIPPED")
                continue
            try:
                encoded = canonical_json(record)
            except (TypeError, ValueError):
                skipped_policy += 1
                diagnostics.append("UNENCODABLE_RECORD_SKIPPED")
                continue
            if len(encoded) > self.policy.max_record_bytes:
                skipped_policy += 1
                diagnostics.append("OVERSIZE_RECORD_SKIPPED")
                continue
            if interest is not None:
                if use_kernel:
                    gated = not kernel_verdicts.get(index, False)
                else:
                    gated = not matches(record, interest)
                if gated:
                    skipped_interest += 1
                    continue
            try:
                receipt = self.ingest_foreign(record, source=source)
            except MeshError as error:
                skipped_policy += 1
                diagnostics.append(error.code)
                continue
            bytes_received += len(encoded)
            if receipt.duplicate:
                duplicates += 1
            else:
                received += 1
        return SyncReport(
            peer=source,
            offered=len(records),
            received=received,
            sent=0,
            duplicates=duplicates,
            skipped_by_interest=skipped_interest,
            skipped_by_policy=skipped_policy,
            bytes_received=bytes_received,
            bytes_sent=0,
            diagnostics=tuple(diagnostics[:32]),
        )
