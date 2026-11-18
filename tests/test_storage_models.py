from copy import deepcopy
from zipfile import ZipFile
import pytest
from isp_app.models import Project
from isp_app.storage import save_project, load_project
from isp_app.validation import japanese_date, parse_date, period, validate_project, ValidationError

def test_roundtrip(tmp_path, project):
    project.fields['final.goals.1.target'] = 'ダミー目標'
    project.start_monitoring()
    project.attachments.append({'name': 'dummy.txt', 'sha256': 'test'})
    for filename in ('a.isp', 'b.isp'):
        save_project(project, tmp_path / filename)
        assert load_project(tmp_path / filename).to_dict() == project.to_dict()
        project = load_project(tmp_path / filename)

@pytest.mark.parametrize('payload', [b'not a zip', b'PK\x03\x04'])
def test_corrupt_rejected(tmp_path, payload):
    path = tmp_path / 'bad.isp'; path.write_bytes(payload)
    with pytest.raises(ValueError): load_project(path)

def test_tampering(tmp_path, project):
    path = tmp_path / 'a.isp'; save_project(project, path)
    with ZipFile(path) as z: contents = {n: z.read(n) for n in z.namelist()}
    contents['project.json'] = contents['project.json'].replace(b'blank', b'other')
    with ZipFile(path, 'w') as z:
        for n, data in contents.items(): z.writestr(n, data)
    with pytest.raises(ValueError, match='整合性'): load_project(path)

def test_traversal_rejected(tmp_path):
    path = tmp_path / 'bad.isp'
    with ZipFile(path, 'w') as z: z.writestr('../escape.txt', 'x')
    with pytest.raises(ValueError): load_project(path)
    assert not (tmp_path.parent / 'escape.txt').exists()

@pytest.mark.parametrize('iso,expected', [('2019-05-01', '令和元年5月1日'), ('2019-04-30', '平成31年4月30日'), ('2024-02-29', '令和6年2月29日')])
def test_japanese_date(iso, expected): assert japanese_date(iso) == expected

@pytest.mark.parametrize('value', ['', '2025-02-29', '2026-13-01', None])
def test_invalid_dates(value):
    with pytest.raises(ValidationError): parse_date(value)

def test_period():
    with pytest.raises(ValidationError): period({'start': '2026-12-01', 'end': '2026-01-01'})
    with pytest.raises(ValidationError): period({'start': '2026-01-01'})

def test_history_duplicate_monitoring(project):
    before = project.snapshot(); project.fields['final.manager'] = 'ダミー担当'
    project.record_change(before, 'サビ管変更', '2026-11-17', '担当交代')
    assert project.history[-1]['changes'][0]['old'] is None
    assert project.history[-1]['changes'][0]['new'] == 'ダミー担当'
    project.fields['final.goals.1.target'] = '目標'
    project.fields['final.consent_date'] = '2026-11-17'
    project.settings['consent_confirmed']['final'] = True
    copy = project.duplicate()
    assert copy.project_id != project.project_id and not copy.settings['consent_confirmed']
    assert 'final.consent_date' not in copy.fields
    copy.start_monitoring(); copy.fields['final.goals.1.target'] = '変更'
    assert copy.monitoring[0]['goals'][0]['target'] == '目標'

def test_state_requires_evidence(project):
    project.metadata['status'] = '確定'
    with pytest.raises(ValidationError): validate_project(project)

def test_date_order(project):
    project.metadata.update(valid_from='2026-12-01', valid_to='2026-01-01')
    with pytest.raises(ValidationError): validate_project(project)
