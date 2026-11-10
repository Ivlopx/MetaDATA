"""Native settings forms. Secrets are staged until the complete dialog is saved."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .appearance import source_name, brand_icon
from .output_files import OutputFilesWidget
from .config import Config
from .credentials import CredentialError, MemoryCredentials, secret_id, commit_settings
from .connection_tests import OverlayCredentials, check_connection


def credential_key(service, config):
    if service == 'radioboss':
        return secret_id(service, config.radioboss_url, config.radioboss_user)
    if service == 'azuracast':
        return secret_id(service, config.azuracast_url)
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


class IcecastDialog(QDialog):
    def __init__(self, target, credentials, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Destino Icecast')
        self.resize(580, 360)
        self.original = target
        self.checker = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.fields = {}
        for key, label, default in [('name', 'Nombre', ''), ('url', 'Servidor', 'https://'),
                                    ('mount', 'Mount', '/stream'), ('username', 'Usuario', 'source'),
                                    ('verify_url', 'Estadísticas JSON (opcional)', '')]:
            field = QLineEdit(target.get(key, default))
            self.fields[key] = field
            form.addRow(label, field)
        key = secret_id('icecast', target.get('url', ''), target.get('mount', ''), target.get('username', 'source'))
        self.secret = SecretField(credentials, key)
        form.addRow('Contraseña', self.secret)
        for key, label in [('enabled', 'Publicar títulos en este destino'), ('send_artwork_url', 'Enviar URL de carátula (Icecast-KH compatible)')]:
            field = QCheckBox(label)
            field.setChecked(target.get(key, False))
            self.fields[key] = field
            form.addRow(field)
        note = QLabel('La ruta habitual es el archivo de títulos de RadioCaster. Activa esta salida solo si el servidor permite actualizar sus metadatos y no hay otro escritor.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.test_message = QLabel('')
        self.test_message.setWordWrap(True)
        layout.addWidget(self.test_message)
        test = QPushButton('Consultar estadísticas')
        test.clicked.connect(lambda: self.test_stats(test))
        layout.addWidget(test)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Guardar')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def test_stats(self, button):
        if self.checker and self.checker.isRunning():
            return
        if getattr(self.parent(), 'demo', False):
            self.test_message.setText('La demostración no consulta servicios externos.')
            return
        target = {key: field.text().strip() for key, field in self.fields.items() if isinstance(field, QLineEdit)}
        try:
            Config._url(target['url'])
            if target['verify_url']:
                Config._url(target['verify_url'])
            if not target['mount'].startswith('/'):
                raise ValueError('El mount debe comenzar por /.')
        except ValueError as error:
            self.test_message.setText(str(error))
            return
        button.setEnabled(False)
        self.test_message.setText('Consultando estadísticas públicas…')
        self.checker = ConnectionCheck('Icecast directo', Config(icecast_targets=[target]), MemoryCredentials(), Path('.'), self)
        self.checker.result.connect(lambda ok, message: self.test_message.setText(message))
        self.checker.finished.connect(lambda: button.setEnabled(True))
        self.checker.start()

    def done(self, result):
        if self.checker and self.checker.isRunning():
            self.test_message.setText('Espera a que termine la consulta antes de cerrar.')
            return
        super().done(result)

    def save(self):
        target = dict(self.original)
        for key, field in self.fields.items():
            target[key] = field.isChecked() if isinstance(field, QCheckBox) else field.text().strip()
        try:
            # Validate URLs and field types without requiring the parent hosting form yet.
            Config._url(target['url'])
            if target['verify_url']:
                Config._url(target['verify_url'])
            if not target['mount'].startswith('/'):
                raise ValueError('El mount debe comenzar por /.')
        except ValueError as error:
            QMessageBox.warning(self, 'Revisar destino', str(error))
            return
        old_key = secret_id('icecast', self.original.get('url', ''), self.original.get('mount', ''), self.original.get('username', 'source'))
        new_key = secret_id('icecast', target['url'], target['mount'], target['username'])
        if self.secret.changed or old_key != new_key:
            target['managed_password'] = True
        self.result_target = target
        key = secret_id('icecast', target['url'], target['mount'], target['username'])
        self.result_changes = self.secret.pending(key)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None, *, store=None, credentials=None, page='Estación', demo=False):
        super().__init__(parent)
        self.setWindowTitle('Ajustes de MetaDATA')
        self.resize(840, 650)
        self.original, self.store, self.demo = config, store, demo
        self.data_directory = parent.store.directory if parent is not None and hasattr(parent, 'store') else (store.directory if store else Path('.'))
        self.credentials = credentials if credentials is not None else MemoryCredentials()
        self.fields, self.secrets, self.target_changes = {}, {}, {}
        self.targets = deepcopy(config.icecast_targets)
        self.checker = None
        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(150)
        self.navigation.setSpacing(3)
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
        for key, label in [('station_name', 'Nombre'), ('slogan', 'Eslogan'), ('description', 'Descripción'),
                           ('website', 'Sitio web'), ('idle_message', 'Mensaje visual sin música'), ('break_message', 'Mensaje visual en pausas')]:
            text(general, key, label)
        text(general, 'logo_path', 'Logo (archivo de imagen)')
        choose = QPushButton('Elegir logo…')
        choose.clicked.connect(self.choose_logo)
        general.addRow(choose)
        theme = QComboBox()
        for label, value in [('Seguir Windows', 'system'), ('Claro', 'light'), ('Oscuro', 'dark')]:
            theme.addItem(label, value)
        theme.setCurrentIndex(theme.findData(config.theme))
        self.fields['theme'] = theme
        general.addRow('Apariencia', theme)
        note(general, 'Sin música se envían artista y título vacíos. Los mensajes y el logo se muestran solo en MetaDATA y su reproductor; no se publican como una canción.')

        rules = section('Música')
        number(rules, 'history_visible_limit', 'Canciones visibles en historial', 10, 1000)
        number(rules, 'cover_cache_mb', 'Espacio máximo para portadas (MB)', 8, 4096)
        from .image_cache import cache_usage
        count, size = cache_usage(self.data_directory / ('demo-output' if demo else 'output'))
        rules.addRow('Uso actual de portadas', QLabel(f'{count} imágenes · {size / (1024 * 1024):.1f} MB'))
        note(rules, 'La caché conserva las portadas de las canciones visibles, sin duplicar imágenes, además de la portada y el logo actuales. Si se alcanza el límite de espacio se retiran las menos recientes. Los límites se aplican a esta computadora; el historial de texto no se borra ni se eliminan imágenes del alojamiento remoto.')
        priority = QComboBox()
        for value in ('radioboss', 'spotify'):
            priority.addItem(brand_icon(value), source_name(value), value)
        priority.setCurrentIndex(priority.findData(config.priority))
        self.fields['priority'] = priority
        rules.addRow('Si ambas reproducen, preferir', priority)
        for key, label in [('music_folders', 'Carpetas de música RadioBOSS'), ('excluded_folders', 'Carpetas excluidas'),
                           ('excluded_terms', 'Palabras excluidas'), ('excluded_types', 'Tipos RadioBOSS excluidos')]:
            field = QPlainTextEdit('\n'.join(getattr(config, key)))
            field.setMaximumHeight(80)
            self.fields[key] = field
            rules.addRow(label + '\nUna por línea', field)
        folder = QPushButton('Agregar carpeta de música…')
        folder.clicked.connect(self.choose_folder)
        rules.addRow(folder)
        note(rules, 'Sin carpetas de música aprobadas, los datos de canción quedan vacíos. Conserva anuncios, jingles y promos en carpetas excluidas.')

        rb = section('RadioBOSS')
        check(rb, 'radioboss_enabled', 'Consultar RadioBOSS')
        text(rb, 'radioboss_url', 'Dirección de la API')
        text(rb, 'radioboss_user', 'Usuario (opcional)')
        secret(rb, 'radioboss', 'Contraseña')
        probe(rb, 'RadioBOSS')
        note(rb, 'Activa el control remoto por HTTP en RadioBOSS. La prueba consulta el estado; no controla su reproducción.')

        sp = section('Spotify')
        check(sp, 'spotify_enabled', 'Consultar Spotify en Windows')
        check(sp, 'spotify_publish', 'Permitir canciones de Spotify en selección e historial')
        note(sp, 'No requiere una clave API. Abre Spotify en esta computadora. La detección de anuncios tiene límites: usa Pausar metadatos cuando sea necesario.')
        probe(sp, 'Spotify')

        caster = section('RadioCaster')
        note(caster, 'En RadioCaster elige Read from XML file y selecciona nowplaying.xml. En Title Format escribe {TRACK[CASTTITLE]}. El TXT se conserva como alternativa. RadioCaster conserva la captura USB y sus encoders hacia AzuraCast y Zeno.fm.')
        caster.addRow(OutputFilesWidget(self.data_directory / ('demo-output' if demo else 'output')))
        note(caster, 'Artista y título viajan en el texto de la canción. La imagen requiere una ruta aparte o la búsqueda de portadas de AzuraCast; Icecast no transporta carátulas como metadato estándar.')
        probe(caster, 'RadioCaster')

        az = section('AzuraCast')
        text(az, 'azuracast_url', 'Panel de AzuraCast')
        text(az, 'azuracast_station', 'ID de estación')
        check(az, 'remote_monitor_enabled', 'Comprobar lo que reciben los servidores')
        check(az, 'azuracast_write_enabled', 'Publicar títulos directamente por API (opcional)')
        secret(az, 'azuracast', 'Clave API')
        probe(az, 'AzuraCast')
        note(az, 'Con RadioCaster como escritor no necesitas una clave API. La salida directa publica artista y título; no carga álbum ni carátula en AzuraCast. La prueba de la clave verifica lectura y no publica nada.')

        art = section('Carátulas')
        text(art, 'stream_url', 'Enlace de audio')
        check(art, 'local_server_enabled', 'Habilitar reproductor local con carátulas')
        check(art, 'webdav_enabled', 'Publicar imágenes y JSON en alojamiento WebDAV')
        for key, label in [('webdav_upload_url', 'Carpeta HTTPS de subida'), ('webdav_public_url', 'Carpeta HTTPS pública'), ('webdav_username', 'Usuario')]:
            text(art, key, label)
        secret(art, 'webdav', 'Contraseña')
        probe(art, 'Alojamiento de carátulas')
        note(art, 'El alojamiento debe existir y permitir WebDAV y lectura pública. Esta salida sirve al reproductor propio; no modifica las portadas de AzuraCast. En pausas y anuncios el logo se muestra solo como identidad visual, con los campos de canción vacíos.')

        ice = section('Icecast directo')
        note(ice, 'Opcional. Utiliza una sola ruta de publicación por mount para evitar títulos que se sobrescriban entre sí.')
        self.target_list = QListWidget()
        ice.addRow(self.target_list)
        row = QHBoxLayout()
        for label, action in [('Agregar…', lambda: self.edit_target(True)), ('Editar…', self.edit_target), ('Quitar', self.remove_target)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        ice.addRow(row)
        self.refresh_targets()

        ogg = section('Codificador')
        note(ogg, 'AAC es la salida principal; MP3 queda como respaldo y Ogg como alternativa experimental. RadioCaster sigue capturando el audio y conectando al servidor. Configura cada salida en una conexión separada.')
        encoder_format = QComboBox()
        for label, value in [('AAC — Principal', 'aac'), ('MP3 — Respaldo', 'mp3'), ('Ogg/Opus — Experimental', 'ogg')]:
            encoder_format.addItem(label, value)
        encoder_format.setCurrentIndex(encoder_format.findData(config.encoder_format))
        self.fields['encoder_format'] = encoder_format
        ogg.addRow('Formato', encoder_format)
        text(ogg, 'ogg_ffmpeg_path', 'Archivo ffmpeg.exe')
        choose_encoder = QPushButton('Elegir FFmpeg…')
        choose_encoder.clicked.connect(self.choose_ffmpeg)
        ogg.addRow(choose_encoder)
        probe(ogg, 'Codificador', 'Comprobar codificador')
        check(ogg, 'encoder_hls_enabled', 'Generar también HLS local con portada (AAC, experimental)')
        self.encoder_mime = QLabel()
        ogg.addRow('MIME para RadioCaster', self.encoder_mime)
        note(ogg, 'En RadioCaster → Custom Encoders pega el comando y el MIME indicados. Los parámetros entre llaves los completa RadioCaster. El comando usa automáticamente la ruta abreviada de Python cuando Windows la ofrece.')
        self.ogg_command = QLineEdit()
        self.ogg_command.setReadOnly(True)
        self.ogg_command.setAccessibleName('Comando del codificador para RadioCaster')
        ogg.addRow('Comando', self.ogg_command)
        copy_command = QPushButton('Copiar comando para RadioCaster')
        copy_command.clicked.connect(self.copy_ogg_command)
        ogg.addRow(copy_command)
        self.fields['ogg_ffmpeg_path'].textChanged.connect(self.refresh_ogg_command)
        encoder_format.currentIndexChanged.connect(self.encoder_format_changed)
        self.fields['encoder_hls_enabled'].toggled.connect(self.refresh_ogg_command)
        self.encoder_format_changed()
        self.refresh_ogg_command()
        note(ogg, 'AAC/MP3 directos entregan audio; los títulos enviados por RadioCaster y los archivos Now Playing siguen siendo vías separadas. No incorporan portadas dinámicas. HLS añade etiquetas ID3 con los datos y la imagen a segmentos AAC en output/hls/live.m3u8. Requiere alojamiento HTTP y un reproductor que interprete ID3/APIC; todavía no está validado en navegadores ni se sube al servidor automáticamente. Ogg conserva sus portadas incorporadas para clientes compatibles.')

        advanced = section('Avanzados')
        number(advanced, 'poll_seconds', 'Consultar fuentes cada (segundos)', 1, 30)
        number(advanced, 'remote_poll_seconds', 'Consultar servidores cada (segundos)', 5, 300)
        number(advanced, 'local_server_port', 'Puerto del reproductor local', 1024, 65535)
        number(advanced, 'stale_seconds', 'Ocultar datos vencidos tras (segundos)', 15, 300)
        text(advanced, 'spotify_app_id_contains', 'Identificador de Spotify contiene')
        text(advanced, 'icecast_monitor_url', 'Servidor Icecast para monitoreo')
        text(advanced, 'icecast_monitor_mount', 'Mount para monitoreo')
        note(advanced, 'Las claves se guardan en el almacén de credenciales de tu usuario de Windows, separadas del archivo de ajustes. Cambiar dirección o usuario requiere la clave de esa conexión. En demostración las claves son temporales.')
        self.message = QLabel('')
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Guardar')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.navigation.setCurrentRow(self.page_names.index(page) if page in self.page_names else 0)

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
        self.encoder_mime.setText({'aac': 'audio/aac', 'mp3': 'audio/mpeg', 'ogg': 'audio/ogg'}[audio_format])
        self.encoder_command_error = ''
        try:
            command = (command_line(path, executable) if audio_format == 'ogg' else
                       aac_command(path, executable, audio_format, self.fields['encoder_hls_enabled'].isChecked())) if executable else ''
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

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta de música')
        if folder:
            self.fields['music_folders'].appendPlainText(folder)

    def choose_logo(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Logo', filter='Imágenes (*.png *.jpg *.jpeg *.webp)')
        if filename:
            self.fields['logo_path'].setText(filename)

    def refresh_targets(self):
        self.target_list.clear()
        for target in self.targets:
            self.target_list.addItem((target.get('name') or target.get('mount', 'Destino')) + (' · activo' if target.get('enabled') else ' · desactivado'))

    def edit_target(self, add=False):
        index = self.target_list.currentRow()
        if not add and index < 0:
            return
        dialog = IcecastDialog({} if add else self.targets[index], OverlayCredentials(self.credentials, self.target_changes), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if add:
                self.targets.append(dialog.result_target)
            else:
                self.targets[index] = dialog.result_target
            self.target_changes.update(dialog.result_changes)
            self.refresh_targets()

    def remove_target(self):
        index = self.target_list.currentRow()
        if index >= 0:
            self.targets.pop(index)
            self.refresh_targets()

    def collect(self):
        values = asdict(self.original)
        for key, field in self.fields.items():
            if isinstance(field, QLineEdit):
                values[key] = field.text().strip()
            elif isinstance(field, QCheckBox):
                values[key] = field.isChecked()
            elif isinstance(field, QComboBox):
                values[key] = field.currentData() if key in ('theme', 'priority', 'encoder_format') else field.currentText()
            elif isinstance(field, QSpinBox):
                values[key] = field.value()
            else:
                values[key] = [v.strip() for v in field.toPlainText().splitlines() if v.strip()]
        values['icecast_targets'] = deepcopy(self.targets)
        config = Config(**values)
        config.validate()
        changes = dict(self.target_changes)
        for service, field in self.secrets.items():
            changes.update(field.pending(credential_key(service, config)))
        changed_endpoints = {credential_key(service, config) for service in self.secrets
                             if credential_key(service, config) != credential_key(service, self.original)}
        config.managed_credentials = sorted(set(config.managed_credentials) | set(changes) | changed_endpoints)
        return config, changes

    def test_connection(self, service, button):
        if self.checker and self.checker.isRunning():
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

    def done(self, result):
        if self.checker and self.checker.isRunning():
            self.message.setText('Espera a que termine la prueba antes de cerrar los ajustes.')
            return
        super().done(result)

    def save(self):
        if self.checker and self.checker.isRunning():
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
