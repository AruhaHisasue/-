import pytest
from isp_app.fee_history import FeeHistoryDB, subject_of
from isp_app.models import Project
from isp_app.ui.main_window import MainWindow


def selection(master_id, name, category='加算', effective='2026-11-01', **extra):
    return {'master_id': master_id, 'version': 'R806', 'selected_at': '2026-11-01T09:00:00+09:00',
            'effective_on': effective, 'reason': '算定開始', 'confirmed': False,
            'item': {'item_name': name, 'category': category, 'expression': '', 'condition_text': ''}, **extra}


def test_db_records_once_and_backfills_old_files(tmp_path):
    db = FeeHistoryDB(tmp_path / 'fee.sqlite')
    p = Project(); p.fields['person.name'] = 'ダミー'
    p.master_selections = [selection('R806-1', '旧加算', ended_on='2026-12-01', end_reason='要件外'),
                           selection('R806-2', '基本', category='基本報酬')]
    assert db.backfill(p) == 3
    assert db.backfill(p) == 0
    rows = db.history(subject_of(p), '加算')
    assert [(r['event'], r['effective_on']) for r in rows] == [('追加', '2026-11-01'), ('終了', '2026-12-01')]
    assert len(db.history(subject_of(p))) == 3
    # 確認の付け外しは毎回記録する
    db.record(p, p.master_selections[0], '確認済み', '2026-11-02'); db.record(p, p.master_selections[0], '確認取消', '2026-11-02')
    db.record(p, p.master_selections[0], '確認済み', '2026-11-02')
    assert len(db.history(subject_of(p), '加算')) == 5
    with pytest.raises(ValueError): db.record(p, p.master_selections[0], '削除', '2026-11-02')


def test_gui_add_end_and_history_survives_duplicate(qapp, root, tmp_path):
    w = MainWindow(root, tmp_path)
    w.add_fee_selection(selection('R806-9', '検証加算'))
    assert w.fee_history_table.rowCount() == 1
    with pytest.raises(ValueError): w.record_fee_end(0, '2026-10-01', '早すぎる')
    with pytest.raises(ValueError): w.record_fee_end(0, '2026-12-01', ' ')
    w.record_fee_end(0, '2026-12-01', '要件を満たさなくなった')
    assert w.project.master_selections[0]['ended_on'] == '2026-12-01'
    events = [w.fee_history_table.item(r, 1).text() for r in range(w.fee_history_table.rowCount())]
    assert events == ['追加', '終了']
    # 終了した加算は留意事項への転記候補から外れる
    assert not [s for s in w.project.master_selections if not s.get('ended_on')]
    # 計画を複製しても同じ利用者の履歴を表示する
    w.activate(w.project.duplicate(), None)
    assert w.fee_history_table.rowCount() == 2
    w.collect(); w.baseline = w.project.snapshot(); w.close()
