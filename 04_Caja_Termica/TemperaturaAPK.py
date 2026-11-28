import asyncio
import math
import queue
import socket
import threading
import time
from collections import deque
from pathlib import Path

import flet as ft
from flet import canvas as cv

try:
    import serial as serial_module
except ImportError:
    serial_module = None


TCP_PORT = 8888
COLORS = {
    "background": "#101923",
    "surface": "#172633",
    "surface_alt": "#1d303d",
    "text": "#e6eef5",
    "muted": "#9aafbd",
    "cyan": "#71d9e8",
    "orange": "#ffb454",
    "green": "#63d69a",
    "red": "#ff7373",
    "off": "#46545f",
}


class TemperaturaApp:
    def __init__(self, page):
        self.page = page
        self.page.title = "Caja térmica"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = COLORS["background"]
        self.page.padding = 12

        self.rx_queue = queue.Queue()
        self.tx_queue = queue.Queue()
        self.worker = None
        self.worker_stop = None
        self.generation = 0
        self.closed = False
        self.connected = False
        self.connecting = False
        self.connection_kind = ""

        self.current_temperature = None
        self.humidity = None
        self.phase = "Desconectado"
        self.previous_actuator_states = {
            "heater": None,
            "peltier": None,
            "fans": None,
            "doors": None,
        }
        self.sensor_error_active = False
        self.range_minimum = 28.0
        self.range_maximum = 35.0
        self.setpoint = 28.0
        self.heater_on = False
        self.peltier_on = False
        self.fans_on = False
        self.doors_open = False
        self.power_percent = 0.0
        self.servo_angle = 0
        self.test_active = False
        self.cycle_active = False
        self.dewpoint_risk = False
        self.dewpoint_temperature = None
        self.history = deque(maxlen=90)
        self.last_sample_time = 0.0
        self.chart_dirty = True
        self.dirty_fields = set()

        self.navigation = [
            ["minimum", "maximum"],
            ["kp", "ki", "kd"],
            ["target", "start_pid"],
            ["apply_range", "apply_pid"],
            ["cycle_min", "cycle_max"],
            ["test", "dimmer"],
            ["purge", "stop"],
        ]
        self.nav_row = 0
        self.nav_column = 0
        self.active_item = self.navigation[0][0]
        self.matrix_mode = "A"
        self.numeric_entry_started = False

        self._create_controls()
        self._build_page()
        self.page.on_close = self.close
        self.page.add(self.root)
        self.page.run_task(self._ui_pump)

    def _create_controls(self):
        self.ip_field = ft.TextField(
            label="IP del ESP32",
            value="192.168.1.50",
            expand=True,
        )
        self.wifi_button = ft.FilledButton(
            content="Conectar Wi-Fi",
            on_click=self.connect_wifi,
        )
        self.com_field = ft.TextField(label="Puerto COM", value="COM3")
        self.serial_button = ft.OutlinedButton(
            content="Conectar Serial",
            on_click=self.connect_serial,
        )
        self.disconnect_button = ft.TextButton(
            content="Desconectar",
            on_click=self.disconnect,
            disabled=True,
        )
        self.connection_status = ft.Text(
            "Desconectado",
            color=COLORS["muted"],
        )
        self.status_text = ft.Text(
            "Conecta el ESP32 por Wi-Fi o Serial.",
            color=COLORS["muted"],
        )

        self.temperature_text = ft.Text("--.- °C", size=30, color=COLORS["cyan"])
        self.humidity_text = ft.Text("Humedad: --%", color=COLORS["muted"])
        self.phase_text = ft.Text("Fase: --", color=COLORS["text"])
        self.range_text = ft.Text("Rango: --", color=COLORS["text"])
        self.dimmer_text = ft.Text("Dimmer: --% · servo: --°", color=COLORS["text"])

        self.indicators = {}
        self.indicator_lights = {}
        for key, label in (
            ("heater", "Foco"),
            ("peltier", "Peltier"),
            ("fans", "Ventiladores"),
            ("doors", "Compuertas"),
        ):
            light = ft.Text("●", color=COLORS["off"], size=18)
            card = ft.Container(
                content=ft.Row(
                    [light, ft.Text(label, color=COLORS["text"])],
                    spacing=8,
                ),
                bgcolor=COLORS["surface_alt"],
                border_radius=10,
                padding=10,
                expand=True,
            )
            self.indicators[key] = card
            self.indicator_lights[key] = light

        self.range_minimum_field = self._numeric_field(
            "Temperatura mínima °C", "28.0", "minimum"
        )
        self.range_maximum_field = self._numeric_field(
            "Temperatura máxima °C", "35.0", "maximum"
        )
        self.kp_field = self._numeric_field("Kp", "2.0", "kp")
        self.ki_field = self._numeric_field("Ki", "0.5", "ki")
        self.kd_field = self._numeric_field("Kd", "1.0", "kd")
        self.target_field = self._numeric_field(
            "Objetivo PID °C", "28.0", "target"
        )

        self.apply_range_button = ft.FilledButton(
            content="Aplicar rango",
            on_click=self.apply_range,
            expand=True,
        )
        self.apply_pid_button = ft.FilledButton(
            content="Aplicar PID",
            on_click=self.apply_pid,
            expand=True,
        )
        self.start_pid_button = ft.OutlinedButton(
            content="Mantener objetivo",
            on_click=self.apply_target,
            expand=True,
        )
        self.cycle_min_button = ft.OutlinedButton(
            content="Ciclo hasta mínima",
            on_click=lambda event: self.start_cycle("MIN", event),
            expand=True,
        )
        self.cycle_max_button = ft.OutlinedButton(
            content="Ciclo hasta máxima",
            on_click=lambda event: self.start_cycle("MAX", event),
            expand=True,
        )
        self.test_button = ft.OutlinedButton(
            content="Probar tapas/ventiladores",
            on_click=self.toggle_test,
            expand=True,
        )
        self.dimmer_button = ft.OutlinedButton(
            content="Probar servo dimmer",
            on_click=self.start_dimmer_test,
            expand=True,
        )
        self.purge_button = ft.OutlinedButton(
            content="Purga de aire",
            on_click=self.show_purge_confirmation,
            expand=True,
        )
        self.stop_button = ft.FilledButton(
            content="Detener todo",
            on_click=self.stop_all,
            expand=True,
        )
        self.command_buttons = [
            self.apply_range_button,
            self.apply_pid_button,
            self.start_pid_button,
            self.cycle_min_button,
            self.cycle_max_button,
            self.test_button,
            self.dimmer_button,
            self.purge_button,
            self.stop_button,
        ]

        self.matrix_mode_text = ft.Text(
            "Teclado: modo A · mover",
            color=COLORS["cyan"],
        )
        matrix_keys = [
            ["1", "2", "3", "A"],
            ["4", "5", "6", "B"],
            ["7", "8", "9", "C"],
            ["*", "0", "#", "D"],
        ]
        self.matrix_buttons = []
        for row in matrix_keys:
            controls = []
            for key in row:
                button = ft.OutlinedButton(
                    content=key,
                    on_click=lambda event, value=key: self._on_matrix_button(
                        event, value
                    ),
                    expand=True,
                )
                controls.append(button)
                self.matrix_buttons.append(button)
            self.matrix_rows = getattr(self, "matrix_rows", [])
            self.matrix_rows.append(ft.Row(controls, spacing=6))

        self.risk_text = ft.Text("", color=COLORS["red"])
        self.risk_banner = ft.Container(
            content=self.risk_text,
            bgcolor="#3a2024",
            border_radius=8,
            padding=10,
            visible=False,
        )
        self.chart_canvas = cv.Canvas(
            shapes=self._build_chart_shapes(),
            width=320,
            height=210,
        )
        self.chart_label = ft.Text(
            "Eje horizontal: tiempo reciente · eje vertical: °C",
            color=COLORS["muted"],
            size=12,
        )
        self.purge_dialog_text = ft.Text(
            "La purga abre las compuertas y activa los ventiladores."
        )
        self.purge_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar purga"),
            content=self.purge_dialog_text,
            actions=[
                ft.TextButton(
                    content="Cancelar",
                    on_click=self.cancel_purge,
                ),
                ft.FilledButton(
                    content="Confirmar",
                    on_click=self.confirm_purge,
                ),
            ],
        )

    def _numeric_field(self, label, value, name):
        return ft.TextField(
            label=label,
            value=value,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_focus=lambda event, field=name: self._on_field_focus(
                event, field
            ),
            on_change=lambda event, field=name: self._on_field_change(
                event, field
            ),
        )

    def _on_matrix_button(self, event, key):
        del event
        self.process_key(key)

    def _on_field_focus(self, event, field):
        del event
        self._select_item(field)

    def _on_field_change(self, event, field):
        del event
        self.dirty_fields.add(field)

    def _section(self, title, controls):
        return ft.Container(
            content=ft.Column(
                [ft.Text(title, size=17, weight=ft.FontWeight.BOLD), *controls],
                spacing=10,
            ),
            bgcolor=COLORS["surface"],
            border_radius=12,
            padding=14,
        )

    def _build_page(self):
        is_mobile = self.page.platform in (
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.IOS,
        )
        connection_controls: list[ft.Control] = [
            ft.Row(
                [self.ip_field, self.wifi_button],
                spacing=8,
            ),
        ]
        if not is_mobile:
            connection_controls.append(
                ft.Row([self.com_field, self.serial_button], spacing=8)
                if serial_module is not None
                else ft.Text(
                    "Puerto COM no disponible en este dispositivo.",
                    color=COLORS["muted"],
                )
            )
        connection_controls.append(
            ft.Row(
                [self.connection_status, self.disconnect_button],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        )
        self.root = ft.SafeArea(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Control de cámara térmica",
                            size=23,
                            weight=ft.FontWeight.BOLD,
                            color=COLORS["text"],
                        ),
                        ft.Text(
                            "ESP32 · conexión TCP Wi-Fi o Serial USB",
                            color=COLORS["muted"],
                        ),
                        self._section(
                            "Conexión",
                            connection_controls,
                        ),
                        self._section(
                            "Lecturas actuales",
                            [
                                self.temperature_text,
                                self.humidity_text,
                                self.phase_text,
                                self.range_text,
                                self.dimmer_text,
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(
                                            content=self.indicators["heater"],
                                            col={"xs": 6, "md": 3},
                                        ),
                                        ft.Container(
                                            content=self.indicators["peltier"],
                                            col={"xs": 6, "md": 3},
                                        ),
                                        ft.Container(
                                            content=self.indicators["fans"],
                                            col={"xs": 6, "md": 3},
                                        ),
                                        ft.Container(
                                            content=self.indicators["doors"],
                                            col={"xs": 6, "md": 3},
                                        ),
                                    ],
                                    spacing=8,
                                    run_spacing=8,
                                ),
                                self.risk_banner,
                            ],
                        ),
                        self._section(
                            "Temperatura en tiempo real",
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            "Temperatura", color=COLORS["cyan"]
                                        ),
                                        ft.Text(
                                            "Setpoint", color=COLORS["orange"]
                                        ),
                                    ],
                                    spacing=20,
                                ),
                                self.chart_canvas,
                                self.chart_label,
                            ],
                        ),
                        self._section(
                            "Rango térmico",
                            [
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(
                                            content=self.range_minimum_field,
                                            col={"xs": 6, "md": 4},
                                        ),
                                        ft.Container(
                                            content=self.range_maximum_field,
                                            col={"xs": 6, "md": 4},
                                        ),
                                        ft.Container(
                                            content=self.apply_range_button,
                                            col={"xs": 12, "md": 4},
                                        ),
                                    ],
                                    spacing=8,
                                ),
                            ],
                        ),
                        self._section(
                            "Control PID",
                            [
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(
                                            content=self.kp_field,
                                            col={"xs": 4},
                                        ),
                                        ft.Container(
                                            content=self.ki_field,
                                            col={"xs": 4},
                                        ),
                                        ft.Container(
                                            content=self.kd_field,
                                            col={"xs": 4},
                                        ),
                                    ],
                                    spacing=8,
                                ),
                                ft.Row([self.apply_pid_button], spacing=8),
                                ft.Row(
                                    [self.target_field, self.start_pid_button],
                                    spacing=8,
                                ),
                            ],
                        ),
                        self._section(
                            "Pruebas y operación",
                            [
                                ft.Row(
                                    [self.cycle_min_button, self.cycle_max_button],
                                    spacing=8,
                                ),
                                ft.Row(
                                    [self.test_button, self.dimmer_button],
                                    spacing=8,
                                ),
                                ft.Row(
                                    [self.purge_button, self.stop_button],
                                    spacing=8,
                                ),
                            ],
                        ),
                        self._section(
                            "Teclado matricial virtual",
                            [
                                self.matrix_mode_text,
                                *self.matrix_rows,
                                ft.Text(
                                    "A: mover · B: escribir · 2/4/6/8: navegar · "
                                    "1/3: ±0,5 · *: decimal · #: aceptar · "
                                    "C: ciclo mínima · D: detener",
                                    color=COLORS["muted"],
                                    size=12,
                                ),
                            ],
                        ),
                        self.status_text,
                    ],
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                expand=True,
                padding=4,
            ),
            expand=True,
        )

        self._refresh_command_buttons()

    def mostrar_notificacion(self, mensaje, color_fondo):
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(mensaje, color=COLORS["text"]),
                bgcolor=color_fondo,
                duration=2000,
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )

    def _build_chart_shapes(self):
        width = 320
        height = 210
        left = 34
        right = width - 8
        top = 12
        bottom = height - 24
        shapes = []
        grid_paint = ft.Paint(color="#344652", stroke_width=1)
        axis_paint = ft.Paint(color="#8fa4b5", stroke_width=1)
        for index in range(5):
            y = top + (bottom - top) * index / 4
            shapes.append(cv.Line(left, y, right, y, paint=grid_paint))
        shapes.append(cv.Line(left, top, left, bottom, paint=axis_paint))
        shapes.append(cv.Line(left, bottom, right, bottom, paint=axis_paint))

        values = [value for _, value in self.history]
        if self.setpoint is not None:
            values.append(self.setpoint)
        low = min(values) if values else 20.0
        high = max(values) if values else 40.0
        if high - low < 4.0:
            center = (high + low) / 2.0
            low, high = center - 2.0, center + 2.0
        else:
            padding = (high - low) * 0.12
            low -= padding
            high += padding
        value_span = max(high - low, 1.0)

        if self.setpoint is not None:
            y = bottom - (self.setpoint - low) / value_span * (bottom - top)
            shapes.append(
                cv.Line(
                    left,
                    y,
                    right,
                    y,
                    paint=ft.Paint(
                        color=COLORS["orange"],
                        stroke_width=2,
                        stroke_dash_pattern=[6, 4],
                    ),
                )
            )

        if len(self.history) > 1:
            first_time = self.history[0][0]
            last_time = self.history[-1][0]
            time_span = max(last_time - first_time, 1.0)
            points = []
            for timestamp, value in self.history:
                x = left + (timestamp - first_time) / time_span * (right - left)
                y = bottom - (value - low) / value_span * (bottom - top)
                points.append((x, y))
            temp_paint = ft.Paint(color=COLORS["cyan"], stroke_width=2.5)
            for start, end in zip(points, points[1:]):
                shapes.append(
                    cv.Line(start[0], start[1], end[0], end[1], paint=temp_paint)
                )
        return shapes

    def _select_item(self, item):
        self.active_item = item
        for row_index, row in enumerate(self.navigation):
            if item in row:
                self.nav_row = row_index
                self.nav_column = row.index(item)
                break

    def _move_navigation(self, key):
        if key in ("2", "8"):
            direction = -1 if key == "2" else 1
            self.nav_row = max(
                0,
                min(len(self.navigation) - 1, self.nav_row + direction),
            )
            self.nav_column = min(
                self.nav_column, len(self.navigation[self.nav_row]) - 1
            )
        else:
            direction = -1 if key == "4" else 1
            self.nav_column = max(
                0,
                min(
                    len(self.navigation[self.nav_row]) - 1,
                    self.nav_column + direction,
                ),
            )
        self.active_item = self.navigation[self.nav_row][self.nav_column]
        self.matrix_mode_text.value = (
            f"Teclado: modo A · seleccionado {self.active_item}"
        )

    def _active_field(self):
        return {
            "minimum": self.range_minimum_field,
            "maximum": self.range_maximum_field,
            "kp": self.kp_field,
            "ki": self.ki_field,
            "kd": self.kd_field,
            "target": self.target_field,
        }.get(self.active_item)

    def process_key(self, key):
        if key == "A":
            self.matrix_mode = "A"
            self.numeric_entry_started = False
            self.matrix_mode_text.value = (
                f"Teclado: modo A · seleccionado {self.active_item}"
            )
            self.page.update()
            return
        if key == "B":
            if self._active_field() is None:
                self.status_text.value = "Selecciona un campo numérico para editar."
            else:
                self.matrix_mode = "B"
                self.numeric_entry_started = False
                self.matrix_mode_text.value = (
                    f"Teclado: modo B · editando {self.active_item}"
                )
            self.page.update()
            return

        if self.matrix_mode == "B":
            if key == "#":
                self._commit_active_field()
                self.matrix_mode = "A"
                self.numeric_entry_started = False
                self.matrix_mode_text.value = (
                    f"Teclado: modo A · seleccionado {self.active_item}"
                )
            elif key == "*":
                self._append_decimal()
            elif key.isdigit():
                self._append_digit(key)
            elif key == "D":
                self.stop_all()
            elif key == "C":
                self.start_cycle("MIN")
            self.page.update()
            return

        if key in ("2", "4", "6", "8"):
            self._move_navigation(key)
        elif key in ("1", "3"):
            self._adjust_active_field(0.5 if key == "1" else -0.5)
        elif key == "#":
            if self._active_field() is not None:
                self.matrix_mode = "B"
                self.numeric_entry_started = False
                self.matrix_mode_text.value = (
                    f"Teclado: modo B · editando {self.active_item}"
                )
            else:
                self._activate_item()
        elif key == "C":
            self.start_cycle("MIN")
        elif key == "D":
            self.stop_all()
        self.page.update()

    def _append_digit(self, digit):
        field = self._active_field()
        if field is None:
            self.status_text.value = "Selecciona un campo numérico antes de escribir."
            return
        value = field.value or ""
        if not self.numeric_entry_started or value in ("0", "0.0"):
            value = ""
        field.value = value + digit
        self.numeric_entry_started = True
        self.dirty_fields.add(self.active_item)

    def _append_decimal(self):
        field = self._active_field()
        if field is None:
            self.status_text.value = "Selecciona un campo numérico antes de escribir."
            return
        value = field.value or ""
        if not self.numeric_entry_started:
            value = "0"
        if "." not in value:
            field.value = (value or "0") + "."
            self.numeric_entry_started = True
            self.dirty_fields.add(self.active_item)

    def _adjust_active_field(self, amount):
        field = self._active_field()
        if field is None:
            self.status_text.value = "Selecciona un campo numérico para ajustar."
            return
        try:
            value = float(field.value)
        except (TypeError, ValueError):
            value = 0.0
        field.value = f"{value + amount:.1f}"
        self.dirty_fields.add(self.active_item)
        if self.active_item in ("minimum", "maximum"):
            self.apply_range()
        elif self.active_item in ("kp", "ki", "kd"):
            self.apply_pid()
        elif self.active_item == "target":
            self.apply_target()

    def _commit_active_field(self):
        if self.active_item in ("minimum", "maximum"):
            self.apply_range()
        elif self.active_item in ("kp", "ki", "kd"):
            self.apply_pid()
        elif self.active_item == "target":
            self.apply_target()
        else:
            self.status_text.value = "Selecciona un campo numérico para confirmar."

    def _activate_item(self):
        actions = {
            "start_pid": self.apply_target,
            "apply_range": self.apply_range,
            "apply_pid": self.apply_pid,
            "cycle_min": lambda: self.start_cycle("MIN"),
            "cycle_max": lambda: self.start_cycle("MAX"),
            "test": self.toggle_test,
            "dimmer": self.start_dimmer_test,
            "purge": self.show_purge_confirmation,
            "stop": self.stop_all,
        }
        action = actions.get(self.active_item)
        if action is not None:
            action()

    def _read_number(self, field, label, minimum=None, maximum=None):
        try:
            value = float(field.value)
        except (TypeError, ValueError):
            self.status_text.value = f"{label}: introduce un número válido."
            return None
        if not math.isfinite(value):
            self.status_text.value = f"{label}: el valor debe ser finito."
            return None
        if minimum is not None and value < minimum:
            self.status_text.value = f"{label}: mínimo {minimum:g}."
            return None
        if maximum is not None and value > maximum:
            self.status_text.value = f"{label}: máximo {maximum:g}."
            return None
        return value

    def apply_range(self, _event=None):
        del _event
        minimum = self._read_number(
            self.range_minimum_field, "Temperatura mínima", 20.0, 50.0
        )
        maximum = self._read_number(
            self.range_maximum_field, "Temperatura máxima", 20.0, 50.0
        )
        if minimum is None or maximum is None:
            self.page.update()
            return
        if minimum + 2.0 > maximum:
            self.status_text.value = (
                "El rango requiere al menos 2 °C entre mínima y máxima."
            )
            self.page.update()
            return
        self._send(f"SETRANGE,{minimum:.1f},{maximum:.1f}")

    def apply_pid(self, _event=None):
        del _event
        values = []
        for field, label in (
            (self.kp_field, "Kp"),
            (self.ki_field, "Ki"),
            (self.kd_field, "Kd"),
        ):
            value = self._read_number(field, label, 0.0, 10.0)
            if value is None:
                self.page.update()
                return
            values.append(value)
        self._send("PID_TUNE,{:.3g},{:.3g},{:.3g}".format(*values))

    def apply_target(self, _event=None):
        del _event
        target = self._read_number(
            self.target_field, "Objetivo PID", 20.0, 50.0
        )
        if target is None:
            self.page.update()
            return
        self._send(f"TEMP_TARGET:{target:.1f}")

    def start_cycle(self, target, _event=None):
        del _event
        self._send(f"CYCLE,{target}")

    def toggle_test(self, _event=None):
        del _event
        self._send("TEST,0" if self.test_active else "TEST,1")

    def start_dimmer_test(self, _event=None):
        del _event
        self._send("DIMMER_TEST")

    def stop_all(self, _event=None):
        del _event
        self._send("STOP")

    def show_purge_confirmation(self, _event=None):
        del _event
        if self.dewpoint_risk:
            self.purge_dialog_text.value = (
                "Hay riesgo de punto de rocío "
                f"({self.dewpoint_temperature:.1f} °C). "
                "Confirma solo si es seguro continuar con la purga."
            )
        else:
            self.purge_dialog_text.value = (
                "La purga abre las compuertas y activa los ventiladores. "
                "¿Deseas continuar?"
            )
        self.page.show_dialog(self.purge_dialog)

    def cancel_purge(self, _event=None):
        del _event
        self.page.pop_dialog()

    def confirm_purge(self, _event=None):
        del _event
        self.page.pop_dialog()
        self._send("PURGE")

    def _send(self, command):
        if not self.connected:
            self.status_text.value = "Conecta el ESP32 antes de enviar comandos."
            self.page.update()
            return False
        self.tx_queue.put(command)
        self.status_text.value = f"Comando encolado: {command}"
        self.page.update()
        return True

    def connect_wifi(self, _event=None):
        del _event
        host = (self.ip_field.value or "").strip()
        if not host:
            self.status_text.value = "Escribe la IP del ESP32."
            self.page.update()
            return
        self._start_worker("Wi-Fi", self._wifi_worker, host)

    def connect_serial(self, _event=None):
        del _event
        if serial_module is None:
            self.status_text.value = "PySerial no está instalado en este equipo."
            self.page.update()
            return
        port = (self.com_field.value or "").strip()
        if not port:
            self.status_text.value = "Escribe el puerto COM."
            self.page.update()
            return
        self._start_worker("Serial", self._serial_worker, port)

    def _start_worker(self, kind, worker_function, address):
        if self.connected or self.connecting:
            self.status_text.value = "Desconecta la sesión actual antes de conectar."
            self.page.update()
            return
        if self.worker is not None and self.worker.is_alive():
            self.status_text.value = "La conexión anterior aún está cerrándose."
            self.page.update()
            return
        while not self.tx_queue.empty():
            try:
                self.tx_queue.get_nowait()
            except queue.Empty:
                break
        self.generation += 1
        generation = self.generation
        self.worker_stop = threading.Event()
        self.connecting = True
        self.connection_status.value = f"Conectando por {kind}..."
        self.status_text.value = "Intentando establecer conexión…"
        self._refresh_command_buttons()
        self.page.update()
        self.worker = threading.Thread(
            target=worker_function,
            args=(generation, self.worker_stop, address),
            daemon=True,
        )
        self.worker.start()

    def _emit(self, event, generation, value=""):
        self.rx_queue.put((event, generation, value))

    def _wifi_worker(self, generation, stop_event, host):
        connection = None
        reason = "Conexión Wi-Fi cerrada."
        try:
            connection = socket.create_connection(
                (host, TCP_PORT),
                timeout=5.0,
            )
            connection.settimeout(0.2)
            connection.sendall(b"KEYPAD_UI,1\n")
            self._emit("connected", generation, "Wi-Fi")
            self._socket_session(connection, generation, stop_event)
        except (OSError, socket.timeout) as error:
            reason = f"No se pudo conectar por Wi-Fi: {error}"
        finally:
            if connection is not None:
                try:
                    connection.sendall(b"KEYPAD_UI,0\n")
                except OSError:
                    pass
                connection.close()
            self._emit("disconnected", generation, reason)

    def _socket_session(self, connection, generation, stop_event):
        pending = bytearray()
        next_heartbeat = time.monotonic() + 1.0
        while not stop_event.is_set():
            now = time.monotonic()
            if now >= next_heartbeat:
                connection.sendall(b"KEYPAD_UI,1\n")
                next_heartbeat = now + 1.0
            self._flush_socket_commands(connection)
            try:
                data = connection.recv(1024)
            except socket.timeout:
                continue
            if not data:
                raise ConnectionError("El ESP32 cerró la conexión TCP.")
            pending.extend(data)
            if len(pending) > 4096 and b"\n" not in pending:
                pending.clear()
                self._emit(
                    "line",
                    generation,
                    "WARN,APP,LINE_TOO_LONG",
                )
                continue
            while b"\n" in pending:
                raw, _, remainder = pending.partition(b"\n")
                pending = bytearray(remainder)
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self._emit("line", generation, line)

    def _flush_socket_commands(self, connection):
        while True:
            try:
                command = self.tx_queue.get_nowait()
            except queue.Empty:
                return
            connection.sendall((command + "\n").encode("utf-8"))

    def _serial_worker(self, generation, stop_event, port):
        if serial_module is None:
            self._emit(
                "disconnected",
                generation,
                "PySerial no está instalado en este equipo.",
            )
            return
        connection = None
        reason = "Conexión Serial cerrada."
        try:
            connection = serial_module.Serial(
                port,
                115200,
                timeout=0.2,
                write_timeout=0.5,
            )
            connection.write(b"KEYPAD_UI,1\n")
            self._emit("connected", generation, "Serial")
            next_heartbeat = time.monotonic() + 1.0
            while not stop_event.is_set():
                now = time.monotonic()
                if now >= next_heartbeat:
                    connection.write(b"KEYPAD_UI,1\n")
                    next_heartbeat = now + 1.0
                self._flush_serial_commands(connection)
                raw = connection.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self._emit("line", generation, line)
        except (OSError, serial_module.SerialException) as error:
            reason = f"No se pudo conectar por Serial: {error}"
        finally:
            if connection is not None:
                try:
                    connection.write(b"KEYPAD_UI,0\n")
                except (OSError, serial_module.SerialException):
                    pass
                connection.close()
            self._emit("disconnected", generation, reason)

    def _flush_serial_commands(self, connection):
        while True:
            try:
                command = self.tx_queue.get_nowait()
            except queue.Empty:
                return
            connection.write((command + "\n").encode("utf-8"))

    async def _ui_pump(self):
        while not self.closed:
            changed = False
            while True:
                try:
                    event, generation, value = self.rx_queue.get_nowait()
                except queue.Empty:
                    break
                if generation != self.generation:
                    continue
                if event == "connected":
                    self.connected = True
                    self.connecting = False
                    self.connection_kind = value
                    self.mostrar_notificacion(
                        "✅ Conectado al ESP32",
                        COLORS["green"],
                    )
                    self.connection_status.value = f"Conectado por {value}"
                    self.status_text.value = (
                        "Teclado matricial habilitado; heartbeat cada 1 s."
                    )
                    self.matrix_mode = "A"
                    self.matrix_mode_text.value = (
                        f"Teclado: modo A · mover ({value})"
                    )
                    self._refresh_command_buttons()
                elif event == "disconnected":
                    was_connected = self.connected
                    self.connected = False
                    self.connecting = False
                    self.connection_kind = ""
                    if was_connected:
                        self.mostrar_notificacion(
                            "⚠️ Desconectado del ESP32",
                            COLORS["orange"],
                        )
                    self.connection_status.value = "Desconectado"
                    self.status_text.value = value
                    self._refresh_command_buttons()
                elif event == "line":
                    self.process_line(value)
                changed = True

            if self.chart_dirty:
                self.chart_canvas.shapes = self._build_chart_shapes()
                self.chart_dirty = False
                changed = True
            if changed:
                self.page.update()
            await asyncio.sleep(0.05)

    def _refresh_command_buttons(self):
        for button in getattr(self, "command_buttons", []):
            button.disabled = not self.connected
        self.wifi_button.disabled = self.connected or self.connecting
        if serial_module is not None:
            self.serial_button.disabled = self.connected or self.connecting
        self.disconnect_button.disabled = not (
            self.connected or self.connecting
        )

    def process_line(self, line):
        parts = line.split(",")
        if parts and parts[0] == "STATUS":
            self._process_status(parts)
            return
        if line.startswith("TEMP_CURRENT:"):
            try:
                temperature = float(line.split(":", 1)[1])
            except ValueError:
                self.status_text.value = "Trama TEMP_CURRENT inválida."
                return
            if math.isfinite(temperature) and 0 <= temperature <= 50:
                self._set_temperature(temperature)
            return
        if len(parts) == 2 and parts[0] == "KEYPAD_KEY":
            if len(parts[1]) == 1 and parts[1] in "0123456789ABCD*#":
                self.process_key(parts[1])
            return
        if len(parts) >= 3 and parts[:2] == ["WARN", "DEWPOINT"]:
            self._process_dewpoint_warning(parts)
            return
        if parts and parts[0] == "WARN":
            self.status_text.value = "Advertencia ESP32: " + ",".join(parts[1:])
            return
        if len(parts) >= 3 and parts[:2] == ["INFO", "KEYPAD"]:
            self._process_keypad_info(parts)
            return
        if parts and parts[0] == "ACK":
            self._process_ack(parts)
            return
        if parts and parts[0] == "ERR":
            detail = ",".join(parts[1:]) or "Error desconocido"
            self.status_text.value = f"ESP32: {detail}"
            return
        if parts and parts[0] == "INFO" and len(parts) >= 3:
            self.status_text.value = "ESP32: " + " ".join(parts[1:])

    def _process_status(self, parts):
        if len(parts) < 4:
            self.status_text.value = "Trama STATUS incompleta."
            return
        sensor_error = len(parts) > 1 and parts[1] == "ERROR"
        try:
            temperature = None if sensor_error else float(parts[1])
            heater = parts[2] == "1"
            peltier = parts[3] == "1"
            fans = len(parts) > 4 and parts[4] == "1"
            doors = len(parts) > 5 and parts[5] == "1"
            phase = parts[6] if len(parts) > 6 else "UNKNOWN"
            humidity = (
                None
                if sensor_error or len(parts) <= 7
                else float(parts[7])
            )
            minimum = float(parts[8]) if len(parts) > 9 else None
            maximum = float(parts[9]) if len(parts) > 9 else None
            cycle = len(parts) > 10 and parts[10] == "1"
            power = float(parts[11]) if len(parts) > 11 else 0.0
            angle = int(float(parts[12])) if len(parts) > 12 else 0
        except (ValueError, IndexError):
            self.status_text.value = "Trama STATUS inválida."
            return

        if temperature is not None and (
            not math.isfinite(temperature) or not 0 <= temperature <= 50
        ):
            self.status_text.value = "Temperatura STATUS fuera de rango."
            return
        if humidity is not None and (
            not math.isfinite(humidity) or not 0 <= humidity <= 100
        ):
            humidity = None
        if power is not None and (
            not math.isfinite(power) or not 0 <= power <= 100
        ):
            power = 0.0

        self._notify_status_transitions(
            heater,
            peltier,
            fans,
            doors,
            sensor_error,
        )
        self.heater_on = heater
        self.peltier_on = peltier
        self.fans_on = fans
        self.doors_open = doors
        self.cycle_active = cycle
        self.phase = self._phase_label(phase)
        self.phase_text.value = f"Fase: {self.phase}"
        self.humidity = humidity
        self.humidity_text.value = (
            "Humedad: --%"
            if humidity is None
            else f"Humedad: {humidity:.0f}%"
        )
        self.power_percent = power
        self.servo_angle = angle
        self.dimmer_text.value = (
            f"Potencia del dimmer: {power:.0f}% · servo: {angle}°"
        )
        self._set_indicator("heater", heater)
        self._set_indicator("peltier", peltier)
        self._set_indicator("fans", fans)
        self._set_indicator("doors", doors)

        if minimum is not None and maximum is not None:
            if (
                math.isfinite(minimum)
                and math.isfinite(maximum)
                and minimum < maximum
            ):
                self.range_minimum = minimum
                self.range_maximum = maximum
                self.range_text.value = (
                    f"Rango actual: {minimum:.1f}–{maximum:.1f} °C"
                )
                if "minimum" not in self.dirty_fields:
                    self.range_minimum_field.value = f"{minimum:.1f}"
                if "maximum" not in self.dirty_fields:
                    self.range_maximum_field.value = f"{maximum:.1f}"
        else:
            self.range_text.value = "Rango actual: no disponible"

        if phase.endswith("_MIN"):
            self.setpoint = self.range_minimum
            self.chart_dirty = True
        elif phase.endswith("_MAX"):
            self.setpoint = self.range_maximum
            self.chart_dirty = True
        if temperature is None:
            self.temperature_text.value = "--.- °C"
            self.status_text.value = "Lectura del DHT11 inválida."
        else:
            self._set_temperature(temperature)
            self.status_text.value = "Datos recibidos del ESP32."

    def _notify_status_transitions(
        self,
        heater,
        peltier,
        fans,
        doors,
        sensor_error,
    ):
        states = {
            "heater": heater,
            "peltier": peltier,
            "fans": fans,
            "doors": doors,
        }
        notifications = (
            ("heater", "🔥 Foco calefactor encendido", COLORS["orange"]),
            ("peltier", "❄️ Módulo Peltier encendido", COLORS["cyan"]),
            ("fans", "🌀 Ventiladores activados", COLORS["green"]),
        )
        for key, message, color in notifications:
            if self.previous_actuator_states[key] is False and states[key]:
                self.mostrar_notificacion(message, color)

        previous_doors = self.previous_actuator_states["doors"]
        if previous_doors is False and doors:
            self.mostrar_notificacion(
                "🚪 Compuertas de purga abiertas",
                COLORS["cyan"],
            )
        elif previous_doors is True and not doors:
            self.mostrar_notificacion(
                "🔒 Compuertas cerradas",
                COLORS["green"],
            )

        self.previous_actuator_states.update(states)
        if sensor_error and not self.sensor_error_active:
            self.mostrar_notificacion(
                "🚨 Error de lectura en sensor DHT11",
                COLORS["red"],
            )
        self.sensor_error_active = sensor_error

    def _set_temperature(self, temperature):
        self.current_temperature = temperature
        self.temperature_text.value = f"{temperature:.1f} °C"
        now = time.monotonic()
        if now - self.last_sample_time >= 0.5:
            self.history.append((now, temperature))
            self.last_sample_time = now
            self.chart_dirty = True

    def _set_indicator(self, key, active):
        self.indicators[key].bgcolor = (
            "#1b493c" if active else COLORS["surface_alt"]
        )
        self.indicator_lights[key].color = (
            COLORS["green"] if active else COLORS["off"]
        )

    def _phase_label(self, phase):
        labels = {
            "HEATING": "Calentando",
            "COOLING": "Enfriando",
            "HOLD": "Manteniendo",
            "STOPPED": "Detenido",
            "TESTING": "Prueba de tapas/ventiladores",
            "DIMMER_TEST": "Prueba del dimmer",
            "PURGE_OPENING": "Purga: abriendo compuertas",
            "PURGE_RUNNING": "Purga: ventilando",
            "PURGE_CLOSING": "Purga: cerrando compuertas",
            "SENSOR_ERROR": "Error del sensor",
            "CYCLE_HEATING_MIN": "Ciclo: calentando hasta mínima",
            "CYCLE_HEATING_MAX": "Ciclo: calentando hasta máxima",
            "CYCLE_COOLING_MIN": "Ciclo: enfriando hasta mínima",
            "CYCLE_COOLING_MAX": "Ciclo: enfriando hasta máxima",
            "NORMAL": "Normal",
        }
        return labels.get(phase, phase.replace("_", " ").title())

    def _process_ack(self, parts):
        if len(parts) >= 2 and parts[1] == "SETRANGE" and len(parts) == 4:
            try:
                self.range_minimum = float(parts[2])
                self.range_maximum = float(parts[3])
            except ValueError:
                self.status_text.value = "ACK de rango inválido."
                return
            self.range_minimum_field.value = f"{self.range_minimum:.1f}"
            self.range_maximum_field.value = f"{self.range_maximum:.1f}"
            self.dirty_fields.discard("minimum")
            self.dirty_fields.discard("maximum")
            self.range_text.value = (
                f"Rango actual: {self.range_minimum:.1f}–"
                f"{self.range_maximum:.1f} °C"
            )
            self.status_text.value = "Rango aplicado."
        elif len(parts) >= 2 and parts[1] == "PID_TUNE":
            for field in ("kp", "ki", "kd"):
                self.dirty_fields.discard(field)
            self.status_text.value = "Parámetros PID aplicados."
        elif len(parts) >= 3 and parts[1] == "TEMP_TARGET":
            try:
                self.setpoint = float(parts[2])
            except ValueError:
                self.status_text.value = "ACK de setpoint inválido."
                return
            self.target_field.value = f"{self.setpoint:.1f}"
            self.dirty_fields.discard("target")
            self.chart_dirty = True
            self.status_text.value = (
                f"Control PID activo a {self.setpoint:.1f} °C."
            )
        elif len(parts) >= 2 and parts[1] == "CYCLE":
            self.cycle_active = True
            target = parts[3] if len(parts) > 3 else "MIN"
            self.setpoint = (
                self.range_maximum if target == "MAX" else self.range_minimum
            )
            self.chart_dirty = True
            self.status_text.value = f"Ciclo térmico iniciado hacia {target}."
        elif len(parts) >= 2 and parts[1] == "TEST":
            self.test_active = len(parts) > 2 and parts[2] == "ON"
            self.test_button.content = (
                "Detener prueba de tapas/ventiladores"
                if self.test_active
                else "Probar tapas/ventiladores"
            )
            self.status_text.value = (
                "Prueba de tapas/ventiladores activa."
                if self.test_active
                else "Prueba detenida."
            )
        elif len(parts) >= 2 and parts[1] == "STOP":
            self.test_active = False
            self.cycle_active = False
            self.test_button.content = "Probar tapas/ventiladores"
            self.status_text.value = "Control detenido."
        elif len(parts) >= 2 and parts[1] == "PURGE":
            self.status_text.value = "Purga de aire iniciada."
        elif len(parts) >= 2 and parts[1] == "DIMMER_TEST":
            self.status_text.value = (
                "Prueba del servo dimmer terminada."
                if len(parts) > 2 and parts[2] == "DONE"
                else "Prueba del servo dimmer iniciada."
            )
        elif len(parts) >= 2 and parts[1] == "KEYPAD_UI":
            self.status_text.value = "Teclado matricial sincronizado."

    def _process_dewpoint_warning(self, parts):
        if len(parts) >= 3 and parts[2] == "CLEAR":
            self.dewpoint_risk = False
            self.dewpoint_temperature = None
            self.risk_banner.visible = False
            self.risk_text.value = ""
            self.status_text.value = "Riesgo de punto de rocío eliminado."
            return
        if len(parts) == 5 and parts[2] == "RISK":
            try:
                dewpoint = float(parts[3])
                minimum = float(parts[4])
            except ValueError:
                self.status_text.value = "Trama de punto de rocío inválida."
                return
            if not math.isfinite(dewpoint) or not math.isfinite(minimum):
                self.status_text.value = "Trama de punto de rocío inválida."
                return
            self.dewpoint_risk = True
            self.dewpoint_temperature = dewpoint
            self.risk_text.value = (
                f"Riesgo de punto de rocío: {dewpoint:.1f} °C "
                f"frente a mínima {minimum:.1f} °C."
            )
            self.risk_banner.visible = True
            self.status_text.value = "Advertencia de punto de rocío recibida."

    def _process_keypad_info(self, parts):
        if len(parts) >= 4 and parts[2] == "EDIT":
            label = "mínima" if parts[3] == "MIN" else "máxima"
            value = parts[4] if len(parts) > 4 else ""
            self.matrix_mode_text.value = (
                f"ESP32 edita temperatura {label}: {value} °C"
            )
        elif len(parts) >= 3 and parts[2] == "SAVED":
            self.matrix_mode_text.value = "Teclado del ESP32: valor guardado."
        elif len(parts) >= 3 and parts[2] == "CANCELLED":
            self.matrix_mode_text.value = "Teclado del ESP32: edición cancelada."
        elif len(parts) >= 3:
            self.matrix_mode_text.value = "Teclado del ESP32: " + parts[2]

    def disconnect(self, _event=None):
        del _event
        if self.worker_stop is not None:
            self.worker_stop.set()
        self.connecting = False
        self.connection_status.value = "Desconectando..."
        self.status_text.value = (
            "El ESP32 recuperará el teclado local si se pierde el heartbeat."
        )
        self._refresh_command_buttons()
        self.page.update()

    def close(self, _event=None):
        del _event
        self.closed = True
        if self.worker_stop is not None:
            self.worker_stop.set()

