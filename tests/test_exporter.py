from copy import deepcopy, copy
from datetime import datetime
import hashlib
from zipfile import ZipFile
import pytest
from openpyxl import load_workbook
from openpyxl.xml.functions import tostring
from isp_app.exporter import template_path, validate_mapping, export_excel
from isp_app.validation import ValidationError

def test_actual_templates_and_map(root, mapping):
    a, b = [load_workbook(template_path(root, mapping, k)) for k in ('blank', 'filled')]
    assert a.sheetnames == b.sheetnames == list(mapping['sheets'].values())
    assert validate_mapping(a, mapping) == validate_mapping(b, mapping) == 133
    for name in a.sheetnames:
        assert a[name].merged_cells == b[name].merged_cells
        assert str(a[name].print_area) == str(b[name].print_area)
    a.close(); b.close()

def test_mapping_xlsx_matches_json(root, mapping):
    wb = load_workbook(root / 'mappings/個別支援計画_Excelセル対応表.xlsx')
    rows = list(wb['セル対応表'].values)
    assert {r[2] for r in rows[1:]} == {m['id'] for m in mapping['mappings']}
    wb.close()

def test_reject_nonanchor_and_duplicate(root, mapping):
    wb = load_workbook(template_path(root, mapping))
    broken = deepcopy(mapping); broken['mappings'][0]['cell'] = 'D2'
    with pytest.raises(ValidationError): validate_mapping(wb, broken)
    broken = deepcopy(mapping); broken['mappings'].append(broken['mappings'][0])
    with pytest.raises(ValidationError): validate_mapping(wb, broken)
    wb.close()

def populate_goals(project, count=4):
    for prefix in ('draft', 'final'):
        for n in range(1, count + 1):
            for field, value in {'category': '本人', 'target': f'ダミー目標{n}',
                'support': {'text': f'支援内容{n}', 'points': f'ポイント{n}'},
                'due': '6か月', 'provider': {'staff': 'ダミー担当', 'agency': '検証事業所'},
                'support_period': {'start': '2026-11-01', 'end': '2027-04-30'},
                'evaluation_period': {'start': '2026-11-01', 'end': '2027-01-31'}, 'priority': n}.items():
                project.fields[f'{prefix}.goals.{n}.{field}'] = value

def test_export_preserves_original_and_all_other_content(root, mapping, tmp_path, project):
    source = template_path(root, mapping); original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    populate_goals(project)
    project.fields.update({'assessment.recorded_on': '2026-11-17', 'final.manager': 'ダミー担当', 'final.notes': '=1+1'})
    out = tmp_path / 'out.xlsx'; result = export_excel(project, mapping, root, out)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    a, b = load_workbook(source), load_workbook(out)
    for name in a.sheetnames:
        sa, sb = a[name], b[name]
        assert sa.merged_cells == sb.merged_cells
        assert tostring(sa.data_validations.to_tree()) == tostring(sb.data_validations.to_tree())
        assert tostring(sa.page_setup.to_tree()) == tostring(sb.page_setup.to_tree())
        assert tostring(sa.page_margins.to_tree()) == tostring(sb.page_margins.to_tree())
        assert str(sa.print_area) == str(sb.print_area)
        assert set(sa.row_dimensions) == set(sb.row_dimensions)
        assert set(sa.column_dimensions) == set(sb.column_dimensions)
        for key, dim in sa.row_dimensions.items():
            other = sb.row_dimensions[key]
            assert (dim.height, dim.hidden, dim.outlineLevel, dim._style) == (other.height, other.hidden, other.outlineLevel, other._style)
        for key, dim in sa.column_dimensions.items():
            other = sb.column_dimensions[key]
            assert (dim.width, dim.hidden, dim.min, dim.max, dim._style) == (other.width, other.hidden, other.min, other.max, other._style)
        for row in sa:
            for cell in row:
                other = sb[cell.coordinate]
                if cell.coordinate not in result['written'].get(name, []): assert cell.value == other.value
                assert copy(cell.font) == copy(other.font) and copy(cell.border) == copy(other.border)
                assert copy(cell.fill) == copy(other.fill) and copy(cell.alignment) == copy(other.alignment)
                if (name, cell.coordinate) != (mapping['sheets']['assessment'], 'C3'):
                    assert cell.number_format == other.number_format
    for m in mapping['mappings']:
        if m['id'].endswith('.target'): assert b[m['sheet']][m['cell']].value == project.fields[m['id']]
        if m['id'].endswith('.support'):
            assert '（ポイント）' in b[m['sheet']][m['cell']].value
    assert b[mapping['sheets']['assessment']]['C3'].value == datetime(2026, 11, 17)
    assert b[mapping['sheets']['final_plan']]['C20'].data_type == 's'
    a.close(); b.close()
    # Unchanged ZIP parts are byte-for-byte identical, including native objects.
    with ZipFile(source) as za, ZipFile(out) as zb:
        for n in za.namelist():
            if n != 'xl/styles.xml' and not n.startswith('xl/worksheets/sheet'): assert za.read(n) == zb.read(n)

