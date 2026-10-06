from __future__ import annotations

import hashlib
import json

import pytest

from mncs_commons.family_graph import (
    FamilyGraphError, audit_stdlib_dependencies, repository_contracts,
)


def manifest(root, repository, provides=(), consumes=()):
    (root / ".mncs").mkdir(parents=True)
    (root / ".mncs/project.json").write_text(json.dumps({
        "repository": repository, "contracts": {
            "provides": list(provides), "consumes": list(consumes)}}))


def test_exports_bind_manifest_identity_instead_of_directory_name(tmp_path):
    manifest(tmp_path, "mncs-commons", [{"contract": "family-change"}],
             [{"contract": "mncs-store.projection-state"}])
    assert repository_contracts(tmp_path) == (
        {"mncs-commons.family-change"}, {"mncs-store.projection-state"})


def test_source_observation_requires_verified_provider_and_declared_edge(tmp_path):
    stdlib = tmp_path / "stdlib"
    manifest(stdlib, "mncs-stdlib", [{"contract": "stdlib-source"}])
    module = stdlib / "library/hash.mncs"
    module.parent.mkdir()
    module.write_text("module mncs.std.hash.v1;")
    (stdlib / "stdlib-manifest.json").write_text(json.dumps({"library_path": "library",
        "modules": [{"name": "mncs.std.hash.v1", "path": "hash.mncs",
                     "content_sha256": hashlib.sha256(module.read_bytes()).hexdigest()}]}))
    consumer = tmp_path / "consumer"
    manifest(consumer, "consumer", [{"contract": "run", "fingerprint_sources": ["native/"]}])
    (consumer / "native/tests").mkdir(parents=True)
    source = consumer / "native/app.mncs"
    source.write_text("// use mncs.std.hash.v1;\nmodule app;\n")
    (consumer / "native/tests/test.mncs").write_text("use mncs.std.hash.v1;")
    assert not audit_stdlib_dependencies({"consumer": consumer}, stdlib)["observed"]
    source.write_text("module app; use mncs.std.hash.v1 as hash;")
    result = audit_stdlib_dependencies({"consumer": consumer}, stdlib)
    assert len(result["missing_consumes"]) == 1
    data = json.loads((consumer / ".mncs/project.json").read_text())
    data["contracts"]["consumes"] = [{"contract": "mncs-stdlib.stdlib-source"}]
    (consumer / ".mncs/project.json").write_text(json.dumps(data))
    assert not audit_stdlib_dependencies({"consumer": consumer}, stdlib)["missing_consumes"]
    module.write_text("changed")
    with pytest.raises(FamilyGraphError, match="stale"):
        audit_stdlib_dependencies({"consumer": consumer}, stdlib)
