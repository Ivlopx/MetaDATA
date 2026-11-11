"""Explicit allow/block folder rules with per-rule recursion."""
from copy import deepcopy

from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .model import effective_folder_rules


class FolderSettings(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.rules = deepcopy(effective_folder_rules(config))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setMinimumHeight(180)
        self.table.setHorizontalHeaderLabels(['Lista', 'Carpeta', 'Incluir subcarpetas'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, action in [('Añadir a lista blanca…', lambda: self.choose('allow')),
                              ('Añadir a lista negra…', lambda: self.choose('block')), ('Quitar', self.remove)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.render()

    def render(self):
        self.table.setRowCount(len(self.rules))
        for index, rule in enumerate(self.rules):
            self.table.setItem(index, 0, QTableWidgetItem('Blanca · permitir' if rule['action'] == 'allow' else 'Negra · bloquear'))
            path = QTableWidgetItem(rule['path'])
            path.setToolTip(rule['path'])
            self.table.setItem(index, 1, path)
            checkbox = QCheckBox('Incluir subcarpetas')
            checkbox.setChecked(rule['recursive'])
            checkbox.toggled.connect(lambda checked, item=rule: item.update(recursive=checked))
            self.table.setCellWidget(index, 2, checkbox)

    def choose(self, action):
        path = QFileDialog.getExistingDirectory(self, 'Seleccionar carpeta')
        if path:
            self.add_rule(path, action)

    def add_rule(self, path, action, recursive=True):
        value = dict(path=path, action=action, recursive=recursive)
        if value not in self.rules:
            self.rules.append(value)
            self.render()

    def remove(self):
        index = self.table.currentRow()
        if index >= 0:
            self.rules.pop(index)
            self.render()
