"""Native settings forms. Secrets are staged until the complete dialog is saved."""
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .output_files import OutputFilesWidget
from .config import Config
from .source_settings import SourceSettings
from .folder_settings import FolderSettings
from .credentials import CredentialError, MemoryCredentials, secret_id, commit_settings
from .connection_tests import OverlayCredentials, check_connection


def credential_key(service, config):
    if service == 'statistics':
        from .monitoring import stats_key
        return stats_key(config)
    if service == 'receiver':
        from .publication import publication_key
        return publication_key(config)
    if service == 'radioboss':
        return secret_id(service, config.radioboss_url, config.radioboss_user)
    return secret_id('webdav', config.webdav_upload_url, config.webdav_username)


class SecretField(QWidget):
    def __init__(self, credentials, key, parent=None):
        super().__init__(parent)
        self.credentials, self.key, self.changed = credentials, key, False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText('Sin cambios · escribe para guardar una clave')
        self.edit.textEdited.connect(self.mark_changed)
        row.addWidget(self.edit, 1)
        self.show_button = QPushButton('Mostrar')
        self.show_button.setCheckable(True)
        self.show_button.toggled.connect(self.toggle)
        row.addWidget(self.show_button)
        clear = QPushButton('Borrar')
        clear.clicked.connect(self.clear_secret)
        row.addWidget(clear)

    def mark_changed(self, *args):
        self.changed = True

    def clear_secret(self):
        self.changed = True
        self.edit.clear()
        self.edit.setPlaceholderText('Se eliminará al guardar')
        self.show_button.setChecked(False)

    def toggle(self, visible):
        if visible and not self.changed:
            try:
                self.edit.setText(self.credentials.get(self.key))
            except CredentialError as error:
                QMessageBox.warning(self, 'Clave guardada', str(error))
                self.show_button.setChecked(False)
                return
        self.edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.show_button.setText('Ocultar' if visible else 'Mostrar')

    def pending(self, key=None):
        return {(key or self.key): self.edit.text()} if self.changed else {}


