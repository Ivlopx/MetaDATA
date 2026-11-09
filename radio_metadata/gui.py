import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import queue
import threading

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QCloseEvent, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .config import Config
from .engine import Engine
from .model import resolve


class Worker(QThread):
    updated = Signal(object)
    failed = Signal(str)

    def __init__(self, config, directory, demo):
        super().__init__()
        self.config, self.directory, self.demo = config, directory, demo
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
            engine = Engine(self.config, self.directory, self.demo)
            engine.mode_provider = lambda: self.requested_mode
            # Clear stale text from the previous execution before the first network request.
            engine.local.publish(resolve([], engine.config), engine.config)
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
                    # Flush safe station text and logo, bypassing normal refresh/backoff.
                    for output in engine.outputs:
                        output.next_attempt = 0
                    if engine.webdav:
                        engine.webdav.next_attempt = 0
                    loop.run_until_complete(engine.publish(decision))
                except Exception:
                    self.failed.emit("No se pudo escribir el mensaje de cierre; revisa RadioCaster.")
                finally:
                    engine.close()
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de la estación")
        self.resize(760, 650)
        self.original = config
        self.fields = {}
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        def page(title):
            widget = QWidget()
            form = QFormLayout(widget)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            tabs.addTab(scroll, title)
            return form

        def text(form, key, label):
            field = QLineEdit(str(getattr(config, key)))
            self.fields[key] = field
            form.addRow(label, field)
            return field

        def check(form, key, label):
            field = QCheckBox(label)
            field.setChecked(getattr(config, key))
            self.fields[key] = field
            form.addRow(field)

        general = page("Estación")
        for key, label in (("station_name", "Nombre"), ("slogan", "Eslogan"), ("description", "Descripción"),
                           ("website", "Sitio web"), ("idle_message", "Sin música"), ("break_message", "Anuncios / pausas")):
            text(general, key, label)
        text(general, "logo_path", "Archivo de logo (opcional)")
        browse = QPushButton("Elegir logo…")
        browse.clicked.connect(self.choose_logo)
        general.addRow(browse)
        priority = QComboBox()
        priority.addItems(["radioboss", "spotify"])
        priority.setCurrentText(config.priority)
        self.fields["priority"] = priority
        general.addRow("Si ambas reproducen, preferir", priority)
        interval = QSpinBox()
        interval.setRange(1, 30)
        interval.setValue(config.poll_seconds)
        self.fields["poll_seconds"] = interval
        general.addRow("Consultar cada (segundos)", interval)

        sources = page("Fuentes")
        check(sources, "radioboss_enabled", "Consultar RadioBOSS")
        text(sources, "radioboss_url", "URL de API local")
        text(sources, "radioboss_user", "Usuario de API (opcional)")
        text(sources, "radioboss_password_env", "Variable con contraseña")
        check(sources, "spotify_enabled", "Observar Spotify en Windows")
        text(sources, "spotify_app_id_contains", "Identificador de app contiene")
        check(sources, "spotify_publish", "Permitir Spotify en selección e historial musical")
        note = QLabel("Spotify inicia solo en observación. Windows no garantiza distinguir todos los anuncios. "
                      "Comprueba la fuente y utiliza Mensaje de estación durante contenido no musical.")
        note.setWordWrap(True)
        sources.addRow(note)

        rules = page("Música y exclusiones")
        for key, label in (("music_folders", "Carpetas aprobadas de música RadioBOSS"),
                           ("excluded_folders", "Carpetas excluidas"),
                           ("excluded_terms", "Palabras / frases excluidas"),
                           ("excluded_types", "Tipos RadioBOSS excluidos")):
            field = QPlainTextEdit("\n".join(getattr(config, key)))
            field.setMaximumHeight(95)
            self.fields[key] = field
            rules.addRow(label + "\n(una por línea)", field)
        browse_folder = QPushButton("Agregar carpeta de música…")
        browse_folder.clicked.connect(self.choose_folder)
        rules.addRow(browse_folder)
        tip = QLabel("Sin carpetas aprobadas, RadioBOSS emite el mensaje de estación. "
                     "Guarda jingles y anuncios fuera de ellas y configura sus tipos en RadioBOSS.")
        tip.setWordWrap(True)
        rules.addRow(tip)

        advanced = page("Salidas")
        explanation = QLabel("La salida recomendada es nowplaying.txt → RadioCaster → ambos servidores. "
                             "Los destinos Icecast directos son opcionales y requieren permiso del servidor. "
                             "No uses dos escritores para el mismo mount. Consulta docs/CONEXIONES.md.")
        explanation.setWordWrap(True)
        advanced.addRow(explanation)
        targets = QPlainTextEdit(json.dumps(config.icecast_targets, ensure_ascii=False, indent=2))
        self.fields["icecast_targets"] = targets
        advanced.addRow("Destinos Icecast (JSON avanzado)", targets)

        connection = page("AzuraCast y monitoreo")
        text(connection, "azuracast_url", "Panel de AzuraCast")
        text(connection, "azuracast_station", "ID de estación")
        check(connection, "remote_monitor_enabled", "Comprobar título y estado en los dos servicios")
        text(connection, "icecast_monitor_url", "Servidor de audio Icecast")
        text(connection, "icecast_monitor_mount", "Mount de la estación")
        remote_interval = QSpinBox()
        remote_interval.setRange(5, 300)
        remote_interval.setValue(config.remote_poll_seconds)
        self.fields["remote_poll_seconds"] = remote_interval
        connection.addRow("Comprobar cada (segundos)", remote_interval)
        check(connection, "azuracast_write_enabled", "Publicar artista y título directamente por AzuraCast")
        text(connection, "azuracast_key_env", "Variable con la clave API")
        restricted = QLabel("La publicación directa requiere permisos y reemplaza la ruta de títulos por RadioCaster. "
                            "La API de AzuraCast filtra álbum e imagen: esos campos quedan en nuestra salida completa. "
                            "El monitor solo observa; una coincidencia no confirma el audio de la consola.")
        restricted.setWordWrap(True)
        connection.addRow(restricted)

        covers = page("Carátulas y reproductor")
        text(covers, "stream_url", "Enlace de audio para el reproductor")
        check(covers, "local_server_enabled", "Habilitar vista de canciones y carátulas en esta computadora")
        port = QSpinBox()
        port.setRange(1024, 65535)
        port.setValue(config.local_server_port)
        self.fields["local_server_port"] = port
        covers.addRow("Puerto de la vista local", port)
        ttl = QSpinBox()
        ttl.setRange(15, 300)
        ttl.setValue(config.stale_seconds)
        self.fields["stale_seconds"] = ttl
        covers.addRow("Ocultar datos sin actualizar tras (segundos)", ttl)
        check(covers, "webdav_enabled", "Subir JSON y carátulas a un alojamiento compatible con WebDAV")
        for key, label in (("webdav_upload_url", "Carpeta HTTPS de subida"), ("webdav_public_url", "Carpeta HTTPS pública"),
                           ("webdav_username", "Usuario del alojamiento"), ("webdav_password_env", "Variable con contraseña del alojamiento")):
            text(covers, key, label)
        cover_note = QLabel("La vista usa la carátula exacta o el logo durante anuncios. Para verla en Internet se necesita "
                            "un alojamiento existente con subida WebDAV y lectura pública; subir aquí no cambia la portada de AzuraCast. "
                            "Icecast-KH puede recibir una URL para reproductores compatibles. Consulta la guía de conexiones.")
        cover_note.setWordWrap(True)
        covers.addRow(cover_note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de música")
        if folder:
            self.fields["music_folders"].appendPlainText(folder)

    def choose_logo(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Logo", filter="Imágenes (*.png *.jpg *.jpeg *.webp)")
        if filename:
            self.fields["logo_path"].setText(filename)

    def save(self):
        values = asdict(self.original)
        try:
            for key, field in self.fields.items():
                if isinstance(field, QLineEdit):
                    values[key] = field.text().strip()
                elif isinstance(field, QCheckBox):
                    values[key] = field.isChecked()
                elif isinstance(field, QComboBox):
                    values[key] = field.currentText()
                elif isinstance(field, QSpinBox):
                    values[key] = field.value()
                elif key == "icecast_targets":
                    values[key] = json.loads(field.toPlainText())
                else:
                    values[key] = [v.strip() for v in field.toPlainText().splitlines() if v.strip()]
            self.result_config = Config(**values)
            self.result_config.validate()
        except (ValueError, TypeError, AttributeError) as error:
            QMessageBox.warning(self, "Revisar ajustes", str(error))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, store, config, demo=False):
        super().__init__()
        self.store, self.config, self.demo = store, config, demo
        self.exiting = False
        self.setWindowTitle("Radio Metadata • " + ("DEMOSTRACIÓN" if demo else config.station_name))
        self.resize(1040, 760)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("RADIO METADATA  /  " + ("DEMOSTRACIÓN" if demo else "ESTUDIO"))
        heading.setStyleSheet("color: #6ee7b7; font-weight: 700; letter-spacing: 2px;")
        layout.addWidget(heading)
        self.station = QLabel(config.station_name)
        self.station.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(self.station)
        warning = QLabel("La fuente seleccionada es una estimación por estado y prioridad. Verifica la consola física.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        row = QHBoxLayout()
        self.cover = QLabel("Sin carátula")
        self.cover.setFixedSize(170, 170)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet("background: #182536; border-radius: 12px;")
        row.addWidget(self.cover)
        text = QVBoxLayout()
        self.title = QLabel("Iniciando…")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 25px; font-weight: 600;")
        self.artist = QLabel("")
        self.artist.setStyleSheet("font-size: 18px; color: #a6b7ca;")
        self.album = QLabel("")
        self.active = QLabel("Fuente: estación")
        self.reason = QLabel("")
        self.reason.setWordWrap(True)
        for widget in (self.title, self.artist, self.album, self.active, self.reason):
            widget.setTextFormat(Qt.TextFormat.PlainText)
            text.addWidget(widget)
        row.addLayout(text, 1)
        layout.addLayout(row)
        controls = QHBoxLayout()
        self.mode = QComboBox()
        for label, value in (("Automático", "auto"), ("Solo RadioBOSS", "radioboss"),
                             ("Solo Spotify", "spotify"), ("Mensaje de estación", "station")):
            self.mode.addItem(label, value)
        controls.addWidget(QLabel("Selección"))
        controls.addWidget(self.mode)
        station_button = QPushButton("Mensaje de estación")
        station_button.clicked.connect(lambda: self.mode.setCurrentIndex(3))
        controls.addWidget(station_button)
        settings = QPushButton("Ajustes")
        settings.clicked.connect(self.settings)
        controls.addWidget(settings)
        preview = QPushButton("Ver carátulas")
        preview.clicked.connect(self.open_preview)
        controls.addWidget(preview)
        hide = QPushButton("Ocultar")
        hide.clicked.connect(self.hide_to_tray)
        controls.addWidget(hide)
        layout.addLayout(controls)
        if demo:
            scenarios = QComboBox()
            for label, value in (("RadioBOSS", "radioboss"), ("Spotify", "spotify"),
                                 ("Ambas reproducen", "both"), ("Anuncio", "ad"), ("Silencio", "silence")):
                scenarios.addItem(label, value)
            scenarios.currentIndexChanged.connect(lambda: self.worker.command("scenario", scenarios.currentData()))
            layout.addWidget(scenarios)
            self.scenarios = scenarios
        tabs = QTabWidget()
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(["Fecha y hora", "Fuente", "Artista", "Título", "Álbum", "Año"])
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabs.addTab(self.history, "Historial musical")
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        tabs.addTab(self.diagnostics, "Estado de fuentes y salidas")
        self.remote = QPlainTextEdit()
        self.remote.setReadOnly(True)
        self.remote.setPlainText("Activa la comprobación remota en Ajustes → AzuraCast y monitoreo. La demo no consulta servidores.")
        tabs.addTab(self.remote, "Lo que reciben los servidores")
        self.guide = QPlainTextEdit()
        self.guide.setReadOnly(True)
        self.guide.setPlainText(
            "CARÁTULAS EN AZURACAST\n\n"
            "Con permisos de administrador: Ajustes del sistema → Servicios → Album Art. "
            "Activa la consulta de portadas para Now Playing; Last.fm admite una clave opcional. "
            "Esta app no modifica ese ajuste. Comprueba varias canciones: las búsquedas pueden fallar o devolver otra edición.\n\n"
            "CARÁTULA EXACTA Y LOGO\n\nLa vista local y el reproductor exportado usan nuestra imagen de la canción y el logo "
            "en pausas/anuncios. Ocultan la canción si sus datos dejan de actualizarse. "
            "El alojamiento opcional permite compartirlo por HTTPS. No es una carga de portada en el panel de AzuraCast.\n\n"
            "OTRAS OPCIONES DEL SERVIDOR\n\nAzuraCast permite AutoDJ de respaldo, grabar programas, distintas calidades y relays "
            "hacia un segundo destino. Se configuran en su panel y dependen de los permisos. "
            "RadioCaster conserva su captura USB, programación y encoders. No se cambia el recorrido físico del audio.\n\n"
            "Consulta README y docs/CONEXIONES.md para las tres rutas de publicación y sus límites.")
        tabs.addTab(self.guide, "Conexiones y carátulas")
        layout.addWidget(tabs, 1)
        self.output_label = QLabel("Archivo para RadioCaster: " + str(store.directory / ("demo-output" if demo else "output") / "nowplaying.txt"))
        self.output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output_label.setWordWrap(True)
        layout.addWidget(self.output_label)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Radio Metadata")
        menu = QMenu()
        menu.addAction("Restaurar", self.restore)
        menu.addAction("Mensaje de estación", lambda: self.mode.setCurrentIndex(3))
        menu.addAction("Salir", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.worker = Worker(config, store.directory, demo)
        self.mode.currentIndexChanged.connect(lambda: self.worker.command("mode", self.mode.currentData()))
        self.worker.updated.connect(self.update_state)
        self.worker.failed.connect(lambda message: self.output_label.setText(message))
        self.worker.start()

    def update_state(self, payload):
        decision, snapshots, statuses, rows, *extra = payload
        self.title.setText(decision.song.title if decision.song else decision.text)
        self.artist.setText(decision.song.artist if decision.song else self.config.slogan)
        if decision.song:
            track = decision.song
            details = [track.album, track.year, track.genre]
            if track.duration_ms:
                seconds = track.duration_ms // 1000
                details.append(f"{seconds // 60}:{seconds % 60:02d}")
            self.album.setText(" · ".join(str(x) for x in details if x))
        else:
            self.album.clear()
        self.active.setText("Fuente seleccionada: " + decision.source)
        self.reason.setText(("⚠ Ambas fuentes reproducen. " if decision.conflict else "") + decision.reason)
        art = decision.song.artwork if decision.song else b""
        pixmap = QPixmap()
        if art:
            pixmap.loadFromData(art)
        if pixmap.isNull() and self.config.logo_path:
            pixmap.load(self.config.logo_path)
        if not pixmap.isNull():
            self.cover.setPixmap(pixmap.scaled(170, 170, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover.clear()
            self.cover.setText("Sin carátula")
        lines = [f"{s.source}: " + (s.error or ("reproduciendo" if s.playing else "pausado / detenido")) +
                 (f"\n  Observado (solo diagnóstico): {s.artist} — {s.title}" if s.title else "") for s in snapshots]
        lines.extend(statuses or ["Salida local: activa" if not statuses else ""])
        lines.append("Los cambios pueden tardar un intervalo de consulta más la latencia del servidor.")
        if self.demo:
            lines.append("Datos sintéticos. No se consulta ni publica a servidores; salida demo separada.")
        self.diagnostics.setPlainText("\n".join(lines))
        if extra and extra[0]:
            remote_lines = []
            for record in extra[0]:
                status = ("No disponible: " + record["error"]) if record["error"] else (
                    "Fuera de línea" if not record['online'] else ("Coincide con la selección" if record['matches'] else "Difiere de la selección; puede existir retardo"))
                remote_lines.extend([f"{record['service']}: {status}", "  Observado: " + record['text'],
                                     "  Álbum remoto: " + record.get('album', ''),
                                     "  Imagen informada: " + record.get('artwork_url', ''),
                                     "  Consultado: " + record['checked_at'], ""])
            remote_lines.append("Los datos remotos no cambian la selección ni entran al historial musical local.")
            self.remote.setPlainText("\n".join(remote_lines))
        else:
            self.remote.setPlainText("Comprobación remota desactivada o modo demo. Actívala en Ajustes → AzuraCast y monitoreo.")
        self.history.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self.history.setItem(i, j, item)
        self.tray.setToolTip(("Radio Metadata • " + decision.text)[:120])

    def settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.store.save(dialog.result_config)
            except OSError as error:
                QMessageBox.warning(self, "No se guardaron ajustes", type(error).__name__)
                return
            self.config = dialog.result_config
            self.worker.command("config", self.config)
            self.station.setText(self.config.station_name)

    def open_preview(self):
        if not self.config.local_server_enabled:
            QMessageBox.information(self, "Vista de carátulas", "Activa la vista local en Ajustes → Carátulas y reproductor.")
            return
        QDesktopServices.openUrl(QUrl(f"http://127.0.0.1:{self.config.local_server_port}/player.html"))

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    def closeEvent(self, event: QCloseEvent):
        if not self.exiting and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            self.worker.stop()
            # No forced termination: wait for bounded network calls and station-text flush.
            self.worker.wait()
            event.accept()

    def quit(self):
        self.exiting = True
        self.close()
        QApplication.quit()


STYLE = """
QWidget { background: #0d1724; color: #e5edf7; font-size: 13px; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QTableWidget {
    background: #152235; border: 1px solid #30435a; border-radius: 5px; padding: 6px;
}
QPushButton { background: #224238; border: 1px solid #38745d; padding: 9px 14px; border-radius: 6px; }
QPushButton:hover { background: #30614e; }
QHeaderView::section { background: #1e3046; padding: 8px; border: 0; }
QTabBar::tab { background: #152235; padding: 10px 16px; }
QTabBar::tab:selected { background: #284339; color: #8df5c3; }
QMenu::item:selected { background: #30614e; }
"""
