from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLineEdit,
    QPlainTextEdit, QComboBox, QCheckBox, QDateEdit, QSpinBox, QLabel, QGroupBox)

class DateField(QWidget):
    def __init__(self, value='', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox('入力')
        self.edit = QDateEdit(QDate.currentDate()); self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat('yyyy-MM-dd')
        self.enabled.toggled.connect(self.edit.setEnabled)
        self.warning = QLabel(); self.warning.setStyleSheet('color: #c62828;'); self.warning.setWordWrap(True)
        layout.addWidget(self.enabled); layout.addWidget(self.edit); layout.addWidget(self.warning, 1)
        self.set_value(value)

    def set_value(self, value):
        self.enabled.setChecked(bool(value)); self.edit.setEnabled(bool(value))
        if value: self.edit.setDate(QDate.fromString(value, 'yyyy-MM-dd'))

    def value(self):
        return self.edit.date().toString('yyyy-MM-dd') if self.enabled.isChecked() else ''

class Field(QWidget):
    def __init__(self, spec, value=None):
        super().__init__()
        self.spec, self.parts = spec, {}
        key, kind = spec['id'], spec['input_type']
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.mode = 'text'
        if key.endswith(('.support_period', '.evaluation_period')):
            self.mode = 'period'; self.structured(layout, [('start', '開始日', 'date'), ('end', '終了日', 'date')], value)
        elif key == 'meeting.when':
            self.mode = 'struct'; self.structured(layout, [('date', '開催日', 'date'), ('start', '開始 HH:MM', 'text'), ('end', '終了 HH:MM', 'text')], value)
        elif key.endswith('.standard_hours'):
            self.mode = 'struct'; self.structured(layout, [('hours', '提供時間', 'text'), ('lunch', '昼食', 'text'), ('transport', '送迎配慮', 'text'), ('disability', '障害特性への配慮', 'text'), ('transfer', '移乗等', 'text'), ('confirmed', '本人の提供条件を確認した', 'check')], value)
        elif key.endswith('.provider'):
            self.mode = 'struct'; self.structured(layout, [('staff', '担当者', 'text'), ('agency', '提供機関', 'text')], value)
        elif '.goals.' in key and key.endswith('.support'):
            self.mode = 'struct'; self.structured(layout, [('text', '支援内容', 'multi'), ('points', '支援上のポイント', 'multi')], value)
        elif key.endswith(('.long_term_goal', '.short_term_goal')):
            self.mode = 'goal'; value = value or {}
            self.structured(layout, [('text', '目標', 'multi'), ('start', '開始日', 'date'), ('end', '終了日', 'date')],
                {'text': value.get('text', ''), **value.get('period', {})})
        elif kind == '日付':
            self.mode = 'date'; self.editor = DateField(value or ''); layout.addWidget(self.editor)
        elif kind == '整数':
            self.mode = 'integer'; self.editor = QSpinBox(); self.editor.setRange(0, 999)
            self.editor.setSpecialValueText('未入力'); self.editor.setValue(value or 0); layout.addWidget(self.editor)
        elif kind.startswith('選択') or key.endswith('.title'):
            self.mode = 'choice'; self.editor = QComboBox()
            choices = ['']
            if '.adl.' in key: choices += ['自立', '見守り', '介助']
            elif key.endswith('.category'): choices += ['本人', '家族', '医療', '地域']
            elif 'rating' in key: choices += ['1', '2', '3', '4', '5']
            elif key.endswith('.title'): choices += ['モニタリング'] if key.startswith('monitor.') else ['個別支援計画書', '個別支援計画書(案)']
            else: self.editor.setEditable(True)
            self.editor.addItems(choices)
            if value and value not in choices: self.editor.addItem(str(value))
            self.editor.setCurrentText(value or ''); layout.addWidget(self.editor)
        elif kind == '複数行':
            self.mode = 'multi'; self.editor = QPlainTextEdit(); self.editor.setMaximumHeight(92)
            self.editor.setPlainText(value or ''); layout.addWidget(self.editor)
        else:
            self.editor = QLineEdit(value or ''); layout.addWidget(self.editor)
        default = spec.get('blank_sample_value')
        if default is not None:
            label = QLabel('未入力時は原本表示を保持：' + str(default)); label.setWordWrap(True)
            label.setObjectName('hint'); layout.addWidget(label)
        if spec.get('notes'): self.setToolTip(spec['notes'])

    def structured(self, layout, specs, values):
        values = values or {}
        form = QFormLayout(); layout.addLayout(form)
        for key, label, kind in specs:
            if kind == 'date': w = DateField(values.get(key, ''))
            elif kind == 'check': w = QCheckBox(); w.setChecked(bool(values.get(key)))
            elif kind == 'multi':
                w = QPlainTextEdit(values.get(key, '')); w.setMaximumHeight(80)
            else: w = QLineEdit(values.get(key, ''))
            self.parts[key] = w; form.addRow(label, w)

    def value(self):
        if self.parts:
            values = {k: read_widget(w) for k, w in self.parts.items()}
            if not any(values.values()): return None
            if self.mode == 'goal':
                return {'text': values['text'], 'period': {'start': values['start'], 'end': values['end']} if values['start'] or values['end'] else {}}
            return values
        value = read_widget(self.editor)
        return value if value not in ('', 0) else None

def read_widget(widget):
    if isinstance(widget, DateField): return widget.value()
    if isinstance(widget, QPlainTextEdit): return widget.toPlainText()
    if isinstance(widget, QComboBox): return widget.currentText()
    if isinstance(widget, QCheckBox): return widget.isChecked()
    if isinstance(widget, QSpinBox): return widget.value()
    return widget.text()
