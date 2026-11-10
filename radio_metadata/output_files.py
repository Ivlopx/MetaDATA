"""Selectable export paths and explicit desktop actions."""
from pathlib import Path
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)


class OutputFilesWidget(QWidget):
    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = Path(directory).resolve()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.kind = QComboBox()
        for label, name in [('XML', 'nowplaying.xml'), ('TXT', 'nowplaying.txt'), ('JSON', 'nowplaying.json')]:
            self.kind.addItem(label, name)
        row.addWidget(self.kind)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setAccessibleName('Ruta del archivo Now Playing')
        row.addWidget(self.path, 1)
        self.copy_button = QPushButton('Copiar ruta')
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.path.text()))
        row.addWidget(self.copy_button)
        self.open_button = QPushButton('Abrir carpeta')
        self.open_button.clicked.connect(self.open_folder)
        row.addWidget(self.open_button)
        layout.addLayout(row)
        self.hint = QLabel()
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setWordWrap(True)
        self.hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.hint)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.path.setText(str(self.directory / self.kind.currentData()))
        self.path.setCursorPosition(0)
        self.hint.setText({'nowplaying.xml': 'XML: atributo TRACK/CASTTITLE para el título combinado; artista, título y álbum separados. La plantilla depende del emisor.',
                           'nowplaying.txt': 'Artista - Título en UTF-8; línea vacía durante pausas.',
                           'nowplaying.json': 'Datos completos; imágenes separadas en la carpeta covers.'}[self.kind.currentData()])

    def open_folder(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.directory))):
                raise OSError()
        except OSError:
            QMessageBox.warning(self, 'Abrir carpeta', 'No se pudo abrir la carpeta. Usa Copiar ruta o revisa sus permisos.')
