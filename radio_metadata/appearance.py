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


def source_name(value, config=None):
    from .source_catalog import source_label
    return source_label(value, config)


def brand_icon(name):
    from pathlib import Path
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QStyle
    key = str(name).casefold()
    filename = {'radioboss': 'radioboss.png', 'spotify': 'spotify.png', 'radiocaster': 'radiocaster.png'}.get(key)
    if filename:
        icon = QIcon(str(Path(__file__).parent / 'assets' / filename))
        if not icon.isNull():
            return icon
    symbol = {'auto': QStyle.StandardPixmap.SP_BrowserReload, 'station': QStyle.StandardPixmap.SP_MediaPause,
              'azuracast': QStyle.StandardPixmap.SP_DriveNetIcon, 'zeno.fm': QStyle.StandardPixmap.SP_DriveNetIcon}.get(key, QStyle.StandardPixmap.SP_ComputerIcon)
    return QApplication.style().standardIcon(symbol)


def status_pixmap(state):
    from PySide6.QtGui import QColor, QPainter, QPixmap
    color = {'ok': '#107c10', 'error': '#c42b1c', 'warning': '#9a6700', 'unknown': '#808080'}[state]
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, 8, 8)
    painter.end()
    return pixmap
