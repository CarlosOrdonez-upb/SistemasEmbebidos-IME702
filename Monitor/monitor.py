"""Monitor ECG en tiempo real para datos seriales de un AD8232."""

import csv
import json
import math
import re
import sys
import time
import unicodedata
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import cast

import numpy as np
import pyqtgraph as pg
import serial
from serial.tools import list_ports
from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from scipy import signal as scipy_signal
except ImportError:
    scipy_signal = None


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


def butterworth_coefficients(
    cutoff_hz: float, sampling_frequency_hz: float, filter_type: str
) -> tuple[np.ndarray, np.ndarray]:
    """Diseña un biquad Butterworth usando SciPy o las ecuaciones bilineales."""
    if scipy_signal is not None:
        coefficients = cast(
            tuple[np.ndarray, np.ndarray],
            scipy_signal.butter(
                2, cutoff_hz, btype=filter_type, fs=sampling_frequency_hz, output="ba"
            ),
        )
        numerator, denominator = coefficients
        return np.asarray(numerator, dtype=float), np.asarray(denominator, dtype=float)

    # Aproximación Butterworth de segundo orden (Q = 1/sqrt(2)).
    omega = 2.0 * np.pi * cutoff_hz / sampling_frequency_hz
    cosine = np.cos(omega)
    alpha = np.sin(omega) / (2.0 * (1.0 / np.sqrt(2.0)))
    if filter_type == "highpass":
        numerator = np.array(
            [(1.0 + cosine) / 2.0, -(1.0 + cosine), (1.0 + cosine) / 2.0]
        )
    else:
        numerator = np.array(
            [(1.0 - cosine) / 2.0, 1.0 - cosine, (1.0 - cosine) / 2.0]
        )
    denominator = np.array([1.0 + alpha, -2.0 * cosine, 1.0 - alpha])
    return numerator / denominator[0], denominator / denominator[0]


class ECGSignalFilter:
    """Filtro pasa-banda en tiempo real con frecuencia medida en las muestras."""

    def __init__(self) -> None:
        self.sample_intervals = deque(maxlen=101)
        self.previous_timestamp: float | None = None
        self.sampling_frequency: float | None = None
        self._configured_frequency: float | None = None
        self._samples_since_design = 0
        self._highpass_coefficients = None
        self._lowpass_coefficients = None
        self.notch_frequency: float | None = None
        self._configured_notch_frequency: float | None = None
        self._notch_coefficients = None
        self._highpass_state = np.zeros(2, dtype=float)
        self._notch_state = np.zeros(2, dtype=float)
        self._lowpass_state = np.zeros(2, dtype=float)

    def set_notch_frequency(self, frequency: float | None) -> None:
        if frequency not in (None, 50.0, 60.0):
            raise ValueError("La frecuencia notch debe ser None, 50 o 60 Hz.")
        self.notch_frequency = frequency if scipy_signal is not None else None
        self._configured_notch_frequency = None

    def add_sample(self, value: float, timestamp: float) -> float | None:
        if self.previous_timestamp is not None:
            interval = timestamp - self.previous_timestamp
            if interval > 0 and math.isfinite(interval):
                self.sample_intervals.append(interval)
                if len(self.sample_intervals) >= 5:
                    self.sampling_frequency = 1.0 / median(self.sample_intervals)
        self.previous_timestamp = timestamp

        sampling_frequency = self.sampling_frequency
        if sampling_frequency is None or sampling_frequency <= 80.0:
            return None

        self._samples_since_design += 1
        needs_design = self._configured_frequency is None
        if self._configured_frequency is not None:
            relative_change = abs(
                sampling_frequency - self._configured_frequency
            ) / self._configured_frequency
            needs_design = relative_change >= 0.02 and self._samples_since_design >= 25
        if needs_design:
            self._configure(sampling_frequency, value)

        if self._highpass_coefficients is None or self._lowpass_coefficients is None:
            return None
        highpass, self._highpass_state = self._filter_stage(
            value, self._highpass_coefficients, self._highpass_state
        )
        if (
            scipy_signal is not None
            and self.notch_frequency is not None
            and self.notch_frequency < sampling_frequency / 2.0
        ):
            if self._configured_notch_frequency != self.notch_frequency:
                notch_coefficients = cast(
                    tuple[np.ndarray, np.ndarray],
                    scipy_signal.iirnotch(
                        self.notch_frequency, 30.0, fs=sampling_frequency
                    ),
                )
                self._notch_coefficients = notch_coefficients
                self._notch_state = (
                    scipy_signal.lfilter_zi(*notch_coefficients) * highpass
                )
                self._configured_notch_frequency = self.notch_frequency
            if self._notch_coefficients is not None:
                highpass, self._notch_state = self._filter_stage(
                    highpass, self._notch_coefficients, self._notch_state
                )
        lowpass, self._lowpass_state = self._filter_stage(
            highpass, self._lowpass_coefficients, self._lowpass_state
        )
        return lowpass

    def _configure(self, sampling_frequency: float, initial_value: float) -> None:
        self._highpass_coefficients = butterworth_coefficients(
            0.5, sampling_frequency, "highpass"
        )
        self._lowpass_coefficients = butterworth_coefficients(
            40.0, sampling_frequency, "lowpass"
        )
        self._configured_frequency = sampling_frequency
        self._samples_since_design = 0
        self._configured_notch_frequency = None
        self._notch_coefficients = None
        self._notch_state = np.zeros(2, dtype=float)

        if scipy_signal is not None:
            high_b, high_a = self._highpass_coefficients
            low_b, low_a = self._lowpass_coefficients
            self._highpass_state = scipy_signal.lfilter_zi(high_b, high_a) * initial_value
            self._lowpass_state = scipy_signal.lfilter_zi(low_b, low_a) * 0.0
        else:
            high_b, high_a = self._highpass_coefficients
            low_b, low_a = self._lowpass_coefficients
            high_gain = np.sum(high_b) / np.sum(high_a)
            self._highpass_state = np.array(
                [
                    high_gain - high_b[0],
                    high_b[2] - high_a[2] * high_gain,
                ],
                dtype=float,
            ) * initial_value
            self._lowpass_state = np.zeros(2, dtype=float)

    @staticmethod
    def _filter_stage(value, coefficients, state):
        numerator, denominator = coefficients
        if scipy_signal is not None:
            output, final_state = scipy_signal.lfilter(
                numerator, denominator, np.asarray([value]), zi=state
            )
            return float(output[0]), final_state

        output = numerator[0] * value + state[0]
        next_state = np.array(
            [
                numerator[1] * value - denominator[1] * output + state[1],
                numerator[2] * value - denominator[2] * output,
            ],
            dtype=float,
        )
        return float(output), next_state


