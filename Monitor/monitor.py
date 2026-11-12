"""Monitor ECG en tiempo real para datos seriales de un AD8232."""

import csv
import math
import sys
import time
from collections import deque
from datetime import datetime

import pyqtgraph as pg
import serial
from serial.tools import list_ports
from PyQt6.QtCore import QPropertyAnimation, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtCore import pyqtProperty  # type: ignore[reportAttributeAccessIssue]
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SerialReader(QThread):
    """Lee y valida las líneas del puerto sin bloquear la interfaz."""

    samples_received = pyqtSignal(object)
    leads_received = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        pending_samples = []
        last_emit = time.monotonic()
        try:
            with serial.Serial(self.port, self.baudrate, timeout=0.1) as connection:
                self.connection_changed.emit(True)
                while not self._stop_requested:
                    line = connection.readline()
                    now = time.monotonic()

                    if line:
                        text = line.decode("ascii", errors="ignore").strip()
                        if text.startswith("valor:"):
                            try:
                                value = int(text.partition(":")[2])
                            except ValueError:
                                value = -1
                            if 0 <= value <= 4095:
                                pending_samples.append((value, now))
                        elif text in ("leads:OK", "leads:ERROR"):
                            self.leads_received.emit(text.partition(":")[2])

                    if pending_samples and (
                        len(pending_samples) >= 128 or now - last_emit >= 0.025
                    ):
                        self.samples_received.emit(pending_samples)
                        pending_samples = []
                        last_emit = now

                if pending_samples:
                    self.samples_received.emit(pending_samples)
        except (serial.SerialException, OSError) as exc:
            if not self._stop_requested:
                self.error_occurred.emit(f"No se pudo leer {self.port}: {exc}")
        finally:
            self.connection_changed.emit(False)


class ECGPeakDetector:
    """Detecta máximos con umbral adaptativo y período refractario."""

    def __init__(self) -> None:
        self.baseline: float | None = None
        self.last_timestamp: float | None = None
        self.previous_value: float | None = None
        self.previous_timestamp: float | None = None
        self.before_previous_value: float | None = None
        self.last_peak_timestamp: float | None = None
        self.peak_amplitude = 40.0
        self.intervals = deque(maxlen=5)

    def add_sample(self, value: float, timestamp: float) -> int | None:
        baseline = self.baseline
        last_timestamp = self.last_timestamp
        if baseline is None or last_timestamp is None:
            self.baseline = value
            self.last_timestamp = timestamp
            self.before_previous_value = value
            self.previous_value = value
            self.previous_timestamp = timestamp
            return None

        previous_value = self.previous_value
        before_previous_value = self.before_previous_value
        previous_timestamp = self.previous_timestamp
        last_peak_timestamp = self.last_peak_timestamp
        elapsed = max(0.0, timestamp - last_timestamp)
        # La línea base sigue lentamente el cambio de offset de la señal.
        alpha = 1.0 - math.exp(-elapsed / 1.5)
        baseline += alpha * (value - baseline)
        self.baseline = baseline
        threshold = max(15.0, self.peak_amplitude * 0.45)

        bpm = None
        peak_detected = False
        if (
            previous_value is not None
            and before_previous_value is not None
            and previous_timestamp is not None
            and previous_value > before_previous_value
            and previous_value >= value
            and previous_value - baseline >= threshold
            and (
                last_peak_timestamp is None
                or previous_timestamp - last_peak_timestamp >= 0.3
            )
        ):
            peak_detected = True
            amplitude = previous_value - baseline
            self.peak_amplitude = 0.8 * self.peak_amplitude + 0.2 * amplitude

            if last_peak_timestamp is not None:
                interval = previous_timestamp - last_peak_timestamp
                if interval > 0:
                    self.intervals.append(interval)
                    bpm = round(60.0 / (sum(self.intervals) / len(self.intervals)))

            self.last_peak_timestamp = previous_timestamp

        self.before_previous_value = previous_value
        self.previous_value = value
        self.previous_timestamp = timestamp
        self.last_timestamp = timestamp
        return bpm if peak_detected else None


