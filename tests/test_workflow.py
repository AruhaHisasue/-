from isp_app.ui.main_window import MainWindow
from isp_app.managers import ManagerDB
import pytest

def test_manager_only_initial_and_changes(tmp_path):
    db = ManagerDB(tmp_path / 'manager.sqlite')
    assert db.register('person1', '担当A', '2026-11-01')
    assert not db.register('person1', '担当A', '2026-11-02')
    assert db.register('person1', '担当B', '2026-11-03')
    assert len(db.history('person1')) == 2
    assert db.history('person1')[0][1] == '2026-11-01'
    with pytest.raises(ValueError): db.register('person1', '担当C', '2026-10-01')

def test_workflow_dates_and_direct_transfer(qapp, root, tmp_path):
    w = MainWindow(root, tmp_path)
    assert [w.tabs.tabText(i) for i in range(8)] == ['基本情報', 'アセスメント', '算定・報酬', '変更履歴 / 設定', 'モニタリング', '仮計画', '本計画', '担当者会議']
    assert w.tabs.tabBar().isHidden() and w.tabs.currentIndex() == 0 and w.nav_buttons['基本情報'].isChecked()
    w.nav_buttons['本計画'].click()
    assert w.tabs.tabText(w.tabs.currentIndex()) == '本計画' and not w.nav_buttons['基本情報'].isChecked()
    w.widgets['assessment.recorded_on'].editor.set_value('2026-11-10')
    w.meta_widgets['draft_created_on'].set_value('2026-11-09')
    assert '警告' in w.meta_widgets['draft_created_on'].warning.text()
    w.meta_widgets['draft_created_on'].set_value('2026-11-11')
    assert not w.meta_widgets['draft_created_on'].warning.text()
    w.widgets['meeting.when'].parts['date'].set_value('2026-11-10')
    assert '警告' in w.widgets['meeting.when'].parts['date'].warning.text()
    w.project.master_selections = [{'item': {'item_name': '検証算定名'}, 'confirmed': False}]
    w.widgets['final.notes'].editor.setPlainText('既存の留意事項')
    w.append_fee_names('final.notes', ['検証算定名']); w.append_fee_names('final.notes', ['検証算定名'])
    assert w.widgets['final.notes'].editor.toPlainText() == '既存の留意事項\n検証算定名'
    assert not w.project.master_selections[0]['confirmed']
    w.collect(); w.baseline = w.project.snapshot(); w.close()