class ECGPeakDetector:
    """Detecta máximos usando amplitud, ruido y rango recientes de la señal."""

    INTERVAL_HISTORY = 8
    SAMPLE_WINDOW = 400
    MIN_VALID_SAMPLES = 50

    def __init__(self) -> None:
        self.samples = deque(maxlen=self.SAMPLE_WINDOW)
        self.previous_value: float | None = None
        self.previous_timestamp: float | None = None
        self.before_previous_value: float | None = None
        self.last_peak_timestamp: float | None = None
        self.intervals = deque(maxlen=self.INTERVAL_HISTORY)
        self.signal_range = 0.0
        self.signal_std = 0.0
        self.signal_too_weak = True
        self.invalid_beat = False

    def add_sample(self, value: float, timestamp: float) -> int | None:
        self.invalid_beat = False
        if not math.isfinite(value):
            return None
        self.samples.append(float(value))
        window = np.asarray(self.samples, dtype=float)
        if window.size:
            minimum = float(np.min(window))
            maximum = float(np.max(window))
            self.signal_range = maximum - minimum
            self.signal_std = float(np.std(window))
        else:
            self.signal_range = 0.0
            self.signal_std = 0.0

        self.signal_too_weak = (
            len(self.samples) < self.MIN_VALID_SAMPLES or self.signal_range < 3.0
        )
        previous_value = self.previous_value
        before_previous_value = self.before_previous_value
        previous_timestamp = self.previous_timestamp
        last_peak_timestamp = self.last_peak_timestamp
        bpm = None
        is_local_maximum = (
            previous_value is not None
            and before_previous_value is not None
            and previous_timestamp is not None
            and previous_value > before_previous_value
            and previous_value >= value
        )

        if not self.signal_too_weak and is_local_maximum and previous_value is not None:
            threshold = max(
                0.5 * self.signal_std,
                0.3 * self.signal_range,
                1.5,
            )
            window_center = float(np.median(window))
            if (
                previous_value - window_center >= threshold
                and previous_timestamp is not None
                and (
                    last_peak_timestamp is None
                    or previous_timestamp - last_peak_timestamp >= 0.4
                )
            ):
                if last_peak_timestamp is not None:
                    interval = previous_timestamp - last_peak_timestamp
                    candidate_intervals = list(self.intervals)
                    candidate_intervals.append(interval)
                    if len(candidate_intervals) > self.INTERVAL_HISTORY:
                        candidate_intervals = candidate_intervals[-self.INTERVAL_HISTORY :]
                    candidate_bpm = 60.0 / median(candidate_intervals)
                    if 40.0 <= candidate_bpm <= 200.0:
                        self.intervals.append(interval)
                        if len(self.intervals) >= 3:
                            bpm = round(60.0 / median(self.intervals))
                    else:
                        self.invalid_beat = True
                self.last_peak_timestamp = previous_timestamp

        self.before_previous_value = previous_value
        self.previous_value = value
        self.previous_timestamp = timestamp
        return bpm


PROJECT_DIRECTORY = Path(__file__).resolve().parent
SUBJECTS_JSON_PATH = PROJECT_DIRECTORY / "sujetos.json"
MEASUREMENTS_DIRECTORY = PROJECT_DIRECTORY / "mediciones"
SEX_OPTIONS = ("Masculino", "Femenino", "Prefiero no decir")
SESSION_TYPES = ("Antes de ejercicio", "Después de ejercicio", "Reposo", "Otro")


def _calculate_bmi(weight_kg: float, height_cm: int) -> float:
    if weight_kg <= 0 or height_cm <= 0:
        return 0.0
    return round(weight_kg / (height_cm / 100) ** 2, 1)


