from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QCheckBox, QDialogButtonBox

class FeeNamePicker(QDialog):
    def __init__(self, selections, parent=None):
        super().__init__(parent)
        self.setWindowTitle('留意事項へ転記する算定名を選択')
        self.resize(650, 420)
        layout = QVBoxLayout(self); layout.addWidget(QLabel('転記する項目にチェックを付けてください。算定名のみ追記します。'))
        area = QScrollArea(); area.setWidgetResizable(True); body = QWidget(); rows = QVBoxLayout(body)
        self.checks = []
        for selection in selections:
            item = selection['item']; name = item['item_name']
            check = QCheckBox(name + (' / ' + item['condition_text'] if item.get('condition_text') else ''))
            check.setToolTip(selection.get('master_id', '') + ' / ' + selection.get('version', ''))
            rows.addWidget(check); self.checks.append((check, name))
        rows.addStretch(); area.setWidget(body); layout.addWidget(area)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def selected_names(self): return list(dict.fromkeys(name for check, name in self.checks if check.isChecked()))
