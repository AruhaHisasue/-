from isp_app.master_db import import_master, MasterDB
from isp_app.ui.master_dialog import MasterDialog

def test_bookmark_persistence_duplicate_and_remove(qapp, root, tmp_path):
    path = tmp_path / 'master.sqlite'
    import_master(root / 'resources/r806_fee_master_fixed.zip', path)
    db = MasterDB(path)
    dialog = MasterDialog(db)
    dialog.table.setCurrentCell(0, 0)
    expected = dialog.rows[0]['master_id']
    dialog.toggle_star(0, 0)
    assert expected in dialog.star_ids
    other = MasterDialog(db)
    assert other.rows[0]['master_id'] == expected
    assert other.table.item(0, 0).text() == '★'
    other.search_text.setText('検索に一致しない文字列'); other.search()
    assert other.rows[0]['master_id'] == expected
    other.toggle_star(0, 0)
    assert expected not in MasterDialog(db).star_ids
