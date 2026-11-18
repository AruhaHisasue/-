import json, hashlib
from pathlib import Path
from copy import deepcopy
from openpyxl import load_workbook

root = Path(__file__).resolve().parents[1]
base = json.loads((root / 'mappings/individual_support_excel_mapping.json').read_text('utf-8'))
path = root / 'templates/モニタリング.xlsx'
wb = load_workbook(path); sheet = wb.active
entries = []
for original in base['mappings']:
    if not original['id'].startswith('final.'): continue
    suffix = original['id'].removeprefix('final.')
    if '.goals.' in original['id'] and suffix.split('.')[-1] not in ('category', 'target', 'support', 'points_column'): continue
    m = deepcopy(original); m.update(id='monitor.' + suffix, sheet=sheet.title)
    m['merged_range'] = next((str(r) for r in sheet.merged_cells.ranges if m['cell'] in r), '')
    m['blank_sample_value'] = sheet[m['cell']].value
    entries.append(m)
for n in range(1, 5):
    for col, key, label, kind in [('F', 'rating', '達成度', '選択（1〜5）'), ('H', 'challenges', '今後の課題', '複数行')]:
        cell = f'{col}{13+n}'
        entries.append(dict(id=f'monitor.goals.{n}.{key}', label=f'目標{n}：{label}', sheet=sheet.title, cell=cell,
            status='転記', input_type=kind, notes='', merged_range=next(str(r) for r in sheet.merged_cells.ranges if cell in r), blank_sample_value=sheet[cell].value))
fixed = [dict(sheet=sheet.title, cell=c.coordinate, label=str(c.value)) for row in sheet for c in row
         if c.value is not None and c.coordinate not in {m['cell'] for m in entries}]
result = dict(schema_version=1, sheets={'monitoring':sheet.title}, mappings=entries, fixed_cells=fixed,
    source_templates=[dict(id='blank', filename=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())], rules={'goals_max':4})
(root/'mappings/monitoring_mapping.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
wb.close()
