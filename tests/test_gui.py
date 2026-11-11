"""Run explicitly: QT_QPA_PLATFORM=offscreen RADIO_GUI_TEST=1 python -m unittest discover -s tests."""
import os
from pathlib import Path
import tempfile
import time
import unittest


@unittest.skipUnless(os.environ.get("RADIO_GUI_TEST") == "1", "Activar RADIO_GUI_TEST=1 para prueba de interfaz")
class GuiTests(unittest.TestCase):
    def test_demo_dashboard_settings_and_station_override(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from radio_metadata.config import ConfigStore
        from radio_metadata.gui import MainWindow, SettingsDialog, STYLE

        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(STYLE)
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            config = store.load()
            config.poll_seconds = 1
            window = MainWindow(store, config, demo=True)
            window.show()
            def until(predicate):
                deadline = time.monotonic() + 6
                while not predicate() and time.monotonic() < deadline:
                    QTest.qWait(20)
                    # Release the Python GIL for the worker and its file-export thread.
                    time.sleep(0.01)
                self.assertTrue(predicate())
            try:
                until(lambda: window.title.text() == "Canción de prueba")
                self.assertEqual(window.history.rowCount(), 1)
                self.assertEqual(window.history.item(0, 1).text(), "RadioBOSS")
                self.assertIn("Álbum de prueba", window.album.text())
                self.assertEqual(window.history.columnCount(), 6)
                self.assertIn("RadioBOSS", window.active.text())
                dialog = SettingsDialog(config, window)
                dialog.fields["station_name"].setText("Radio de prueba")
                dialog.fields["stream_url"].setText("https://radio.example/live.mp3")
                dialog.save()
                self.assertEqual(dialog.result_config.station_name, "Radio de prueba")
                self.assertFalse(dialog.result_config.remote_monitor_enabled)
                self.assertNotIn('AzuraCast', dialog.page_names)
                self.assertNotIn('Icecast directo', dialog.page_names)
                self.assertIn('Now Playing', dialog.page_names)
                self.assertEqual(dialog.result_config.stream_url, "https://radio.example/live.mp3")
                window.scenarios.setCurrentIndex(3)
                until(lambda: window.title.text() == config.break_message)
                self.assertEqual(window.history.rowCount(), 1)
                self.assertEqual(window.album.text(), "")
                window.scenarios.setCurrentIndex(2)
                until(lambda: "Varias" in window.reason.text() and window.title.text() == "Canción de prueba")
                window.mode.setCurrentIndex(3)
                until(lambda: window.title.text() == config.break_message and "activado" in window.reason.text())
                if os.environ.get("RADIO_SCREENSHOT"):
                    window.grab().save(os.environ["RADIO_SCREENSHOT"])
            finally:
                window.quit()
            self.assertFalse(window.worker.isRunning())
            text = (Path(tmp) / "demo-output" / "nowplaying.txt").read_text()
            self.assertEqual(text.strip(), "")

    def test_four_pages_and_secure_settings_save_cancel_and_export(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication, QLineEdit, QDialog
        from radio_metadata.config import ConfigStore
        from radio_metadata.gui import MainWindow, SettingsDialog
        from radio_metadata.credentials import MemoryCredentials, secret_id
        from radio_metadata.appearance import apply_appearance
        from radio_metadata.storage import History
        from radio_metadata.model import resolve, Snapshot
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            config = store.load()
            vault = MemoryCredentials()
            dialog = SettingsDialog(config, store=store, credentials=vault)
            self.assertEqual(dialog.source_settings.rows[0]['name'], "RadioBOSS")
            secret = dialog.secrets['radioboss']
            self.assertEqual(secret.edit.echoMode(), QLineEdit.EchoMode.Password)
            secret.edit.setText('private-test-key')
            secret.mark_changed()
            secret.show_button.setChecked(True)
            self.assertEqual(secret.edit.echoMode(), QLineEdit.EchoMode.Normal)
            secret.show_button.setChecked(False)
            dialog.fields['theme'].setCurrentIndex(2)
            dialog.save()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            key = secret_id('radioboss', config.radioboss_url, config.radioboss_user)
            self.assertEqual(vault.get(key), 'private-test-key')
            self.assertIn(key, store.load().managed_credentials)
            self.assertNotIn('private-test-key', store.path.read_text())
            cancelled = SettingsDialog(store.load(), store=store, credentials=vault)
            cancelled.secrets['radioboss'].clear_secret()
            cancelled.reject()
            self.assertEqual(vault.get(key), 'private-test-key')
            cleared = SettingsDialog(store.load(), store=store, credentials=vault)
            cleared.secrets['radioboss'].clear_secret()
            cleared.save()
            self.assertEqual(vault.get(key), '')
            moved = SettingsDialog(store.load(), store=store, credentials=vault)
            moved.fields['radioboss_url'].setText('http://127.0.0.1:9002/')
            moved.save()
            moved_key = secret_id('radioboss', 'http://127.0.0.1:9002/', config.radioboss_user)
            self.assertIn(moved_key, store.load().managed_credentials)
            for theme in ('light', 'dark', 'system'):
                apply_appearance(app, theme)
                self.assertEqual(app.styleSheet(), '')
            config = store.load()
            window = MainWindow(store, config, demo=True)
            try:
                self.assertEqual([window.tabs.tabText(i) for i in range(5)], ['Inicio', 'Historial', 'Conexiones', 'Monitoreo', 'Ajustes'])
                window.worker.stop()
                window.worker.wait()
                history = History(Path(tmp) / 'demo-history.sqlite3')
                for i in range(205):
                    history.record(resolve([Snapshot('spotify', True, 'Artista', f'Canción {i}', kind='music')], __import__('dataclasses').replace(config, spotify_publish=True)))
                history.close()
                path = Path(tmp) / 'history.csv'
                with patch('radio_metadata.gui.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV (*.csv)')):
                    window.export_history()
                import csv
                with path.open(encoding='utf-8-sig') as stream:
                    rows = list(csv.reader(stream))
                self.assertGreaterEqual(len(rows), 206)
                self.assertEqual(rows[0][0], 'Fecha y hora')
                self.assertEqual(rows[1][3], 'Canción 204')
                window.toggle_station()
                self.assertEqual(window.mode.currentData(), 'station')
                window.toggle_station()
                self.assertEqual(window.mode.currentData(), 'auto')
            finally:
                window.quit()

    def test_export_paths_can_be_copied_and_folder_opened_from_main_and_settings(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        from radio_metadata.config import ConfigStore
        from radio_metadata.gui import MainWindow, SettingsDialog
        from radio_metadata.output_files import OutputFilesWidget
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            config = store.load()
            window = MainWindow(store, config, demo=True)
            try:
                window.worker.stop(); window.worker.wait()
                files = window.output_files
                self.assertTrue(files.path.isReadOnly())
                files.copy_button.click()
                self.assertEqual(app.clipboard().text(), str((Path(tmp) / 'demo-output' / 'nowplaying.xml').resolve()))
                files.kind.setCurrentIndex(1)
                files.copy_button.click()
                self.assertTrue(app.clipboard().text().endswith('nowplaying.txt'))
                with patch('radio_metadata.output_files.QDesktopServices.openUrl', return_value=True) as opened:
                    files.open_button.click()
                    self.assertEqual(opened.call_args.args[0].toLocalFile(), str((Path(tmp) / 'demo-output').resolve()))
                self.assertEqual(set(window.connection_labels), {'RadioBOSS', 'Spotify', 'Now Playing', 'Receptor'})
                dialog = SettingsDialog(config, window, page='Now Playing')
                self.assertTrue(dialog.findChildren(OutputFilesWidget))
                dialog.fields['history_visible_limit'].setValue(30)
                dialog.fields['cover_cache_mb'].setValue(64)
                dialog.fields['ogg_ffmpeg_path'].setText('C:/Program Files/FFmpeg/ffmpeg.exe')
                dialog.save()
                self.assertEqual(dialog.result_config.history_visible_limit, 30)
                self.assertEqual(dialog.result_config.cover_cache_mb, 64)
                self.assertIn('--sample-rate 48000', dialog.ogg_command.text())
                self.assertNotIn('{SampleRate}', dialog.ogg_command.text())
                dialog.fields['encoder_radiocaster_variables'].setChecked(True)
                self.assertIn('{SampleRate}', dialog.ogg_command.text())
                self.assertFalse(dialog.fields['encoder_sample_rate'].isEnabled())
                dialog.fields['encoder_radiocaster_variables'].setChecked(False)
                dialog.fields['encoder_sample_rate'].setCurrentIndex(1)
                self.assertIn('--sample-rate 44100', dialog.ogg_command.text())
                self.assertEqual(dialog.result_config.encoder_format, 'aac')
                self.assertIn('--format aac', dialog.ogg_command.text())
                self.assertEqual(dialog.encoder_mime.text(), 'audio/aac')
                dialog.fields['encoder_hls_enabled'].setChecked(True)
                self.assertIn('--hls-dir', dialog.ogg_command.text())
                dialog.fields['encoder_format'].setCurrentIndex(1)
                self.assertFalse(dialog.fields['encoder_hls_enabled'].isChecked())
                self.assertFalse(dialog.fields['encoder_hls_enabled'].isEnabled())
                self.assertIn('--format mp3', dialog.ogg_command.text())
                self.assertEqual(dialog.encoder_mime.text(), 'audio/mpeg')
                dialog.fields['encoder_format'].setCurrentIndex(2)
                self.assertIn('-m radio_metadata.ogg_encoder', dialog.ogg_command.text())
                self.assertEqual(dialog.encoder_mime.text(), 'audio/ogg')
            finally:
                window.quit()

    def test_discovered_sources_permissions_priority_and_folder_rules_save_cancel(self):
        from PySide6.QtWidgets import QApplication
        from radio_metadata.config import ConfigStore
        from radio_metadata.settings import SettingsDialog
        from radio_metadata.credentials import MemoryCredentials
        from radio_metadata.source_catalog import windows_source_id
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            config = store.load()
            vault = MemoryCredentials()
            dialog = SettingsDialog(config, store=store, credentials=vault, page='Fuentes')
            sources = dialog.source_settings
            sources.apply_discovery([dict(app_id='vlc.exe', name='VLC', playing=True, sessions=1)])
            self.assertFalse(sources.rows[-1]['enabled'])
            self.assertFalse(sources.rows[-1]['publish'])
            sources.table.cellWidget(2, 2).setChecked(True)
            sources.table.cellWidget(2, 3).setChecked(True)
            sources.table.selectRow(2)
            sources.move(-1)
            sources.move(-1)
            dialog.folder_settings.add_rule(r'C:\Music', 'allow', False)
            dialog.folder_settings.add_rule(r'C:\Music\Ads', 'block', True)
            dialog.fields['station_genre'].setText('Pop')
            dialog.fields['receiver_url'].setText('https://metadata.example')
            dialog.fields['receiver_enabled'].setChecked(True)
            dialog.secrets['receiver'].edit.setText('test-publication-key-long-enough-123')
            dialog.secrets['receiver'].mark_changed()
            dialog.save()
            saved = store.load()
            self.assertEqual(saved.source_priority[0], windows_source_id('vlc.exe'))
            self.assertTrue(saved.windows_sources[0]['publish'])
            self.assertFalse(saved.folder_rules[0]['recursive'])
            self.assertEqual(saved.station_genre, 'Pop')
            self.assertNotIn('test-publication-key', store.path.read_text())
            cancelled = SettingsDialog(saved, store=store, credentials=vault)
            cancelled.source_settings.rows[0]['publish'] = False
            cancelled.folder_settings.rules.clear()
            cancelled.reject()
            self.assertTrue(store.load().windows_sources[0]['publish'])
            self.assertEqual(len(store.load().folder_rules), 2)

    def test_title_presets_custom_preview_and_monitor_settings_roundtrip(self):
        from PySide6.QtWidgets import QApplication
        from radio_metadata.config import ConfigStore
        from radio_metadata.settings import SettingsDialog
        from radio_metadata.credentials import MemoryCredentials
        from radio_metadata.monitor_panel import MonitorPanel
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            config = store.load()
            dialog = SettingsDialog(config, store=store, credentials=MemoryCredentials(), page='Now Playing')
            dialog.title_presets.setCurrentIndex(1)
            self.assertEqual(dialog.fields['title_format'].text(), '{artist} - {title}')
            dialog.title_presets.setCurrentIndex(4)
            dialog.fields['title_format'].setText('{title} | {artist}')
            dialog.fields['audio_monitor_enabled'].setChecked(True)
            dialog.fields['stream_url'].setText('https://audio.example/live.aac')
            dialog.fields['statistics_enabled'].setChecked(True)
            dialog.fields['statistics_url'].setText('https://stats.example/current')
            dialog.fields['statistics_format'].setCurrentIndex(1)
            dialog.save()
            saved = store.load()
            self.assertEqual(saved.title_format, '{title} | {artist}')
            self.assertEqual(saved.statistics_format, 'icecast')
            reopened = SettingsDialog(saved, store=store, credentials=MemoryCredentials())
            self.assertEqual(reopened.title_presets.currentIndex(), 4)
            self.assertEqual(reopened.fields['title_format'].text(), '{title} | {artist}')
            panel = MonitorPanel()
            panel.update_data(dict(statistics_enabled=True, audio_enabled=False, records=[dict(
                channel='statistics', state='error', message='Sin datos', checked_at='2026-11-11T10:00:00+00:00', listeners=None)],
                samples=[], incidents=[], summary=(0, None, None)))
            self.assertIn('Sin datos', panel.labels['statistics'].text())
            self.assertNotIn('0 simultáneos', panel.labels['statistics'].text())

    def test_embedded_settings_single_export_widget_save_discard_and_navigation(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from radio_metadata.config import ConfigStore
        from radio_metadata.gui import MainWindow
        from radio_metadata.output_files import OutputFilesWidget
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            config = store.load()
            window = MainWindow(store, config, demo=True)
            window.show()
            try:
                window.worker.stop();window.worker.wait()
                window.settings('Now Playing')
                self.assertEqual(window.tabs.currentIndex(), 4)
                self.assertTrue(window.settings_form.embedded)
                self.assertEqual(len(window.findChildren(OutputFilesWidget)), 1)
                self.assertEqual(window.settings_form.navigation.currentItem().text(), 'Now Playing')
                form = window.settings_form
                window.settings('Estación')
                form.fields['station_name'].setText('Draft station')
                form.fields['station_name'].setFocus()
                QTest.keyClick(form.fields['station_name'], Qt.Key.Key_Return)
                self.assertIs(window.settings_form, form)
                self.assertEqual(window.config.station_name, config.station_name)
                form.secrets['receiver'].edit.setText('draft-key')
                form.secrets['receiver'].mark_changed()
                window.tabs.setCurrentIndex(0)
                window.settings('Publicación')
                self.assertIs(window.settings_form, form)
                self.assertEqual(window.settings_form.fields['station_name'].text(), 'Draft station')
                form.reject()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertEqual(window.settings_form.fields['station_name'].text(), config.station_name)
                self.assertEqual(window.credentials.values, {})
                self.assertEqual(len(window.findChildren(OutputFilesWidget)), 1)
                form = window.settings_form
                form.fields['station_name'].setText('Saved station')
                form.fields['receiver_url'].setText('https://metadata.example')
                form.secrets['receiver'].edit.setText('saved-private-key')
                form.secrets['receiver'].mark_changed()
                form.save()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertEqual(window.config.station_name, 'Saved station')
                self.assertEqual(window.settings_store.load().station_name, 'Saved station')
                self.assertNotIn('saved-private-key', window.settings_store.path.read_text())
                self.assertEqual(len(window.findChildren(OutputFilesWidget)), 1)
                self.assertEqual(window.station.text(), 'Saved station')
                self.assertFalse(window.settings_form.isWindow())
            finally:
                window.quit()

    def test_embedded_check_allows_hiding_but_prevents_destroying_running_thread(self):
        import threading
        from unittest.mock import patch
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
        from radio_metadata.config import ConfigStore
        from radio_metadata.gui import MainWindow
        app = QApplication.instance() or QApplication([])
        finished = threading.Event()
        class Check(QThread):
            def run(self):
                finished.wait(3)
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            window = MainWindow(store, store.load(), demo=True)
            window.show()
            window.worker.stop();window.worker.wait()
            check = Check(window.settings_form)
            check.start()
            try:
                with patch('radio_metadata.gui.QSystemTrayIcon.isSystemTrayAvailable', return_value=True):
                    window.close()
                    self.assertFalse(window.isVisible())
                    self.assertTrue(check.isRunning())
                window.show()
                window.quit()
                self.assertFalse(window.exiting)
                self.assertEqual(window.tabs.currentIndex(), 4)
                self.assertIn('termine', window.settings_form.message.text())
            finally:
                finished.set();check.wait()
                window.quit()
