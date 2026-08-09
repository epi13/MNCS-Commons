from __future__ import annotations

from mncs_commons.application import CommonsApplication, CompatibilityApplication


def test_application_services_expose_core_identity_and_registry() -> None:
    value = {"b": 2, "a": 1}
    application = CommonsApplication()
    assert application.identity(value).startswith("sha256:")
    assert application.canonicalize(value) == b'{"a":1,"b":2}'
    contracts = CompatibilityApplication.list_contracts()
    assert {item["producer"] for item in contracts} >= {
        "forge",
        "fabric",
        "mnel",
        "ravel",
        "mncs-language",
    }
