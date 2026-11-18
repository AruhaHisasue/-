from pathlib import Path
import pytest
from isp_app.master_db import import_master, MasterDB

@pytest.fixture
def db(root, tmp_path):
    path = tmp_path / 'r806.sqlite'
    assert import_master(root / 'resources/r806_fee_master_fixed.zip', path) == {'services': 33, 'fee_items': 5096, 'version': 'R806'}
    return MasterDB(path)

def test_master_real_data(db):
    assert len(db.services()) == 33
    assert len(db.search(limit=6000)) == 5096
    service = next(s for s in db.services() if '生活介護' in s['service_name'])
    rows = db.search(service['service_id'], '加算')
    assert rows and all(r['category'] == '加算' for r in rows)
    assert {'units', 'units_increment', 'rate_op', 'rate_num', 'rate_den', 'applies_to', 'calc_unit'} <= rows[0].keys()
    selection = db.selection(rows[0]['master_id'], '2026-11-17', '検証用の選択')
    assert selection['amount'] is None and selection['eligibility'] == '要確認'
    assert selection['version'] == 'R806'

def test_unsupported_system_and_sql_input(db):
    with pytest.raises(ValueError): db.search(system='介護保険')
    with pytest.raises(ValueError): db.search(version='R704')
    assert not db.search(text="' OR 1=1 --")

def test_missing_master(tmp_path):
    with pytest.raises(ValueError, match='未取込'): MasterDB(tmp_path / 'missing.sqlite').search()
