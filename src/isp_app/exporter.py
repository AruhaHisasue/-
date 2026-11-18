"""Validate with openpyxl; patch only permitted OOXML cells to retain native features."""
from collections import defaultdict
from copy import deepcopy
from datetime import date
import hashlib
import os
from pathlib import Path
import re
import tempfile
from xml.dom import minidom
from zipfile import ZipFile
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.datetime import to_excel
from .validation import ValidationError, validate_project, parse_date, japanese_date, period, meeting_text

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

def template_path(root, mapping, template_id='blank'):
    spec = next(t for t in mapping['source_templates'] if t['id'] == template_id)
    path = Path(root) / 'templates' / spec['filename']
    if not path.exists(): raise ValidationError(f'原本がありません: {path.name}')
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
        raise ValidationError(f'原本のハッシュが一致しません: {path.name}。別の利用者情報の混入を防ぐため出力停止')
    return path

def validate_mapping(wb, mapping):
    seen, ids = set(), set()
    for name in mapping['sheets'].values():
        if name not in wb.sheetnames: raise ValidationError(f'シート名が一致しません: {name!r}')
    fixed = {(m['sheet'], m['cell']) for m in mapping['fixed_cells']}
    for m in mapping['mappings']:
        key = (m['sheet'], m['cell'])
        if key in seen or m['id'] in ids: raise ValidationError(f'マップ重複: {m["id"]}')
        seen.add(key); ids.add(m['id'])
        if m['status'] not in ('転記', '条件付き', '要確認', '固定/保留'):
            raise ValidationError('不明な転記区分です')
        if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]*', m['cell']): raise ValidationError('セル番地が不正です')
        if m['sheet'] not in wb.sheetnames: raise ValidationError('シートが存在しません')
        ws = wb[m['sheet']]
        max_row, max_column = ws.max_row, ws.max_column
        c = ws[m['cell']]
        if c.row > max_row or c.column > max_column or isinstance(c, MergedCell):
            raise ValidationError(f'結合セル左上以外または範囲外: {key}')
        actual = next((str(r) for r in ws.merged_cells.ranges if m['cell'] in r), '')
        if actual != m.get('merged_range', ''): raise ValidationError(f'結合範囲がマップと不一致: {key}')
        if key in fixed and m['status'] != '固定/保留': raise ValidationError(f'固定セルと転記先が衝突: {key}')
    return len(seen)

def format_value(m, value, project):
    key = m['id']
    prefix = key.split('.')[0]
    if key.endswith('.consent_date'):
        if not project.settings['consent_confirmed'].get(prefix):
            raise ValidationError('同意日は同意確認をチェックした場合だけ出力できます')
        return japanese_date(value)
    if key == 'assessment.recorded_on': return parse_date(value)
    if key == 'meeting.when': return meeting_text(value)
    if key.endswith(('.support_period', '.evaluation_period')): return period(value)
    if key.endswith('.standard_hours'):
        if not isinstance(value, dict) or not value.get('confirmed'):
            raise ValidationError('提供時間は利用者ごとの確認が必要です')
        labels = {'hours': '提供時間', 'lunch': '昼食', 'transport': '送迎配慮', 'disability': '障害特性への配慮', 'transfer': '移乗等'}
        text = '\n'.join(f'{label}：{value[k]}' for k, label in labels.items() if value.get(k))
        if not text: raise ValidationError('提供時間等の入力がありません')
        return text
    if key.endswith('.provider'):
        if not isinstance(value, dict): raise ValidationError('担当者・提供機関は構造化入力が必要です')
        return '\n'.join(f'{label}：{value[k]}' for k, label in (('staff', '担当者'), ('agency', '提供機関')) if value.get(k))
    if key.endswith('.support') and '.goals.' in key:
        if not isinstance(value, dict): raise ValidationError('支援内容・ポイントは構造化入力が必要です')
        return value.get('text', '') + ('\n（ポイント）' + value['points'] if value.get('points') else '')
    if key.endswith(('.long_term_goal', '.short_term_goal')):
        if not isinstance(value, dict): raise ValidationError('目標・期間は構造化入力が必要です')
        return value.get('text', '') + ('\n' + period(value['period']) if value.get('period') else '')
    if key in ('monitor.manager', 'draft.manager', 'final.manager'):
        return 'サービス管理責任者氏名：' + str(value).removeprefix('サービス管理責任者氏名：')
    if key.endswith('.priority'):
        if type(value) is not int or value < 1: raise ValidationError('優先順位は1以上の整数です')
        return value
    if not isinstance(value, str): raise ValidationError(f'{m["label"]}: 文字列を入力してください')
    if key.endswith('.category') and value not in ('本人', '家族', '医療', '地域'):
        raise ValidationError('支援区分は本人・家族・医療・地域から選択してください')
    return value

