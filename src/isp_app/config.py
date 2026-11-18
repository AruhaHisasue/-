import json
import os
import sys
from pathlib import Path

def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))

def data_root():
    p = Path(os.environ.get('ISP_DATA_DIR', Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'IndividualSupportPlan'))
    p.mkdir(parents=True, exist_ok=True)
    return p

def load_mapping(root=None):
    path = (root or resource_root()) / 'mappings/individual_support_excel_mapping.json'
    if not path.exists(): raise ValueError(f'セル対応JSONがありません: {path}')
    result = json.loads(path.read_text('utf-8-sig'))
    if result.get('schema_version') != 1 or not isinstance(result.get('mappings'), list):
        raise ValueError('未対応のセルマップです')
    return result

def input_status(root=None):
    root = root or resource_root()
    expected = ['mappings/individual_support_excel_mapping.json', 'mappings/個別支援計画_Excelセル対応表.xlsx',
        'resources/r806_fee_master_fixed.zip', 'individual_support_plan_app_overview.txt']
    try:
        expected += ['templates/' + t['filename'] for t in load_mapping(root)['source_templates']]
    except ValueError: pass
    return [(name, (root / name).exists()) for name in expected]
