"""加算・算定項目の履歴DB。追記専用（記録の更新・削除は行わない）。"""
import sqlite3
from .models import now
from .validation import parse_date

EVENTS = ('追加', '終了', '確認済み', '確認取消')


def selection_key(selection):
    """選択ごとの不変キー。旧ファイルには selection_id がないため、IDと選択日時から決める。"""
    return selection.get('selection_id') or f"{selection['master_id']}|{selection.get('selected_at', '')}"


def subject_of(project):
    """利用者単位のID。計画の複製後も同じ値を引き継ぐ。"""
    return project.metadata.get('subject_id') or project.metadata.get('manager_subject_id') or project.project_id


class FeeHistoryDB:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as con:
            con.execute('''CREATE TABLE IF NOT EXISTS fee_events (
                id INTEGER PRIMARY KEY, subject_id TEXT NOT NULL, person_name TEXT, project_id TEXT,
                selection_key TEXT NOT NULL, master_id TEXT NOT NULL, version TEXT, item_name TEXT,
                category TEXT, event TEXT NOT NULL, effective_on TEXT, reason TEXT, recorded_at TEXT NOT NULL)''')
            # 追加・終了は1選択につき1回だけ。確認の付け外しは毎回記録する。
            con.execute('''CREATE UNIQUE INDEX IF NOT EXISTS fee_events_once ON fee_events(subject_id, selection_key, event)
                WHERE event IN ('追加', '終了')''')

    def record(self, project, selection, event, effective_on, reason=''):
        if event not in EVENTS: raise ValueError('不正な履歴区分です')
        parse_date(effective_on)
        item = selection.get('item', {})
        with sqlite3.connect(self.path) as con:
            cur = con.execute('''INSERT OR IGNORE INTO fee_events(subject_id, person_name, project_id, selection_key, master_id,
                version, item_name, category, event, effective_on, reason, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (subject_of(project), project.fields.get('person.name', ''), project.project_id, selection_key(selection),
                 selection['master_id'], selection.get('version', ''), item.get('item_name', ''), item.get('category', ''),
                 event, effective_on, reason, now()))
            return cur.rowcount == 1

    def backfill(self, project):
        """履歴DB導入前に選択済みだった項目を「追加」として登録する（重複登録はしない）。"""
        added = 0
        for s in project.master_selections:
            added += self.record(project, s, '追加', s.get('effective_on') or s.get('selected_at', '')[:10], s.get('reason', ''))
            if s.get('ended_on'):
                added += self.record(project, s, '終了', s['ended_on'], s.get('end_reason', ''))
        return added

    def history(self, subject_id, category=''):
        sql = ('SELECT recorded_at, event, effective_on, category, item_name, master_id, reason, person_name '
               'FROM fee_events WHERE subject_id=?')
        args = [subject_id]
        if category: sql += ' AND category=?'; args.append(category)
        with sqlite3.connect(self.path) as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(sql + ' ORDER BY effective_on, id', args)]
