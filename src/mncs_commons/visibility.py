"""Non-authoritative local serving visibility overlay.

Visibility is deployment policy, not record lifecycle, truth, or deletion.  It
is intentionally operator-only and is never accepted from remote clients.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .canonical import canonical_json


class VisibilityPolicy:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._withheld: dict[str, str] = {}
        if self.path is not None and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        raw = self.path.read_bytes()
        if len(raw) > 256 * 1024:
            raise ValueError("visibility policy exceeds bounded size")
        value = json.loads(raw.decode("utf-8"))
        withheld = value.get("withheld", {}) if isinstance(value, dict) else None
        if not isinstance(withheld, dict):
            raise ValueError("visibility policy withheld must be an object")
        self._withheld = {
            str(digest): str(reason)[:512]
            for digest, reason in withheld.items()
            if isinstance(digest, str) and isinstance(reason, str)
        }

    def is_visible(self, digest: str) -> bool:
        return digest not in self._withheld

    def reason(self, digest: str) -> str | None:
        return self._withheld.get(digest)

    def entries(self) -> dict[str, str]:
        return dict(sorted(self._withheld.items()))

    def set_withheld(self, digest: str, reason: str) -> None:
        if not digest.startswith("sha256:") or len(digest) > 128:
            raise ValueError("visibility digest must be a bounded sha256 identity")
        self._withheld[digest] = reason[:512]
        self.save()

    def clear(self, digest: str) -> None:
        self._withheld.pop(digest, None)
        self.save()

    def save(self) -> None:
        if self.path is None:
            raise ValueError("visibility policy has no configured path")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_json({"version": 1, "withheld": self.entries()})
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
