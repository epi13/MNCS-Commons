"""Pin the Commons agent contract to real repository paths."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "AGENTS.md"


def contract_text() -> str:
    assert CONTRACT.is_file(), "AGENTS.md (agent execution contract) is missing"
    return CONTRACT.read_text(encoding="utf-8")


def test_contract_names_existing_paths():
    text = contract_text()
    for ref in ("src/mncs_commons/", "docs/INSTITUTIONAL_MEMORY.md", "README.md"):
        assert ref in text, f"contract must mention {ref}"
        assert (REPO / ref).exists(), f"contract names missing {ref}"


def test_contract_claims_coordination_role_and_routes_language():
    text = contract_text()
    assert "coordination exchange" in text
    assert "mncs-language" in text
    assert "development-pressure" in text
    assert "tests/test_agent_contract.py" in text