class PulseLabel(QLabel):
    """Etiqueta BPM cuyo tamaño puede animarse mediante QPropertyAnimation."""

    def __init__(self, text: str, point_size: float, parent=None) -> None:
        super().__init__(text, parent)
        self._point_size = point_size
        self._pulse_scale = 1.0
        self._pulse_animation: QPropertyAnimation | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(115)
        self._apply_font()

    def _apply_font(self) -> None:
        font = QFont("Segoe UI", QFont.Weight.Bold)
        font.setPointSizeF(self._point_size * self._pulse_scale)
        self.setFont(font)

    def get_pulse_scale(self) -> float:
        return self._pulse_scale

    def set_pulse_scale(self, scale: float) -> None:
        self._pulse_scale = scale
        self._apply_font()

    pulseScale = pyqtProperty(float, get_pulse_scale, set_pulse_scale)


class HeartWidget(QWidget):
    """Dibuja un corazón que se agranda brevemente en cada latido."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pulse_scale = 1.0
        self._pulse_animation: QPropertyAnimation | None = None
        self.setMinimumSize(90, 90)

    def get_pulse_scale(self) -> float:
        return self._pulse_scale

    def set_pulse_scale(self, scale: float) -> None:
        self._pulse_scale = scale
        self.update()

    pulseScale = pyqtProperty(float, get_pulse_scale, set_pulse_scale)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(self._pulse_scale, self._pulse_scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.red)
        font = QFont("Segoe UI Symbol", 48, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(-40, 35, "♥")


class MainWindow(QMainWindow):
    """Ventana principal del monitor ECG."""

    HISTORY_SIZE = 500

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Monitor ECG | AD8232")
        self.resize(1050, 760)

        self.reader = None
        self.leads_state = "DESCONOCIDO"
        self.csv_file = None
        self.csv_writer = None
        self.raw_values = deque(maxlen=self.HISTORY_SIZE)
        self.plot_values = deque(maxlen=self.HISTORY_SIZE)
        self.smoothing_values = deque(maxlen=5)
        self.peak_detector = ECGPeakDetector()

        self._build_ui()
        self._configure_theme()

        self.lead_blink_timer = QTimer(self)
        self.lead_blink_timer.setInterval(500)
        self.lead_blink_timer.timeout.connect(self._toggle_lead_error)
        self._lead_error_visible = True

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("MONITOR ECG")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("Puerto"))
        self.port_selector = QComboBox()
        self.port_selector.setEditable(True)
        self.port_selector.setMinimumWidth(150)
        header.addWidget(self.port_selector)

        refresh_button = QPushButton("Actualizar")
        refresh_button.clicked.connect(self.refresh_ports)
        header.addWidget(refresh_button)

        self.connect_button = QPushButton("Conectar")
        self.connect_button.setObjectName("connectButton")
        self.connect_button.clicked.connect(self.toggle_connection)
        header.addWidget(self.connect_button)
        layout.addLayout(header)

        status_row = QHBoxLayout()
        self.connection_label = QLabel("Desconectado")
        self.connection_label.setObjectName("mutedLabel")
        status_row.addWidget(self.connection_label)
        status_row.addStretch()
        status_row.addWidget(QLabel("Electrodos:"))
        self.leads_label = QLabel("DESCONOCIDO")
        self.leads_label.setObjectName("leadsUnknown")
        status_row.addWidget(self.leads_label)
        layout.addLayout(status_row)

        bpm_row = QHBoxLayout()
        bpm_row.addStretch()
        bpm_column = QVBoxLayout()
        bpm_caption = QLabel("FRECUENCIA CARDÍACA")
        bpm_caption.setObjectName("mutedLabel")
        bpm_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bpm_label = PulseLabel("--", 72)
        self.bpm_label.setObjectName("bpmLabel")
        unit = QLabel("BPM")
        unit.setObjectName("mutedLabel")
        unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bpm_column.addWidget(bpm_caption)
        bpm_column.addWidget(self.bpm_label)
        bpm_column.addWidget(unit)
        bpm_row.addLayout(bpm_column)
        heart_column = QVBoxLayout()
        heart_column.addStretch()
        self.heart_widget = HeartWidget()
        heart_column.addWidget(self.heart_widget)
        heart_column.addStretch()
        bpm_row.addLayout(heart_column)
        bpm_row.addStretch()
        layout.addLayout(bpm_row)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#0a0a0a")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "Señal", units="ADC")
        self.plot_widget.setLabel("bottom", "Muestras recientes")
        self.plot_widget.setYRange(0, 4095)
        self.plot_widget.setXRange(0, self.HISTORY_SIZE - 1)
        plot_item = self.plot_widget.getPlotItem()
        if plot_item is not None:
            plot_item.setMenuEnabled(False)
            plot_item.hideButtons()
        self.curve = self.plot_widget.plot(pen=pg.mkPen("#00ff66", width=2))
        layout.addWidget(self.plot_widget, stretch=1)

        footer = QHBoxLayout()
        self.smoothing_checkbox = QCheckBox("Suavizado (media móvil de 5 muestras)")
        footer.addWidget(self.smoothing_checkbox)
        footer.addStretch()
        self.save_button = QPushButton("Guardar CSV")
        self.save_button.clicked.connect(self.toggle_csv_recording)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        self.message_label = QLabel("")
        self.message_label.setObjectName("messageLabel")
        layout.addWidget(self.message_label)

        self.refresh_ports()

    def _configure_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #0a0a0a; color: #eeeeee; }
            QLabel { color: #eeeeee; }
            QLabel#title { color: #00ff66; font-size: 20px; font-weight: 700; }
            QLabel#mutedLabel { color: #9a9a9a; }
            QLabel#bpmLabel { color: #ff3b30; }
            QLabel#leadsUnknown { color: #aaaaaa; font-weight: 700; }
            QLabel#leadsOk { color: #00ff66; font-weight: 700; }
            QLabel#leadsError { color: #ff3b30; font-weight: 700; }
            QLabel#messageLabel { color: #ff806f; }
            QComboBox {
                background: #1a1a1a; border: 1px solid #343434; border-radius: 6px;
                padding: 8px; min-height: 20px;
            }
            QComboBox QAbstractItemView { background: #1a1a1a; selection-background-color: #333333; }
            QPushButton {
                background: #202020; border: 1px solid #393939; border-radius: 7px;
                padding: 9px 16px; color: #eeeeee;
            }
            QPushButton:hover { background: #303030; border-color: #00cc55; }
            QPushButton#connectButton { background: #087f3d; border-color: #00b84a; }
            QPushButton#connectButton:hover { background: #0a994a; }
            QCheckBox { color: #cccccc; spacing: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            """
        )

    def refresh_ports(self) -> None:
        current_port = self.port_selector.currentText().strip() or "COM3"
        ports = [port.device for port in list_ports.comports()]
        if current_port not in ports:
            ports.insert(0, current_port)
        if "COM3" not in ports:
            ports.append("COM3")

        self.port_selector.clear()
        self.port_selector.addItems(ports)
        self.port_selector.setCurrentText(current_port)

    def toggle_connection(self) -> None:
        if self.reader is not None and self.reader.isRunning():
            self.connect_button.setEnabled(False)
            self.connection_label.setText("Desconectando…")
            self.reader.stop()
            return

        port = self.port_selector.currentText().strip()
        if not port:
            self.message_label.setText("Selecciona un puerto serial.")
            return

        self.message_label.clear()
        self._set_leads_state("DESCONOCIDO")
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Conectando…")
        self.connection_label.setText(f"Conectando a {port}…")

        self.reader = SerialReader(port)
        self.reader.samples_received.connect(self.process_samples)
        self.reader.leads_received.connect(self._set_leads_state)
        self.reader.connection_changed.connect(self._connection_changed)
        self.reader.error_occurred.connect(self._show_error)
        self.reader.start()

    def _connection_changed(self, connected: bool) -> None:
        self.connect_button.setEnabled(True)
        if connected:
            self.connect_button.setText("Desconectar")
            self.connection_label.setText(f"Conectado a {self.port_selector.currentText()}")
            self.message_label.clear()
        else:
            self.connect_button.setText("Conectar")
            self.connection_label.setText("Desconectado")

    def _show_error(self, message: str) -> None:
        self.message_label.setText(message)

    def _set_leads_state(self, state: str) -> None:
        self.leads_state = state
        if state == "OK":
            self.lead_blink_timer.stop()
            self._lead_error_visible = True
            self.leads_label.setText("OK")
            self.leads_label.setObjectName("leadsOk")
        elif state == "ERROR":
            self._lead_error_visible = True
            self.leads_label.setText("ERROR")
            self.leads_label.setObjectName("leadsError")
            self.lead_blink_timer.start()
        else:
            self.lead_blink_timer.stop()
            self.leads_label.setText("DESCONOCIDO")
            self.leads_label.setObjectName("leadsUnknown")
        style = self.leads_label.style()
        if style is not None:
            style.unpolish(self.leads_label)
            style.polish(self.leads_label)

    def _toggle_lead_error(self) -> None:
        self._lead_error_visible = not self._lead_error_visible
        color = "#ff3b30" if self._lead_error_visible else "#61201d"
        self.leads_label.setStyleSheet(f"color: {color}; font-weight: 700;")

    def process_samples(self, samples: list[tuple[int, float]]) -> None:
        for raw_value, timestamp in samples:
            self.raw_values.append(raw_value)
            plotted_value = raw_value
            if self.smoothing_checkbox.isChecked():
                self.smoothing_values.append(raw_value)
                plotted_value = sum(self.smoothing_values) / len(self.smoothing_values)

            self.plot_values.append(plotted_value)
            bpm = self.peak_detector.add_sample(plotted_value, timestamp)
            if bpm is not None:
                self.bpm_label.setText(str(bpm))
                self._animate_beat()

            if self.csv_writer is not None:
                try:
                    self.csv_writer.writerow(
                        [datetime.now().isoformat(timespec="milliseconds"), raw_value, self.leads_state]
                    )
                except OSError as exc:
                    self._stop_csv_recording()
                    self._show_error(f"No se pudo escribir el CSV: {exc}")

        self.curve.setData(list(self.plot_values))

    def _animate_beat(self) -> None:
        for widget, duration in ((self.bpm_label, 220), (self.heart_widget, 420)):
            animation = widget._pulse_animation
            if animation is None:
                animation = QPropertyAnimation(widget, b"pulseScale", self)
                animation.setDuration(duration)
                animation.setKeyValueAt(0.0, 1.0)
                animation.setKeyValueAt(0.35, 1.3)
                animation.setKeyValueAt(1.0, 1.0)
                widget._pulse_animation = animation
            animation.stop()
            animation.start()

    def toggle_csv_recording(self) -> None:
        if self.csv_writer is not None:
            self._stop_csv_recording()
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Guardar datos ECG", "ecg_datos.csv", "Archivos CSV (*.csv)"
        )
        if not filename:
            return
        try:
            self.csv_file = open(filename, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["fecha_hora", "valor", "leads"])
        except OSError as exc:
            self.csv_file = None
            self.csv_writer = None
            QMessageBox.critical(self, "Error al guardar", f"No se pudo crear el archivo:\n{exc}")
            return

        self.save_button.setText("Detener CSV")

    def _stop_csv_recording(self) -> None:
        if self.csv_file is not None:
            self.csv_file.close()
        self.csv_file = None
        self.csv_writer = None
        self.save_button.setText("Guardar CSV")

    def closeEvent(self, event) -> None:
        if self.reader is not None and self.reader.isRunning():
            self.reader.stop()
            self.reader.wait()
        self._stop_csv_recording()
        event.accept()


def main() -> None:
    """Inicia la aplicación de escritorio."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()