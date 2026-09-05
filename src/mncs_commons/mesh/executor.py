"""Batch execution of normative MNCS kernels through the host toolchain.

The ``.mncs`` kernels own mesh decision law; this module is the capability
shell that executes them on real production paths.  A subprocess per
decision is infeasible (one ``experiment run`` costs seconds, dominated by
compilation), so decisions run batched: a single ``experiment run`` over a
synthetic corpus, with actual verdicts read from per-case ``returned``
values.  Corpus ``expected`` entries are placeholders -- the harness
compares them, but production only reads ``returned``.

When the toolchain is absent (no ``mncs-language`` checkout with a built
``mncs`` binary), callers fall back to the Python mirrors.  The fallback
is explicit at the call site (``executor=None``), never silent: mirrors
are pinned to the same corpora the backends execute, so either lane
decides the identical law.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

PLACEHOLDER_EXPECTED = [{"boolean": {"value": False}}]


def find_toolchain() -> Path | None:
    """Locate a built ``mncs`` binary, or ``None`` when unavailable."""

    override = os.environ.get("MNCS_LANGUAGE_CHECKOUT")
    candidates = [Path(override)] if override else []
    root = Path(__file__).resolve().parent.parent.parent.parent.parent
    candidates.append(root / "mncs-language")
    for candidate in candidates:
        binary = candidate / "target" / "debug" / "mncs"
        if binary.exists():
            return candidate
    return None


def returned_boolean(values: list) -> bool:
    """Decode a kernel ``returned`` payload to a boolean verdict."""

    if len(values) != 1:
        raise MeshExecutorError(f"expected one return value, got {len(values)}")
    return bool(values[0]["boolean"]["value"])


def returned_integer(values: list) -> int:
    """Decode a kernel ``returned`` payload to an integer verdict."""

    if len(values) != 1:
        raise MeshExecutorError(f"expected one return value, got {len(values)}")
    return int(values[0]["integer"]["value"])


class MeshExecutorError(Exception):
    """The toolchain exists but a batched kernel decision failed."""


@dataclass
class KernelCall:
    """One batched decision request against a kernel entry point."""

    case_id: str
    module: str
    function: str
    arguments: list


@dataclass
class MncsKernelExecutor:
    """Execute normative kernels in production through ``experiment run``.

    ``decide`` is the only execution primitive: marshal N decisions into
    one corpus, run once, read N ``returned`` payloads back in order.
    Plan for seconds per batch (compile-dominated); this lane trades
    latency for law-ownership on paths where that trade is acceptable
    (batched sync ingest/select, audit-grade replays).  Hot single-decision
    paths keep the Python mirrors, which the corpora pin to this same law.
    """

    backend: str = "mncs-research-bytecode"
    timeout: int = 600
    _checkout: Path | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._checkout is None:
            self._checkout = find_toolchain()

    @property
    def available(self) -> bool:
        return self._checkout is not None

    def _environment(self) -> dict[str, str]:
        assert self._checkout is not None
        environment = dict(os.environ)
        library = str(self._checkout / "library")
        mesh_mncs = str(Path(__file__).resolve().parent / "mncs")
        environment["MNCS_LIBRARY_PATH"] = library + ":" + mesh_mncs
        return environment

    def decide(self, kernel: str, calls: list[KernelCall]) -> list[list]:
        """Run batched kernel decisions; returns raw ``returned`` payloads."""

        if self._checkout is None:
            raise MeshExecutorError("no mncs toolchain available for kernel execution")
        if not calls:
            return []
        binary = self._checkout / "target" / "debug" / "mncs"
        corpus = {
            "schema_version": "0.1",
            "name": "commons-production-batch",
            "cases": [
                {
                    "id": call.case_id,
                    "request": {
                        "schema_version": "0.1",
                        "target": {"module": call.module, "function": call.function},
                        "arguments": call.arguments,
                        "step_budget": 4096,
                    },
                    "expected": PLACEHOLDER_EXPECTED,
                }
                for call in calls
            ],
        }
        with tempfile.TemporaryDirectory(prefix="mncs-batch-") as work:
            corpus_path = Path(work) / "batch.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            completed = subprocess.run(
                [
                    str(binary),
                    "experiment",
                    "run",
                    str(Path(__file__).resolve().parent / "mncs" / kernel),
                    "--backend",
                    self.backend,
                    "--corpus",
                    str(corpus_path),
                    "--output-dir",
                    str(Path(work) / "result"),
                    "--node-id",
                    "commons-production",
                ],
                capture_output=True,
                text=True,
                env=self._environment(),
                check=False,
                timeout=self.timeout,
            )
        try:
            result = json.loads(completed.stdout)
        except (json.JSONDecodeError, ValueError) as error:
            raise MeshExecutorError(
                f"kernel {kernel} produced no result document: {completed.stderr[-500:]}"
            ) from error
        by_id = {item.get("case_id"): item for item in result.get("cases", [])}
        returned: list[list] = []
        for call in calls:
            item = by_id.get(call.case_id)
            if not isinstance(item, Mapping) or item.get("status") != "returned":
                raise MeshExecutorError(
                    f"kernel {kernel} case {call.case_id} did not return: "
                    f"{json.dumps(item)[:300] if item else 'missing'}"
                )
            returned.append(list(item.get("returned", [])))
        return returned


def corpus_argument(value: Any) -> dict:
    """Encode one Python value as a corpus argument (bool/int/str-name)."""

    if isinstance(value, bool):
        return {"boolean": {"value": value}}
    if isinstance(value, int):
        return {"integer": {"value": value, "type": {"bits": 64, "signed": True}}}
    raise MeshExecutorError(f"unsupported corpus argument type: {type(value).__name__}")


def decide_membership(
    executor: MncsKernelExecutor,
    decisions: list[tuple[Mapping[str, Any], Any, str | None]],
) -> list[bool]:
    """Decide batched membership through the normative interest kernel.

    Each decision is ``(record, interest_filter, lifecycle_state)``; the
    host projects (capability shell) and the kernel owns the combination
    law.  Returns one boolean per decision, in order.
    """

    from .interest import project_full_args

    calls = []
    for index, (record, interest, lifecycle_state) in enumerate(decisions):
        flat: list = []
        for value in project_full_args(record, interest, lifecycle_state=lifecycle_state):
            if isinstance(value, tuple):
                flat.extend(value)
            else:
                flat.append(value)
        calls.append(
            KernelCall(
                case_id=f"membership-{index}",
                module="commons.mesh.interest",
                function="candidate_matches_full",
                arguments=[corpus_argument(item) for item in flat],
            )
        )
    decided = executor.decide("commons/mesh/interest.mncs", calls)
    return [returned_boolean(payload) for payload in decided]
