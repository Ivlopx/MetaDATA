import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Metadatos de estación para RadioCaster")
    parser.add_argument("--demo", action="store_true", help="datos sintéticos; sin conexiones externas")
    parser.add_argument("--data-dir", type=Path, help="carpeta de configuración, historial y salidas")
    args = parser.parse_args()
    directory = args.data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "RadioMetadataManager-OggPrueba"
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger("radio_metadata").addHandler(handler)
    logging.getLogger("radio_metadata").setLevel(logging.INFO)

    from PySide6.QtCore import QLockFile, QThread
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .config import ConfigStore
    from .gui import MainWindow
    from .appearance import apply_appearance

    app = QApplication(sys.argv[:1])
    app.setApplicationName("MetaDATA · Prueba de codificadores")
    lock = QLockFile(str(directory / "app.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "Radio Metadata", "Ya existe una instancia usando esta carpeta de datos.")
        return 1
    store = ConfigStore(directory)
    try:
        config = store.load()
    except (ValueError, TypeError, OSError) as error:
        QMessageBox.critical(None, "Configuración inválida", f"No se inició la aplicación ({type(error).__name__}). Revisa {store.path}. No se sobrescribió tu configuración.")
        return 1
    apply_appearance(app, config.theme)
    window = MainWindow(store, config, args.demo)
    # Windows logout / OS quit also shut down the worker.
    def shutdown():
        window.worker.stop()
        window.worker.wait()
        for checker in window.findChildren(QThread):
            checker.wait()
    app.aboutToQuit.connect(shutdown)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
