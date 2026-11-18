import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
mapping = json.loads((ROOT / 'mappings/individual_support_excel_mapping.json').read_text('utf-8'))
report = {'templates': [], 'mapping_workbook': {}, 'missing': []}
for spec in mapping['source_templates']:
    path = ROOT / 'templates' / spec['filename']
    wb = load_workbook(path)
    report['templates'].append({'id': spec['id'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'hash_matches': hashlib.sha256(path.read_bytes()).hexdigest() == spec['sha256'],
        'sheets': [{'name': s.title, 'dimensions': s.calculate_dimension(), 'merged': sorted(str(r) for r in s.merged_cells.ranges),
                    'print_area': str(s.print_area), 'orientation': s.page_setup.orientation,
                    'populated_cells': sum(c.value is not None for row in s for c in row)} for s in wb]})
    wb.close()
wb = load_workbook(ROOT / 'mappings/個別支援計画_Excelセル対応表.xlsx', data_only=False)
for s in wb:
    rows = list(s.values)
    report['mapping_workbook'][s.title] = {'rows': len(rows), 'columns': s.max_column, 'headers': rows[0],
        'nonempty_values': sum(v is not None for row in rows for v in row)}
wb.close()
archive = ROOT / 'resources/r806_fee_master_fixed.zip'
with ZipFile(archive) as z:
    report['master_files'] = z.namelist()
    for n in z.namelist():
        if n in ('README.md', 'schema.sql', 'import_sqlite.py'):
            print('\nFILE', n, '\n', z.read(n).decode('utf-8-sig'))
        elif n.endswith('.csv'):
            lines = z.read(n).decode('utf-8-sig').splitlines()
            print('CSV', n, 'header:', lines[0], 'physical lines:', len(lines))
if not (ROOT / 'individual_support_plan_app_overview.txt').exists():
    report['missing'].append('individual_support_plan_app_overview.txt（任意）')
(ROOT / 'outputs/input_inspection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
