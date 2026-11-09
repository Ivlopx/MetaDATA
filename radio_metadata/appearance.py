"""Desktop controls and system-managed appearance, without a custom color skin."""
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QStyleFactory


def apply_appearance(app: QApplication, theme='system'):
    app.setStyleSheet('')
    if sys.platform == 'win32':
        styles = {name.casefold(): name for name in QStyleFactory.keys()}
        if 'windows11' in styles and app.style().objectName().casefold() != 'windows11':
            app.setStyle(styles['windows11'])
    scheme = {'system': Qt.ColorScheme.Unknown, 'light': Qt.ColorScheme.Light, 'dark': Qt.ColorScheme.Dark}[theme]
    app.styleHints().setColorScheme(scheme)
