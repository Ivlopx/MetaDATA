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
            self.assertEqual(text.strip(), config.idle_message)