async def main(page):
  page.title = "Caja térmica"
  page.theme_mode = ft.ThemeMode.DARK
  page.bgcolor = "#0F172A"

  icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
  logo = (
      ft.Image(src="icon.png", width=96, height=96)
      if icon_path.is_file()
      else ft.Icon(ft.Icons.THERMOSTAT, size=96, color=COLORS["cyan"])
  )
  page.add(
      ft.Container(
          content=ft.Column(
              [
                  logo,
                  ft.Text(
                      "Control de Cámara Térmica",
                      size=24,
                      weight=ft.FontWeight.BOLD,
                      color="#F8FAFC",
                      text_align=ft.TextAlign.CENTER,
                  ),
                  ft.Text(
                      "Sistemas Embebidos · ESP32",
                      color="#CBD5E1",
                      text_align=ft.TextAlign.CENTER,
                  ),
                  ft.ProgressRing(
                      width=24,
                      height=24,
                      stroke_width=2,
                      color=COLORS["cyan"],
                  ),
              ],
              alignment=ft.MainAxisAlignment.CENTER,
              horizontal_alignment=ft.CrossAxisAlignment.CENTER,
              spacing=18,
          ),
          bgcolor="#0F172A",
          expand=True,
          alignment=ft.Alignment.CENTER,
      )
  )
  await asyncio.sleep(2.5)
  page.clean()
  TemperaturaApp(page)


if __name__ == "__main__":
  ft.run(main, assets_dir="assets")
