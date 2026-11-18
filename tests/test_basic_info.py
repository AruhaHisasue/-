from isp_app.ui.main_window import MainWindow
from isp_app.validation import validate_project, ValidationError
import pytest


def test_basic_confirm_fills_tabs_and_manager_buttons(qapp, root, tmp_path, monkeypatch):
    w = MainWindow(root, tmp_path)
    errors = []; monkeypatch.setattr(w, 'error', lambda e: errors.append(str(e)))
    assert 'facility_name' in w.meta_widgets and 'status_evidence' not in w.meta_widgets
    w.widgets['person.name'].editor.setText('ダミー利用者')
    w.meta_widgets['facility_name'].setText('ダミー事業所')
    w.confirm_basic()
    for key in ('monitor.facility', 'draft.facility', 'final.facility', 'meeting.facility'):
        assert w.widgets[key].editor.text() == 'ダミー事業所'
    assert w.widgets['meeting.person'].editor.text() == 'ダミー利用者'
    assert w.project.metadata['basic_confirmed_at']
    # 初回登録前の転記はエラー、担当変更も使えない
    w.transfer_manager('draft.manager'); assert errors
    assert not w.change_manager_name.isEnabled() and w.manager_name.isEnabled()
    w.manager_name.setCurrentText('担当A'); w.manager_date.set_value('2026-11-01'); w.register_manager('initial')
    assert all(w.widgets[k].editor.text() == '担当A' for k in w.MANAGER_KEYS)
    assert not w.manager_name.isEnabled() and w.change_manager_name.isEnabled()
    # 担当変更は各タブを上書きせず、ボタンで転記する
    w.change_manager_name.setCurrentText('担当B'); w.change_manager_date.set_value('2026-12-01'); w.register_manager('change')
    assert w.widgets['final.manager'].editor.text() == '担当A'
    for key in ('monitor.manager', 'draft.manager', 'final.manager', 'meeting.manager'):
        w.transfer_manager(key); assert w.widgets[key].editor.text() == '担当B'
    w.collect(); w.baseline = w.project.snapshot(); w.close()


def test_status_change_needs_only_date(project):
    project.metadata['status'] = '会議後'
    with pytest.raises(ValidationError): validate_project(project)
    project.metadata['status_date'] = '2026-11-17'
    validate_project(project)
