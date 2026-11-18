import json
import sqlite3
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QPlainTextEdit, QCheckBox,
    QMessageBox, QAbstractItemView)
from .widgets import DateField
from ..models import today

class MasterDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db, self.selection_result, self.rows = db, None, []
        self.setWindowTitle('算定・報酬マスタ検索 — 障害福祉 R806')
        screen = self.screen().availableGeometry()
        self.resize(min(1040, screen.width() - 40), min(640, screen.height() - 40))
        layout = QVBoxLayout(self)
        self.bookmark_path = db.path.parent / 'bookmarks.sqlite'
        with sqlite3.connect(self.bookmark_path) as con:
            con.execute('CREATE TABLE IF NOT EXISTS bookmarks (version TEXT, master_id TEXT, PRIMARY KEY(version, master_id))')
        warning = QLabel('障害福祉 R806 専用。算定可否・併算定・地域単価は要確認。確定報酬額は計算しません。介護保険・別年度は該当マスタが必要です。')
        warning.setWordWrap(True); layout.addWidget(warning)
        bar = QHBoxLayout(); layout.addLayout(bar)
        self.service = QComboBox(); self.service.addItem('全サービス', '')
        for s in db.services(): self.service.addItem(s['service_name'], s['service_id'])
        index = self.service.findText('生活介護', flags=__import__('PySide6.QtCore', fromlist=['Qt']).Qt.MatchFlag.MatchContains)
        if index >= 0: self.service.setCurrentIndex(index)
        self.category = QComboBox(); self.category.addItems(['', '基本報酬', '加算', '減算', '注による調整'])
        self.search_text = QLineEdit(); self.search_text.setPlaceholderText('項目・条件・適用範囲・計算式・ID')
        button = QPushButton('検索'); button.clicked.connect(self.search)
        for w in (self.service, self.category, self.search_text, button): bar.addWidget(w)
        self.search_text.returnPressed.connect(self.search)
        self.table = QTableWidget(); self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellClicked.connect(self.toggle_star)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_detail); layout.addWidget(self.table, 2)
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True); layout.addWidget(self.detail, 1)
        self.count = QLabel(); layout.addWidget(self.count)
        bar = QHBoxLayout(); layout.addLayout(bar)
        self.effective = DateField(today()); self.reason = QLineEdit(); self.reason.setPlaceholderText('選択理由（必須）')
        self.confirmed = QCheckBox('担当者が項目の記載内容を確認した')
        bar.addWidget(QLabel('適用日')); bar.addWidget(self.effective); bar.addWidget(self.reason)
        layout.addWidget(self.confirmed)
        choose = QPushButton('選択して計画に保存'); choose.clicked.connect(self.choose); layout.addWidget(choose)
        self.search()

    def refresh_bookmarks(self):
        with sqlite3.connect(self.bookmark_path) as con:
            self.star_ids = {r[0] for r in con.execute('SELECT master_id FROM bookmarks WHERE version=?', ('R806',))}

    def toggle_star(self, row, column):
        if column != 0 or not 0 <= row < len(self.rows): return
        master_id = self.rows[row]['master_id']
        with sqlite3.connect(self.bookmark_path) as con:
            if master_id in self.star_ids:
                con.execute('DELETE FROM bookmarks WHERE version=? AND master_id=?', ('R806', master_id))
            else: con.execute('INSERT OR IGNORE INTO bookmarks VALUES (?,?)', ('R806', master_id))
        self.search()
        for i, item in enumerate(self.rows):
            if item['master_id'] == master_id: self.table.setCurrentCell(i, 1); break

    def search(self):
        self.refresh_bookmarks()
        matches = self.db.search(self.service.currentData(), self.category.currentText(), self.search_text.text(), limit=6000)
        all_rows = self.db.search(limit=6000) if self.star_ids else []
        pinned = [r for r in all_rows if r['master_id'] in self.star_ids]
        self.rows = pinned + [r for r in matches if r['master_id'] not in self.star_ids]
        self.table.clearContents()
        columns = [('star', '★'), ('master_id', 'ID'), ('service_name', 'サービス'), ('category', '分類'), ('item_name', '算定項目'), ('condition_text', '区分・条件'), ('expression', '計算式原文')]
        self.table.setColumnCount(len(columns)); self.table.setRowCount(len(self.rows))
        self.table.setHorizontalHeaderLabels([x[1] for x in columns])
        for i, row in enumerate(self.rows):
            for j, (key, _) in enumerate(columns):
                value = ('★' if row['master_id'] in self.star_ids else '☆') if key == 'star' else str(row.get(key) or '')
                item = QTableWidgetItem(value)
                if key == 'star': item.setToolTip('クリックでブックマーク登録 / 解除')
                self.table.setItem(i, j, item)
        for col, width in enumerate([40, 110, 140, 90, 210, 260, 200]): self.table.setColumnWidth(col, width)
        self.count.setText(f'★ {len(pinned)}件を同じ一覧の先頭に固定表示（検索条件外も表示）。☆ / ★をクリックして登録・解除。')
        self.count.setWordWrap(True)
        self.detail.clear()

    def show_detail(self):
        i = self.table.currentRow()
        if 0 <= i < len(self.rows): self.detail.setPlainText(json.dumps(self.rows[i], ensure_ascii=False, indent=2))

    def choose(self):
        try:
            i = self.table.currentRow()
            if i < 0: raise ValueError('項目を選択してください')
            self.selection_result = self.db.selection(self.rows[i]['master_id'], self.effective.value(), self.reason.text(), self.confirmed.isChecked())
            self.accept()
        except ValueError as e: QMessageBox.warning(self, '入力確認', str(e))