class SubjectStore:
    """Lee y persiste sujetos y sesiones en el JSON del proyecto."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SUBJECTS_JSON_PATH

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"El archivo {self.path.name} no contiene JSON válido.") from exc

        if not isinstance(data, dict) or not isinstance(data.get("sujetos"), list):
            raise ValueError(f"El archivo {self.path.name} no tiene la estructura esperada.")
        subjects = data["sujetos"]
        for subject in subjects:
            if (
                not isinstance(subject, dict)
                or not subject.get("id")
                or not subject.get("nombre")
                or not isinstance(subject.get("sesiones", []), list)
                or any(
                    not isinstance(session, dict)
                    for session in subject.get("sesiones", [])
                )
            ):
                raise ValueError("La lista de sujetos contiene registros inválidos.")
            try:
                age = int(subject.get("edad", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Un sujeto tiene una edad inválida en sujetos.json.") from exc
            if not 1 <= age <= 120 or subject.get("sexo") not in SEX_OPTIONS:
                raise ValueError("Un sujeto tiene edad o sexo inválido en sujetos.json.")
            try:
                weight = float(subject.get("peso_kg", 0.0))
                height = int(subject.get("altura_cm", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Un sujeto tiene peso o altura inválidos en sujetos.json.") from exc
            if (weight != 0 and not 20 <= weight <= 250) or (
                height != 0 and not 50 <= height <= 250
            ):
                raise ValueError("Un sujeto tiene peso o altura fuera de rango en sujetos.json.")
            if not isinstance(subject.get("fumador", False), bool) or not isinstance(
                subject.get("cafeina_hoy", False), bool
            ):
                raise ValueError("Los hábitos del sujeto son inválidos en sujetos.json.")
            subject["peso_kg"] = weight
            subject["altura_cm"] = height
            subject["imc"] = _calculate_bmi(weight, height)
            subject["fumador"] = subject.get("fumador", False)
            subject["cafeina_hoy"] = subject.get("cafeina_hoy", False)
        return subjects

    def save(self, subjects: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump({"sujetos": subjects}, file, ensure_ascii=False, indent=2)

    def get(self, subject_id: str) -> dict | None:
        return next((subject for subject in self.load() if subject.get("id") == subject_id), None)

    def add_subject(self, subject_data: dict) -> str:
        name = str(subject_data.get("nombre", "")).strip()
        age = int(subject_data.get("edad", 0))
        sex = str(subject_data.get("sexo", ""))
        if not name or not 1 <= age <= 120 or sex not in SEX_OPTIONS:
            raise ValueError("Los datos del sujeto no son válidos.")
        weight = float(subject_data.get("peso_kg", 0.0))
        height = int(subject_data.get("altura_cm", 0))
        smoker = subject_data.get("fumador", False)
        caffeine = subject_data.get("cafeina_hoy", False)
        if (
            (weight != 0 and not 20 <= weight <= 250)
            or (height != 0 and not 50 <= height <= 250)
            or not isinstance(smoker, bool)
            or not isinstance(caffeine, bool)
        ):
            raise ValueError("Los datos biométricos o de estilo de vida no son válidos.")

        subjects = self.load()
        existing_numbers = [
            int(match.group(1))
            for subject in subjects
            if (match := re.fullmatch(r"S(\d+)", str(subject.get("id", ""))))
        ]
        subject_id = f"S{max(existing_numbers, default=0) + 1:03d}"
        subjects.append(
            {
                "id": subject_id,
                "nombre": name,
                "edad": age,
                "sexo": sex,
                "peso_kg": weight,
                "altura_cm": height,
                "imc": _calculate_bmi(weight, height),
                "fumador": smoker,
                "cafeina_hoy": caffeine,
                "sesiones": [],
            }
        )
        self.save(subjects)
        return subject_id

    def update_subject(self, subject_id: str, subject_data: dict) -> None:
        name = str(subject_data.get("nombre", "")).strip()
        age = int(subject_data.get("edad", 0))
        sex = str(subject_data.get("sexo", ""))
        if not name or not 1 <= age <= 120 or sex not in SEX_OPTIONS:
            raise ValueError("Los datos del sujeto no son válidos.")
        weight = float(subject_data.get("peso_kg", 0.0))
        height = int(subject_data.get("altura_cm", 0))
        smoker = subject_data.get("fumador", False)
        caffeine = subject_data.get("cafeina_hoy", False)
        if (
            (weight != 0 and not 20 <= weight <= 250)
            or (height != 0 and not 50 <= height <= 250)
            or not isinstance(smoker, bool)
            or not isinstance(caffeine, bool)
        ):
            raise ValueError("Los datos biométricos o de estilo de vida no son válidos.")
        subjects = self.load()
        for subject in subjects:
            if subject.get("id") == subject_id:
                subject["nombre"] = name
                subject["edad"] = age
                subject["sexo"] = sex
                subject["peso_kg"] = weight
                subject["altura_cm"] = height
                subject["imc"] = _calculate_bmi(weight, height)
                subject["fumador"] = smoker
                subject["cafeina_hoy"] = caffeine
                self.save(subjects)
                return
        raise KeyError("No se encontró el sujeto seleccionado.")

    def delete_subject(self, subject_id: str) -> None:
        subjects = self.load()
        updated_subjects = [subject for subject in subjects if subject.get("id") != subject_id]
        if len(updated_subjects) == len(subjects):
            raise KeyError("No se encontró el sujeto seleccionado.")
        self.save(updated_subjects)

    def add_session(self, subject_id: str, session: dict) -> None:
        subjects = self.load()
        for subject in subjects:
            if subject.get("id") == subject_id:
                subject.setdefault("sesiones", []).append(session)
                self.save(subjects)
                return
        raise KeyError("El sujeto asociado a la sesión ya no existe.")


def apply_dialog_theme(dialog: QDialog) -> None:
    """Aplica el tema oscuro a los diálogos de gestión y análisis."""
    dialog.setStyleSheet(
        """
        QDialog { background: #0a0a0a; color: #eeeeee; }
        QLabel { color: #eeeeee; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget {
            background: #171717; color: #eeeeee; border: 1px solid #393939;
            border-radius: 5px; padding: 5px;
        }
        QHeaderView::section {
            background: #222222; color: #eeeeee; padding: 6px;
            border: 1px solid #393939;
        }
        QPushButton {
            background: #202020; color: #eeeeee; border: 1px solid #393939;
            border-radius: 6px; padding: 7px 12px;
        }
        QPushButton:hover { background: #303030; border-color: #00cc55; }
        QCheckBox { color: #eeeeee; spacing: 8px; }
        """
    )


class SubjectEditorDialog(QDialog):
    """Formulario modal para crear o editar un sujeto."""

    def __init__(self, subject: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar sujeto" if subject else "Nuevo sujeto")
        apply_dialog_theme(self)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(subject.get("nombre", "") if subject else "")
        self.age_spin = QSpinBox()
        self.age_spin.setRange(1, 120)
        self.age_spin.setValue(int(subject.get("edad", 25)) if subject else 25)
        self.sex_combo = QComboBox()
        self.sex_combo.addItems(SEX_OPTIONS)
        if subject:
            self.sex_combo.setCurrentText(subject.get("sexo", SEX_OPTIONS[0]))
        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(20.0, 250.0)
        self.weight_spin.setDecimals(1)
        weight = float(subject.get("peso_kg", 0.0)) if subject else 0.0
        self._weight_available = 20 <= weight <= 250
        self.weight_spin.setValue(weight if self._weight_available else 20.0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(50, 250)
        height = int(subject.get("altura_cm", 0)) if subject else 0
        self._height_available = 50 <= height <= 250
        self.height_spin.setValue(height if self._height_available else 50)
        self.smoker_checkbox = QCheckBox("Es fumador")
        self.smoker_checkbox.setChecked(bool(subject.get("fumador", False)) if subject else False)
        self.caffeine_checkbox = QCheckBox("Consumió cafeína en las últimas 4 horas")
        self.caffeine_checkbox.setChecked(
            bool(subject.get("cafeina_hoy", False)) if subject else False
        )
        self.bmi_label = QLabel()
        self.bmi_label.setStyleSheet("color: #eeeeee;")
        height_bmi_row = QWidget(self)
        height_bmi_layout = QHBoxLayout(height_bmi_row)
        height_bmi_layout.setContentsMargins(0, 0, 0, 0)
        height_bmi_layout.addWidget(self.height_spin)
        height_bmi_layout.addWidget(self.bmi_label)
        form.addRow("Nombre completo:", self.name_edit)
        form.addRow("Edad:", self.age_spin)
        form.addRow("Sexo:", self.sex_combo)
        form.addRow("Peso (kg):", self.weight_spin)
        form.addRow("Altura (cm):", height_bmi_row)
        form.addRow("", self.smoker_checkbox)
        form.addRow("", self.caffeine_checkbox)
        self.weight_spin.valueChanged.connect(self._weight_changed)
        self.weight_spin.editingFinished.connect(self._mark_weight_available)
        self.height_spin.valueChanged.connect(self._height_changed)
        self.height_spin.editingFinished.connect(self._mark_height_available)
        self._update_bmi()
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def subject_data(self) -> dict:
        return {
            "nombre": self.name_edit.text().strip(),
            "edad": self.age_spin.value(),
            "sexo": self.sex_combo.currentText(),
            "peso_kg": self.weight_spin.value() if self._weight_available else 0.0,
            "altura_cm": self.height_spin.value() if self._height_available else 0,
            "imc": _calculate_bmi(
                self.weight_spin.value() if self._weight_available else 0.0,
                self.height_spin.value() if self._height_available else 0,
            ),
            "fumador": self.smoker_checkbox.isChecked(),
            "cafeina_hoy": self.caffeine_checkbox.isChecked(),
        }

    def _update_bmi(self) -> None:
        if not self._weight_available or not self._height_available:
            self.bmi_label.setText("IMC: Ingresa peso y altura")
            self.bmi_label.setStyleSheet("color: #eeeeee;")
            return
        bmi = _calculate_bmi(self.weight_spin.value(), self.height_spin.value())
        if bmi < 18.5:
            status, color = "Bajo peso", "#00cc55"
        elif bmi < 25:
            status, color = "Normal", "#e6c229"
        elif bmi < 30:
            status, color = "Sobrepeso", "#ff8c00"
        else:
            status, color = "Obesidad", "#ff3b30"
        self.bmi_label.setText(f"IMC: {bmi:.1f} - {status}")
        self.bmi_label.setStyleSheet(f"color: {color};")

    def _weight_changed(self) -> None:
        self._weight_available = True
        self._update_bmi()

    def _height_changed(self) -> None:
        self._height_available = True
        self._update_bmi()

    def _mark_weight_available(self) -> None:
        self._weight_available = True
        self._update_bmi()

    def _mark_height_available(self) -> None:
        self._height_available = True
        self._update_bmi()

    def _accept_if_valid(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Dato obligatorio", "Ingresa el nombre completo del sujeto.")
            self.name_edit.setFocus()
            return
        self.accept()


class SubjectManagementDialog(QDialog):
    """Administra sujetos registrados y muestra sus sesiones previas."""

    subjects_changed = pyqtSignal()

    def __init__(
        self,
        store: SubjectStore,
        protected_subject_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.protected_subject_id = protected_subject_id
        self.subjects: list[dict] = []
        self.setWindowTitle("Gestión de sujetos y sesiones")
        self.resize(900, 650)
        apply_dialog_theme(self)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Sujetos registrados"))
        self.subject_table = QTableWidget(0, 4)
        self.subject_table.setHorizontalHeaderLabels(["Nombre", "Edad", "Sexo", "# Sesiones"])
        self._configure_table(self.subject_table)
        self.subject_table.cellClicked.connect(self._show_subject_sessions)
        layout.addWidget(self.subject_table, stretch=1)

        subject_buttons = QHBoxLayout()
        self.new_button = QPushButton("Nuevo Sujeto")
        self.new_button.clicked.connect(self._new_subject)
        subject_buttons.addWidget(self.new_button)
        self.edit_button = QPushButton("Editar")
        self.edit_button.clicked.connect(self._edit_subject)
        subject_buttons.addWidget(self.edit_button)
        self.delete_button = QPushButton("Eliminar")
        self.delete_button.clicked.connect(self._delete_subject)
        subject_buttons.addWidget(self.delete_button)
        subject_buttons.addStretch()
        layout.addLayout(subject_buttons)

        layout.addWidget(QLabel("Sesiones del sujeto seleccionado"))
        self.sessions_table = QTableWidget(0, 7)
        self.sessions_table.setHorizontalHeaderLabels(
            ["Fecha", "Tipo", "Duración (s)", "BPM promedio", "BPM min", "BPM max", "CSV"]
        )
        self._configure_table(self.sessions_table)
        layout.addWidget(self.sessions_table, stretch=1)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        self._reload_subjects()

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _reload_subjects(self, selected_id: str | None = None) -> None:
        try:
            self.subjects = self.store.load()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Error de datos", str(exc))
            self.subjects = []
        self.subject_table.setRowCount(0)
        self.sessions_table.setRowCount(0)
        for subject in self.subjects:
            row = self.subject_table.rowCount()
            self.subject_table.insertRow(row)
            sessions = subject.get("sesiones", [])
            values = (
                str(subject.get("nombre", "")),
                str(subject.get("edad", "")),
                str(subject.get("sexo", "")),
                str(len(sessions) if isinstance(sessions, list) else 0),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, subject.get("id"))
                self.subject_table.setItem(row, column, item)
            if subject.get("id") == selected_id:
                self.subject_table.setCurrentCell(row, 0)
                self._populate_sessions(subject)

    def _selected_subject(self) -> dict | None:
        row = self.subject_table.currentRow()
        if row < 0:
            return None
        item = self.subject_table.item(row, 0)
        if item is None:
            return None
        subject_id = item.data(Qt.ItemDataRole.UserRole)
        return next((subject for subject in self.subjects if subject.get("id") == subject_id), None)

    def _show_subject_sessions(self, row: int, column: int) -> None:
        del column
        item = self.subject_table.item(row, 0)
        if item is None:
            return
        subject_id = item.data(Qt.ItemDataRole.UserRole)
        subject = next(
            (entry for entry in self.subjects if entry.get("id") == subject_id), None
        )
        if subject is not None:
            self._populate_sessions(subject)

    def _populate_sessions(self, subject: dict) -> None:
        sessions = subject.get("sesiones", [])
        if not isinstance(sessions, list):
            sessions = []
        self.sessions_table.setRowCount(0)
        for session in sessions:
            row = self.sessions_table.rowCount()
            self.sessions_table.insertRow(row)
            values = (
                str(session.get("fecha", "")),
                str(session.get("tipo", "")),
                str(session.get("duracion_segundos", "")),
                _format_number(session.get("bpm_promedio")),
                _format_number(session.get("bpm_min")),
                _format_number(session.get("bpm_max")),
                str(session.get("csv_path", "")),
            )
            for column, value in enumerate(values):
                self.sessions_table.setItem(row, column, QTableWidgetItem(value))

    def _new_subject(self) -> None:
        dialog = SubjectEditorDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            subject_id = self.store.add_subject(dialog.subject_data())
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self._reload_subjects(subject_id)
        self.subjects_changed.emit()

    def _edit_subject(self) -> None:
        subject = self._selected_subject()
        if subject is None:
            QMessageBox.information(self, "Selecciona un sujeto", "Elige un sujeto para editar.")
            return
        dialog = SubjectEditorDialog(subject, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.store.update_subject(str(subject["id"]), dialog.subject_data())
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "No se pudo actualizar", str(exc))
            return
        self._reload_subjects(str(subject["id"]))
        self.subjects_changed.emit()

    def _delete_subject(self) -> None:
        subject = self._selected_subject()
        if subject is None:
            QMessageBox.information(self, "Selecciona un sujeto", "Elige un sujeto para eliminar.")
            return
        subject_id = str(subject["id"])
        if subject_id == self.protected_subject_id:
            QMessageBox.warning(
                self, "Medición activa", "No se puede eliminar el sujeto de una medición activa."
            )
            return
        answer = QMessageBox.question(
            self,
            "Confirmar eliminación",
            "¿Eliminar el sujeto y sus sesiones registradas? Los archivos CSV existentes no se borrarán.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_subject(subject_id)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "No se pudo eliminar", str(exc))
            return
        self._reload_subjects()
        self.subjects_changed.emit()


def _format_number(value) -> str:
    """Formatea valores numéricos de sesiones o muestra N/D."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    return "N/D"


class ProtocolDialog(QDialog):
    """Guía la preparación del sujeto y el tipo de medición."""

    REST_SECONDS = 5 * 60

    def __init__(self, subject_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Protocolo de medición")
        self.resize(560, 500)
        apply_dialog_theme(self)

        self.remaining_seconds = self.REST_SECONDS
        self.timer_complete = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._timer_tick)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Sujeto: {subject_name}"))
        layout.addWidget(QLabel("Lista de preparación"))
        self.checklist = [
            QCheckBox("Sujeto en reposo durante 5 minutos"),
            QCheckBox("Electrodos colocados correctamente (RA, LA, RL)"),
            QCheckBox("Sujeto sin movimientos durante la medición"),
            QCheckBox("Sin hablar durante la medición"),
        ]
        for checkbox in self.checklist:
            checkbox.toggled.connect(self._update_begin_button)
            layout.addWidget(checkbox)

        self.skip_timer_checkbox = QCheckBox("Omitir timer de reposo")
        self.skip_timer_checkbox.toggled.connect(self._skip_timer_changed)
        layout.addWidget(self.skip_timer_checkbox)

        timer_row = QHBoxLayout()
        self.countdown_label = QLabel(self._format_countdown(self.remaining_seconds))
        timer_row.addWidget(self.countdown_label)
        self.start_timer_button = QPushButton("Iniciar Timer")
        self.start_timer_button.clicked.connect(self._start_timer)
        timer_row.addWidget(self.start_timer_button)
        timer_row.addStretch()
        layout.addLayout(timer_row)

        session_form = QFormLayout()
        self.session_type_combo = QComboBox()
        self.session_type_combo.addItems(SESSION_TYPES)
        session_form.addRow("Tipo de sesión:", self.session_type_combo)
        layout.addLayout(session_form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.begin_button = QPushButton("Comenzar Medición")
        self.begin_button.setEnabled(False)
        self.begin_button.clicked.connect(self.accept)
        layout.addWidget(self.begin_button)
        self._update_begin_button()

    @staticmethod
    def _format_countdown(seconds: int) -> str:
        minutes, remaining = divmod(max(seconds, 0), 60)
        return f"Tiempo de reposo: {minutes:02d}:{remaining:02d}"

    @property
    def session_type(self) -> str:
        return self.session_type_combo.currentText()

    def _skip_timer_changed(self, checked: bool) -> None:
        if checked:
            self.timer.stop()
            self.timer_complete = True
            self.countdown_label.setText("Timer de reposo omitido")
            self.start_timer_button.setEnabled(False)
        else:
            self.timer_complete = False
            self.remaining_seconds = self.REST_SECONDS
            self.countdown_label.setText(self._format_countdown(self.remaining_seconds))
            self.start_timer_button.setEnabled(True)
        self._update_begin_button()

    def _start_timer(self) -> None:
        if self.skip_timer_checkbox.isChecked():
            return
        self.remaining_seconds = self.REST_SECONDS
        self.timer_complete = False
        self.countdown_label.setText(self._format_countdown(self.remaining_seconds))
        self.start_timer_button.setEnabled(False)
        self.timer.start()
        self._update_begin_button()

    def _timer_tick(self) -> None:
        self.remaining_seconds -= 1
        self.countdown_label.setText(self._format_countdown(self.remaining_seconds))
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self.timer_complete = True
            self.countdown_label.setText("Reposo completado")
        self._update_begin_button()

    def _update_begin_button(self, checked: bool = False) -> None:
        del checked
        checklist_complete = all(checkbox.isChecked() for checkbox in self.checklist)
        timer_ready = self.timer_complete or self.skip_timer_checkbox.isChecked()
        self.begin_button.setEnabled(checklist_complete and timer_ready)


class SessionDetailsDialog(QDialog):
    """Presenta las sesiones y sus estadísticas para un sujeto."""

    def __init__(self, subject: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sesiones de {subject.get('nombre', '')}")
        self.resize(760, 420)
        apply_dialog_theme(self)
        layout = QVBoxLayout(self)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            ["Fecha", "Tipo", "Duración (s)", "BPM promedio", "BPM min", "BPM max"]
        )
        SubjectManagementDialog._configure_table(table)
        for session in subject.get("sesiones", []):
            row = table.rowCount()
            table.insertRow(row)
            values = (
                str(session.get("fecha", "")),
                str(session.get("tipo", "")),
                str(session.get("duracion_segundos", "")),
                _format_number(session.get("bpm_promedio")),
                _format_number(session.get("bpm_min")),
                _format_number(session.get("bpm_max")),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(table)
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)


def _session_bpm_values(subject: dict) -> list[float]:
    """Devuelve los BPM promedio de las sesiones que tienen mediciones válidas."""
    values = []
    for session in subject.get("sesiones", []):
        value = session.get("bpm_promedio")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def _subject_summary(subject: dict) -> tuple[float | None, str]:
    """Calcula BPM general y fecha de la última sesión registrada."""
    values = _session_bpm_values(subject)
    sessions = subject.get("sesiones", [])
    latest = max(
        sessions,
        key=lambda session: str(session.get("fecha", "")),
        default=None,
    )
    latest_date = str(latest.get("fecha", "N/D")) if latest else "N/D"
    return (mean(values) if values else None, latest_date)


class ComparisonDialog(QDialog):
    """Resume y compara BPM de sujetos o sesiones individuales."""

    def __init__(self, subjects: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.subjects = subjects
        self.setWindowTitle("Comparación de sujetos y sesiones")
        self.resize(1100, 760)
        apply_dialog_theme(self)

        layout = QVBoxLayout(self)
        self.summary_table = QTableWidget(0, 9)
        self.summary_table.setHorizontalHeaderLabels(
            [
                "Nombre",
                "Edad",
                "Sexo",
                "IMC",
                "Fumador",
                "Cafeína",
                "# Sesiones",
                "BPM Promedio General",
                "Última Medición",
            ]
        )
        SubjectManagementDialog._configure_table(self.summary_table)
        self.summary_table.cellDoubleClicked.connect(self._show_selected_details)
        layout.addWidget(self.summary_table, stretch=1)
        self._populate_summary()

        chart_controls = QHBoxLayout()
        chart_controls.addWidget(QLabel("Comparar:"))
        self.comparison_selector = QComboBox()
        self.comparison_selector.addItem("Todos los sujetos", None)
        for subject in subjects:
            self.comparison_selector.addItem(
                str(subject.get("nombre", "")), str(subject.get("id", ""))
            )
        self.comparison_selector.currentIndexChanged.connect(self._draw_comparison)
        chart_controls.addWidget(self.comparison_selector)
        self.details_button = QPushButton("Ver Detalle")
        self.details_button.clicked.connect(lambda: self._show_selected_details())
        chart_controls.addWidget(self.details_button)
        layout.addLayout(chart_controls)

        self.chart_widget = pg.PlotWidget()
        self.chart_widget.setBackground("#0a0a0a")
        self.chart_widget.showGrid(x=True, y=True, alpha=0.2)
        plot_item = self.chart_widget.getPlotItem()
        if plot_item is not None:
            for axis_name in ("left", "bottom"):
                axis = plot_item.getAxis(axis_name)
                axis.setPen(pg.mkPen("#777777"))
                axis.setTextPen(pg.mkPen("#aaaaaa"))
        layout.addWidget(self.chart_widget, stretch=2)
        self.chart_message = QLabel("")
        layout.addWidget(self.chart_message)

        bottom_buttons = QHBoxLayout()
        self.export_button = QPushButton("Exportar Resumen")
        self.export_button.clicked.connect(self._export_summary)
        bottom_buttons.addWidget(self.export_button)
        bottom_buttons.addStretch()
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        bottom_buttons.addWidget(close_button)
        layout.addLayout(bottom_buttons)
        self._draw_comparison()

    def _populate_summary(self) -> None:
        self.summary_table.setRowCount(0)
        for subject in self.subjects:
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)
            sessions = subject.get("sesiones", [])
            average, latest_date = _subject_summary(subject)
            values = (
                str(subject.get("nombre", "")),
                str(subject.get("edad", "")),
                str(subject.get("sexo", "")),
                _format_number(subject.get("imc")) if subject.get("imc", 0) else "N/D",
                "Sí" if subject.get("fumador", False) else "No",
                "Sí" if subject.get("cafeina_hoy", False) else "No",
                str(len(sessions)),
                _format_number(average),
                latest_date,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, subject.get("id"))
                self.summary_table.setItem(row, column, item)

    def _draw_comparison(self, index: int = 0) -> None:
        del index
        plot_item = self.chart_widget.getPlotItem()
        if plot_item is None:
            return
        plot_item.clear()
        selected_id = self.comparison_selector.currentData()
        if selected_id is None:
            plot_item.setLabel("left", "BPM")
            plot_item.setLabel("bottom", "Sujeto")
            chart_subjects = [
                (subject, mean(values))
                for subject in self.subjects
                if (values := _session_bpm_values(subject))
            ]
            if not chart_subjects:
                self.chart_message.setText("No hay sesiones con BPM válidos para comparar.")
                return
            positions = list(range(len(chart_subjects)))
            names = [str(subject.get("nombre", "")) for subject, _ in chart_subjects]
            averages = [average for _, average in chart_subjects]
            plot_item.addItem(
                pg.BarGraphItem(
                    x=positions,
                    height=averages,
                    width=0.65,
                    brush="#00ff66",
                    pen=pg.mkPen("#00cc55"),
                )
            )
            plot_item.getAxis("bottom").setTicks(
                [[(position, name[:12]) for position, name in zip(positions, names)]]
            )
            self.chart_widget.getViewBox().autoRange()
            self.chart_message.setText("BPM promedio general por sujeto.")
            return

        subject = next(
            (entry for entry in self.subjects if entry.get("id") == selected_id), None
        )
        if subject is None:
            self.chart_message.setText("No se encontró el sujeto seleccionado.")
            return
        plot_item.setLabel("left", "BPM")
        plot_item.setLabel("bottom", "Sesión")
        sessions = sorted(
            subject.get("sesiones", []),
            key=lambda session: str(session.get("fecha", "")),
        )
        valid_sessions = [
            session
            for session in sessions
            if isinstance(session.get("bpm_promedio"), (int, float))
            and not isinstance(session.get("bpm_promedio"), bool)
        ]
        if not valid_sessions:
            self.chart_message.setText("El sujeto no tiene sesiones con BPM válidos.")
            return
        positions = list(range(1, len(valid_sessions) + 1))
        bpm_values = [float(session["bpm_promedio"]) for session in valid_sessions]
        plot_item.plot(
            positions,
            bpm_values,
            pen=pg.mkPen("#00ff66", width=2),
            symbol="o",
            symbolBrush="#00ff66",
            symbolSize=8,
        )
        labels = [
            f"{position}: {str(session.get('tipo', ''))[:10]}"
            for position, session in zip(positions, valid_sessions)
        ]
        plot_item.getAxis("bottom").setTicks(
            [[(position, label) for position, label in zip(positions, labels)]]
        )
        self.chart_widget.getViewBox().autoRange()
        self.chart_message.setText(f"Sesiones registradas de {subject.get('nombre', '')}.")

    def _show_selected_details(self, row: int | None = None, column: int = 0) -> None:
        del column
        if row is None:
            row = self.summary_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecciona un sujeto", "Elige un sujeto de la tabla.")
            return
        item = self.summary_table.item(row, 0)
        if item is None:
            return
        subject_id = item.data(Qt.ItemDataRole.UserRole)
        subject = next(
            (entry for entry in self.subjects if entry.get("id") == subject_id), None
        )
        if subject is not None:
            SessionDetailsDialog(subject, self).exec()

    def _export_summary(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exportar resumen de sujetos", "resumen_sujetos.csv", "Archivos CSV (*.csv)"
        )
        if not filename:
            return
        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "Nombre",
                        "Edad",
                        "Sexo",
                        "IMC",
                        "Fumador",
                        "Cafeína",
                        "# Sesiones",
                        "BPM Promedio General",
                        "Última Medición",
                    ]
                )
                for subject in self.subjects:
                    average, latest_date = _subject_summary(subject)
                    writer.writerow(
                        [
                            subject.get("nombre", ""),
                            subject.get("edad", ""),
                            subject.get("sexo", ""),
                            _format_number(subject.get("imc"))
                            if subject.get("imc", 0)
                            else "N/D",
                            "Sí" if subject.get("fumador", False) else "No",
                            "Sí" if subject.get("cafeina_hoy", False) else "No",
                            len(subject.get("sesiones", [])),
                            _format_number(average),
                            latest_date,
                        ]
                    )
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar", f"No se pudo guardar el CSV:\n{exc}")
            return
        QMessageBox.information(self, "Exportación completada", "El resumen CSV se guardó correctamente.")


class MainWindow(QMainWindow):
    """Ventana principal del monitor ECG."""

    HISTORY_SIZE = 500

    def __init__(self, subject_store: SubjectStore | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Monitor ECG | AD8232")
        self.resize(1050, 760)

        self.subject_store = subject_store or SubjectStore()
        self.project_directory = self.subject_store.path.parent
        self.measurements_directory = self.project_directory / "mediciones"
        self.active_measurement: dict | None = None
        self.measurement_samples: list[tuple[str, int, str]] = []
        self.measurement_bpms: list[int] = []
        self.reader = None
        self.leads_state = "DESCONOCIDO"
        self.window_seconds = 5.0
        self.plot_start_timestamp: float | None = None
        self.raw_values = deque(maxlen=self.HISTORY_SIZE)
        self.plot_values: deque[tuple[float, int]] = deque()
        self.smoothing_values = deque(maxlen=5)
        self.signal_filter = ECGSignalFilter()
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

        header.addWidget(QLabel("Ventana"))
        self.window_selector = QComboBox()
        for seconds in (2.0, 5.0, 10.0, 20.0):
            self.window_selector.addItem(f"{int(seconds)} s", seconds)
        self.window_selector.setCurrentIndex(1)
        self.window_selector.currentIndexChanged.connect(self._window_changed)
        header.addWidget(self.window_selector)

        header.addWidget(QLabel("Notch"))
        self.notch_selector = QComboBox()
        self.notch_selector.addItem("Off", None)
        self.notch_selector.addItem("50 Hz", 50.0)
        self.notch_selector.addItem("60 Hz", 60.0)
        self.notch_selector.setEnabled(scipy_signal is not None)
        if scipy_signal is None:
            self.notch_selector.setToolTip("Requiere SciPy")
        self.notch_selector.currentIndexChanged.connect(self._notch_changed)
        header.addWidget(self.notch_selector)

        self.connect_button = QPushButton("Conectar")
        self.connect_button.setObjectName("connectButton")
        self.connect_button.clicked.connect(self.toggle_connection)
        header.addWidget(self.connect_button)
        layout.addLayout(header)

        session_controls = QHBoxLayout()
        session_controls.addWidget(QLabel("Sujeto activo:"))
        self.subject_selector = QComboBox()
        self.subject_selector.setMinimumWidth(180)
        session_controls.addWidget(self.subject_selector)
        self.subjects_button = QPushButton("Sujetos")
        self.subjects_button.clicked.connect(self._open_subject_management)
        session_controls.addWidget(self.subjects_button)
        self.start_measurement_button = QPushButton("Iniciar Medición")
        self.start_measurement_button.clicked.connect(self._start_measurement)
        session_controls.addWidget(self.start_measurement_button)
        self.compare_button = QPushButton("Comparar")
        self.compare_button.clicked.connect(self._open_comparison)
        session_controls.addWidget(self.compare_button)
        session_controls.addStretch()
        layout.addLayout(session_controls)

        status_row = QHBoxLayout()
        self.connection_label = QLabel("Desconectado")
        self.connection_label.setObjectName("mutedLabel")
        status_row.addWidget(self.connection_label)
        status_row.addStretch()

        signal_status_column = QVBoxLayout()
        leads_row = QHBoxLayout()
        leads_row.addWidget(QLabel("Electrodos:"))
        self.leads_label = QLabel("DESCONOCIDO")
        self.leads_label.setObjectName("leadsUnknown")
        leads_row.addWidget(self.leads_label)
        signal_status_column.addLayout(leads_row)
        amplitude_row = QHBoxLayout()
        amplitude_row.addWidget(QLabel("Amplitud:"))
        self.amplitude_label = QLabel("0.0 ADC")
        self.amplitude_label.setStyleSheet("color: #ff3b30;")
        amplitude_row.addWidget(self.amplitude_label)
        signal_status_column.addLayout(amplitude_row)
        status_row.addLayout(signal_status_column)
        layout.addLayout(status_row)

        bpm_column = QVBoxLayout()
        bpm_caption = QLabel("FRECUENCIA CARDÍACA")
        bpm_caption.setObjectName("mutedLabel")
        bpm_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bpm_label = QLabel("--")
        self.bpm_label.setObjectName("bpmLabel")
        bpm_font = QFont("Segoe UI", QFont.Weight.Bold)
        bpm_font.setPointSize(72)
        self.bpm_label.setFont(bpm_font)
        self.bpm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bpm_label.setMinimumHeight(115)
        unit = QLabel("BPM")
        unit.setObjectName("mutedLabel")
        unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bpm_column.addWidget(bpm_caption)
        bpm_column.addWidget(self.bpm_label)
        bpm_column.addWidget(unit)
        layout.addLayout(bpm_column)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#0a0a0a")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("left", "Señal", units="ADC")
        self.plot_widget.setLabel("bottom", "Tiempo", units="s")
        self.plot_widget.setXRange(0, self.window_seconds, padding=0)  # type: ignore[reportCallIssue]
        self.plot_widget.getViewBox().setMouseEnabled(x=False, y=True)
        plot_item = self.plot_widget.getPlotItem()
        if plot_item is not None:
            plot_item.setMenuEnabled(False)
            plot_item.hideButtons()
            for axis_name in ("left", "bottom"):
                axis = plot_item.getAxis(axis_name)
                axis.setPen(pg.mkPen("#777777"))
                axis.setTextPen(pg.mkPen("#aaaaaa"))
        self.curve = self.plot_widget.plot(pen=pg.mkPen("#00ff66", width=2))
        layout.addWidget(self.plot_widget, stretch=1)

        footer = QHBoxLayout()
        self.smoothing_checkbox = QCheckBox("Suavizado (media móvil de 5 muestras)")
        footer.addWidget(self.smoothing_checkbox)
        footer.addStretch()
        self.save_button = QPushButton("Guardar CSV")
        self.save_button.clicked.connect(self.toggle_csv_recording)
        footer.addWidget(self.save_button)
        self.view_button = QPushButton("Vista")
        self.view_button.clicked.connect(self._reset_plot_view)
        footer.addWidget(self.view_button)
        layout.addLayout(footer)

        self.message_label = QLabel("")
        self.message_label.setObjectName("messageLabel")
        layout.addWidget(self.message_label)

        self.refresh_ports()
        self._refresh_subject_selector()

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

    def _refresh_subject_selector(self, selected_id: str | None = None) -> None:
        current_id = selected_id or self.subject_selector.currentData()
        try:
            subjects = self.subject_store.load()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Error de sujetos", str(exc))
            subjects = []

        previous_block_state = self.subject_selector.blockSignals(True)
        self.subject_selector.clear()
        self.subject_selector.addItem("Selecciona sujeto", None)
        for subject in subjects:
            self.subject_selector.addItem(
                f"{subject.get('nombre', '')} ({subject.get('id', '')})",
                subject.get("id"),
            )
        if current_id is not None:
            index = self.subject_selector.findData(current_id)
            if index >= 0:
                self.subject_selector.setCurrentIndex(index)
        self.subject_selector.blockSignals(previous_block_state)

    def _open_subject_management(self) -> None:
        protected_id = (
            self.active_measurement.get("subject_id")
            if self.active_measurement is not None
            else None
        )
        dialog = SubjectManagementDialog(self.subject_store, protected_id, self)
        dialog.subjects_changed.connect(lambda: self._refresh_subject_selector())
        dialog.exec()
        self._refresh_subject_selector()

    def _open_comparison(self) -> None:
        try:
            subjects = self.subject_store.load()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Error de sujetos", str(exc))
            return
        if not subjects:
            QMessageBox.information(
                self, "Sin sujetos", "Registra al menos un sujeto antes de comparar."
            )
            return
        ComparisonDialog(subjects, self).exec()

    def _start_measurement(self) -> None:
        if self.active_measurement is not None:
            QMessageBox.information(
                self, "Medición activa", "Finaliza y guarda la medición actual antes de iniciar otra."
            )
            return

        subject_id = self.subject_selector.currentData()
        if subject_id is None:
            QMessageBox.information(
                self, "Selecciona un sujeto", "Selecciona un sujeto antes de iniciar la medición."
            )
            return
        try:
            subject = self.subject_store.get(str(subject_id))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Error de sujetos", str(exc))
            return
        if subject is None:
            QMessageBox.warning(
                self, "Sujeto no disponible", "El sujeto seleccionado ya no está registrado."
            )
            self._refresh_subject_selector()
            return
        if not self.port_selector.currentText().strip():
            QMessageBox.warning(self, "Puerto requerido", "Selecciona un puerto serial válido.")
            return

        protocol = ProtocolDialog(str(subject.get("nombre", "")), self)
        if protocol.exec() != QDialog.DialogCode.Accepted:
            return

        started_at = datetime.now()
        self.active_measurement = {
            "subject_id": str(subject["id"]),
            "nombre": str(subject.get("nombre", "")),
            "edad": int(subject.get("edad", 0)),
            "sexo": str(subject.get("sexo", "")),
            "peso_kg": float(subject.get("peso_kg", 0.0)),
            "altura_cm": int(subject.get("altura_cm", 0)),
            "imc": float(subject.get("imc", 0.0)),
            "fumador": bool(subject.get("fumador", False)),
            "cafeina_hoy": bool(subject.get("cafeina_hoy", False)),
            "tipo": protocol.session_type,
            "started_at": started_at,
            "started_monotonic": time.monotonic(),
        }
        self.measurement_samples = []
        self.measurement_bpms = []
        self.save_button.setText("Finalizar y guardar CSV")

        if self.reader is not None and self.reader.isRunning():
            self.peak_detector = ECGPeakDetector()
            self.bpm_label.setText("--")
        else:
            self.toggle_connection()
        self.message_label.setText(
            f"Medición activa: {subject.get('nombre', '')} — {protocol.session_type}"
        )

    def _window_changed(self, index: int) -> None:
        seconds = self.window_selector.itemData(index)
        if seconds is not None:
            self.window_seconds = float(seconds)
            self._redraw_plot()

    def _notch_changed(self, index: int) -> None:
        frequency = self.notch_selector.itemData(index)
        self.signal_filter.set_notch_frequency(
            float(frequency) if frequency is not None else None
        )

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
        self.signal_filter = ECGSignalFilter()
        frequency = self.notch_selector.currentData()
        self.signal_filter.set_notch_frequency(
            float(frequency) if frequency is not None else None
        )
        self.peak_detector = ECGPeakDetector()
        self.smoothing_values.clear()
        self.plot_values.clear()
        self.plot_start_timestamp = None
        self._redraw_plot()
        self.bpm_label.setText("--")
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
            detector_input = raw_value
            if self.smoothing_checkbox.isChecked():
                self.smoothing_values.append(raw_value)
                detector_input = sum(self.smoothing_values) / len(self.smoothing_values)

            if self.plot_start_timestamp is None:
                self.plot_start_timestamp = timestamp
            self.plot_values.append((timestamp, raw_value))
            filtered_value = self.signal_filter.add_sample(detector_input, timestamp)
            if filtered_value is not None:
                bpm = self.peak_detector.add_sample(filtered_value, timestamp)
                if self.peak_detector.signal_too_weak or self.peak_detector.invalid_beat:
                    self.bpm_label.setText("--")
                elif bpm is not None:
                    self.bpm_label.setText(str(bpm))
                    if self.active_measurement is not None:
                        self.measurement_bpms.append(bpm)

            if self.active_measurement is not None:
                elapsed = max(
                    0.0,
                    timestamp - self.active_measurement["started_monotonic"],
                )
                sample_time = self.active_measurement["started_at"] + timedelta(
                    seconds=elapsed
                )
                self.measurement_samples.append(
                    (
                        sample_time.isoformat(timespec="milliseconds"),
                        raw_value,
                        self.leads_state,
                    )
                )

        signal_range = self.peak_detector.signal_range
        self.amplitude_label.setText(f"{signal_range:.1f} ADC")
        if signal_range > 50:
            amplitude_color = "#00ff66"
        elif signal_range >= 5:
            amplitude_color = "#ffd60a"
        else:
            amplitude_color = "#ff3b30"
        self.amplitude_label.setStyleSheet(f"color: {amplitude_color};")

        self._redraw_plot()

    def _redraw_plot(self) -> None:
        if not self.plot_values:
            self.curve.setData(x=[], y=[])
            self.plot_widget.setXRange(0, self.window_seconds, padding=0)  # type: ignore[reportCallIssue]
            return

        latest_timestamp = self.plot_values[-1][0]
        cutoff = latest_timestamp - self.window_seconds
        while self.plot_values and self.plot_values[0][0] < cutoff:
            self.plot_values.popleft()

        if self.plot_start_timestamp is None:
            self.plot_start_timestamp = self.plot_values[0][0]
        t_now = latest_timestamp - self.plot_start_timestamp
        x = [timestamp - self.plot_start_timestamp for timestamp, _ in self.plot_values]
        y = [value for _, value in self.plot_values]
        self.curve.setData(x=x, y=y)
        self.plot_widget.setXRange(t_now - self.window_seconds, t_now, padding=0)  # type: ignore[reportCallIssue]
        if y:
            ymin = min(y)
            ymax = max(y)
            if ymax == ymin:
                ymin -= 10
                ymax += 10
            else:
                margin = 0.15 * (ymax - ymin)
                ymin -= margin
                ymax += margin
            self.plot_widget.getViewBox().setRange(
                yRange=(ymin, ymax), padding=0  # type: ignore[reportCallIssue]
            )

    def _reset_plot_view(self) -> None:
        self.plot_widget.getViewBox().autoRange()

    def toggle_csv_recording(self) -> None:
        if self.active_measurement is None:
            QMessageBox.information(
                self, "Sin medición activa", "Inicia una medición antes de guardar sus datos."
            )
            return
        measurement = self.active_measurement
        started_at = measurement["started_at"]
        session_type = str(measurement["tipo"])
        subject_name = str(measurement["nombre"])
        session_labels = {
            "Antes de ejercicio": "AntesEjercicio",
            "Después de ejercicio": "DespuesEjercicio",
            "Reposo": "Reposo",
            "Otro": "Otro",
        }
        name_component = unicodedata.normalize("NFKD", subject_name)
        name_component = name_component.encode("ascii", "ignore").decode("ascii")
        name_component = re.sub(r"[^A-Za-z0-9]+", "", name_component) or str(
            measurement["subject_id"]
        )
        timestamp_label = started_at.strftime("%Y%m%d_%H%M%S")
        base_name = (
            f"{name_component}_{session_labels.get(session_type, 'Otro')}_{timestamp_label}"
        )
        duration = max(0.0, time.monotonic() - measurement["started_monotonic"])
        bpm_values = self.measurement_bpms
        bpm_average = round(mean(bpm_values)) if bpm_values else None
        bpm_minimum = min(bpm_values) if bpm_values else None
        bpm_maximum = max(bpm_values) if bpm_values else None
        session_id = (
            f"{measurement['subject_id']}_{started_at.strftime('%Y%m%d_%H%M%S_%f')}"
        )

        try:
            self.measurements_directory.mkdir(parents=True, exist_ok=True)
            csv_path = self.measurements_directory / f"{base_name}.csv"
            suffix = 2
            while csv_path.exists():
                csv_path = self.measurements_directory / f"{base_name}_{suffix}.csv"
                suffix += 1
            with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "Nombre",
                        "Edad",
                        "Sexo",
                        "Peso_kg",
                        "Altura_cm",
                        "IMC",
                        "Fumador",
                        "Cafeina_Hoy",
                        "Tipo_Sesion",
                        "Fecha",
                        "BPM_Promedio",
                        "BPM_Min",
                        "BPM_Max",
                        "Duracion_seg",
                    ]
                )
                writer.writerow(
                    [
                        subject_name,
                        measurement["edad"],
                        measurement["sexo"],
                        measurement["peso_kg"] or "",
                        measurement["altura_cm"] or "",
                        measurement["imc"] or "",
                        measurement["fumador"],
                        measurement["cafeina_hoy"],
                        session_type,
                        started_at.strftime("%Y-%m-%d %H:%M:%S"),
                        bpm_average if bpm_average is not None else "",
                        bpm_minimum if bpm_minimum is not None else "",
                        bpm_maximum if bpm_maximum is not None else "",
                        round(duration, 2),

                    ]
                )
                writer.writerow(["timestamp", "valor_ADC", "leads_state"])
                writer.writerows(self.measurement_samples)

            relative_csv_path = csv_path.relative_to(self.project_directory).as_posix()
            session = {
                "id": session_id,
                "tipo": session_type,
                "fecha": started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "fecha_fin": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duracion_segundos": round(duration, 2),
                "bpm_promedio": bpm_average,
                "bpm_min": bpm_minimum,
                "bpm_max": bpm_maximum,
                "csv_path": relative_csv_path,
            }
            self.subject_store.add_session(str(measurement["subject_id"]), session)
        except OSError as exc:
            QMessageBox.critical(
                self, "Error al guardar", f"No se pudo guardar la medición:\n{exc}"
            )
            return
        except (ValueError, KeyError) as exc:
            QMessageBox.critical(
                self,
                "Error al registrar sesión",
                f"El CSV puede haberse creado, pero no se pudo actualizar sujetos.json:\n{exc}",
            )
            return

        self.active_measurement = None
        self.measurement_samples = []
        self.measurement_bpms = []
        self.save_button.setText("Guardar CSV")
        self.message_label.setText(f"Medición guardada: {relative_csv_path}")
        self._refresh_subject_selector(str(measurement["subject_id"]))
        QMessageBox.information(
            self,
            "Medición guardada",
            f"Sesión registrada correctamente.\nArchivo: {relative_csv_path}",
        )

    def closeEvent(self, event) -> None:
        if self.active_measurement is not None:
            answer = QMessageBox.question(
                self,
                "Medición activa",
                "Hay una medición sin guardar. ¿Deseas finalizarla y guardar el CSV antes de salir?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Yes:
                self.toggle_csv_recording()
                if self.active_measurement is not None:
                    event.ignore()
                    return
            else:
                self.active_measurement = None
        if self.reader is not None and self.reader.isRunning():
            self.reader.stop()
            self.reader.wait()
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