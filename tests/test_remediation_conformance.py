"""Reference conformance battery for mncs.remediation/1 (repository domain).

Runs the scenario battery against a remediation provider binary and
validates every envelope against schemas/mncs-remediation-v1.schema.json.
Envelope shape, scope echo, dry-run purity, budget/hint/idempotence
mechanics, and evidence routing hold for every conformant provider;
repair-occurrence assertions pin the reference fixtures
(tests/fixtures/remediation/). Future domains reuse the mechanics with
their own fixtures. Provider defaults to the sibling mncs-doctor
release build (DOCTOR_BINARY overrides), matching how the native tests
assume a sibling mncs-language build.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/remediation"
SCHEMA = json.loads((ROOT / "schemas/mncs-remediation-v1.schema.json").read_text())


def _provider() -> str:
    override = os.environ.get("DOCTOR_BINARY")
    if override:
        return override
    release = ROOT.parent / "mncs-doctor/target/release/mncs-doctor"
    if release.is_file():
        return str(release)
    return str(ROOT.parent / "mncs-doctor/target/debug/mncs-doctor")


def _run(provider: str, root: Path, *argv: str, env: dict | None = None) -> dict:
    completed = subprocess.run(
        [provider, "remediate", "--target", str(root), "--json", *argv],
        capture_output=True, text=True, timeout=180,
        env={**os.environ, **(env or {})},
    )
    envelope = json.loads(completed.stdout)
    jsonschema.validate(envelope, SCHEMA)
    return envelope


class RemediationConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = _provider()
        assert Path(cls.provider).is_file(), f"provider binary missing: {cls.provider}"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mncs-remediation-conformance-")
        self.addCleanup(self.temp.cleanup)

    def stage(self, name: str) -> Path:
        dest = Path(self.temp.name) / name
        shutil.copytree(FIXTURES / name, dest)
        return dest

    def test_scope_is_echoed(self):
        root = self.stage("messy")
        envelope = _run(self.provider, root)
        self.assertEqual(envelope["schema_version"], "mncs.remediation/1")
        self.assertEqual(envelope["scope"]["domain"], "repository")
        self.assertEqual(envelope["scope"]["target"], str(root))

    def test_repair_then_quiet_rerun(self):
        root = self.stage("messy")
        first = _run(self.provider, root)
        self.assertGreaterEqual(first["summary"]["repaired"], 1)
        for record in first["repairs"]:
            self.assertTrue(record["validated"])
            self.assertEqual(record["class"], "safe_automatic")
        second = _run(self.provider, root)
        self.assertEqual(second["summary"]["repaired"], 0)
        self.assertEqual(second["summary"]["reconciled"], 0)

    def test_dry_run_mutates_nothing(self):
        root = self.stage("messy")
        before = {str(path.relative_to(root)): path.read_bytes()
                  for path in root.rglob("*.mncs") if path.is_file()}
        envelope = _run(self.provider, root, "--dry-run")
        self.assertTrue(envelope["dry_run"])
        for record in envelope["repairs"]:
            self.assertFalse(record["validated"])
        after = {str(path.relative_to(root)): path.read_bytes()
                 for path in root.rglob("*.mncs") if path.is_file()}
        self.assertEqual(after, before)

    def test_budget_bounds_prefix_and_escalates_rest(self):
        root = self.stage("messy")
        shutil.copy(root / "src/a.mncs", root / "src/c.mncs")
        envelope = _run(self.provider, root, "--budget", "1")
        self.assertEqual(envelope["summary"]["repaired"], 1)
        self.assertTrue(envelope["budget"]["exhausted"])
        self.assertTrue(any(item.startswith("budget-exhausted:") for item in envelope["remaining"]))

    def test_changed_path_hint_scopes_repair(self):
        root = self.stage("messy")
        shutil.copy(root / "src/a.mncs", root / "src/c.mncs")
        envelope = _run(self.provider, root, "--changed-path", "src/a.mncs")
        repaired = {record.get("target") for record in envelope["repairs"]}
        self.assertIn("src/a.mncs", repaired)
        self.assertNotIn("src/c.mncs", repaired)

    def test_malformed_source_escalates_without_repair(self):
        root = self.stage("malformed")
        envelope = _run(self.provider, root)
        self.assertGreaterEqual(envelope["summary"]["blockers"], 1)
        self.assertTrue(envelope["remaining"])
        for record in envelope["repairs"]:
            self.assertNotEqual(record.get("target"), "src/bad.mncs")

    def test_evidence_routes_to_session_artifact_dir(self):
        root = self.stage("messy")
        artifacts = Path(self.temp.name) / "artifacts"
        artifacts.mkdir()
        envelope = _run(self.provider, root, env={"MNCS_ENV_SESSION_ARTIFACT_DIR": str(artifacts)})
        self.assertTrue(str(envelope["evidence"]).startswith(str(artifacts)))
        payload = json.loads(Path(envelope["evidence"]).read_text())
        self.assertEqual(payload["schema_version"], "mncs.remediation-evidence/1")


if __name__ == "__main__":
    unittest.main()
