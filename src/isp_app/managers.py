import sqlite3
from .models import now
from .validation import parse_date

class ManagerDB:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as con:
            con.execute('CREATE TABLE IF NOT EXISTS managers (name TEXT PRIMARY KEY)')
            con.execute('CREATE TABLE IF NOT EXISTS assignments (id INTEGER PRIMARY KEY, subject_id TEXT NOT NULL, name TEXT NOT NULL, effective_on TEXT NOT NULL, recorded_at TEXT NOT NULL)')

    def names(self):
        with sqlite3.connect(self.path) as con:
            return [r[0] for r in con.execute('SELECT name FROM managers ORDER BY name')]

    def history(self, subject_id):
        with sqlite3.connect(self.path) as con:
            return con.execute('SELECT name,effective_on,recorded_at FROM assignments WHERE subject_id=? ORDER BY id', (subject_id,)).fetchall()

    def register(self, subject_id, name, effective_on):
        name = name.strip()
        if not name: raise ValueError('担当サービス管理責任者の名前を入力してください')
        parse_date(effective_on)
        with sqlite3.connect(self.path) as con:
            con.execute('BEGIN IMMEDIATE')
            previous = con.execute('SELECT name,effective_on FROM assignments WHERE subject_id=? ORDER BY id DESC LIMIT 1', (subject_id,)).fetchone()
            if previous and previous[0] == name: return False
            if previous and effective_on < previous[1]: raise ValueError('変更日は前回の担当開始日以降にしてください')
            con.execute('INSERT OR IGNORE INTO managers VALUES (?)', (name,))
            con.execute('INSERT INTO assignments(subject_id,name,effective_on,recorded_at) VALUES (?,?,?,?)', (subject_id, name, effective_on, now()))
        return True
