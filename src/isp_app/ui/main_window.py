from copy import deepcopy
import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QComboBox, QCheckBox, QListWidget,
    QListWidgetItem, QTabWidget, QScrollArea, QSplitter, QGroupBox, QMessageBox,
    QFileDialog, QInputDialog, QDialog, QDialogButtonBox, QButtonGroup,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView)
from ..config import load_mapping, resource_root, data_root, input_status
from ..models import Project, today, now, diff
from ..storage import save_project, load_project
from ..exporter import export_excel, template_path, validate_mapping
from ..validation import validate_project
from ..master_db import MasterDB, import_master
from ..managers import ManagerDB
from ..fee_history import FeeHistoryDB, subject_of
from uuid import uuid4
from ..printing import available, print_workbook
from .widgets import Field, DateField, read_widget
from .master_dialog import MasterDialog
from .fee_picker import FeeNamePicker
from ..transfers import transfer_fields

STYLE = '''
QMainWindow { background: #f3f6f9; }
QWidget { font-family: "Yu Gothic UI"; font-size: 10pt; color: #203349; }
QToolBar { background: #173e59; spacing: 9px; padding: 9px; }
QToolBar QToolButton { color: white; padding: 7px; }
QToolBar QToolButton:hover { background: #315b77; }
QTabBar::tab { padding: 10px 12px; background: #e2eaf0; }
QTabBar::tab:selected { background: white; border-bottom: 3px solid #177a7d; }
QLineEdit, QPlainTextEdit, QComboBox, QDateEdit, QSpinBox { background: white; border: 1px solid #b9c8d4; border-radius: 4px; padding: 5px; }
QPushButton { padding: 7px 12px; background: #e4efef; border: 1px solid #a8c8c9; border-radius: 4px; }
QPushButton:hover { background: #cce5e5; }
QGroupBox { font-weight: bold; border: 1px solid #c9d6df; border-radius: 5px; margin-top: 15px; padding-top: 15px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; }
QLabel#hint { color: #627689; font-size: 9pt; }
QListWidget { background: #edf3f7; border: none; }
QPushButton#navtab { padding: 9px 16px; background: #e2eaf0; border: none; border-bottom: 3px solid transparent; border-radius: 0; }
QPushButton#navtab:hover { background: #d3e0e8; }
QPushButton#navtab:checked { background: white; border-bottom: 3px solid #177a7d; font-weight: bold; }
'''

# 上段：基本情報系、下段：工程（モニタリング → 仮計画 → 本計画 → 担当者会議）
TAB_ROWS = [['基本情報', 'アセスメント', '算定・報酬', '変更履歴 / 設定'],
            ['モニタリング', '仮計画', '本計画', '担当者会議']]

