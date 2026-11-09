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
                self.assertIn("Álbum de prueba", window.album.text())
                self.assertEqual(window.history.columnCount(), 6)
                dialog = SettingsDialog(config, window)
                dialog.fields["station_name"].setText("Radio de prueba")
                dialog.fields["remote_monitor_enabled"].setChecked(True)
                dialog.fields["stream_url"].setText("https://radio.example/live.mp3")
                dialog.save()
                self.assertEqual(dialog.result_config.station_name, "Radio de prueba")
                self.assertTrue(dialog.result_config.remote_monitor_enabled)
                self.assertEqual(dialog.result_config.stream_url, "https://radio.example/live.mp3")
                window.scenarios.setCurrentIndex(3)
                until(lambda: window.title.text() == config.break_message)
                self.assertEqual(window.history.rowCount(), 1)
                self.assertEqual(window.album.text(), "")
                window.scenarios.setCurrentIndex(2)
                until(lambda: "Ambas" in window.reason.text() and window.title.text() == "Canción de prueba")
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
                self.assertEqual([window.tabs.tabText(i) for i in range(4)], ['Inicio', 'Historial', 'Conexiones', 'Ajustes'])
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