def test_empty_placeholders_and_protected_cells(root, mapping, tmp_path, project):
    out = tmp_path / 'out.xlsx'; export_excel(project, mapping, root, out)
    a, b = load_workbook(template_path(root, mapping)), load_workbook(out)
    for m in mapping['mappings']:
        if m['id'] not in ('person.name', 'meeting.person'):
            assert a[m['sheet']][m['cell']].value == b[m['sheet']][m['cell']].value
    for m in mapping['fixed_cells']: assert a[m['sheet']][m['cell']].value == b[m['sheet']][m['cell']].value
    a.close(); b.close()

def test_five_goals_rejected(root, mapping, tmp_path, project):
    populate_goals(project, 5)
    with pytest.raises(ValidationError, match='最大4件'): export_excel(project, mapping, root, tmp_path / 'out.xlsx')

def test_filled_template_never_leaks(root, mapping, tmp_path, project):
    project.template_id = 'filled'
    with pytest.raises(ValidationError, match='記入済み'): export_excel(project, mapping, root, tmp_path / 'out.xlsx')
    assert not (tmp_path / 'out.xlsx').exists()

def test_overwrite_original_forbidden(root, mapping, project):
    with pytest.raises(ValidationError, match='上書き'): export_excel(project, mapping, root, template_path(root, mapping))

def test_conditional_consent_and_review(root, mapping, tmp_path, project):
    project.fields['final.consent_date'] = '2026-11-17'
    with pytest.raises(ValidationError, match='同意確認'): export_excel(project, mapping, root, tmp_path / 'out.xlsx')
    project.settings['consent_confirmed']['final'] = True
    # 旧「要確認」5項目は原本の結合修正後、確認記録なしで常に出力する
    project.fields.update({'assessment.goal_review.goal': '検証', 'assessment.goal_review.rating': '4',
        'assessment.policy.continue': '継続', 'assessment.policy.challenges': '課題', 'assessment.wishes.person': '希望'})
    result = export_excel(project, mapping, root, tmp_path / 'out.xlsx')
    assert not result['warnings']
    assert not [m for m in mapping['mappings'] if m['status'] == '要確認']
    ws = load_workbook(tmp_path / 'out.xlsx')[mapping['sheets']['assessment']]
    assert [ws[c].value for c in ('B32', 'J32', 'D34', 'D35', 'B38')] == ['検証', '4', '継続', '課題', '希望']

def test_hours_requires_structured_confirmation(root, mapping, tmp_path, project):
    project.fields['final.standard_hours'] = {'hours': '09:00～15:00'}
    with pytest.raises(ValidationError): export_excel(project, mapping, root, tmp_path / 'out.xlsx')
    project.fields['final.standard_hours']['confirmed'] = True
    export_excel(project, mapping, root, tmp_path / 'out.xlsx')

def test_long_strings_rejected(root, mapping, tmp_path, project):
    project.fields['final.policy'] = '長' * 32768
    with pytest.raises(ValidationError): export_excel(project, mapping, root, tmp_path / 'out.xlsx')
