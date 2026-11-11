"""Source selection and session discovery, with staged settings changes."""
import asyncio
from copy import deepcopy

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .source_catalog import configured_sources, source_order, windows_source_id


class SessionDiscovery(QThread):
    result = Signal(object, str)

    def run(self):
        from .sources import discover_windows_sessions
        try:
            rows = asyncio.run(asyncio.wait_for(discover_windows_sessions(), 10))
            self.result.emit(rows, '')
        except ModuleNotFoundError:
            self.result.emit([], 'Falta un componente de Windows. Ejecuta instalar.bat y vuelve a abrir MetaDATA.')
        except Exception:
            self.result.emit([], 'No se pudieron consultar las sesiones. Abre un reproductor en Windows y vuelve a detectar.')


class SourceSettings(QWidget):
    def __init__(self, config, *, demo=False, parent=None):
        super().__init__(parent)
        catalog = {row['id']: row for row in configured_sources(config)}
        self.rows = [deepcopy(catalog[key]) for key in source_order(config)]
        self.spotify_match = config.spotify_app_id_contains.casefold()
        self.demo = demo
        self.discovery = None
        self.observed = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel('Orden de prioridad de arriba hacia abajo. Consultar permite leer la fuente. Publicar permite usar sus canciones. Abre cada reproductor para detectar su sesión de Windows.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 5)
        self.table.setMinimumHeight(220)
        self.table.setHorizontalHeaderLabels(['Fuente', 'Última detección', 'Consultar', 'Publicar', 'Tipo desconocido'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.detect_button = QPushButton('Detectar reproductores')
        self.detect_button.clicked.connect(self.detect)
        buttons.addWidget(self.detect_button)
        for label, action in [('Subir', lambda: self.move(-1)), ('Bajar', lambda: self.move(1)), ('Quitar', self.remove)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.message = QLabel('Una aplicación instalada puede no exponer una sesión. La detección comprueba disponibilidad multimedia, no el audio que pasa por la consola.')
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.render()

    def render(self):
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            name = QTableWidgetItem(row['name'])
            name.setToolTip(row.get('app_id', row['name']))
            self.table.setItem(index, 0, name)
            status = self.observed.get(row['id'], 'API local' if row['id'] == 'radioboss' else 'Sin comprobar')
            self.table.setItem(index, 1, QTableWidgetItem(status))
            for column, key in ((2, 'enabled'), (3, 'publish'), (4, 'allow_unknown')):
                checkbox = QCheckBox()
                checkbox.setAccessibleName(row['name'] + ' · ' + self.table.horizontalHeaderItem(column).text())
                checkbox.setChecked(row.get(key, False))
                if row['id'] in ('radioboss', 'spotify') and key == 'allow_unknown':
                    checkbox.setEnabled(False)
                if row['id'] == 'radioboss' and key == 'publish':
                    checkbox.setEnabled(False)
                checkbox.setToolTip('Aceptar tipo desconocido puede incluir anuncios mal clasificados. Se siguen exigiendo artista y título válidos y se aplican las exclusiones.' if key == 'allow_unknown' else '')
                checkbox.toggled.connect(lambda checked, item=row, field=key: item.update({field: checked}))
                self.table.setCellWidget(index, column, checkbox)

    def move(self, offset):
        index = self.table.currentRow()
        target = index + offset
        if index < 0 or not 0 <= target < len(self.rows):
            return
        self.rows[index], self.rows[target] = self.rows[target], self.rows[index]
        self.render()
        self.table.selectRow(target)

    def remove(self):
        index = self.table.currentRow()
        if index < 0:
            return
        if self.rows[index]['id'] in ('radioboss', 'spotify'):
            self.message.setText('Puedes desactivar esta fuente con Consultar.')
            return
        self.rows.pop(index)
        self.render()

    def detect(self):
        if self.demo:
            self.message.setText('La demostración no consulta sesiones reales. Abre el modo normal para detectar reproductores.')
            return
        if self.discovery and self.discovery.isRunning():
            return
        self.message.setText('Consultando sesiones multimedia de Windows…')
        self.detect_button.setEnabled(False)
        self.discovery = SessionDiscovery(self)
        self.discovery.result.connect(self.apply_discovery)
        self.discovery.finished.connect(lambda: self.detect_button.setEnabled(True))
        self.discovery.start()

    def apply_discovery(self, sessions, error=''):
        if error:
            self.message.setText(error)
            return
        self.observed = {row['id']: 'Sin sesión visible' for row in self.rows if row['id'] != 'radioboss'}
        for session in sessions:
            app_id = session['app_id']
            key = 'spotify' if self.spotify_match in app_id.casefold() else windows_source_id(app_id)
            if not any(row['id'] == key for row in self.rows):
                if len(self.rows) >= 34:
                    break
                self.rows.append(dict(id=key, name=session['name'], app_id=app_id,
                                      enabled=False, publish=False, allow_unknown=False))
            self.observed[key] = ('Varias sesiones' if session['sessions'] > 1 else
                                  'Reproduciendo' if session['playing'] else 'Disponible · en pausa')
        self.render()
        self.message.setText('Detección terminada. Activa las fuentes que quieras consultar y autoriza su publicación. Guarda para aplicar los cambios.')

    def values(self):
        catalog = {row['id']: row for row in self.rows}
        return dict(radioboss_enabled=catalog['radioboss']['enabled'], spotify_enabled=catalog['spotify']['enabled'],
                    spotify_publish=catalog['spotify']['publish'],
                    windows_sources=[dict(row) for row in self.rows if row['id'] not in ('radioboss', 'spotify')],
                    source_priority=[row['id'] for row in self.rows])