class MainWindow(QMainWindow):
    def __init__(self, root=None, data=None):
        super().__init__()
        self.root, self.data = root or resource_root(), data or data_root()
        self.data.mkdir(parents=True, exist_ok=True)
        self.project = Project(); self.path = None
        self.project.metadata['subject_id'] = self.project.project_id; self.baseline = self.project.snapshot()
        self.mapping_error = ''
        try: self.mapping = load_mapping(self.root)
        except Exception as e: self.mapping = {'mappings': [], 'sheets': {}}; self.mapping_error = str(e)
        self.db = MasterDB(self.data / 'r806.sqlite')
        monitor_map = self.root / 'mappings/monitoring_mapping.json'
        self.monitor_mapping = json.loads(monitor_map.read_text('utf-8')) if monitor_map.exists() else {'mappings': []}
        self.manager_db = ManagerDB(self.data / 'managers.sqlite')
        self.fee_history = FeeHistoryDB(self.data / 'fee_history.sqlite')
        self.widgets, self.meta_widgets, self.monitor_widgets = {}, {}, []
        self.setWindowTitle('個別支援計画 — オフライン MVP'); self.resize(1330, 900)
        self.setMinimumSize(1020, 700); self.setStyleSheet(STYLE)
        toolbar = self.addToolBar('操作'); toolbar.setMovable(False)
        actions = [('新規', self.new, 'Ctrl+N'), ('開く', self.open, 'Ctrl+O'), ('保存', self.save, 'Ctrl+S'),
            ('名前を付けて保存', lambda: self.save(True), 'Ctrl+Shift+S'), ('Excel出力', self.export, ''),
            ('印刷', self.print_dialog, ''), ('算定マスタ', self.search_master, ''), ('変更履歴', self.show_history, '')]
        self.actions = {}
        for label, fn, shortcut in actions:
            action = QAction(label, self); action.triggered.connect(lambda checked=False, f=fn: f())
            if shortcut: action.setShortcut(QKeySequence(shortcut))
            toolbar.addAction(action); self.actions[label] = action
        central = QWidget(); outer = QVBoxLayout(central); self.setCentralWidget(central)
        split = QSplitter(); outer.addWidget(split, 1)
        left = QWidget(); ll = QVBoxLayout(left); ll.addWidget(QLabel('保存済み利用者・計画'))
        self.project_list = QListWidget(); self.project_list.itemDoubleClicked.connect(self.open_recent); ll.addWidget(self.project_list)
        button = QPushButton('前計画を複製して更新'); button.clicked.connect(self.duplicate); ll.addWidget(button)
        button = QPushButton('一時保存を復元'); button.clicked.connect(self.recover); ll.addWidget(button)
        ll.addWidget(QLabel('ダブルクリックで開く\n自動一時保存：60秒ごと'))
        split.addWidget(left)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(2)
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True); self.nav_buttons = {}
        for titles in TAB_ROWS:
            row = QHBoxLayout(); row.setSpacing(2)
            for title in titles:
                b = QPushButton(title); b.setObjectName('navtab'); b.setCheckable(True)
                b.clicked.connect(lambda checked=False, t=title: self.select_tab(t))
                self.nav_group.addButton(b); self.nav_buttons[title] = b; row.addWidget(b)
            row.addStretch(); rl.addLayout(row)
        self.tabs = QTabWidget(); self.tabs.tabBar().hide(); rl.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self.sync_nav)
        split.addWidget(right); split.setSizes([230, 1100])
        self.render(); self.refresh_list()
        self.timer = QTimer(self); self.timer.timeout.connect(self.autosave); self.timer.start(60000)
        self.statusBar().showMessage('準備完了。まず基本情報を入力してください。')

    def select_tab(self, title):
        index = next((i for i in range(self.tabs.count()) if self.tabs.tabText(i) == title), -1)
        if index >= 0: self.tabs.setCurrentIndex(index)

    def sync_nav(self, index):
        button = self.nav_buttons.get(self.tabs.tabText(index)) if index >= 0 else None
        if button: button.setChecked(True)

    def error(self, error): QMessageBox.warning(self, '確認してください', str(error))

    def add_scroll(self, title, parent=None):
        target = parent or self.tabs
        area = QScrollArea(); area.setWidgetResizable(True)
        widget = QWidget(); layout = QVBoxLayout(widget); area.setWidget(widget)
        target.addTab(area, title)
        return layout

    def add_field(self, form, spec):
        editor = Field(spec, self.project.fields.get(spec['id']))
        self.widgets[spec['id']] = editor
        label = spec['label'] + ('［要確認］' if spec['status'] == '要確認' else '')
        if spec['id'] in ('monitor.notes', 'draft.notes', 'final.notes'):
            container = QWidget(); row = QHBoxLayout(container); row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(editor, 1)
            button = QPushButton('選択済みの算定名を入力')
            button.clicked.connect(lambda checked=False, key=spec['id']: self.insert_fee_names(key))
            row.addWidget(button)
            form.addRow(label, container)
        elif spec['id'] in self.MANAGER_KEYS:
            container = QWidget(); row = QHBoxLayout(container); row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(editor, 1)
            button = QPushButton('サビ管名を転記')
            button.clicked.connect(lambda checked=False, key=spec['id']: self.transfer_manager(key))
            row.addWidget(button)
            form.addRow(label, container)
        else:
            form.addRow(label, editor)

    def insert_fee_names(self, key):
        selections = [s for s in self.project.master_selections if not s.get('ended_on')]
        if not selections:
            self.error('算定・報酬で算定中の項目を選択してください。'); return
        picker = FeeNamePicker(selections, self)
        if picker.exec() != QDialog.DialogCode.Accepted: return
        self.append_fee_names(key, picker.selected_names())

    def append_fee_names(self, key, names):
        self.collect()
        existing = self.project.fields.get(key, '')
        additions = [name for name in names if name not in existing.splitlines()]
        self.project.fields[key] = '\n'.join(([existing] if existing else []) + additions)
        self.widgets[key].editor.setPlainText(self.project.fields[key])
        self.statusBar().showMessage(f'算定名を{len(additions)}件転記しました。留意事項欄で確認・修正できます。')

    def render(self):
        old = self.tabs.currentIndex(); self.tabs.clear()
        self.widgets, self.meta_widgets, self.monitor_widgets, self.consent_widgets = {}, {}, [], {}
        layout = self.add_scroll('基本情報')
        group = QGroupBox('利用者・事業所'); form = QFormLayout(group); layout.addWidget(group)
        name_spec = next((m for m in self.mapping['mappings'] if m['id'] == 'person.name'),
                         {'id': 'person.name', 'label': '利用者氏名', 'input_type': 'テキスト', 'status': '転記'})
        self.add_field(form, name_spec)
        editor = QLineEdit(self.project.metadata.get('facility_name', '')); form.addRow('事業所名', editor); self.meta_widgets['facility_name'] = editor
        b = QPushButton('基本情報を確定（利用者名・事業所名を各タブへ入力）'); b.clicked.connect(self.confirm_basic); form.addRow(b)
        confirmed = self.project.metadata.get('basic_confirmed_at', '')
        form.addRow(QLabel('確定日時：' + (confirmed[:16].replace('T', ' ') if confirmed else '未確定')))
        group = QGroupBox('計画の期間・進捗'); form = QFormLayout(group); layout.addWidget(group)
        for key, label in [('valid_from', '適用開始日'), ('valid_to', '適用終了日'), ('next_review_on', '次回確認予定'), ('status_date', '進捗の確認日')]:
            editor = DateField(self.project.metadata.get(key, '')); form.addRow(label, editor); self.meta_widgets[key] = editor
        self.status_combo = QComboBox(); self.status_combo.addItems(['下書き', '会議後', '説明済み', '同意済み', '確定'])
        self.status_combo.setCurrentText(self.project.metadata.get('status', '下書き')); form.addRow('進捗状態', self.status_combo)
        history = self.manager_db.history(self.manager_subject())
        current = history[-1][0] if history else ''
        group = QGroupBox('担当サービス管理責任者：初回登録'); form = QFormLayout(group); layout.addWidget(group)
        self.manager_name = QComboBox(); self.manager_name.setEditable(True)
        self.manager_name.addItem(''); self.manager_name.addItems(self.manager_db.names()); self.manager_name.setCurrentText(current)
        self.manager_date = DateField(history[0][1] if history else '')
        form.addRow('担当サービス管理責任者', self.manager_name); form.addRow('担当開始日', self.manager_date)
        b = QPushButton('初回登録'); b.clicked.connect(lambda: self.register_manager('initial')); form.addRow(b)
        for w in (self.manager_name, self.manager_date, b): w.setEnabled(not history)
        if history: form.addRow(QLabel('登録済みです。変更は下の「担当変更」で行ってください。'))
        group = QGroupBox('担当サービス管理責任者：担当変更'); form = QFormLayout(group); layout.addWidget(group)
        self.change_manager_name = QComboBox(); self.change_manager_name.setEditable(True)
        self.change_manager_name.addItem(''); self.change_manager_name.addItems(self.manager_db.names()); self.change_manager_name.setCurrentText('')
        self.change_manager_date = DateField('')
        form.addRow('新しい担当者', self.change_manager_name); form.addRow('変更日', self.change_manager_date)
        b = QPushButton('担当変更を保存'); b.clicked.connect(lambda: self.register_manager('change')); form.addRow(b)
        for w in (self.change_manager_name, self.change_manager_date, b): w.setEnabled(bool(history))
        if not history: form.addRow(QLabel('初回登録の後に使用できます。'))
        self.manager_history = QLabel(); self.manager_history.setWordWrap(True); form.addRow('担当履歴', self.manager_history)
        self.refresh_manager_history()
        layout.addWidget(QLabel('各タブのサービス管理責任者欄は、欄の横の「サビ管名を転記」で現在の担当者を入力します。'))
        layout.addStretch()
        layout = self.add_scroll('アセスメント'); form = QFormLayout(); layout.addLayout(form)
        for spec in self.mapping['mappings']:
            if spec['id'].startswith('assessment.'): self.add_field(form, spec)
        layout.addStretch()
        for prefix, label in [('monitor', 'モニタリング'), ('draft', '仮計画'), ('final', '本計画')]:
            layout = self.add_scroll(label)
            if prefix in ('draft', 'final'):
                button = QPushButton('モニタリングの内容を転記' if prefix == 'draft' else '仮計画の内容を転記')
                button.clicked.connect(lambda checked=False, p=prefix: self.copy_plan('monitor' if p == 'draft' else 'draft', p))
                layout.addWidget(button)
            else:
                self.monitor_layout = layout
                button = QPushButton('モニタリングExcel出力'); button.clicked.connect(self.export_monitoring); layout.addWidget(button)
            form = QFormLayout(); layout.addLayout(form)
            date_key = {'monitor': 'monitor_created_on', 'draft': 'draft_created_on', 'final': 'created_on'}[prefix]
            editor = DateField(self.project.metadata.get(date_key, ''))
            self.meta_widgets[date_key] = editor; form.addRow(label + '作成日', editor)
            specs = self.monitor_mapping['mappings'] if prefix == 'monitor' else self.mapping['mappings']
            for spec in specs:
                if spec['id'].startswith(prefix + '.') and '.goals.' not in spec['id']:
                    self.add_field(form, spec)
            consent = QCheckBox('同意を確認した（署名は自動生成しません）')
            consent.setChecked(bool(self.project.settings['consent_confirmed'].get(prefix)))
            self.consent_widgets[prefix] = consent; layout.addWidget(consent)
            layout.addWidget(QLabel('目標は最大4件。未使用枠は空欄のままにしてください。原本のプレースホルダーは保持されます。'))
            goal_tabs = QTabWidget(); layout.addWidget(goal_tabs)
            for n in range(1, 5):
                gl = self.add_scroll(f'目標 {n}', goal_tabs); gf = QFormLayout(); gl.addLayout(gf)
                for spec in specs:
                    if spec['id'].startswith(f'{prefix}.goals.{n}.') and spec['status'] != '固定/保留': self.add_field(gf, spec)
                gl.addStretch()
            goal_tabs.setMinimumHeight(540)
            layout.addStretch()
        layout = self.add_scroll('担当者会議'); form = QFormLayout(); layout.addLayout(form)
        for spec in self.mapping['mappings']:
            if spec['id'].startswith('meeting.'): self.add_field(form, spec)
        layout.addStretch()
        self.render_monitoring(); self.render_fees(); self.render_settings()
        order = [title for titles in TAB_ROWS for title in titles]
        for target, title in enumerate(order):
            index = next(i for i in range(self.tabs.count()) if self.tabs.tabText(i) == title)
            self.tabs.tabBar().moveTab(index, target)
        for date_field in self.findChildren(DateField):
            date_field.edit.dateChanged.connect(self.update_date_warnings)
            date_field.enabled.toggled.connect(self.update_date_warnings)
        self.update_date_warnings()
        self.tabs.setCurrentIndex(max(old, 0)); self.sync_nav(self.tabs.currentIndex())
        self.actions['Excel出力'].setEnabled(not self.mapping_error)
        ok, reason = available(); self.actions['印刷'].setEnabled(ok and not self.mapping_error); self.actions['印刷'].setToolTip(reason)

    def render_monitoring(self):
        layout = self.monitor_layout
        layout.addWidget(QLabel('過去の評価記録（従来形式）は以下に保持します。今回の様式への入力は上のフォームを使用してください。'))
        bar = QHBoxLayout(); layout.addLayout(bar)
        for plan, label in [('final', '本計画'), ('draft', '仮計画')]:
            b = QPushButton(label + 'から記録を作成'); b.clicked.connect(lambda checked=False, p=plan: self.start_monitoring(p)); bar.addWidget(b)
        for record in self.project.monitoring:
            group = QGroupBox('モニタリング ' + record['recorded_on']); form = QFormLayout(group); layout.addWidget(group)
            record_widgets = {}
            for key, label in [('recorded_on', '記録日'), ('recorded_by', '記録者'), ('next_review_on', '次回確認日')]:
                w = QLineEdit(record.get(key, '')) if key == 'recorded_by' else DateField(record.get(key, ''))
                form.addRow(label, w); record_widgets[key] = w
            goal_widgets = []
            for goal in record['goals']:
                title = QLabel(f'目標 {goal["number"]}：{goal["target"]}'); title.setWordWrap(True); form.addRow(title)
                editors = {}
                for key, label in [('actual', '実績評価'), ('achievement', '達成状況'), ('response', '対応方針')]:
                    if key == 'achievement':
                        w = QComboBox(); w.addItems(['未評価', '達成', '一部達成', '未達成', '見直し']); w.setCurrentText(goal.get(key, '未評価'))
                    else: w = QPlainTextEdit(goal.get(key, '')); w.setMaximumHeight(80)
                    form.addRow(label, w); editors[key] = w
                goal_widgets.append(editors)
            self.monitor_widgets.append((record_widgets, goal_widgets))
        layout.addStretch()

    def render_fees(self):
        layout = self.add_scroll('算定・報酬')
        note = QLabel('障害福祉 R806 の検索・選択を保存します。算定可否・確定金額は要確認。介護保険や別年度への自動転用はしません。')
        note.setWordWrap(True); layout.addWidget(note)
        b = QPushButton('修正版ZIPを取り込む'); b.clicked.connect(self.import_zip); layout.addWidget(b)
        b = QPushButton('算定項目を検索・選択'); b.clicked.connect(self.search_master); b.setEnabled(self.db.path.exists()); layout.addWidget(b)
        self.actions['算定マスタ'].setEnabled(self.db.path.exists())
        if not self.db.path.exists(): layout.addWidget(QLabel('マスタ未取込のため検索は無効です。上のボタンで取込できます。'))
        for index, selection in enumerate(self.project.master_selections):
            ended = selection.get('ended_on')
            group = QGroupBox(selection['master_id'] + ' / ' + selection['version'] + ('　［算定終了］' if ended else '')); gl = QVBoxLayout(group)
            text = f'{selection["item"]["item_name"]}\n{selection["item"].get("condition_text", "")}\n{selection["item"]["expression"]}\n適用日：{selection["effective_on"]}　理由：{selection["reason"]}'
            if ended: text += f'\n終了日：{ended}　理由：{selection.get("end_reason", "")}'
            label = QLabel(text + '\n算定可否・報酬額：要確認')
            label.setWordWrap(True); gl.addWidget(label)
            row = QHBoxLayout(); gl.addLayout(row)
            b = QCheckBox('担当者が記載内容を確認済み'); b.setChecked(selection.get('confirmed', False))
            b.toggled.connect(lambda state, i=index: self.set_fee_confirmed(i, state)); row.addWidget(b); row.addStretch()
            if not ended:
                b = QPushButton('算定終了を記録'); b.clicked.connect(lambda checked=False, i=index: self.end_fee(i)); row.addWidget(b)
            layout.addWidget(group)
        history = QGroupBox('加算の変更履歴（この利用者・全計画）'); hl = QVBoxLayout(history); layout.addWidget(history)
        bar = QHBoxLayout(); hl.addLayout(bar)
        self.fee_history_filter = QComboBox(); self.fee_history_filter.addItems(['加算', '減算', '基本報酬', '注による調整', '全分類'])
        self.fee_history_filter.currentTextChanged.connect(self.refresh_fee_history)
        bar.addWidget(QLabel('分類')); bar.addWidget(self.fee_history_filter); bar.addStretch()
        self.fee_history_table = QTableWidget(); self.fee_history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fee_history_table.setMinimumHeight(260); hl.addWidget(self.fee_history_table)
        hint = QLabel('履歴は fee_history.sqlite に即時記録され、計画ファイルを保存しなくても残ります。記録の修正・削除はできません。')
        hint.setObjectName('hint'); hint.setWordWrap(True); hl.addWidget(hint)
        self.refresh_fee_history()
        layout.addStretch()

    def refresh_fee_history(self, *args):
        category = self.fee_history_filter.currentText()
        rows = self.fee_history.history(subject_of(self.project), '' if category == '全分類' else category)
        columns = [('effective_on', '適用日'), ('event', '区分'), ('category', '分類'), ('item_name', '算定項目'),
                   ('master_id', 'ID'), ('reason', '理由'), ('recorded_at', '記録日時')]
        table = self.fee_history_table; table.clearContents()
        table.setColumnCount(len(columns)); table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels([c[1] for c in columns])
        for r, row in enumerate(rows):
            row['recorded_at'] = str(row.get('recorded_at') or '')[:16].replace('T', ' ')
            for c, (key, _) in enumerate(columns): table.setItem(r, c, QTableWidgetItem(str(row.get(key) or '')))
        table.resizeColumnsToContents(); table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def ensure_subject(self):
        self.project.metadata.setdefault('subject_id', subject_of(self.project))

    def set_fee_confirmed(self, index, state):
        selection = self.project.master_selections[index]
        if bool(selection.get('confirmed')) == state: return
        selection['confirmed'] = state; self.ensure_subject()
        self.fee_history.record(self.project, selection, '確認済み' if state else '確認取消', today())
        self.refresh_fee_history()

    def end_fee(self, index):
        selection = self.project.master_selections[index]
        dialog = QDialog(self); dialog.setWindowTitle('算定終了を記録'); form = QFormLayout(dialog)
        form.addRow(QLabel(selection['item']['item_name']))
        date_field = DateField(today()); reason = QLineEdit(); reason.setPlaceholderText('終了理由（必須）')
        form.addRow('終了日', date_field); form.addRow('理由', reason)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        try: self.record_fee_end(index, date_field.value(), reason.text())
        except Exception as e: self.error(e)

    def record_fee_end(self, index, ended_on, reason):
        selection = self.project.master_selections[index]
        if not reason.strip(): raise ValueError('終了理由を記入してください')
        if not ended_on: raise ValueError('終了日を入力してください')
        if ended_on < selection['effective_on']: raise ValueError('終了日は適用日以降にしてください')
        self.collect(); self.ensure_subject()
        self.fee_history.record(self.project, selection, '終了', ended_on, reason)
        selection.update(ended_on=ended_on, end_reason=reason); self.render(); self.select_tab('算定・報酬')
        self.statusBar().showMessage('算定終了を履歴に記録しました。計画ファイルも保存してください。')

    def add_fee_selection(self, selection):
        self.collect(); self.ensure_subject()
        selection.setdefault('selection_id', str(uuid4()))
        self.project.master_selections.append(selection)
        self.fee_history.record(self.project, selection, '追加', selection['effective_on'], selection.get('reason', ''))
        self.render(); self.select_tab('算定・報酬')

    MANAGER_KEYS = ('monitor.manager', 'draft.manager', 'final.manager', 'meeting.manager', 'meeting.attendee.manager')

    def manager_subject(self):
        return self.project.metadata.get('manager_subject_id', self.project.project_id)

    def refresh_manager_history(self):
        self.manager_history.setText('\n'.join(f'{d}：{name}' for name, d, _ in self.manager_db.history(self.manager_subject())))

    def register_manager(self, kind='initial'):
        try:
            subject = self.manager_subject(); history = self.manager_db.history(subject)
            if kind == 'initial':
                if history: raise ValueError('初回登録は済んでいます。担当変更を使用してください。')
                name, effective = self.manager_name.currentText().strip(), self.manager_date.value()
            else:
                if not history: raise ValueError('先に初回登録をしてください。')
                name, effective = self.change_manager_name.currentText().strip(), self.change_manager_date.value()
            if not effective: raise ValueError('担当開始日・変更日を入力してください。')
            if not self.manager_db.register(subject, name, effective):
                self.statusBar().showMessage('担当者が同じため、履歴は追加していません。'); return
            self.collect()
            self.project.metadata.update(manager_subject_id=subject, manager_name=name, manager_effective_on=effective)
            if kind == 'initial':
                for key in self.MANAGER_KEYS: self.project.fields[key] = name
            self.render(); self.select_tab('基本情報')
            self.statusBar().showMessage('担当者をDBに保存しました。' + ('各タブの担当者欄にも入力しました。' if kind == 'initial'
                else '各タブの担当者欄は「サビ管名を転記」で更新してください。') + '計画も保存してください。')
        except Exception as e: self.error(e)

    def transfer_manager(self, key):
        history = self.manager_db.history(self.manager_subject())
        name = history[-1][0] if history else self.project.metadata.get('manager_name', '')
        if not name: self.error('基本情報で担当サービス管理責任者を初回登録してください。'); return
        self.widgets[key].editor.setText(name)
        self.statusBar().showMessage(f'サービス管理責任者「{name}」を転記しました。')

    BASIC_TARGETS = {'meeting.person': 'person.name', 'monitor.facility': 'facility_name', 'draft.facility': 'facility_name',
                     'final.facility': 'facility_name', 'meeting.facility': 'facility_name'}

    def confirm_basic(self):
        self.collect()
        name = str(self.project.fields.get('person.name', '')).strip()
        facility = self.project.metadata.get('facility_name', '').strip()
        if not name or not facility: self.error('利用者氏名と事業所名を入力してください。'); return
        for key, source in self.BASIC_TARGETS.items():
            self.project.fields[key] = name if source == 'person.name' else facility
        self.project.metadata['basic_confirmed_at'] = now()
        self.render(); self.select_tab('基本情報')
        self.statusBar().showMessage('基本情報を確定し、利用者名・事業所名を各タブへ入力しました。計画も保存してください。')

    def update_date_warnings(self, *args):
        for field in self.findChildren(DateField): field.warning.clear()
        chain = [('モニタリング作成日', self.meta_widgets['monitor_created_on'])]
        monitoring_dates = [(w['recorded_on'].value(), w['recorded_on']) for w, _ in self.monitor_widgets if w['recorded_on'].value()]
        if monitoring_dates and not self.meta_widgets['monitor_created_on'].value(): chain = [('モニタリング記録日', max(monitoring_dates, key=lambda x: x[0])[1])]
        if 'assessment.recorded_on' in self.widgets: chain.append(('アセスメント記入日', self.widgets['assessment.recorded_on'].editor))
        chain.append(('仮計画作成日', self.meta_widgets['draft_created_on']))
        if 'meeting.when' in self.widgets: chain.append(('会議開催日', self.widgets['meeting.when'].parts['date']))
        chain.append(('本計画作成日', self.meta_widgets['created_on']))
        previous = None
        for label, field in chain:
            value = field.value()
            if not value: continue
            if previous and value < previous[1]: field.warning.setText(f'警告：{previous[0]}（{previous[1]}）より前の日付です')
            if previous is None or value >= previous[1]: previous = (label, value)
        pairs = [(self.meta_widgets['valid_from'], self.meta_widgets['valid_to'])]
        for field in self.widgets.values():
            if isinstance(field.parts.get('start'), DateField): pairs.append((field.parts['start'], field.parts['end']))
        for record, _ in self.monitor_widgets: pairs.append((record['recorded_on'], record['next_review_on']))
        for prefix in ('draft', 'final'):
            consent = self.widgets.get(prefix + '.consent_date')
            if consent: pairs.append((self.meta_widgets['draft_created_on' if prefix == 'draft' else 'created_on'], consent.editor))
        for start, end in pairs:
            if start.value() and end.value() and end.value() < start.value(): end.warning.setText('警告：開始日・作成日・記録日より前の日付です')

    def render_settings(self):
        layout = self.add_scroll('変更履歴 / 設定')
        form = QFormLayout(); layout.addLayout(form)
        self.reason = QComboBox(); self.reason.addItems(['定期', 'サビ管変更', '加算変更', 'その他'])
        self.effective = DateField(today()); self.reason_detail = QLineEdit()
        form.addRow('保存時の変更理由', self.reason); form.addRow('変更基準日', self.effective); form.addRow('変更内容の補足', self.reason_detail)
        layout.addWidget(QLabel('サビ管・加算の変更が計画再作成を必須とするかは自動判定しません。担当者の判断を記録してください。'))
        b = QPushButton('未保存の差分を表示'); b.clicked.connect(self.show_diff); layout.addWidget(b)
        self.history_text = QPlainTextEdit(json.dumps(self.project.history, ensure_ascii=False, indent=2)); self.history_text.setReadOnly(True); layout.addWidget(self.history_text)
        for spec in self.mapping['mappings']:
            if spec['status'] != '要確認': continue
            row = QHBoxLayout(); layout.addLayout(row)
            label = QLabel(spec['label'] + ' — ' + spec['notes']); label.setWordWrap(True); row.addWidget(label, 1)
            b = QPushButton('表示・印刷確認を記録'); b.clicked.connect(lambda checked=False, s=spec: self.review_field(s)); row.addWidget(b)
        toggle = QPushButton('管理者向け情報を表示 ▼'); toggle.setCheckable(True); layout.addWidget(toggle)
        admin = QGroupBox('管理者向け情報（原本・マップの配置、Excel、参照資料）'); admin.setVisible(False); layout.addWidget(admin)
        toggle.toggled.connect(lambda on: (admin.setVisible(on), toggle.setText('管理者向け情報を隠す ▲' if on else '管理者向け情報を表示 ▼')))
        outer_layout, layout = layout, QVBoxLayout(admin)
        info = QLabel('\n'.join(('配置済み：' if ok else '未提供：') + name for name, ok in input_status(self.root)))
        info.setWordWrap(True); layout.addWidget(info)
        if self.mapping_error: layout.addWidget(QLabel(self.mapping_error))
        b = QPushButton('原本2点・セルマップを検査'); b.clicked.connect(self.inspect_templates); layout.addWidget(b)
        layout.addWidget(QLabel(available()[1]))
        layout.addWidget(QLabel('AI：未接続。APIキー不要・外部送信なし。添付資料はメタデータのみ保存。'))
        b = QPushButton('参照資料のメタデータを追加'); b.clicked.connect(self.add_attachment); layout.addWidget(b)
        self.attachments_label = QLabel('\n'.join(a['name'] for a in self.project.attachments)); layout.addWidget(self.attachments_label)
        outer_layout.addStretch()

    def collect(self):
        for key, widget in self.widgets.items():
            value = widget.value()
            if value is None: self.project.fields.pop(key, None)
            else: self.project.fields[key] = value
        for key, widget in self.meta_widgets.items():
            value = read_widget(widget)
            if value: self.project.metadata[key] = value
            else: self.project.metadata.pop(key, None)
        self.project.metadata['status'] = self.status_combo.currentText()
        for p, w in self.consent_widgets.items():
            if w.isChecked(): self.project.settings['consent_confirmed'][p] = True
            else: self.project.settings['consent_confirmed'].pop(p, None)
        for record, (record_widgets, goals) in zip(self.project.monitoring, self.monitor_widgets):
            record.update({k: read_widget(w) for k, w in record_widgets.items()})
            for goal, editors in zip(record['goals'], goals): goal.update({k: read_widget(w) for k, w in editors.items()})

    def guard(self):
        self.collect()
        if self.project.snapshot() == self.baseline: return True
        result = QMessageBox.question(self, '未保存の変更', '変更を保存しますか？', QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if result == QMessageBox.StandardButton.Cancel: return False
        return self.save() if result == QMessageBox.StandardButton.Save else True

    def new(self):
        if self.guard(): self.activate(Project(), None)

    def activate(self, project, path):
        self.project, self.path = project, Path(path) if path else None
        # 複製で project_id が変わっても同じ利用者の履歴を辿れるよう、利用者IDを固定する
        project.metadata.setdefault('subject_id', subject_of(project))
        self.fee_history.backfill(project)
        self.baseline = project.snapshot(); self.render()
        self.setWindowTitle(f'個別支援計画 — {self.path.name if self.path else "新規・未保存"}')

    def open(self):
        if not self.guard(): return
        path, _ = QFileDialog.getOpenFileName(self, '計画を開く', str(self.data), '個別支援計画 (*.isp)')
        if path: self.load_path(path)

    def load_path(self, path):
        try: self.activate(load_project(path), path)
        except Exception as e: self.error(e)

    def save(self, save_as=False):
        try:
            self.collect(); validate_project(self.project)
            path = self.path
            if path is None or save_as:
                name, _ = QFileDialog.getSaveFileName(self, '計画を保存', str(self.data / '新規計画.isp'), '個別支援計画 (*.isp)')
                if not name: return False
                path = Path(name if name.lower().endswith('.isp') else name + '.isp')
            candidate = Project.from_dict(self.project.to_dict())
            candidate.record_change(self.baseline, self.reason.currentText(), self.effective.value(), self.reason_detail.text())
            save_project(candidate, path)
            self.project, self.path = candidate, path; self.baseline = self.project.snapshot()
            self.history_text.setPlainText(json.dumps(candidate.history, ensure_ascii=False, indent=2))
            self.refresh_list(); self.statusBar().showMessage(f'保存しました：{path}')
            self.setWindowTitle(f'個別支援計画 — {path.name}')
            return True
        except Exception as e: self.error(e); return False

    def autosave(self):
        try:
            self.collect()
            if self.project.snapshot() != self.baseline:
                p = self.data / 'recovery' / (self.project.project_id + '.isp')
                save_project(self.project, p); self.statusBar().showMessage('未確定の入力を一時保存しました（通常保存とは別）')
        except Exception as e: self.statusBar().showMessage(f'一時保存できませんでした：{e}')

    def recover(self):
        if not self.guard(): return
        path, _ = QFileDialog.getOpenFileName(self, '一時保存を復元', str(self.data / 'recovery'), '個別支援計画 (*.isp)')
        if path:
            try: self.activate(load_project(path), None); self.statusBar().showMessage('復元しました。名前を付けて保存してください。')
            except Exception as e: self.error(e)

    def refresh_list(self):
        self.project_list.clear()
        paths = list(self.data.glob('*.isp'))
        if self.path and self.path not in paths: paths.insert(0, self.path)
        for path in paths:
            try:
                p = load_project(path); item = QListWidgetItem(f'{p.fields.get("person.name", "氏名未入力")}\n{path.name}')
                item.setData(Qt.ItemDataRole.UserRole, str(path)); self.project_list.addItem(item)
            except Exception: pass

    def open_recent(self, item):
        if self.guard(): self.load_path(item.data(Qt.ItemDataRole.UserRole))

    def duplicate(self):
        if self.guard():
            duplicate = self.project.duplicate(); self.activate(duplicate, None)
            self.statusBar().showMessage('同一利用者の更新案を複製しました。同意と進捗は再確認してください。')

    def copy_draft(self):
        self.copy_plan('draft', 'final')

    def copy_plan(self, source, target):
        self.collect()
        if QMessageBox.question(self, '共通項目の転記', '転記先の共通項目を、転記元の内容（空欄を含む）で置き換えます。よろしいですか？\n書類タイトルと同意確認・進捗は引き継ぎません。') != QMessageBox.StandardButton.Yes: return
        specs = self.mapping['mappings'] + self.monitor_mapping['mappings']
        common = lambda p: {m['id'].split('.', 1)[1] for m in specs if m['id'].startswith(p + '.') and m['status'] != '固定/保留'}
        transfer_fields(self.project, source, target, (common(source) & common(target)) - {'title'})
        dates = {'monitor': 'monitor_created_on', 'draft': 'draft_created_on', 'final': 'created_on'}
        self.project.metadata[dates[target]] = self.project.metadata.get(dates[source], '')
        self.render()

    def export_monitoring(self):
        try:
            self.collect()
            path, _ = QFileDialog.getSaveFileName(self, 'モニタリングExcel出力', str(self.data / 'モニタリング.xlsx'), 'Excel (*.xlsx)')
            if path:
                export_excel(self.project, self.monitor_mapping, self.root, path)
                self.statusBar().showMessage('モニタリングを指定書式で出力しました。')
        except Exception as e: self.error(e)

    def start_monitoring(self, plan):
        try: self.collect(); self.project.start_monitoring(plan); self.render()
        except Exception as e: self.error(e)

    def import_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, 'R806修正版ZIPを選択', str(self.root / 'resources/r806_fee_master_fixed.zip'), 'ZIP (*.zip)')
        if not path: return
        try:
            result = import_master(path, self.db.path); self.collect(); self.render()
            QMessageBox.information(self, '取込完了', f'{result["services"]}サービス・{result["fee_items"]}項目を取り込みました。')
        except Exception as e: self.error(e)

    def search_master(self):
        try:
            dialog = MasterDialog(self.db, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.add_fee_selection(dialog.selection_result)
        except Exception as e: self.error(e)

    def review_field(self, spec):
        text, ok = QInputDialog.getText(self, '表示・印刷確認の記録', '原本/出力の表示・印刷を確認した担当者名と検証記録（出力ファイル・結果）を入力してください。')
        if ok and text.strip():
            self.project.settings['reviewed_fields'][spec['id']] = {'reviewer': text, 'date': today(), 'evidence': text}
            self.statusBar().showMessage(spec['label'] + ' の確認を記録しました。次回出力から転記します。')

    def show_history(self): self.select_tab('変更履歴 / 設定')

    def show_diff(self):
        self.collect(); self.history_text.setPlainText(json.dumps(diff(self.baseline, self.project.snapshot()), ensure_ascii=False, indent=2))

    def inspect_templates(self):
        try:
            from openpyxl import load_workbook
            result = []
            for spec in self.mapping['source_templates']:
                wb = load_workbook(template_path(self.root, self.mapping, spec['id']))
                try: result.append(f'{spec["id"]}: {validate_mapping(wb, self.mapping)}セル、ハッシュ一致')
                finally: wb.close()
            QMessageBox.information(self, '原本検査', '\n'.join(result) + '\n記載例からの出力は無効です。')
        except Exception as e: self.error(e)

    def add_attachment(self):
        import hashlib
        path, _ = QFileDialog.getOpenFileName(self, '参照資料を登録')
        if path:
            p = Path(path); self.project.attachments.append({'name': p.name, 'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'added_at': now()})
            self.attachments_label.setText('\n'.join(a['name'] for a in self.project.attachments))

    def export(self, destination=None):
        try:
            self.collect()
            if destination is None:
                template, ok = QInputDialog.getItem(self, 'Excel原本を選択', '出力元（記載例は比較検証専用で出力不可）', ['未記入原本 — 標準の新規出力'], 0, False)
                if not ok: return None
                destination, _ = QFileDialog.getSaveFileName(self, 'Excel出力', str(self.data / '個別支援計画.xlsx'), 'Excel (*.xlsx)')
                if not destination: return None
            result = export_excel(self.project, self.mapping, self.root, destination)
            message = 'Excelを出力しました。文字の収まりはプレビューで確認してください。'
            if result['warnings']: message += '\n' + '\n'.join(result['warnings'])
            self.statusBar().showMessage(message)
            if result['warnings']: QMessageBox.information(self, '未転記の確認項目', message)
            return Path(destination)
        except Exception as e: self.error(e); return None

    def print_dialog(self):
        d = QDialog(self); d.setWindowTitle('印刷対象とプレビュー'); layout = QVBoxLayout(d)
        layout.addWidget(QLabel('現在の入力から印刷用Excelを作成します。\nアセスメント・会議録は候補の印刷範囲を一時コピーに適用します。'))
        checks = []
        for key, name in self.mapping['sheets'].items():
            w = QCheckBox(name); w.setChecked(True); checks.append(w); layout.addWidget(w)
        mode = QComboBox(); mode.addItems(['Excelプレビュー', 'プリンター選択・印刷', 'PDFプレビューを保存']); layout.addWidget(mode)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(d.accept); buttons.rejected.connect(d.reject); layout.addWidget(buttons)
        if d.exec() != QDialog.DialogCode.Accepted: return
        try:
            import tempfile
            with tempfile.TemporaryDirectory(prefix='isp-output-') as folder:
                path = self.export(Path(folder) / 'plan.xlsx')
                if not path: return
                pdf = None
                if mode.currentIndex() == 2:
                    pdf, _ = QFileDialog.getSaveFileName(self, 'PDFを保存', str(self.data / '個別支援計画.pdf'), 'PDF (*.pdf)')
                    if not pdf: return
                print_workbook(path, [w.text() for w in checks if w.isChecked()], self.mapping,
                               ['preview', 'print', 'pdf'][mode.currentIndex()], pdf)
        except Exception as e: self.error(e)

    def closeEvent(self, event):
        if self.guard(): event.accept()
        else: event.ignore()
