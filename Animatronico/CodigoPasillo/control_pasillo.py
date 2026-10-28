"""Interfaz para seleccionar y reproducir rutinas del animatronico."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


ROUTINES: tuple[
    tuple[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]], ...
] = (
    (
        "1. Despertar",
        (
            (
                350,
                (("NECK", 105), ("R_ARM", 105), ("L_ARM", 75), ("WAIST", 95)),
            ),
            (
                350,
                (("NECK", 80), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
            (
                400,
                (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
        ),
    ),
    (
        "2. Mirada curiosa",
        (
            (400, (("NECK", 65), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
            (
                400,
                (("NECK", 115), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
            (
                400,
                (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
        ),
    ),
    (
        "3. Saludo",
        (
            (
                300,
                (("NECK", 100), ("R_ARM", 125), ("L_ARM", 95), ("WAIST", 90)),
            ),
            (
                300,
                (("NECK", 100), ("R_ARM", 90), ("L_ARM", 95), ("WAIST", 90)),
            ),
            (
                300,
                (("NECK", 100), ("R_ARM", 125), ("L_ARM", 95), ("WAIST", 90)),
            ),
            (
                400,
                (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
        ),
    ),
    (
        "4. Giro de cintura",
        (
            (400, (("NECK", 100), ("R_ARM", 95), ("L_ARM", 85), ("WAIST", 70))),
            (
                400,
                (("NECK", 80), ("R_ARM", 85), ("L_ARM", 95), ("WAIST", 110)),
            ),
            (
                400,
                (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
        ),
    ),
    (
        "5. Brazos arriba",
        (
            (
                350,
                (("NECK", 100), ("R_ARM", 115), ("L_ARM", 110), ("WAIST", 90)),
            ),
            (
                350,
                (("NECK", 80), ("R_ARM", 70), ("L_ARM", 65), ("WAIST", 90)),
            ),
            (
                400,
                (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
        ),
    ),
    (
        "6. Balanceo",
        (
            (
                350,
                (("NECK", 105), ("R_ARM", 105), ("L_ARM", 75), ("WAIST", 75)),
            ),
            (
                350,
                (("NECK", 75), ("R_ARM", 75), ("L_ARM", 105), ("WAIST", 105)),
            ),
            (
                400,
                (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90)),
            ),
        ),
    ),
)

COMPLEX_ROUTINES: tuple[
    tuple[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]], ...
] = (
    (
        "1. Despertar con estiramiento",
        (
            (450, (("NECK", 102), ("R_ARM", 98), ("L_ARM", 82), ("WAIST", 92))),
            (500, (("NECK", 108), ("R_ARM", 112), ("L_ARM", 70), ("WAIST", 95))),
            (350, (("NECK", 100), ("R_ARM", 120), ("L_ARM", 68), ("WAIST", 90))),
            (550, (("NECK", 88), ("R_ARM", 105), ("L_ARM", 80), ("WAIST", 88))),
            (400, (("NECK", 78), ("R_ARM", 92), ("L_ARM", 92), ("WAIST", 90))),
            (500, (("NECK", 94), ("R_ARM", 88), ("L_ARM", 96), ("WAIST", 92))),
            (600, (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
        ),
    ),
    (
        "2. Buscar un sonido",
        (
            (400, (("NECK", 98), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
            (450, (("NECK", 76), ("R_ARM", 98), ("L_ARM", 86), ("WAIST", 84))),
            (500, (("NECK", 68), ("R_ARM", 108), ("L_ARM", 78), ("WAIST", 78))),
            (350, (("NECK", 72), ("R_ARM", 116), ("L_ARM", 74), ("WAIST", 82))),
            (500, (("NECK", 92), ("R_ARM", 100), ("L_ARM", 88), ("WAIST", 98))),
            (450, (("NECK", 112), ("R_ARM", 92), ("L_ARM", 96), ("WAIST", 104))),
            (600, (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
        ),
    ),
    (
        "3. Saludo natural",
        (
            (400, (("NECK", 98), ("R_ARM", 100), ("L_ARM", 86), ("WAIST", 92))),
            (450, (("NECK", 104), ("R_ARM", 126), ("L_ARM", 82), ("WAIST", 94))),
            (300, (("NECK", 100), ("R_ARM", 110), ("L_ARM", 84), ("WAIST", 92))),
            (300, (("NECK", 102), ("R_ARM", 128), ("L_ARM", 82), ("WAIST", 94))),
            (350, (("NECK", 98), ("R_ARM", 114), ("L_ARM", 88), ("WAIST", 90))),
            (450, (("NECK", 88), ("R_ARM", 98), ("L_ARM", 94), ("WAIST", 88))),
            (550, (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
        ),
    ),
    (
        "4. Duda y encogimiento",
        (
            (450, (("NECK", 98), ("R_ARM", 96), ("L_ARM", 86), ("WAIST", 94))),
            (500, (("NECK", 110), ("R_ARM", 112), ("L_ARM", 68), ("WAIST", 98))),
            (400, (("NECK", 114), ("R_ARM", 120), ("L_ARM", 64), ("WAIST", 100))),
            (500, (("NECK", 104), ("R_ARM", 108), ("L_ARM", 72), ("WAIST", 96))),
            (450, (("NECK", 80), ("R_ARM", 92), ("L_ARM", 96), ("WAIST", 86))),
            (500, (("NECK", 86), ("R_ARM", 96), ("L_ARM", 92), ("WAIST", 88))),
            (550, (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
        ),
    ),
    (
        "5. Mirar alrededor",
        (
            (400, (("NECK", 90), ("R_ARM", 94), ("L_ARM", 86), ("WAIST", 90))),
            (450, (("NECK", 72), ("R_ARM", 98), ("L_ARM", 84), ("WAIST", 82))),
            (400, (("NECK", 68), ("R_ARM", 102), ("L_ARM", 80), ("WAIST", 76))),
            (450, (("NECK", 94), ("R_ARM", 96), ("L_ARM", 88), ("WAIST", 98))),
            (400, (("NECK", 112), ("R_ARM", 90), ("L_ARM", 96), ("WAIST", 108))),
            (450, (("NECK", 106), ("R_ARM", 88), ("L_ARM", 100), ("WAIST", 102))),
            (550, (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
        ),
    ),
    (
        "6. Balanceo con gestos",
        (
            (400, (("NECK", 96), ("R_ARM", 106), ("L_ARM", 80), ("WAIST", 82))),
            (450, (("NECK", 104), ("R_ARM", 114), ("L_ARM", 74), ("WAIST", 76))),
            (400, (("NECK", 100), ("R_ARM", 108), ("L_ARM", 84), ("WAIST", 84))),
            (450, (("NECK", 84), ("R_ARM", 82), ("L_ARM", 108), ("WAIST", 102))),
            (400, (("NECK", 76), ("R_ARM", 74), ("L_ARM", 116), ("WAIST", 108))),
            (450, (("NECK", 82), ("R_ARM", 86), ("L_ARM", 104), ("WAIST", 98))),
            (550, (("NECK", 90), ("R_ARM", 90), ("L_ARM", 90), ("WAIST", 90))),
        ),
    ),
)


class SerialWorker(QThread):
    """Lee el puerto serie y escribe comandos sin bloquear la interfaz."""

    connection_changed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str) -> None:
        super().__init__()
        self.port = port
        self.commands: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()

    def send_command(self, command: str) -> None:
        if command and "\n" not in command and "\r" not in command:
            self.commands.put(command)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        if serial is None:
            self.error_occurred.emit(
                "Falta pyserial. Instálalo con: pip install pyserial"
            )
            self.connection_changed.emit(False, "pyserial no instalado")
            return

        try:
            port_handle = serial.Serial(
                self.port,
                115200,
                timeout=0.1,
                write_timeout=1.0,
            )
        except (serial.SerialException, OSError) as error:
            self.error_occurred.emit(f"No se pudo abrir {self.port}: {error}")
            self.connection_changed.emit(False, f"Error de conexión: {error}")
            return

        self.connection_changed.emit(True, f"Conectado: {self.port}")
        disconnect_message = "Desconectado"
        try:
            while not self._stop_event.is_set():
                try:
                    line = (
                        port_handle.readline()
                        .decode("ascii", errors="ignore")
                        .strip()
                    )
                except (serial.SerialException, OSError) as error:
                    self.error_occurred.emit(
                        f"Se perdió la conexión con {self.port}: {error}"
                    )
                    disconnect_message = f"Error de conexión: {error}"
                    break

                try:
                    while True:
                        command = self.commands.get_nowait()
                        try:
                            port_handle.write(f"{command}\n".encode("ascii"))
                        except (serial.SerialException, OSError) as error:
                            self.error_occurred.emit(
                                f"Error enviando '{command}': {error}"
                            )
                            disconnect_message = (
                                f"Error enviando '{command}': {error}"
                            )
                            return
                except queue.Empty:
                    pass
        finally:
            if port_handle.is_open:
                port_handle.close()
            self.connection_changed.emit(False, disconnect_message)


class PasilloWindow(QMainWindow):
    """Ventana mínima de control del modo demostración."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Animatronico - Demo de pasillo")
        self.setMinimumWidth(420)
        self.setStyleSheet(
            "QWidget { background:#101214; color:#e4e8e5; "
            "font-family:Consolas,monospace; } "
            "QPushButton, QComboBox { padding:8px; background:#282020; "
            "border:1px solid #704545; } "
            "QPushButton:hover { background:#492b2b; } "
            "QGroupBox { border:1px solid #704545; margin-top:8px; "
            "padding-top:8px; } "
            "QCheckBox::indicator { width:16px; height:16px; } "
            "QCheckBox::indicator:checked { background:#e05252; "
            "border:1px solid #ff8a8a; } "
            "QSlider::groove:horizontal { height:6px; background:#493232; } "
            "QSlider::handle:horizontal { background:#e05252; width:14px; "
            "margin:-5px 0; border-radius:7px; }"
        )

        self.worker: SerialWorker | None = None
        self.connected = False
        self.routine_active = False
        self.routine_sequence: list[
            tuple[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]
        ] = []
        self.routine_index = 0
        self.step_index = 0

        central = QWidget()
        layout = QVBoxLayout(central)
        connection_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self._refresh_ports()
        self.connection_button = QPushButton("CONECTAR")
        self.connection_button.clicked.connect(self._toggle_connection)
        connection_row.addWidget(self.port_combo, 1)
        connection_row.addWidget(self.connection_button)
        layout.addLayout(connection_row)

        self.connection_label = QLabel("ESP32 desconectado")
        layout.addWidget(self.connection_label)

        self.speed_value_label = QLabel("Velocidad: 350 ms")
        layout.addWidget(self.speed_value_label)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(100, 3000)
        self.speed_slider.setValue(350)
        self.speed_slider.valueChanged.connect(self._update_speed_label)
        layout.addWidget(self.speed_slider)

        routine_group = QGroupBox("RUTINAS BÁSICAS")
        routine_layout = QVBoxLayout(routine_group)
        routine_layout.addWidget(
            QLabel("Selecciona una o varias; se reproducen en orden numérico.")
        )
        self.routine_checks: list[QCheckBox] = []
        for name, _steps in ROUTINES:
            checkbox = QCheckBox(name)
            self.routine_checks.append(checkbox)
            routine_layout.addWidget(checkbox)

        self.start_button = QPushButton("REPRODUCIR BÁSICAS EN BUCLE")
        self.start_button.clicked.connect(self._start_routine_sequence)
        routine_layout.addWidget(self.start_button)

        complex_group = QGroupBox("RUTINAS COMPLEJAS")
        complex_layout = QVBoxLayout(complex_group)
        complex_layout.addWidget(
            QLabel(
                "Secuencias coordinadas de más de 5 pasos. "
                "Selecciona una o varias para repetirlas."
            )
        )
        self.complex_routine_checks: list[QCheckBox] = []
        for name, _steps in COMPLEX_ROUTINES:
            checkbox = QCheckBox(name)
            self.complex_routine_checks.append(checkbox)
            complex_layout.addWidget(checkbox)
        self.start_complex_button = QPushButton(
            "REPRODUCIR COMPLEJAS EN BUCLE"
        )
        self.start_complex_button.clicked.connect(
            self._start_complex_routine_sequence
        )
        complex_layout.addWidget(self.start_complex_button)

        self.stop_button = QPushButton("DETENER")
        self.stop_button.clicked.connect(self._stop_routine_sequence)
        self.stop_button.setEnabled(False)
        layout.addWidget(routine_group)
        layout.addWidget(complex_group)

        sound_group = QGroupBox("SONIDOS MP3")
        sound_layout = QVBoxLayout(sound_group)
        sound_layout.addWidget(
            QLabel("Marca los sonidos que quieres incluir en la playlist.")
        )
        self.sound_checks: list[QCheckBox] = []
        sound_files = sorted(
            (Path(__file__).resolve().parent / "sonidos").glob("*.mp3"),
            key=lambda path: path.name.casefold(),
        )
        if sound_files:
            sound_grid = QGridLayout()
            for index, sound_file in enumerate(sound_files):
                checkbox = QCheckBox(sound_file.name)
                checkbox.setProperty("sound_path", str(sound_file))
                self.sound_checks.append(checkbox)
                sound_grid.addWidget(checkbox, index // 2, index % 2)
            sound_layout.addLayout(sound_grid)
        else:
            sound_layout.addWidget(
                QLabel("No se encontraron archivos MP3 en la carpeta sonidos.")
            )

        self.sound_playlist: list[Path] = []
        self.sound_playlist_index = 0
        self.sound_playlist_active = False
        self.sound_play_button = QPushButton(
            "REPRODUCIR SELECCIÓN EN BUCLE"
        )
        self.sound_play_button.clicked.connect(self._start_sound_playlist)
        sound_layout.addWidget(self.sound_play_button)
        self.sound_stop_button = QPushButton("DETENER SONIDO")
        self.sound_stop_button.clicked.connect(self._stop_sound_playlist)
        sound_layout.addWidget(self.sound_stop_button)
        self.sound_status_label = QLabel("Playlist detenida")
        self.sound_status_label.setWordWrap(True)
        sound_layout.addWidget(self.sound_status_label)

        self.sound_player = QMediaPlayer(self)
        self.sound_output = QAudioOutput(self)
        self.sound_output.setVolume(0.8)
        self.sound_player.setAudioOutput(self.sound_output)
        self.sound_player.errorOccurred.connect(self._sound_error)
        self.sound_player.mediaStatusChanged.connect(
            self._advance_sound_playlist
        )

        layout.addWidget(sound_group)
        layout.addWidget(self.stop_button)

        self.state_label = QLabel("SELECCIONA Y REPRODUCE UNA RUTINA")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setMinimumHeight(70)
        self.state_label.setWordWrap(True)
        self.state_label.setStyleSheet(
            "font-size:30px; font-weight:bold; color:#e05252;"
        )
        layout.addWidget(self.state_label)
        self.routine_timer = QTimer(self)
        self.routine_timer.timeout.connect(self._advance_routine)
        self.setCentralWidget(central)

    def _refresh_ports(self) -> None:
        self.port_combo.clear()
        if list_ports is None:
            self.port_combo.addItem("pyserial no instalado")
            return
        ports = sorted(port.device for port in list_ports.comports())
        self.port_combo.addItems(ports)
        if not ports:
            self.port_combo.addItem("Sin puertos disponibles")

    def _toggle_connection(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)
            self.worker = None
            return
        if serial is None:
            QMessageBox.critical(
                self,
                "Dependencia faltante",
                "Falta pyserial. Instálalo con: pip install pyserial",
            )
            return

        port = self.port_combo.currentText()
        if not port or port == "Sin puertos disponibles":
            self._refresh_ports()
            port = self.port_combo.currentText()
        if not port or port == "Sin puertos disponibles":
            QMessageBox.warning(
                self, "Puerto no disponible", "No se encontró un puerto COM."
            )
            return

        self.worker = SerialWorker(port)
        self.worker.connection_changed.connect(self._connection_status)
        self.worker.error_occurred.connect(self._show_error)
        self.worker.start()

    def _connection_status(self, connected: bool, message: str) -> None:
        self.connected = connected
        if not connected and self.routine_active:
            self._stop_routine_sequence()
        self.connection_label.setText(message)
        self.connection_button.setText(
            "DESCONECTAR" if connected else "CONECTAR"
        )
        self.port_combo.setEnabled(not connected)

    def _show_error(self, message: str) -> None:
        self.connection_label.setText(message)

    def _update_speed_label(self, value: int) -> None:
        self.speed_value_label.setText(f"Velocidad: {value} ms")

    def _start_sound_playlist(self) -> None:
        selected = [
            Path(checkbox.property("sound_path"))
            for checkbox in self.sound_checks
            if checkbox.isChecked()
        ]
        if not selected:
            QMessageBox.warning(
                self,
                "Playlist vacía",
                "Selecciona al menos un sonido para reproducir.",
            )
            return

        self.sound_playlist = selected
        self.sound_playlist_index = 0
        self.sound_playlist_active = True
        self._play_sound_playlist_track()

    def _play_sound_playlist_track(self) -> None:
        if not self.sound_playlist_active:
            return

        sound_file = self.sound_playlist[self.sound_playlist_index]
        if not sound_file.is_file():
            self.sound_playlist_active = False
            self.sound_status_label.setText(
                f"No se encontró el archivo: {sound_file.name}"
            )
            return
        self.sound_player.setSource(
            QUrl.fromLocalFile(str(sound_file.resolve()))
        )
        self.sound_player.play()
        self.sound_status_label.setText(
            f"Reproduciendo {self.sound_playlist_index + 1}/"
            f"{len(self.sound_playlist)}: {sound_file.name}"
        )

    def _advance_sound_playlist(
        self, status: QMediaPlayer.MediaStatus
    ) -> None:
        if (
            self.sound_playlist_active
            and status == QMediaPlayer.MediaStatus.EndOfMedia
        ):
            self.sound_playlist_index = (
                self.sound_playlist_index + 1
            ) % len(self.sound_playlist)
            self._play_sound_playlist_track()

    def _stop_sound_playlist(self) -> None:
        self.sound_playlist_active = False
        self.sound_player.stop()
        self.sound_status_label.setText("Playlist detenida")

    def _sound_error(
        self, _error: QMediaPlayer.Error, error_message: str
    ) -> None:
        self.sound_playlist_active = False
        self.sound_status_label.setText(
            f"Error reproduciendo sonido ({_error}): {error_message}"
        )

    def _send_commands(self, commands: tuple[str, ...]) -> None:
        if not self.connected or self.worker is None:
            return
        for command in commands:
            self.worker.send_command(command)

    def _start_routine_sequence(self) -> None:
        self._start_selected_sequence(self.routine_checks, ROUTINES)

    def _start_complex_routine_sequence(self) -> None:
        self._start_selected_sequence(
            self.complex_routine_checks, COMPLEX_ROUTINES
        )

    def _start_selected_sequence(
        self,
        checkboxes: list[QCheckBox],
        routines: tuple[
            tuple[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]], ...
        ],
    ) -> None:
        if not self.connected:
            QMessageBox.warning(
                self,
                "ESP32 desconectado",
                "Conecta el ESP32 antes de reproducir.",
            )
            return

        selected = [
            routines[index]
            for index, checkbox in enumerate(checkboxes)
            if checkbox.isChecked()
        ]
        if not selected:
            QMessageBox.warning(
                self, "Sin rutinas", "Selecciona al menos una rutina."
            )
            return

        self.routine_sequence = selected
        self.routine_index = 0
        self.step_index = 0
        self.routine_active = True
        self.start_button.setEnabled(False)
        self.start_complex_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        for checkbox in self.routine_checks + self.complex_routine_checks:
            checkbox.setEnabled(False)
        self._play_routine_step()

    def _stop_routine_sequence(self) -> None:
        self.routine_timer.stop()
        self.routine_active = False
        self._send_commands(
            (
                f"SPEED:ACTION:{self.speed_slider.value()}",
                "SERVO:NECK:90",
                "SERVO:R_ARM:90",
                "SERVO:L_ARM:90",
                "SERVO:WAIST:90",
            )
        )
        self.start_button.setEnabled(True)
        self.start_complex_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        for checkbox in self.routine_checks + self.complex_routine_checks:
            checkbox.setEnabled(True)
        self.state_label.setText("RUTINAS DETENIDAS")
        self.state_label.setStyleSheet(
            "font-size:24px; font-weight:bold; color:#e05252;"
        )

    def _play_routine_step(self) -> None:
        if not self.routine_active:
            return

        name, steps = self.routine_sequence[self.routine_index]
        hold_ms, positions = steps[self.step_index]
        self.state_label.setText(
            f"{name}\nPaso {self.step_index + 1}/{len(steps)}"
        )
        self.state_label.setStyleSheet(
            "font-size:24px; font-weight:bold; color:#ff6b6b;"
        )
        commands = [f"SPEED:ACTION:{self.speed_slider.value()}"]
        commands.extend(f"SERVO:{part}:{angle}" for part, angle in positions)
        self._send_commands(tuple(commands))
        self.routine_timer.start(self.speed_slider.value() + hold_ms)

    def _advance_routine(self) -> None:
        if not self.routine_active:
            return

        _name, steps = self.routine_sequence[self.routine_index]
        self.step_index += 1
        if self.step_index >= len(steps):
            self.step_index = 0
            self.routine_index = (
                self.routine_index + 1
            ) % len(self.routine_sequence)
        self._play_routine_step()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_routine_sequence()
        self._stop_sound_playlist()
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        super().closeEvent(event)


def main() -> None:
    app = QApplication([])
    window = PasilloWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
