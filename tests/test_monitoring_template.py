import json
from copy import deepcopy
from openpyxl import load_workbook
from isp_app.exporter import export_excel, validate_mapping, template_path
from isp_app.transfers import transfer_fields
from isp_app.ui.fee_picker import FeeNamePicker
from isp_app.storage import save_project, load_project

def test_real_monitoring_export(root, project, tmp_path):
    mapping = json.loads((root/'mappings/monitoring_mapping.json').read_text('utf-8'))
    source = template_path(root, mapping); original = source.read_bytes()
    wb = load_workbook(source); validate_mapping(wb, mapping); wb.close()
    project.fields.update({'monitor.wishes':'本人の希望（ダミー）', 'monitor.manager':'検証担当',
        'monitor.goals.1.target':'目標', 'monitor.goals.1.support':{'text':'支援', 'points':'配慮'},
        'monitor.goals.1.rating':'4', 'monitor.goals.1.challenges':'今後の課題'})
    out = tmp_path/'monitor.xlsx'; result = export_excel(project, mapping, root, out)
    a, b = load_workbook(source), load_workbook(out)
    assert b.active['F14'].value == '4' and b.active['H14'].value == '今後の課題'
    assert b.active['B22'].value == 'サービス管理責任者氏名：検証担当'
    assert a.active.merged_cells == b.active.merged_cells
    assert str(a.active.print_area) == str(b.active.print_area)
    for row in a.active:
        for cell in row:
            if cell.coordinate not in result['written']['モニタリング']:
                assert cell.value == b.active[cell.coordinate].value
    assert source.read_bytes() == original
    a.close(); b.close()
    save_project(project, tmp_path/'p.isp')
    assert load_project(tmp_path/'p.isp').fields == project.fields

def test_common_transfer_and_no_shared_objects(project):
    project.fields.update({'monitor.wishes':'希望', 'monitor.goals.1.support':{'text':'支援','points':'配慮'}, 'draft.policy':'以前の文章'})
    transfer_fields(project, 'monitor', 'draft', {'wishes', 'goals.1.support', 'policy'})
    assert project.fields['draft.wishes'] == '希望'
    assert 'draft.policy' not in project.fields
    project.fields['draft.goals.1.support']['text'] = '修正'
    assert project.fields['monitor.goals.1.support']['text'] == '支援'

def test_fee_multiselect(qapp):
    picker = FeeNamePicker([{'item':{'item_name':n}} for n in ['算定A','算定B','算定C']])
    assert picker.selected_names() == []
    picker.checks[0][0].setChecked(True); picker.checks[2][0].setChecked(True)
    assert picker.selected_names() == ['算定A','算定C']