class ConnectionCheck(QThread):
    result = Signal(bool, str)

    def __init__(self, service, config, credentials, directory, parent):
        super().__init__(parent)
        self.arguments = service, config, credentials, directory

    def run(self):
        import asyncio
        self.result.emit(*asyncio.run(check_connection(*self.arguments)))


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None, *, store=None, credentials=None, page='Estación', demo=False, embedded=False):
        super().__init__(parent)
        self.embedded = embedded
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle('Ajustes de MetaDATA')
        self.resize(840, 650)
        self.original, self.store, self.demo = config, store, demo
        self.data_directory = parent.store.directory if parent is not None and hasattr(parent, 'store') else (store.directory if store else Path('.'))
        self.credentials = credentials if credentials is not None else MemoryCredentials()
        self.fields, self.secrets = {}, {}
        self.checker = None
        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(150)
        self.navigation.setSpacing(3)
        self.navigation.setAccessibleName('Secciones de ajustes')
        body.addWidget(self.navigation)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.page_names = []

        def section(name):
            self.page_names.append(name)
            self.navigation.addItem(name)
            widget = QWidget()
            form = QFormLayout(widget)
            form.setContentsMargins(16, 12, 16, 12)
            form.setVerticalSpacing(12)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(widget)
            heading = QLabel(name)
            heading_font = heading.font()
            heading_font.setPointSize(heading_font.pointSize() + 3)
            heading_font.setBold(True)
            heading.setFont(heading_font)
            form.addRow(heading)
            self.pages.addWidget(scroll)
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
            return field

        def number(form, key, label, low, high):
            field = QSpinBox()
            field.setRange(low, high)
            field.setValue(getattr(config, key))
            self.fields[key] = field
            form.addRow(label, field)

        def note(form, value):
            label = QLabel(value)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label)

        def secret(form, service, label):
            field = SecretField(self.credentials, credential_key(service, config))
            self.secrets[service] = field
            form.addRow(label, field)

        def probe(form, service, label='Probar conexión'):
            button = QPushButton(label)
            button.setMaximumWidth(180)
            button.clicked.connect(lambda: self.test_connection(service, button))
            form.addRow(button)

        general = section('Estación')
        for key, label in [('station_name', 'Nombre'), ('description', 'Descripción'),
                           ('website', 'Sitio web'), ('station_genre', 'Género de la estación')]:
            text(general, key, label)
        text(general, 'logo_path', 'Logo (archivo de imagen)')
        choose = QPushButton('Elegir logo…')
        choose.setMaximumWidth(180)
        choose.clicked.connect(self.choose_logo)
        general.addRow(choose)
        theme = QComboBox()
        for label, value in [('Seguir Windows', 'system'), ('Claro', 'light'), ('Oscuro', 'dark')]:
            theme.addItem(label, value)
        theme.setCurrentIndex(theme.findData(config.theme))
        self.fields['theme'] = theme
        general.addRow('Apariencia', theme)
        note(general, 'Sin música se envían artista y título vacíos. Los mensajes y el logo se muestran solo en MetaDATA y su reproductor; no se publican como una canción.')

        messages_button = QPushButton('Personalizar mensajes visuales')
        messages_button.setMaximumWidth(250)
        messages_button.setCheckable(True)
        general.addRow(messages_button)
        messages = QWidget()
        messages_form = QFormLayout(messages)
        for key, label in [('slogan', 'Eslogan'), ('idle_message', 'Sin música'), ('break_message', 'En pausa')]:
            text(messages_form, key, label)
        messages.setVisible(False)
        messages_button.toggled.connect(messages.setVisible)
        general.addRow(messages)

        sources = section('Fuentes')
        self.source_settings = SourceSettings(config, demo=demo)
        sources.addRow(self.source_settings)

        rb = section('RadioBOSS')
        text(rb, 'radioboss_url', 'Dirección de la API')
        text(rb, 'radioboss_user', 'Usuario (opcional)')
        secret(rb, 'radioboss', 'Contraseña')
        probe(rb, 'RadioBOSS')
        note(rb, 'Activa el control remoto por HTTP en RadioBOSS. La consulta y prioridad se activan en Fuentes. La prueba consulta el estado; no controla su reproducción.')

        rules = section('Reglas')
        number(rules, 'history_visible_limit', 'Canciones visibles en historial', 10, 1000)
        number(rules, 'cover_cache_mb', 'Espacio máximo para portadas (MB)', 8, 4096)
        from .image_cache import cache_usage
        count, size = cache_usage(self.data_directory / ('demo-output' if demo else 'output'))
        rules.addRow('Uso actual de portadas', QLabel(f'{count} imágenes · {size / (1024 * 1024):.1f} MB'))
        note(rules, 'La caché conserva las portadas de las canciones visibles, sin duplicar imágenes, además de la portada y el logo actuales. Si se alcanza el límite de espacio se retiran las menos recientes. Los límites se aplican a esta computadora; el historial de texto no se borra ni se eliminan imágenes del alojamiento remoto.')
        self.folder_settings = FolderSettings(config)
        rules.addRow(self.folder_settings)
        note(rules, 'Las carpetas de la lista blanca autorizan archivos de RadioBOSS. La lista negra tiene prioridad. Cada regla permite elegir si abarca subcarpetas. Las exclusiones de palabras y tipos también se aplican a las fuentes multimedia.')
        for key, label in [('excluded_terms', 'Palabras excluidas'), ('excluded_types', 'Tipos excluidos')]:
            field = QPlainTextEdit('\n'.join(getattr(config, key)))
            field.setMaximumHeight(80)
            self.fields[key] = field
            rules.addRow(label + '\nUna por línea', field)

        caster = section('Now Playing')
        self.title_presets = QComboBox()
        presets = [('Canción - Artista', '{title} - {artist}'), ('Artista - Canción', '{artist} - {title}'),
                   ('Solo canción', '{title}'), ('Canción - Artista (Álbum)', '{title} - {artist} ({album})'),
                   ('Personalizado…', None)]
        for label, value in presets:
            self.title_presets.addItem(label, value)
        index = self.title_presets.findData(config.title_format)
        self.title_presets.setCurrentIndex(index if index >= 0 else len(presets) - 1)
        caster.addRow('Formato del título combinado', self.title_presets)
        title_format = QLineEdit(config.title_format)
        self.fields['title_format'] = title_format
        custom_row = QWidget()
        custom_layout = QVBoxLayout(custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.addWidget(title_format)
        custom_help = QLabel('Campos: {title}, {artist}, {album}, {album_artist}, {year}, {genre}.')
        custom_help.setWordWrap(True)
        custom_layout.addWidget(custom_help)
        caster.addRow(custom_row)
        preview = QLabel()
        preview.setTextFormat(Qt.TextFormat.PlainText)
        def preview_format():
            from .title_format import format_title
            from .model import Snapshot
            try:
                preview.setText(format_title(Snapshot('preview', artist='Artista', title='Canción', album='Álbum', year='2026'), title_format.text()))
            except ValueError as error:
                preview.setText(str(error))
        def choose_title_preset():
            value = self.title_presets.currentData()
            custom_row.setVisible(value is None)
            if value is not None:
                title_format.setText(value)
        self.title_presets.currentIndexChanged.connect(choose_title_preset)
        title_format.textChanged.connect(preview_format)
        caster.addRow('Ejemplo', preview)
        choose_title_preset()
        preview_format()
        note(caster, 'El formato cambia el texto combinado. Artista, título y álbum conservan sus campos separados.')
        caster.addRow(OutputFilesWidget(self.data_directory / ('demo-output' if demo else 'output')))
        help_button = QPushButton('Cómo conectarlo a mi emisor')
        help_button.setMaximumWidth(240)
        help_button.setCheckable(True)
        caster.addRow(help_button)
        help_widget = QWidget()
        help_form = QFormLayout(help_widget)
        help_form.setContentsMargins(0, 4, 0, 4)
        note(help_form, 'Selecciona en tu emisor el archivo y formato que admita. TXT entrega el título combinado; XML y JSON requieren un lector compatible. Las conexiones de audio se configuran en el emisor.')
        note(help_form, 'RadioCaster: Read from XML file, con Title Format {TRACK[CASTTITLE]}. Puedes mantener esa plantilla y cambiar el contenido desde la lista de MetaDATA. El XML no transporta imágenes por sí solo.')
        help_widget.hide()
        help_button.toggled.connect(help_widget.setVisible)
        caster.addRow(help_widget)
        probe(caster, 'Now Playing', 'Comprobar archivos')

        publish = section('Publicación')
        check(publish, 'receiver_enabled', 'Enviar al receptor autohospedado')
        text(publish, 'receiver_url', 'Dirección HTTPS del receptor')
        secret(publish, 'receiver', 'Clave de publicación')
        number(publish, 'receiver_heartbeat_seconds', 'Confirmar vigencia cada (segundos)', 1, 10)
        probe(publish, 'Receptor')
        note(publish, 'Envía la ficha y la imagen juntas al cambiar la canción. Durante pausas y exclusiones vacía los campos. El receptor publica /nowplaying.json y /artwork; si se corta la conexión, caducan automáticamente. Funciona con tu servidor, independientemente del programa de emisión. Requiere instalar el receptor incluido en el proyecto.')

        art = section('Carátulas')
        text(art, 'stream_url', 'Enlace de audio')
        check(art, 'local_server_enabled', 'Habilitar reproductor local con carátulas')
        webdav_toggle = check(art, 'webdav_enabled', 'Usar un alojamiento WebDAV existente (avanzado)')
        webdav_widget = QWidget()
        webdav_form = QFormLayout(webdav_widget)
        webdav_form.setContentsMargins(0, 8, 0, 8)
        for key, label in [('webdav_upload_url', 'Carpeta HTTPS de subida'), ('webdav_public_url', 'Carpeta HTTPS pública'), ('webdav_username', 'Usuario')]:
            text(webdav_form, key, label)
        secret(webdav_form, 'webdav', 'Contraseña')
        probe(webdav_form, 'Alojamiento de carátulas')
        note(webdav_form, 'El alojamiento debe permitir WebDAV y lectura pública. Es una alternativa al receptor autohospedado de Publicación. No modifica las carátulas del servidor de audio ni publica canciones durante las pausas.')
        webdav_widget.setVisible(config.webdav_enabled)
        webdav_toggle.toggled.connect(webdav_widget.setVisible)
        art.addRow(webdav_widget)

        ogg = section('Codificador')
        note(ogg, 'AAC es la salida principal; MP3 queda como respaldo y Ogg como alternativa experimental. Para un emisor que admita codificador externo por consola: recibe audio PCM de 16 bits por entrada estándar y devuelve audio codificado por salida estándar. Comprueba ese contrato en tu programa; este módulo no captura audio ni conecta al servidor.')
        encoder_format = QComboBox()
        for label, value in [('AAC — Principal', 'aac'), ('MP3 — Respaldo', 'mp3'), ('Ogg/Opus — Experimental', 'ogg')]:
            encoder_format.addItem(label, value)
        encoder_format.setCurrentIndex(encoder_format.findData(config.encoder_format))
        self.fields['encoder_format'] = encoder_format
        ogg.addRow('Formato', encoder_format)
        rate = QComboBox()
        for value in (32000, 44100, 48000):
            rate.addItem(str(value), value)
        rate.setCurrentIndex(rate.findData(config.encoder_sample_rate))
        self.fields['encoder_sample_rate'] = rate
        ogg.addRow('Frecuencia de entrada (Hz)', rate)
        number(ogg, 'encoder_channels', 'Canales (1 mono / 2 estéreo)', 1, 2)
        number(ogg, 'encoder_bitrate', 'Tasa de bits (kbps)', 32, 320)
        check(ogg, 'encoder_radiocaster_variables', 'Usar variables de RadioCaster en el comando')
        text(ogg, 'ogg_ffmpeg_path', 'Archivo ffmpeg.exe')
        choose_encoder = QPushButton('Elegir FFmpeg…')
        choose_encoder.setMaximumWidth(180)
        choose_encoder.clicked.connect(self.choose_ffmpeg)
        ogg.addRow(choose_encoder)
        probe(ogg, 'Codificador', 'Comprobar codificador')
        check(ogg, 'encoder_hls_enabled', 'Generar también HLS local con portada (AAC, experimental)')
        self.encoder_mime = QLabel()
        ogg.addRow('Tipo MIME', self.encoder_mime)
        note(ogg, 'El comando general usa los valores de audio elegidos aquí: deben coincidir con la entrada del emisor. Para RadioCaster puedes activar sus variables; ese modo también usa la ruta abreviada de Python si Windows la ofrece. Esta integración específica no cambia las salidas Now Playing.')
        self.ogg_command = QLineEdit()
        self.ogg_command.setReadOnly(True)
        self.ogg_command.setAccessibleName('Comando del codificador externo')
        ogg.addRow('Comando', self.ogg_command)
        copy_command = QPushButton('Copiar comando')
        copy_command.setMaximumWidth(180)
        copy_command.clicked.connect(self.copy_ogg_command)
        ogg.addRow(copy_command)
        self.fields['ogg_ffmpeg_path'].textChanged.connect(self.refresh_ogg_command)
        encoder_format.currentIndexChanged.connect(self.encoder_format_changed)
        self.fields['encoder_hls_enabled'].toggled.connect(self.refresh_ogg_command)
        rate.currentIndexChanged.connect(self.refresh_ogg_command)
        self.fields['encoder_channels'].valueChanged.connect(self.refresh_ogg_command)
        self.fields['encoder_bitrate'].valueChanged.connect(self.refresh_ogg_command)
        self.fields['encoder_radiocaster_variables'].toggled.connect(self.refresh_ogg_command)
        self.encoder_format_changed()
        self.refresh_ogg_command()
        note(ogg, 'AAC/MP3 directos entregan audio; los títulos enviados por tu emisor y los archivos Now Playing siguen siendo vías separadas. No incorporan portadas dinámicas. HLS añade etiquetas ID3 con los datos y la imagen a segmentos AAC en output/hls/live.m3u8. Requiere alojamiento HTTP y un reproductor que interprete ID3/APIC; hay una prueba de laboratorio con Chrome y hls.js, pendiente de validar con tu emisor en Windows. No se sube al servidor automáticamente. Ogg conserva sus portadas incorporadas para clientes compatibles.')

        monitoring = section('Monitoreo')
        check(monitoring, 'audio_monitor_enabled', 'Comprobar la recepción y el silencio del audio')
        note(monitoring, 'Usa el enlace de audio de Carátulas y el FFmpeg seleccionado en Codificador. Toma muestras periódicas desde esta computadora, sin reproducir sonido por los altavoces. No representa un monitoreo continuo ni desde varios países. Cada comprobación abre una conexión de oyente y consume datos.')
        number(monitoring, 'monitor_interval_seconds', 'Comprobar cada (segundos)', 15, 300)
        number(monitoring, 'monitor_sample_seconds', 'Duración de muestra (segundos)', 3, 10)
        number(monitoring, 'monitor_silence_seconds', 'Silencio mínimo en la muestra (segundos)', 1, 10)
        number(monitoring, 'monitor_threshold_db', 'Umbral de silencio (dBFS)', -90, -10)
        number(monitoring, 'monitor_confirmations', 'Resultados consecutivos para abrir/cerrar incidentes', 1, 5)
        number(monitoring, 'monitor_retention_days', 'Conservar datos de monitoreo (días)', 1, 365)
        check(monitoring, 'statistics_enabled', 'Consultar oyentes al servidor de audio (solo lectura)')
        text(monitoring, 'statistics_url', 'URL completa de estadísticas JSON')
        stats_format = QComboBox()
        for label, value in [('JSON genérico', 'generic'), ('Icecast status-json', 'icecast'), ('AzuraCast Now Playing', 'azuracast')]:
            stats_format.addItem(label, value)
        stats_format.setCurrentIndex(stats_format.findData(config.statistics_format))
        self.fields['statistics_format'] = stats_format
        monitoring.addRow('Formato de la respuesta', stats_format)
        text(monitoring, 'statistics_mount', 'Punto de montaje (solo Icecast)')
        secret(monitoring, 'statistics', 'Token Bearer opcional')
        probe(monitoring, 'Estadísticas')
        note(monitoring, 'Son lecturas opcionales de datos reales del servidor; no conectan ni controlan la emisión. JSON genérico: {"listeners": 10}. Se guardan muestras, pico y promedio de oyentes simultáneos; no identifican oyentes únicos ni equivalen al número total de personas. Un fallo no se registra como cero oyentes.')

        advanced = section('Avanzados')
        number(advanced, 'poll_seconds', 'Consultar fuentes cada (segundos)', 1, 30)
        number(advanced, 'local_server_port', 'Puerto del reproductor local', 1024, 65535)
        number(advanced, 'stale_seconds', 'Ocultar datos vencidos tras (segundos)', 15, 300)
        text(advanced, 'spotify_app_id_contains', 'Identificador de Spotify contiene')
        note(advanced, 'Las claves se guardan en el almacén de credenciales de tu usuario de Windows, separadas del archivo de ajustes. Cambiar dirección o usuario requiere la clave de esa conexión. En demostración las claves son temporales.')
        self.message = QLabel('')
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Guardar')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        if embedded:
            buttons.button(QDialogButtonBox.StandardButton.Save).setText('Guardar cambios')
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Descartar cambios')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        page = {'Música': 'Reglas', 'Spotify': 'Fuentes'}.get(page, page)
        self.navigation.setCurrentRow(self.page_names.index(page) if page in self.page_names else 0)
        if embedded:
            for button in self.findChildren(QPushButton):
                button.setAutoDefault(False)
                button.setDefault(False)
            save_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
            save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            save_shortcut.activated.connect(self.save)

    def choose_ffmpeg(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Selecciona FFmpeg', filter='Programas (ffmpeg.exe ffmpeg);;Todos los archivos (*)')
        if filename:
            self.fields['ogg_ffmpeg_path'].setText(filename)

    def refresh_ogg_command(self):
        from .ogg_encoder import command_line, find_ffmpeg, EncoderError
        from .aac_encoder import command_line as aac_command
        path = self.data_directory / ('demo-output' if self.demo else 'output') / 'nowplaying.json'
        executable = find_ffmpeg(self.fields['ogg_ffmpeg_path'].text().strip())
        audio_format = self.fields['encoder_format'].currentData()
        use_variables = self.fields['encoder_radiocaster_variables'].isChecked()
        for key in ('encoder_sample_rate', 'encoder_channels', 'encoder_bitrate'):
            self.fields[key].setEnabled(not use_variables)
        options = dict(use_variables=use_variables, sample_rate=self.fields['encoder_sample_rate'].currentData(),
                       channels=self.fields['encoder_channels'].value(), bitrate=self.fields['encoder_bitrate'].value())
        self.encoder_mime.setText({'aac': 'audio/aac', 'mp3': 'audio/mpeg', 'ogg': 'audio/ogg'}[audio_format])
        self.encoder_command_error = ''
        try:
            command = (command_line(path, executable, **options) if audio_format == 'ogg' else
                       aac_command(path, executable, audio_format, self.fields['encoder_hls_enabled'].isChecked(), **options)) if executable else ''
            self.ogg_command.setText(command)
            self.ogg_command.setCursorPosition(0)
            self.ogg_command.setToolTip(self.ogg_command.text())
        except EncoderError as error:
            self.ogg_command.clear()
            self.encoder_command_error = str(error)
        self.ogg_command.setPlaceholderText(self.encoder_command_error or 'Selecciona FFmpeg; requiere la instalación Python.')

    def encoder_format_changed(self):
        aac = self.fields['encoder_format'].currentData() == 'aac'
        if not aac:
            self.fields['encoder_hls_enabled'].setChecked(False)
        self.fields['encoder_hls_enabled'].setEnabled(aac)
        self.refresh_ogg_command()

    def copy_ogg_command(self):
        from PySide6.QtWidgets import QApplication
        self.refresh_ogg_command()
        if self.ogg_command.text():
            QApplication.clipboard().setText(self.ogg_command.text())
            self.message.setText(f'Comando copiado. Usa una conexión de prueba y MIME {self.encoder_mime.text()}.')
        else:
            self.message.setText(self.encoder_command_error or 'Selecciona FFmpeg antes de copiar el comando.')

    def choose_logo(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Logo', filter='Imágenes (*.png *.jpg *.jpeg *.webp)')
        if filename:
            self.fields['logo_path'].setText(filename)

    def collect(self):
        values = asdict(self.original)
        for key, field in self.fields.items():
            if isinstance(field, QLineEdit):
                values[key] = field.text().strip()
            elif isinstance(field, QCheckBox):
                values[key] = field.isChecked()
            elif isinstance(field, QComboBox):
                values[key] = field.currentData() if key in ('theme', 'priority', 'encoder_format', 'encoder_sample_rate', 'statistics_format') else field.currentText()
            elif isinstance(field, QSpinBox):
                values[key] = field.value()
            else:
                values[key] = [v.strip() for v in field.toPlainText().splitlines() if v.strip()]
        values['azuracast_write_enabled'] = False
        values['remote_monitor_enabled'] = False
        values['icecast_targets'] = [dict(target, enabled=False, send_artwork_url=False)
                                    for target in self.original.icecast_targets]
        values.update(self.source_settings.values())
        values['folder_rules'] = [dict(rule) for rule in self.folder_settings.rules]
        values['music_folders'] = [rule['path'] for rule in values['folder_rules'] if rule['action'] == 'allow']
        values['excluded_folders'] = [rule['path'] for rule in values['folder_rules'] if rule['action'] == 'block']
        config = Config(**values)
        config.validate()
        changes = {}
        for service, field in self.secrets.items():
            changes.update(field.pending(credential_key(service, config)))
        changed_endpoints = {credential_key(service, config) for service in self.secrets
                             if credential_key(service, config) != credential_key(service, self.original)}
        config.managed_credentials = sorted(set(config.managed_credentials) | set(changes) | changed_endpoints)
        return config, changes

    def test_connection(self, service, button):
        if any(thread.isRunning() for thread in self.findChildren(QThread)):
            self.message.setText('Espera a que termine la prueba actual.')
            return
        if self.demo and service not in ('Codificador Ogg', 'Codificador'):
            self.message.setText('La demostración no consulta servicios. Abre el modo real para probar la conexión.')
            return
        try:
            config, changes = self.collect()
        except (ValueError, TypeError) as error:
            self.message.setText(str(error))
            return
        self.message.setText('Comprobando conexión…')
        button.setEnabled(False)
        self.checker = ConnectionCheck(service, config, OverlayCredentials(self.credentials, changes), self.data_directory, self)
        self.checker.result.connect(lambda ok, message: self.message.setText(('Correcto. ' if ok else 'Revisar. ') + message))
        self.checker.finished.connect(lambda: button.setEnabled(True))
        self.checker.start()

    def keyPressEvent(self, event):
        if self.embedded and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, QPushButton):
                focused.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def done(self, result):
        if any(thread.isRunning() for thread in self.findChildren(QThread)):
            self.message.setText('Espera a que termine la prueba antes de cerrar los ajustes.')
            return
        if self.embedded:
            if result == QDialog.DialogCode.Accepted:
                self.accepted.emit()
            else:
                self.rejected.emit()
            return
        super().done(result)

    def save(self):
        if any(thread.isRunning() for thread in self.findChildren(QThread)):
            self.message.setText('Espera a que termine la prueba antes de guardar.')
            return
        try:
            config, changes = self.collect()
            if self.store:
                commit_settings(self.store, config, self.credentials, changes)
            elif changes:
                self.message.setText('No se definió una carpeta de datos para guardar las claves.')
                return
            self.result_config = config
        except (ValueError, TypeError, CredentialError) as error:
            self.message.setText(str(error))
            return
        except Exception:
            self.message.setText('No se pudieron guardar los ajustes. Revisa los permisos de la carpeta de datos.')
            return
        self.accept()