def prepare_writes(project, mapping):
    validate_project(project, exporting=True)
    writes = defaultdict(dict)
    warnings = []
    for m in mapping['mappings']:
        key, status = m['id'], m['status']
        value = project.fields.get(key)
        if key == 'meeting.person' and not value: value = project.fields.get('person.name')
        if status == '固定/保留': continue
        if value in (None, '', {}):
            # Default is preserve. Clearing requires an explicitly chosen per-field policy.
            if status == '転記' and project.settings['empty_policy'].get(key) == 'clear' and not m.get('blank_sample_value'):
                writes[m['sheet']][m['cell']] = None
            continue
        if status == '要確認':
            evidence = project.settings['reviewed_fields'].get(key)
            if not isinstance(evidence, dict) or not all(evidence.get(k) for k in ('reviewer', 'date', 'evidence')):
                warnings.append(f'{m["label"]}: 未確認のため転記していません')
                continue
            parse_date(evidence['date'])
        try:
            result = format_value(m, value, project)
            if isinstance(result, str) and (len(result) > 32767 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', result)):
                raise ValidationError('文字数上限または制御文字を検出しました')
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationError(f'{m["label"]}: {e}') from e
        writes[m['sheet']][m['cell']] = result
    return writes, warnings

def _elements(node, local):
    return node.getElementsByTagNameNS(NS, local)

def _patch_sheet(raw, changes, date_styles, epoch):
    doc = minidom.parseString(raw)
    cells = {c.getAttribute('r'): c for c in _elements(doc, 'c')}
    sheet_data = _elements(doc, 'sheetData')[0]
    for address, value in changes.items():
        c = cells.get(address)
        if c is None:
            row_num = re.search(r'\d+', address)[0]
            row = next((r for r in _elements(doc, 'row') if r.getAttribute('r') == row_num), None)
            if row is None:
                row = doc.createElementNS(NS, 'row'); row.setAttribute('r', row_num)
                later = next((r for r in _elements(sheet_data, 'row') if int(r.getAttribute('r')) > int(row_num)), None)
                sheet_data.insertBefore(row, later)
            c = doc.createElementNS(NS, 'c'); c.setAttribute('r', address)
            from openpyxl.utils.cell import column_index_from_string
            col = lambda a: column_index_from_string(re.match(r'[A-Z]+', a)[0])
            later = next((x for x in _elements(row, 'c') if col(x.getAttribute('r')) > col(address)), None)
            row.insertBefore(c, later)
        for child in list(c.childNodes):
            if child.nodeType == child.ELEMENT_NODE and child.localName in ('v', 'f', 'is'):
                c.removeChild(child)
        c.removeAttribute('t') if c.hasAttribute('t') else None
        if value is None: continue
        if isinstance(value, date):
            c.setAttribute('s', str(date_styles[int(c.getAttribute('s') or 0)]))
            value = to_excel(value, epoch)
        if isinstance(value, (int, float)):
            node = doc.createElementNS(NS, 'v'); node.appendChild(doc.createTextNode(str(value))); c.appendChild(node)
        else:
            # inlineStr prevents formula injection even when text starts with '='.
            c.setAttribute('t', 'inlineStr')
            inline = doc.createElementNS(NS, 'is'); node = doc.createElementNS(NS, 't')
            node.setAttribute('xml:space', 'preserve'); node.appendChild(doc.createTextNode(str(value)))
            inline.appendChild(node); c.appendChild(inline)
    return doc.toxml(encoding='utf-8')

def export_excel(project, mapping, root, destination):
    if project.template_id != 'blank': raise ValidationError('記入済み原本からの出力は無効です。未記入原本を選択してください')
    source = template_path(root, mapping)
    destination = Path(destination)
    if destination.suffix.lower() != '.xlsx': raise ValidationError('出力拡張子は .xlsx にしてください')
    if destination.resolve() in {template_path(root, mapping, t['id']).resolve() for t in mapping['source_templates'] if (Path(root)/'templates'/t['filename']).exists()}:
        raise ValidationError('原本ファイルへの上書きは禁止です')
    wb = load_workbook(source)
    try:
        validate_mapping(wb, mapping)
        writes, warnings = prepare_writes(project, mapping)
        fixed = {(m['sheet'], m['cell']) for m in mapping['fixed_cells']}
        date_styles = {}
        for sheet, changes in writes.items():
            for cell, value in changes.items():
                if (sheet, cell) in fixed or wb[sheet][cell].data_type == 'f':
                    raise ValidationError('固定セルまたは数式の変更を検出しました')
        with ZipFile(source) as z:
            replacements = {}
            workbook = minidom.parseString(z.read('xl/workbook.xml'))
            rels = minidom.parseString(z.read('xl/_rels/workbook.xml.rels'))
            targets = {r.getAttribute('Id'): r.getAttribute('Target') for r in rels.getElementsByTagName('Relationship')}
            sheet_entries = {}
            for s in _elements(workbook, 'sheet'):
                target = targets[s.getAttribute('r:id')]
                sheet_entries[s.getAttribute('name')] = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            for sheet, changes in writes.items():
                raw_sheet = minidom.parseString(z.read(sheet_entries[sheet]))
                raw_styles = {c.getAttribute('r'): int(c.getAttribute('s') or 0) for c in _elements(raw_sheet, 'c')}
                for cell, value in changes.items():
                    if isinstance(value, date): date_styles[raw_styles.get(cell, 0)] = None
            if date_styles:
                doc = minidom.parseString(z.read('xl/styles.xml'))
                xfs = _elements(doc, 'cellXfs')[0]
                styles = [x for x in xfs.childNodes if x.nodeType == x.ELEMENT_NODE]
                for old_id in date_styles:
                    clone = styles[old_id].cloneNode(True); clone.setAttribute('numFmtId', '14')
                    date_styles[old_id] = len(styles); xfs.appendChild(clone); styles.append(clone)
                xfs.setAttribute('count', str(len(styles)))
                replacements['xl/styles.xml'] = doc.toxml(encoding='utf-8')
            # Resolve sheet filenames through workbook relationships, never assume sheet1 order.
            for name, entry in sheet_entries.items():
                if not writes.get(name): continue
                replacements[entry] = _patch_sheet(z.read(entry), writes[name], date_styles, wb.epoch)
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=destination.parent, suffix='.xlsx'); os.close(fd)
            try:
                with ZipFile(name, 'w') as out:
                    for item in z.infolist(): out.writestr(item, replacements.get(item.filename, z.read(item.filename)))
                check = load_workbook(name)
                validate_mapping(check, mapping); check.close()
                os.replace(name, destination)
            finally: Path(name).unlink(missing_ok=True)
        return {'written': {k: list(v) for k, v in writes.items()}, 'warnings': warnings}
    finally: wb.close()
