import asyncio
from datetime import datetime
from pathlib import Path
import queue
import threading

from PySide6.QtCore import Qt, QThread, Signal, QEvent, QTimer
from PySide6.QtGui import QCloseEvent, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QScrollArea, QGroupBox,
)

from .output_files import OutputFilesWidget
from .appearance import apply_appearance, source_name, brand_icon, status_pixmap
from .connection_status import connection_states
from .credentials import WindowsCredentials, MemoryCredentials
from .settings import SettingsDialog
from .engine import Engine
from .model import resolve
from .source_catalog import configured_sources, source_order


class Worker(QThread):
    updated = Signal(object)
    failed = Signal(str)

    def __init__(self, config, directory, demo, credentials=None):
        super().__init__()
        self.config, self.directory, self.demo = config, directory, demo
        self.credentials = credentials
        self.commands = queue.Queue()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.requested_mode = "auto"

    def command(self, name, value):
        if name == "mode":
            self.requested_mode = value
        self.commands.put((name, value))
        self.wake.set()

    def stop(self):
        self.stopping.set()
        self.wake.set()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        engine = None
        try:
            engine = Engine(self.config, self.directory, self.demo, self.credentials)
            engine.mode_provider = lambda: self.requested_mode
            # Clear stale text from the previous execution before the first network request.
            engine.local.publish(resolve([], engine.config), engine.config, engine.cache_history)
            while not self.stopping.is_set():
                self.wake.clear()
                while True:
                    try:
                        name, value = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    if name == "config":
                        engine.configure(value)
                    elif name == "mode":
                        engine.mode = value
                    elif name == "scenario":
                        engine.scenario = value
                self.updated.emit(loop.run_until_complete(engine.tick()) + (engine.remote_records,))
                self.wake.wait(engine.config.poll_seconds)
        except Exception as error:
            self.failed.emit(f"El administrador se detuvo ({type(error).__name__}). Revisa el registro y los permisos de la carpeta de datos.")
        finally:
            if engine:
                try:
                    decision = resolve([], engine.config)
                    # Clear song metadata on shutdown, bypassing normal refresh/backoff.
                    for output in engine.outputs:
                        output.next_attempt = 0
                    if engine.webdav:
                        engine.webdav.next_attempt = 0
                    if engine.receiver:
                        engine.receiver.next_attempt = 0
                    loop.run_until_complete(engine.publish(decision))
                except Exception:
                    self.failed.emit("No se pudo vaciar Now Playing al cerrar; revisa los archivos de salida.")
                finally:
                    engine.close()
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()


