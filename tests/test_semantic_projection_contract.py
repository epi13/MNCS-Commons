"""Shared semantic projection contract: explicit ownership and versioned views."""
import copy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Draft202012Validator(json.loads((ROOT/'schemas/semantic-projection-1.schema.json').read_text()))


def example():
    return json.loads((ROOT/'.mncs/projections.json').read_text())['projections'][0]


def test_declared_projection_contracts_validate():
    for row in json.loads((ROOT/'.mncs/projections.json').read_text())['projections']:
        CONTRACT.validate(row)


@pytest.mark.parametrize('field', ['owner','subjects','renderer','manual_edit_policy','validation'])
def test_missing_semantic_ownership_contract_fails(field):
    row = example()
    del row[field]
    with pytest.raises(ValidationError):
        CONTRACT.validate(row)


def test_unknown_manual_edit_policy_fails():
    row = example(); row['manual_edit_policy']='silently-overwrite'
    with pytest.raises(ValidationError):
        CONTRACT.validate(row)


def test_machine_view_requires_source_identity():
    validator = Draft202012Validator(json.loads((ROOT/'schemas/project-view-1.schema.json').read_text()))
    view = json.loads((ROOT/'.mncs/project-view.json').read_text())
    validator.validate(view)
    del view['source_identity']
    with pytest.raises(ValidationError):
        validator.validate(view)
