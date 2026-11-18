from datetime import date, time
import re

class ValidationError(ValueError):
    pass

def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f'日付を YYYY-MM-DD で入力してください: {value}') from None

def japanese_date(value):
    d = parse_date(value)
    for start, era in ((date(2019, 5, 1), '令和'), (date(1989, 1, 8), '平成'), (date(1926, 12, 25), '昭和')):
        if d >= start:
            year = d.year - start.year + 1
            return f'{era}{"元" if year == 1 else year}年{d.month}月{d.day}日'
    return f'{d.year}年{d.month}月{d.day}日'

def period(value):
    if not isinstance(value, dict) or not value.get('start') or not value.get('end'):
        raise ValidationError('期間は開始日と終了日の両方が必要です')
    if parse_date(value['start']) > parse_date(value['end']):
        raise ValidationError('開始日が終了日より後です')
    return japanese_date(value['start']) + '\n～' + japanese_date(value['end'])

def validate_project(project, exporting=False):
    errors = []
    for key, value in project.fields.items():
        m = re.search(r'\.goals\.(\d+)\.', key)
        if m and int(m[1]) not in range(1, 5) and value not in ('', None, {}):
            errors.append('目標は最大4件です。5件以上は追加帳票とマップの拡張が必要です')
        if isinstance(value, str) and (len(value) > 32767 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value)):
            errors.append(f'{key}: Excelで扱えない文字または文字数です')
    for a, b in (('valid_from', 'valid_to'),):
        start, end = project.metadata.get(a), project.metadata.get(b)
        try:
            if start: parse_date(start)
            if end: parse_date(end)
            if start and end and start > end: errors.append('適用開始日が終了日より後です')
        except ValidationError as e: errors.append(str(e))
    for key in ('created_on', 'monitor_created_on', 'draft_created_on', 'next_review_on', 'status_date'):
        if project.metadata.get(key):
            try: parse_date(project.metadata[key])
            except ValidationError as e: errors.append(str(e))
    if project.metadata.get('status', '下書き') != '下書き':
        if not project.metadata.get('status_date'):
            errors.append('進捗状態の変更には確認日の記入が必要です')
    if project.metadata.get('status') in ('同意済み', '確定'):
        if not project.settings['consent_confirmed'].get('final') or not project.fields.get('final.consent_date'):
            errors.append('同意済み・確定には本計画の同意確認と同意日が必要です')
    if exporting and not str(project.fields.get('person.name', '')).strip():
        errors.append('Excel出力には利用者氏名が必要です')
    if errors: raise ValidationError('\n'.join(dict.fromkeys(errors)))

def meeting_text(value):
    d = parse_date(value.get('date'))
    try:
        start, end = time.fromisoformat(value['start']), time.fromisoformat(value['end'])
    except (KeyError, ValueError, TypeError):
        raise ValidationError('会議の開始・終了時刻が必要です') from None
    if start >= end: raise ValidationError('会議終了は開始より後にしてください')
    return f'{japanese_date(d.isoformat())}（{"月火水木金土日"[d.weekday()]}） {start:%H:%M}～{end:%H:%M}'