class MainWindow(QMainWindow):
    def __init__(self, store, config, demo=False):
        super().__init__()
        self.store, self.config, self.demo = store, config, demo
        if demo:
            from .config import ConfigStore
            self.settings_store = ConfigStore(store.directory / 'demo-settings')
        else:
            self.settings_store = store
        self.credentials = MemoryCredentials() if demo else WindowsCredentials(store.directory)
        self.history_rows = []
        self.exiting = False
        self.setWindowTitle('MetaDATA · Broadcast' + (' · Demostración' if demo else ''))
        self.resize(960, 680)
        self.setMinimumSize(760, 560)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        heading = QHBoxLayout()
        self.station = QLabel(config.station_name)
        self.station.setTextFormat(Qt.TextFormat.PlainText)
        font = self.station.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.station.setFont(font)
        heading.addWidget(self.station, 1)
        hide = QPushButton('Ocultar')
        hide.clicked.connect(self.hide_to_tray)
        heading.addWidget(hide)
        layout.addLayout(heading)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        for index in range(4):
            shortcut = QShortcut(QKeySequence(f'Ctrl+{index + 1}'), self)
            shortcut.activated.connect(lambda selected=index: self.tabs.setCurrentIndex(selected))
        preferences = QShortcut(QKeySequence('Ctrl+,'), self)
        preferences.activated.connect(lambda: self.settings())

        def page(name):
            widget = QWidget()
            content = QVBoxLayout(widget)
            content.setContentsMargins(16, 20, 16, 16)
            content.setSpacing(12)
            self.tabs.addTab(widget, name)
            return content

        home = page('Inicio')
        if demo:
            home.addWidget(QLabel('Demostración · datos de ejemplo, sin conexiones externas'))
        playback = QGroupBox('Reproducción')
        playback_layout = QVBoxLayout(playback)
        playback_layout.setContentsMargins(16, 20, 16, 16)
        playback_layout.setSpacing(16)
        home.addWidget(playback)
        row = QHBoxLayout()
        row.setSpacing(20)
        self.cover = QLabel('Sin carátula')
        self.cover.setFixedSize(144, 144)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFrameShape(QLabel.Shape.StyledPanel)
        row.addWidget(self.cover)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.setAlignment(Qt.AlignmentFlag.AlignTop)
        song_details = QVBoxLayout()
        song_details.setSpacing(2)
        song_details.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title = QLabel('Iniciando…')
        font = self.title.font()
        font.setPointSize(font.pointSize() + 5)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        self.artist, self.album = QLabel(''), QLabel('')
        self.active, self.reason = QLabel('Fuente: estación'), QLabel('')
        self.reason.setWordWrap(True)
        self.reason.setToolTip('La selección se basa en reproducción y prioridad. Comprueba qué audio está al aire en tu consola.')
        for widget in (self.title, self.artist, self.album, self.active, self.reason):
            widget.setTextFormat(Qt.TextFormat.PlainText)
        for widget in (self.title, self.artist, self.album):
            song_details.addWidget(widget)
        text.addLayout(song_details)
        text.addSpacing(8)
        text.addWidget(self.active)
        text.addWidget(self.reason)
        row.addLayout(text, 1)
        playback_layout.addLayout(row)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Fuente'))
        self.mode = QComboBox()
        self.mode.addItem('Automático', 'auto')
        for key in source_order(config):
            self.mode.addItem(brand_icon(key), 'Solo ' + source_name(key, config), key)
        self.mode.addItem('Pausar metadatos', 'station')
        controls.addWidget(self.mode)
        self.station_button = QPushButton('Pausar metadatos')
        self.station_button.clicked.connect(self.toggle_station)
        controls.addWidget(self.station_button)
        controls.addStretch()
        playback_layout.addLayout(controls)
        self.mode.setToolTip('Selección por reproducción y prioridad; verifica el audio en la consola.')
        if demo:
            self.scenarios = QComboBox()
            for label, value in [('RadioBOSS', 'radioboss'), ('Spotify', 'spotify'), ('Ambas reproducen', 'both'), ('Anuncio', 'ad'), ('Silencio', 'silence')]:
                self.scenarios.addItem(label, value)
            self.scenarios.currentIndexChanged.connect(lambda: self.worker.command('scenario', self.scenarios.currentData()))
            scenario_row = QHBoxLayout()
            scenario_row.addWidget(QLabel('Escenario de prueba'))
            scenario_row.addWidget(self.scenarios)
            scenario_row.addStretch()
            home.addLayout(scenario_row)
        home.addSpacing(8)
        home.addWidget(QLabel('Últimas canciones'))
        self.recent = QTableWidget(0, 3)
        self.recent.setHorizontalHeaderLabels(['Hora', 'Artista', 'Título'])
        self.setup_table(self.recent)
        self.recent.setMaximumHeight(145)
        self.recent.hide()
        home.addWidget(self.recent)
        self.recent_empty = QLabel('Las canciones válidas aparecerán aquí.')
        home.addWidget(self.recent_empty)
        home.addStretch()

        history_page = page('Historial')
        history_heading = QHBoxLayout()
        history_heading.addWidget(QLabel('Solo canciones con artista y título válidos'), 1)
        export = QPushButton('Exportar CSV…')
        export.clicked.connect(self.export_history)
        history_heading.addWidget(export)
        history_page.addLayout(history_heading)
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(['Fecha y hora', 'Fuente', 'Artista', 'Título', 'Álbum', 'Año'])
        self.setup_table(self.history)
        history_page.addWidget(self.history, 1)

        connections = page('Conexiones')
        connections.addWidget(QLabel('Fuentes de metadatos y archivos para tu emisor'))
        sources_button = QPushButton('Administrar fuentes y prioridades…')
        sources_button.setMaximumWidth(260)
        sources_button.clicked.connect(lambda: self.settings('Fuentes'))
        connections.addWidget(sources_button)
        source_scroll = QScrollArea()
        source_scroll.setWidgetResizable(True)
        source_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        source_widget = QWidget()
        self.connection_rows = QVBoxLayout(source_widget)
        self.connection_rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        source_scroll.setWidget(source_widget)
        connections.addWidget(source_scroll, 1)
        self.refresh_source_connections()
        details = QPushButton('Mostrar detalles')
        details.setMaximumWidth(160)
        details.setCheckable(True)
        connections.addWidget(details)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setVisible(False)
        details.toggled.connect(self.diagnostics.setVisible)
        details.toggled.connect(lambda visible: details.setText('Ocultar detalles' if visible else 'Mostrar detalles'))
        connections.addWidget(self.diagnostics, 1)

        self.settings_page = page('Ajustes')
        self.settings_tab = self.tabs.count() - 1
        self.settings_page.setContentsMargins(0, 0, 0, 0)
        self.settings_form = None
        self.output_label = QLabel('')
        self.output_label.setTextFormat(Qt.TextFormat.PlainText)
        self.output_label.setWordWrap(True)
        layout.addWidget(self.output_label)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('MetaDATA')
        menu = QMenu()
        menu.addAction('Restaurar', self.restore)
        menu.addAction('Pausar metadatos', lambda: self.mode.setCurrentIndex(self.mode.findData('station')))
        menu.addAction('Salir', self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.worker = Worker(config, store.directory, demo, self.credentials)
        self.mode.currentIndexChanged.connect(lambda: self.worker.command('mode', self.mode.currentData()))
        self.mode.currentIndexChanged.connect(lambda: self.station_button.setText('Reanudar automático' if self.mode.currentData() == 'station' else 'Pausar metadatos'))
        self.worker.updated.connect(self.update_state)
        self.worker.failed.connect(self.report_failure)
        self.rebuild_settings()
        self.worker.start()

    @staticmethod
    def setup_table(table):
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def display_time(value, short=False):
        try:
            return datetime.fromisoformat(str(value)).astimezone().strftime('%H:%M:%S' if short else '%d/%m/%Y %H:%M:%S')
        except ValueError:
            return str(value or '')

    def toggle_station(self):
        self.mode.setCurrentIndex(0 if self.mode.currentData() == 'station' else self.mode.findData('station'))

    def refresh_source_connections(self):
        while self.connection_rows.count():
            self.connection_rows.takeAt(0).widget().deleteLater()
        self.connection_labels, self.connection_dots = {}, {}
        for title, rows in (
            ('Fuentes de reproducción', configured_sources(self.config)),
            ('Salidas de metadatos', [dict(id='Now Playing', name='Now Playing'), dict(id='Receptor', name='Receptor')])):
            group = QGroupBox(title)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(16, 16, 16, 8)
            self.connection_rows.addWidget(group)
            for source in rows:
                key = source['name'] if source['id'] in ('radioboss', 'spotify') else source['id']
                destination = ('RadioBOSS' if source['id'] == 'radioboss' else
                               'Now Playing' if key == 'Now Playing' else
                               'Publicación' if key == 'Receptor' else 'Fuentes')
                widget = QWidget()
                row = QHBoxLayout(widget)
                row.setContentsMargins(0, 8, 0, 8)
                icon = QLabel()
                icon.setPixmap(brand_icon(source['name']).pixmap(24, 24))
                row.addWidget(icon)
                label = QLabel(source['name'])
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setMinimumWidth(110)
                row.addWidget(label)
                dot = QLabel()
                dot.setPixmap(status_pixmap('unknown'))
                dot.setProperty('state', 'unknown')
                row.addWidget(dot)
                status = QLabel('Esperando comprobación')
                status.setTextFormat(Qt.TextFormat.PlainText)
                status.setWordWrap(True)
                row.addWidget(status, 1)
                button = QPushButton('Configurar…')
                button.clicked.connect(lambda checked=False, page=destination: self.settings(page))
                row.addWidget(button)
                group_layout.addWidget(widget)
                self.connection_labels[key], self.connection_dots[key] = status, dot

    def refresh_source_modes(self):
        current = self.mode.currentData()
        self.mode.blockSignals(True)
        self.mode.clear()
        self.mode.addItem('Automático', 'auto')
        for key in source_order(self.config):
            self.mode.addItem('Solo ' + source_name(key, self.config), key)
        self.mode.addItem('Pausar metadatos', 'station')
        index = self.mode.findData(current)
        self.mode.setCurrentIndex(index if index >= 0 else 0)
        self.mode.blockSignals(False)
        self.worker.command('mode', self.mode.currentData())
        self.station_button.setText('Reanudar automático' if self.mode.currentData() == 'station' else 'Pausar metadatos')

    def export_history(self):
        filename, _ = QFileDialog.getSaveFileName(self, 'Exportar historial', 'historial.csv', 'CSV (*.csv)')
        if not filename:
            return
        try:
            import csv
            with open(filename, 'w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['Fecha y hora', 'Fuente', 'Artista', 'Título', 'Álbum', 'Año'])
                # Export every stored song, not only the screen's recent rows.
                from .storage import History
                history = History(self.store.directory / ('demo-history.sqlite3' if self.demo else 'history.sqlite3'))
                try:
                    rows = history.db.execute('SELECT played_at, source, artist, title, album, year FROM songs ORDER BY id DESC').fetchall()
                finally:
                    history.close()
                rows = [(row[0], source_name(row[1], self.config), *row[2:]) for row in rows]
                writer.writerows([("'" + str(v) if str(v).startswith(('=', '+', '-', '@')) else v) for v in row] for row in rows)
        except Exception:
            QMessageBox.warning(self, 'Exportar historial', 'No se pudo exportar. Revisa la ubicación y los permisos del archivo.')

    def update_state(self, payload):
        decision, snapshots, statuses, rows, *extra = payload
        self.title.setText(decision.song.title if decision.song else decision.text)
        self.artist.setText(decision.song.artist if decision.song else '')
        self.artist.setVisible(decision.song is not None)
        self.album.setVisible(decision.song is not None)
        if decision.song:
            track = decision.song
            details = [track.album, track.year, track.genre]
            if track.duration_ms:
                seconds = track.duration_ms // 1000
                details.append(f"{seconds // 60}:{seconds % 60:02d}")
            self.album.setText(" · ".join(str(x) for x in details if x))
        else:
            self.album.clear()
        self.active.setText("Fuente seleccionada: " + source_name(decision.source, self.config))
        reason = decision.reason.replace("; comprobar consola", "")
        self.reason.setText(("⚠ Varias fuentes reproducen. " if decision.conflict else "") + reason)
        art = decision.song.artwork if decision.song else b""
        pixmap = QPixmap()
        if art:
            pixmap.loadFromData(art)
        if pixmap.isNull() and self.config.logo_path:
            pixmap.load(self.config.logo_path)
        if not pixmap.isNull():
            self.cover.setPixmap(pixmap.scaled(144, 144, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover.clear()
            self.cover.setText("Sin carátula")
        lines = [f"{source_name(s.source, self.config)}: " + (s.error or ("reproduciendo" if s.playing else "pausado / detenido")) +
                 (f"\n  Observado (solo diagnóstico): {s.artist} — {s.title}" if s.title else "") for s in snapshots]
        lines.extend(statuses or ["Salida local: activa" if not statuses else ""])
        lines.append("Los cambios pueden tardar un intervalo de consulta más la latencia del servidor.")
        if self.demo:
            lines.append("Datos sintéticos. No se consulta ni publica a servidores; salida demo separada.")
        self.diagnostics.setPlainText("\n".join(lines))
        self.history_rows = rows
        self.recent.setRowCount(min(3, len(rows)))
        self.recent_empty.setVisible(not rows)
        self.recent.setVisible(bool(rows))
        for i, row in enumerate(rows[:3]):
            for j, value in enumerate((self.display_time(row[0], short=True), row[2], row[3])):
                self.recent.setItem(i, j, QTableWidgetItem(str(value or '')))
        evidence = connection_states(self.config, snapshots, statuses, extra[0] if extra else [],
                                     demo=self.demo, mode=self.mode.currentData(),
                                     local_exists=(self.output_files.directory / 'nowplaying.xml').is_file())
        for name, (state, message) in evidence.items():
            if name not in self.connection_labels:
                continue
            self.connection_labels[name].setText(message)
            self.connection_dots[name].setPixmap(status_pixmap(state))
            self.connection_dots[name].setProperty('state', state)
            self.connection_dots[name].setAccessibleName(name + ': ' + message)
        self.history.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(self.display_time(value) if j == 0 else (source_name(str(value), self.config) if j == 1 else str(value or "")))
                item.setToolTip(item.text())
                self.history.setItem(i, j, item)
        self.tray.setToolTip(("Radio Metadata • " + decision.text)[:120])

    def report_failure(self, message):
        self.output_label.setText(message)
        for name, dot in self.connection_dots.items():
            state = 'error' if name == 'Now Playing' else 'unknown'
            dot.setPixmap(status_pixmap(state))
            dot.setProperty('state', state)
            self.connection_labels[name].setText('Administrador detenido · estado sin actualizar')

    def settings(self, page='Estación'):
        self.tabs.setCurrentIndex(self.settings_tab)
        page = {'Música': 'Reglas', 'Spotify': 'Fuentes'}.get(page, page)
        if page in self.settings_form.page_names:
            self.settings_form.navigation.setCurrentRow(self.settings_form.page_names.index(page))

    def rebuild_settings(self):
        page, kind = 'Estación', 'nowplaying.xml'
        if self.settings_form is not None:
            old = self.settings_form
            page = old.page_names[old.navigation.currentRow()]
            kind = self.output_files.kind.currentData()
            self.settings_page.removeWidget(old)
            old.hide()
            old.deleteLater()
        self.settings_form = SettingsDialog(self.config, self, store=self.settings_store,
                                            credentials=self.credentials, page=page, demo=self.demo, embedded=True)
        self.settings_form.accepted.connect(self.apply_settings)
        self.settings_form.rejected.connect(self.discard_settings)
        self.settings_page.addWidget(self.settings_form)
        self.output_files = self.settings_form.findChildren(OutputFilesWidget)[0]
        self.output_files.kind.setCurrentIndex(self.output_files.kind.findData(kind))

    def apply_settings(self):
        self.config = self.settings_form.result_config
        apply_appearance(QApplication.instance(), self.config.theme)
        self.worker.command('config', self.config)
        self.refresh_source_modes()
        self.refresh_source_connections()
        self.station.setText(self.config.station_name)
        self.rebuild_settings()
        self.statusBar().showMessage('Cambios guardados', 5000)

    def discard_settings(self):
        self.rebuild_settings()
        self.statusBar().showMessage('Cambios descartados', 5000)

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def present_initially(self, *, force_hidden=False, force_visible=False):
        hidden = not self.demo and not force_visible and (force_hidden or self.config.start_hidden)
        if not hidden:
            self.showNormal()
        elif QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            self.hide()
        else:
            self.showMinimized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange and self.isMinimized()
                and self.config.minimize_to_tray and QSystemTrayIcon.isSystemTrayAvailable()):
            QTimer.singleShot(0, self.hide_if_minimized)

    def hide_if_minimized(self):
        if self.isMinimized() and self.config.minimize_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            self.hide()

    def hide_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    def closeEvent(self, event: QCloseEvent):
        will_exit = self.exiting or not self.config.close_to_tray or not QSystemTrayIcon.isSystemTrayAvailable()
        if (will_exit and self.settings_form
                and any(thread.isRunning() for thread in self.settings_form.findChildren(QThread))):
            self.settings_form.message.setText('Espera a que termine la comprobación antes de salir.')
            self.tabs.setCurrentIndex(self.settings_tab)
            event.ignore()
            return
        if not will_exit:
            self.tray.show()
            self.hide()
            event.ignore()
        else:
            self.worker.stop()
            # Wait for bounded network calls and the metadata clear.
            self.worker.wait()
            event.accept()
            QApplication.quit()

    def quit(self):
        self.exiting = True
        if self.close():
            QApplication.quit()
        else:
            self.exiting = False


STYLE = ''  # Compatibility for integrations; use the operating system palette.
