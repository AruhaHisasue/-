"""Generate dummy-only artifacts and exercise real Excel PDF output."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from isp_app.models import Project
from isp_app.config import load_mapping
from isp_app.storage import save_project
from isp_app.exporter import export_excel
from isp_app.master_db import import_master
from isp_app.printing import available, print_workbook

root = Path(__file__).resolve().parents[1]
out = root / 'outputs'
mapping = load_mapping(root)
p = Project()
p.fields = {'person.name': '検証用ダミー利用者', 'assessment.recorded_on': '2026-11-17',
            'assessment.health': '動作確認専用の架空データです。', 'final.manager': '検証担当者'}
for prefix in ('draft', 'final'):
    for n in range(1, 5):
        p.fields[f'{prefix}.goals.{n}.target'] = f'検証用目標{n}'
        p.fields[f'{prefix}.goals.{n}.support'] = {'text': f'検証用支援内容{n}', 'points': '担当者が確認する'}
save_project(p, out / 'dummy_plan.isp')
export_excel(p, mapping, root, out / 'dummy_plan.xlsx')
result = {'master': import_master(root / 'resources/r806_fee_master_fixed.zip', out / 'r806.sqlite'), 'excel': available()}
if result['excel'][0]:
    try:
        print_workbook(out / 'dummy_plan.xlsx', list(mapping['sheets'].values()), mapping,
                       'pdf', out / 'dummy_plan_preview.pdf')
        result['pdf'] = 'success'
    except Exception as e:
        result['pdf'] = str(e)
(out / 'release-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps(result, ensure_ascii=False))
