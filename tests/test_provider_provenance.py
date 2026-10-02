"""Execute Commons provenance law without host semantic substitutes."""
import json
import os
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('MNCS_BINARY', '/unavailable'))
SOURCE = ROOT / 'src/mncs_commons/mesh/mncs/commons/family/provenance/v1.mncs'


def call(function, a, b, *flags):
    if not BINARY.is_file():
        pytest.skip('explicit compiler required')
    args = [{'sequence': {'values': [{'byte': {'value': value}} for value in digest]}} for digest in (a, b)]
    args += [{'integer': {'value': value}} for value in flags]
    result = subprocess.run([str(BINARY), 'call', str(SOURCE), '--module', 'mncs.commons.family.provenance.v1',
                             '--function', function, '--args-json', json.dumps(args)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)['call']['returned'][0]


@pytest.mark.parametrize('known,present,intact,expected', [(1,1,1,1),(0,1,1,0),(1,0,1,2),(1,1,0,2)])
def test_artifact_state_requires_exact_known_intact_receipt(known,present,intact,expected):
    assert call('artifact_state',bytes(32),bytes(32),known,present,intact)['integer']['value'] == expected


def test_byte_mismatch_invalidates_artifact_and_domain_admission_is_independent():
    a,b=bytes(32),bytes([1])+bytes(31)
    assert call('artifact_state',a,b,1,1,1)['integer']['value'] == 2
    assert call('evidence_applicable',a,a,1,1,0)['boolean']['value'] is False
    assert call('evidence_applicable',a,a,1,1,1)['boolean']['value'] is True
    assert call('evidence_applicable',a,b,1,1,1)['boolean']['value'] is False
