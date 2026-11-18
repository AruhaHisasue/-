from pathlib import Path
from isp_app.ui.main_window import MainWindow
from isp_app.storage import load_project

def test_gui_edit_save_export_and_recovery(qapp, root, tmp_path):
    window = MainWindow(root, tmp_path)
    window.show(); qapp.processEvents()
    assert window.tabs.count() == 8
    window.widgets['person.name'].editor.setText('GUI検証用ダミー')
    window.widgets['final.goals.1.target'].editor.setPlainText('GUIの入力を保存する')
    window.widgets['final.goals.1.support'].parts['text'].setPlainText('見守り')
    window.path = tmp_path / 'gui.isp'
    assert window.save()
    p = load_project(window.path)
    assert p.fields['person.name'] == 'GUI検証用ダミー'
    assert p.fields['final.goals.1.support']['text'] == '見守り'
    window.widgets['assessment.health'].editor.setPlainText('ダミー変更')
    window.autosave()
    assert list((tmp_path / 'recovery').glob('*.isp'))
    assert window.export(tmp_path / 'gui.xlsx').exists()
    window.start_monitoring('final')
    assert window.project.monitoring[0]['goals'][0]['target'] == 'GUIの入力を保存する'
    window.collect(); window.baseline = window.project.snapshot(); window.close()
