"""Small canonical operation registry shared by exchange bindings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    read_only: bool
    store_required: bool
    public_allowed: bool
    bounded: bool
    max_response_bytes: int
    bindings: tuple[str, ...] = ("python-api", "cli", "stdio-mcp", "http")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "readOnly": self.read_only,
            "storeRequired": self.store_required,
            "publicAllowed": self.public_allowed,
            "bounded": self.bounded,
            "maxResponseBytes": self.max_response_bytes,
            "bindings": list(self.bindings),
        }


_OPERATIONS = (
    OperationSpec("commons.describe", True, False, True, True, 128 * 1024),
    OperationSpec("record.validate", True, False, True, True, 128 * 1024),
    OperationSpec("record.publish", False, True, True, True, 128 * 1024),
    OperationSpec("record.get", True, True, True, True, 4 * 1024 * 1024),
    OperationSpec("records.query", True, True, True, True, 4 * 1024 * 1024),
    OperationSpec("records.sync", True, True, True, True, 4 * 1024 * 1024),
    OperationSpec("conversation.get", True, True, True, True, 4 * 1024 * 1024),
    OperationSpec("experiment.get", True, True, True, True, 4 * 1024 * 1024),
    OperationSpec("work.list", True, True, True, True, 2 * 1024 * 1024),
    OperationSpec("work.next", True, True, True, True, 2 * 1024 * 1024),
    OperationSpec("work.policy", True, False, True, True, 512 * 1024),
    OperationSpec("work.scope-check", True, False, True, True, 512 * 1024),
    OperationSpec("family.registry", True, False, True, True, 512 * 1024),
    OperationSpec("family.coverage", True, True, True, True, 2 * 1024 * 1024),
    OperationSpec("family.consistency", True, False, True, True, 2 * 1024 * 1024),
    OperationSpec("work.propose", False, True, False, True, 512 * 1024),
    OperationSpec("family.health-sweep", False, True, False, True, 4 * 1024 * 1024),
    OperationSpec(
        "work.claim",
        False,
        True,
        False,
        True,
        512 * 1024,
        ("python-api", "cli", "stdio-mcp", "http"),
    ),
    OperationSpec("lifecycle.get", True, True, True, True, 512 * 1024, ("python-api", "cli")),
    OperationSpec("lifecycle.domains", True, True, True, True, 512 * 1024, ("python-api", "cli")),
    OperationSpec("evidence.trace", True, True, True, True, 4 * 1024 * 1024),
    OperationSpec("bundle.verify", True, False, True, True, 512 * 1024, ("python-api", "cli")),
)


def operations() -> tuple[OperationSpec, ...]:
    return _OPERATIONS


def operations_for(binding: str) -> tuple[OperationSpec, ...]:
    """Return the canonical operation set exposed by one interface binding."""

    return tuple(item for item in _OPERATIONS if binding in item.bindings)


def operation(name: str) -> OperationSpec | None:
    return next((item for item in _OPERATIONS if item.name == name), None)
