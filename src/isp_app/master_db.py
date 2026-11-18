"""R806 importer. Parse column constants as data; never execute supplied Python."""
import ast
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZipFile
from .models import now

def inspect_archive(path):
    with ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 50 * 1024 * 1024:
            raise ValueError('マスタZIPが上限50MBを超えています')
        def read(suffix):
            found = [n for n in z.namelist() if n == suffix or n.endswith('/' + suffix)]
            if len(found) != 1: raise ValueError(f'{suffix} が一意に見つかりません')
            return z.read(found[0]).decode('utf-8-sig')
        info = {k: read(k) for k in ('README.md', 'schema.sql', 'import_sqlite.py')}
        cols = {}
        for node in ast.parse(info['import_sqlite.py']).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ('SERVICE_COLS', 'ITEM_COLS'):
                        cols[target.id] = ast.literal_eval(node.value)
        if len(cols) != 2: raise ValueError('取込カラム定義がありません')
        data = {}
        for n in z.namelist():
            if not n.lower().endswith('.csv'): continue
            reader = csv.DictReader(io.StringIO(z.read(n).decode('utf-8-sig')))
            header = set(reader.fieldnames or [])
            if 'マスタID' in header: data['fee_items'] = list(reader)
            elif 'サービスID' in header and '対象区分の根拠' in header: data['services'] = list(reader)
        if set(data) != {'fee_items', 'services'}: raise ValueError('必要なCSVがありません')
        if len(data['services']) != 33 or len(data['fee_items']) != 5096:
            raise ValueError('このアダプターは R806 修正版（33サービス・5096項目）専用です。別版は専用アダプターが必要です')
        if any(not r['マスタID'].startswith('R806-') for r in data['fee_items']):
            raise ValueError('R806以外の項目を検出しました')
        return info, cols, data

def import_master(archive, destination):
    info, cols, data = inspect_archive(archive)
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=destination.parent, suffix='.sqlite'); os.close(fd)
    con = None
    try:
        con = sqlite3.connect(temp)
        # Restrict schema to its intended DDL. No attach, file writes, extensions, or triggers.
        forbidden = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_CREATE_TRIGGER,
                     sqlite3.SQLITE_CREATE_VTABLE, sqlite3.SQLITE_FUNCTION}
        def authorizer(action, a, b, db, trigger):
            if action in forbidden: return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_PRAGMA and a != 'foreign_keys': return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        con.set_authorizer(authorizer)
        con.executescript(info['schema.sql'])
        con.set_authorizer(None)
        for table, key in (('services', 'SERVICE_COLS'), ('fee_items', 'ITEM_COLS')):
            column_map = cols[key]
            actual = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
            if not set(column_map.values()) <= actual: raise ValueError('CSVとSQLのカラムが一致しません')
            if not all(str(n).replace('_', '').isalnum() for n in column_map.values()): raise ValueError('不正な列名です')
            names = ','.join('"' + n + '"' for n in column_map.values())
            con.executemany(f'INSERT INTO {table} ({names}) VALUES ({",".join("?" for _ in column_map)})',
                [[r.get(k) or None for k in column_map] for r in data[table]])
        if con.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('参照整合性エラー')
        con.execute('CREATE TABLE app_master_metadata(version TEXT, sha256 TEXT, imported_at TEXT, readme TEXT)')
        con.execute('INSERT INTO app_master_metadata VALUES(?,?,?,?)', ('R806', hashlib.sha256(Path(archive).read_bytes()).hexdigest(), now(), info['README.md']))
        con.commit(); con.close(); con = None
        os.replace(temp, destination)
    finally:
        if con: con.close()
        Path(temp).unlink(missing_ok=True)
    return {'services': len(data['services']), 'fee_items': len(data['fee_items']), 'version': 'R806'}

class MasterDB:
    def __init__(self, path): self.path = Path(path)

    def connect(self):
        if not self.path.exists(): raise ValueError('マスタ未取込です。修正版ZIPを取り込んでください')
        con = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        return con

    def query(self, sql, args=()):
        con = self.connect()
        try: return [dict(r) for r in con.execute(sql, args)]
        finally: con.close()

    def services(self): return self.query('SELECT * FROM services ORDER BY service_id')
    def metadata(self): return self.query('SELECT * FROM app_master_metadata')[0]

    def search(self, service_id='', category='', text='', limit=500, system='障害福祉', version='R806'):
        if system != '障害福祉' or version != 'R806':
            raise ValueError('未提供の制度・版です。該当マスタを追加取込する必要があります')
        clauses, args = [], []
        for col, value in (('f.service_id', service_id), ('f.category', category)):
            if value: clauses.append(col + ' = ?'); args.append(value)
        if text:
            clauses.append('(f.item_name LIKE ? OR f.condition_text LIKE ? OR f.expression LIKE ? OR f.applies_to LIKE ? OR f.master_id LIKE ?)')
            args.extend(['%' + text + '%'] * 5)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        return self.query('SELECT f.*, s.service_name FROM fee_items f JOIN services s USING(service_id)' + where + ' ORDER BY f.master_id LIMIT ?', args + [min(max(limit, 1), 6000)])

    def selection(self, master_id, effective_on, reason, confirmed=False):
        from .validation import parse_date
        parse_date(effective_on)
        if not reason.strip(): raise ValueError('選択理由を記入してください')
        rows = self.query('SELECT * FROM fee_items WHERE master_id=?', (master_id,))
        if not rows: raise ValueError('マスタIDが存在しません')
        return {'master_id': master_id, 'version': 'R806', 'master_sha256': self.metadata()['sha256'],
                'selected_at': now(), 'effective_on': effective_on, 'reason': reason,
                'confirmed': confirmed, 'item': rows[0], 'eligibility': '要確認', 'amount': None}
