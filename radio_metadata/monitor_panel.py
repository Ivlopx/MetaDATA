"""Compact presentation of measured audio, server counts and local incidents."""
import csv
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox)
from .appearance import status_pixmap


class MonitorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.rows = []
        self.labels, self.dots = {}, {}
        for channel, label in (('audio', 'Audio recibido'), ('statistics', 'Oyentes del servidor')):
            row = QHBoxLayout()
            dot = QLabel()
            dot.setPixmap(status_pixmap('unknown'))
            row.addWidget(dot)
            row.addWidget(QLabel(label))
            status = QLabel('Desactivado')
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            row.addWidget(status, 1)
            self.labels[channel], self.dots[channel] = status, dot
            layout.addLayout(row)
        self.summary = QLabel('Estadísticas: sin muestras disponibles')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        actions = QHBoxLayout()
        self.check_button = QPushButton('Comprobar ahora')
        self.settings_button = QPushButton('Configurar…')
        export = QPushButton('Exportar incidentes…')
        export.clicked.connect(self.export_incidents)
        actions.addWidget(self.check_button)
        actions.addWidget(self.settings_button)
        actions.addWidget(export)
        actions.addStretch()
        layout.addLayout(actions)
        note = QLabel('Muestras periódicas desde esta computadora. El audio comprobado puede llegar con retraso respecto de la canción local. Los datos no cambian la selección de fuente ni controlan el emisor.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(QLabel('Incidentes recientes'))
        self.incidents = self.table(['Inicio', 'Fin', 'Servicio', 'Estado', 'Detalle'])
        layout.addWidget(self.incidents, 2)
        layout.addWidget(QLabel('Últimas muestras de oyentes simultáneos'))
        self.samples = self.table(['Fecha y hora', 'Oyentes'])
        layout.addWidget(self.samples, 1)

    @staticmethod
    def table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)
        return table

    @staticmethod
    def stamp(value):
        if not value:
            return 'Abierto'
        try:
            return datetime.fromisoformat(value).astimezone().strftime('%d/%m/%Y %H:%M:%S')
        except ValueError:
            return ''

    def update_data(self, data):
        records = {row['channel']: row for row in data.get('records', [])}
        for channel, enabled_key in (('audio', 'audio_enabled'), ('statistics', 'statistics_enabled')):
            row = records.get(channel)
            if data.get('demo') or not data.get(enabled_key):
                text, color = ('Demostración · no se consulta' if data.get('demo') else 'Desactivado'), 'unknown'
            elif not row:
                text, color = 'Esperando comprobación', 'unknown'
            else:
                color = 'ok' if row['state'] == 'ok' else 'warning' if row['state'] == 'silence' else 'error'
                text = row['message']
                if row.get('listeners') is not None:
                    text += f" · {row['listeners']} simultáneos"
                if row.get('rms_db') is not None:
                    text += f" · {row['rms_db']} dBFS"
                text += ' · ' + self.stamp(row['checked_at'])
            self.labels[channel].setText(text)
            self.dots[channel].setPixmap(status_pixmap(color))
            self.dots[channel].setAccessibleName(text)
        count, peak, average = data.get('summary', (0, None, None))
        self.summary.setText(f'Últimas 24 horas: pico {peak} · promedio de muestras {average:.1f} · {count} muestras válidas. No son oyentes únicos.'
                             if count else 'Estadísticas: sin muestras disponibles')
        self.rows = data.get('incidents', [])
        self.incidents.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            display = [self.stamp(row[0]), self.stamp(row[1]), 'Audio' if row[2] == 'audio' else 'Estadísticas',
                       {'error': 'Error', 'silence': 'Silencio'}.get(row[3], row[3]), row[4]]
            for j, value in enumerate(display):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.incidents.setItem(i, j, item)
        samples = data.get('samples', [])
        self.samples.setRowCount(len(samples))
        for i, row in enumerate(samples):
            self.samples.setItem(i, 0, QTableWidgetItem(self.stamp(row[0])))
            self.samples.setItem(i, 1, QTableWidgetItem(str(row[1])))

    def export_incidents(self):
        name, _ = QFileDialog.getSaveFileName(self, 'Exportar incidentes visibles', 'incidentes.csv', 'CSV (*.csv)')
        if not name:
            return
        try:
            with open(name, 'w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['Inicio', 'Fin', 'Servicio', 'Estado', 'Detalle'])
                for row in self.rows:
                    writer.writerow(["'" + str(value) if str(value).startswith(('=', '+', '-', '@')) else value for value in row])
        except OSError:
            QMessageBox.warning(self, 'Exportar incidentes', 'No se pudo guardar el archivo; revisa la carpeta y sus permisos.')
