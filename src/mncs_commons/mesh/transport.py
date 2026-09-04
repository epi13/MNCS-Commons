"""Transport neutrality: carriers move bytes, never meaning.

The mesh sync protocol (frontiers -> missing/wanted -> bounded transfer ->
projection update) runs over any ``Carrier``:

.. code-block:: text

    Commons Exchange
       |-- DirectCarrier   (in-process / local IPC model)
       |-- BundleCarrier   (offline bundle/file transfer)
       |-- RelayCarrier    (optional relay-assisted)
       |-- HttpCarrier     (direct peer HTTPS; explicit, bounded)
       `-- FabricCarrier   (optional MNCS-native carrier)

Transport mechanics never redefine record semantics: every record arriving
over any carrier passes the same validation and lands as possession-only
knowledge.  Fabric is a preferred MNCS-native carrier where both peers
have it; no mesh path requires it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from ..bundle import create_bundle, import_bundle
from ..canonical import canonical_json
from .errors import MeshError
from .interest import InterestFilter

if TYPE_CHECKING:
    from .node import CommonsNode
    from .relay import CommonsRelay

MAX_CARRIER_RECORDS = 1_000


class Carrier(ABC):
    """One side of a bounded record transfer."""

    name: str = "abstract"

    @property
    def source_label(self) -> str:
        """Possession-provenance label recorded as ``foreign:<label>``."""
        return self.name

    @abstractmethod
    def fetch_frontier(self) -> frozenset[str]:
        """Remote possession frontier (identities only, never evidence)."""

    @abstractmethod
    def fetch_records(
        self, digests: list[str], *, limit: int = MAX_CARRIER_RECORDS
    ) -> list[Mapping[str, Any]]:
        """Fetch named records, bounded; unknown digests are skipped."""

    def offer_records(
        self, records: list[Mapping[str, Any]], *, source: str
    ) -> Mapping[str, object]:
        raise MeshError("TRANSPORT_READ_ONLY", f"{self.name} carrier does not accept offers")


class DirectCarrier(Carrier):
    """In-process carrier around a peer node (local IPC model)."""

    name = "direct"

    def __init__(self, peer: "CommonsNode") -> None:
        self._peer = peer

    @property
    def source_label(self) -> str:
        return self._peer.node_id

    def fetch_frontier(self) -> frozenset[str]:
        return self._peer.frontier()

    def fetch_records(
        self, digests: list[str], *, limit: int = MAX_CARRIER_RECORDS
    ) -> list[Mapping[str, Any]]:
        wanted = set(digests[:limit])
        return [
            record
            for record in self._peer.store.records()
            if str(record.get("contentDigest")) in wanted
        ][:limit]

    def offer_records(
        self, records: list[Mapping[str, Any]], *, source: str
    ) -> Mapping[str, object]:
        report = self._peer.receive_records(records, source=source)
        return report.as_dict()


class BundleCarrier(Carrier):
    """Offline carrier: an exported bundle file (sneakernet / air-gap)."""

    name = "bundle"

    def __init__(self, bundle_path: Path | str) -> None:
        self.bundle_path = Path(bundle_path)

    @classmethod
    def export(
        cls,
        node: "CommonsNode",
        digests: list[str],
        path: Path | str,
    ) -> "BundleCarrier":
        """Export named records as a depth-0 bundle (selective offline transfer).

        Interest filtering is applied by the receiver's ingest gate, so the
        bundle stays a deterministic function of the requested identities.
        """

        create_bundle(node.store, Path(path), roots=digests[:MAX_CARRIER_RECORDS], max_depth=0)
        return cls(path)

    def fetch_frontier(self) -> frozenset[str]:
        from ..bundle import verify_bundle

        report = verify_bundle(self.bundle_path)
        if not report.valid or report.manifest is None:
            raise MeshError("BUNDLE_UNREADABLE", "bundle carrier cannot read its manifest")
        members = report.manifest.get("members", [])
        return frozenset(
            str(item.get("contentDigest"))
            for item in members
            if isinstance(item, Mapping) and item.get("contentDigest")
        )

    def fetch_records(
        self, digests: list[str], *, limit: int = MAX_CARRIER_RECORDS
    ) -> list[Mapping[str, Any]]:
        import tempfile

        from ..store import CommonsStore

        wanted = set(digests[:limit])
        with tempfile.TemporaryDirectory(prefix="mesh-bundle-") as staging:
            staging_store = CommonsStore(Path(staging) / "store")
            staging_store.init()
            verification = import_bundle(self.bundle_path, staging_store)
            if not verification.valid:
                raise MeshError("BUNDLE_UNREADABLE", "bundle carrier cannot import its bundle")
            return [
                record
                for record in staging_store.records()
                if str(record.get("contentDigest")) in wanted
            ][:limit]


class RelayCarrier(Carrier):
    """Relay-assisted carrier: pull compact records through an optional relay."""

    name = "relay"

    def __init__(self, relay: "CommonsRelay", *, interest: InterestFilter | None = None) -> None:
        self._relay = relay
        self._interest = interest

    def fetch_frontier(self) -> frozenset[str]:
        return self._relay.frontier()

    def fetch_records(
        self, digests: list[str], *, limit: int = MAX_CARRIER_RECORDS
    ) -> list[Mapping[str, Any]]:
        wanted = set(digests[:limit])
        return self._relay.fetch(list(wanted), limit=limit)

    def offer_records(
        self, records: list[Mapping[str, Any]], *, source: str
    ) -> Mapping[str, object]:
        from .errors import MeshError as _MeshError

        retained = 0
        refused: list[str] = []
        for record in records[:MAX_CARRIER_RECORDS]:
            try:
                self._relay.offer_record(record)
                retained += 1
            except _MeshError as error:
                refused.append(error.code)
        return {"carrier": self.name, "retained": retained, "refused": refused[:32]}


class FabricCarrier(Carrier):
    """Optional Fabric-backed carrier.

    Fabric may provide authenticated transport, enrollment, endpoint
    reachability, framing, replay protection, routing, and resource-bounded
    transport.  It never decides correctness, acceptance, independence,
    conformance, or promotion.  Constructing this carrier without a Fabric
    runtime raises a bounded, machine-readable error -- mesh sync must
    never implicitly require Fabric.
    """

    name = "fabric"

    def __init__(self, endpoint: str) -> None:
        try:
            import mncs_fabric  # type: ignore[import-not-found, import-untyped]  # noqa: F401
        except ImportError as error:
            raise MeshError(
                "TRANSPORT_UNAVAILABLE",
                "fabric carrier requested but no Fabric runtime is installed; "
                "use direct, bundle, or relay transport instead",
            ) from error
        if not endpoint or len(endpoint) > 1024:
            raise MeshError("INVALID_ENDPOINT", "fabric endpoint must be a bounded string")
        self.endpoint = endpoint

    def fetch_frontier(self) -> frozenset[str]:
        raise MeshError("TRANSPORT_UNBOUND", "fabric carrier endpoint is not bound in this profile")

    def fetch_records(
        self, digests: list[str], *, limit: int = MAX_CARRIER_RECORDS
    ) -> list[Mapping[str, Any]]:
        raise MeshError("TRANSPORT_UNBOUND", "fabric carrier endpoint is not bound in this profile")


def synchronize(
    local: "CommonsNode",
    carrier: Carrier,
    *,
    interest: InterestFilter | None = None,
    push_interest: InterestFilter | None = None,
    limit: int | None = None,
    push: bool = True,
) -> Mapping[str, object]:
    """Run one bounded pull (+ optional push) sync round over any carrier.

    Pull: fetch the remote frontier, compute locally-missing identities,
    fetch them bounded, ingest through the node's interest gate.
    Push: offer locally-held records the remote lacks (only carriers that
    accept offers; read-only carriers report ``pushSkipped``).
    """

    from .node import MAX_SYNC_RECORDS, SyncReport

    interest = interest or InterestFilter.match_all()
    bound = min(limit if limit is not None else MAX_SYNC_RECORDS, MAX_SYNC_RECORDS)
    remote_frontier = set(carrier.fetch_frontier())
    local_frontier = set(local.frontier())
    missing = sorted(remote_frontier - local_frontier)[:bound]
    offered = len(missing)
    fetched = carrier.fetch_records(missing, limit=bound) if missing else []
    pull_report = local.receive_records(fetched, source=carrier.source_label, interest=interest)

    push_report: SyncReport | None = None
    push_skipped: str | None = None
    if push:
        outgoing = local.select_for_peer(
            remote_frontier, push_interest or InterestFilter.match_all(), limit=bound
        )
        try:
            carrier.offer_records(outgoing, source=local.node_id)
            push_report = SyncReport(
                peer=carrier.name,
                offered=len(outgoing),
                received=0,
                sent=len(outgoing),
                duplicates=0,
                skipped_by_interest=0,
                skipped_by_policy=0,
                bytes_received=0,
                bytes_sent=sum(len(canonical_json(item)) for item in outgoing),
            )
        except MeshError as error:
            push_skipped = error.code
    return {
        "meshVersion": local.describe()["nodeDescriptorVersion"],
        "carrier": carrier.name,
        "pull": pull_report.as_dict(),
        "push": push_report.as_dict() if push_report is not None else {"pushSkipped": push_skipped},
        "offered": offered,
    }
