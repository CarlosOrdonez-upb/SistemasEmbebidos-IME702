import sys
import math
from collections import deque
from functools import partial
from typing import cast
import serial
import pyqtgraph as pg
from serial.tools import list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QDoubleSpinBox,
                             QPushButton, QScrollArea, QGroupBox,
                             QAbstractButton,
                             QComboBox, QDialog,
                             QMessageBox,
                             QGraphicsView, QGraphicsScene, QGraphicsRectItem, 
                             QGraphicsEllipseItem, QGraphicsTextItem,
                             QGraphicsItemGroup, QGraphicsPolygonItem,
                             QGraphicsLineItem)
from PyQt5.QtCore import QEvent, QTimer, Qt, QPointF
from PyQt5.QtGui import (QBrush, QPen, QColor, QPainter, QPolygonF,
                         QRadialGradient, QLinearGradient, QPainterPath,
                         QPixmap, QKeyEvent)

class SimulacionCuarto(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control de Cámara Térmica - Simulación")
        self.resize(1000, 800)

        self.arduino = None
        self.sensor_valido = False
        self.purga_soportada = False
        self.buffer_serial = bytearray()
        self.modo_termico = "MANTENIENDO"
        self.fase_particulas = 0
        self.angulo_fan = 0
        self.ventiladores_activos = False
        self.puertas_abiertas = False
        self.prueba_conexion_activa = False
        self.prueba_dimmer_activa = False
        self.control_pid_activo = False
        self.ciclo_activo = False
        self.ciclo_soportado = False
        self.temperatura_actual = None
        self.potencia_foco = None
        self.angulo_servo_dimmer = None
        self.dimmer_soportado = False
        self.edicion_teclado_activa = False
        self.modo_teclado_matriz = "A"
        self.dialogo_purga = None
        self.lbl_detalle_purga = None
        self.lbl_cuenta_purga = None
        self.boton_iniciar_purga = None
        self.boton_cancelar_purga = None
        self.color_ambiente = QColor(203, 209, 207)
        self.color_ambiente_objetivo = QColor(203, 209, 207)
        self.buffer_temp = deque(maxlen=150)
        self.buffer_time = deque(maxlen=150)
        self.tiempo_actual = 0

        # --- Interfaz Gráfica ---
        main_widget = QWidget()
        main_widget.setStyleSheet("""
            QWidget {
                background-color: #101923;
                color: #e6eef5;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QLabel#titulo {
                color: #f4f8fb;
                font-size: 16pt;
                font-weight: 700;
            }
            QLabel#subtitulo {
                color: #8fa4b5;
                font-size: 9pt;
            }
            QLabel#temperatura {
                color: #7de3ef;
                background-color: #172633;
                border: 1px solid #294454;
                border-radius: 10px;
                padding: 12px;
                font-size: 19pt;
                font-weight: 700;
            }
            QLabel#estado {
                color: #b7c8d4;
                background-color: #17232e;
                border: 1px solid #263744;
                border-radius: 8px;
                padding: 8px;
            }
            QComboBox, QDoubleSpinBox {
                background-color: #1a2a36;
                border: 1px solid #354b5a;
                border-radius: 6px;
                padding: 7px;
                selection-background-color: #168da0;
            }
            QPushButton {
                background-color: #167d8b;
                border: 0;
                border-radius: 7px;
                padding: 9px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1b9bad; }
            QPushButton:pressed { background-color: #116672; }
            QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #35c4d2;
            }
            QPushButton#secundario { background-color: #263744; }
            QPushButton#secundario:hover { background-color: #354b5a; }
        """)
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(18)

        # Lado Izquierdo: Simulación Visual
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setFrameShape(QGraphicsView.NoFrame)
        self.view.setStyleSheet(
            "background-color: #101923; border: 1px solid #263744; "
            "border-radius: 12px;"
        )
        main_layout.addWidget(self.view, 2)

        # Lado Derecho: Controles
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(4, 4, 4, 4)
        control_layout.setSpacing(10)
        control_scroll = QScrollArea()
        control_scroll.setWidgetResizable(True)
        control_scroll.setFrameShape(QScrollArea.NoFrame)
        control_scroll.setWidget(control_panel)
        self.control_scroll = control_scroll
        main_layout.addWidget(control_scroll, 1)

        titulo = QLabel("CÁMARA TÉRMICA")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Panel de monitoreo y control")
        subtitulo.setObjectName("subtitulo")
        self.lbl_temp_actual = QLabel("--.- °C")
        self.lbl_temp_actual.setObjectName("temperatura")
        self.lbl_estado = QLabel("Estado: Esperando conexión")
        self.lbl_estado.setObjectName("estado")
        self.lbl_rango_actual = QLabel("Rango actual: --.- °C - --.- °C")

        humedad_layout = QHBoxLayout()
        self.icono_humedad = QLabel()
        self.icono_humedad.setPixmap(self.crear_icono_gota())
        self.lbl_humedad = QLabel("Humedad: --%")
        humedad_layout.addWidget(self.icono_humedad)
        humedad_layout.addWidget(self.lbl_humedad)
        humedad_layout.addStretch()
        self.lbl_dimmer = QLabel(
            "Potencia solicitada al dimmer: --% · Servo comandado: --°"
        )

        self.combo_puertos = QComboBox()
        self.boton_conexion = QPushButton("Conectar")
        self.boton_conexion.clicked.connect(self.conectar_serial)
        self.boton_actualizar_puertos = QPushButton("Actualizar puertos")
        self.boton_actualizar_puertos.setObjectName("secundario")
        self.boton_actualizar_puertos.clicked.connect(self.cargar_puertos)
        self.boton_prueba_conexion = QPushButton(
            "Probar tapas y ventiladores"
        )
        self.boton_prueba_conexion.setObjectName("secundario")
        self.boton_prueba_conexion.setToolTip(
            "Mueve los servos de tapas GPIO 22/23 y solicita HIGH en GPIO 18 "
            "para los ventiladores. No mueve el servo dimmer GPIO 21."
        )
        self.boton_prueba_conexion.setEnabled(False)
        self.boton_prueba_conexion.clicked.connect(self.alternar_prueba_conexion)
        self.boton_prueba_dimmer = QPushButton("Probar servo dimmer (GPIO 21)")
        self.boton_prueba_dimmer.setObjectName("secundario")
        self.boton_prueba_dimmer.setToolTip(
            "Con DHT11 válido y control detenido, lleva el dimmer a 50° "
            "(50% del recorrido) durante un segundo y vuelve a 0°. "
            "Este es el botón que prueba GPIO 21."
        )
        self.boton_prueba_dimmer.setEnabled(False)
        self.boton_prueba_dimmer.clicked.connect(
            self.solicitar_prueba_dimmer
        )
        self.boton_purga = QPushButton("Purga de aire")
        self.boton_purga.setEnabled(False)
        self.boton_purga.clicked.connect(self.solicitar_purga_manual)
        self.boton_iniciar_ciclo = QPushButton("Iniciar ciclo térmico")
        self.boton_iniciar_ciclo.setEnabled(False)
        self.boton_iniciar_ciclo.clicked.connect(self.solicitar_inicio_ciclo)
        self.boton_detener_ciclo = QPushButton("Detener todo")
        self.boton_detener_ciclo.setObjectName("secundario")
        self.boton_detener_ciclo.setEnabled(False)
        self.boton_detener_ciclo.clicked.connect(self.detener_ciclo)
        ciclo_layout = QHBoxLayout()
        ciclo_layout.addWidget(self.boton_iniciar_ciclo)
        ciclo_layout.addWidget(self.boton_detener_ciclo)

        self.teclas_virtuales = {}
        distribucion_teclado = QGridLayout()
        distribucion_teclado.setSpacing(5)
        teclas = (
            ("1", "2", "3", "A"),
            ("4", "5", "6", "B"),
            ("7", "8", "9", "C"),
            ("*", "0", "#", "D"),
        )
        acciones_teclas = {
            "A": "Modo A: mover el foco por la interfaz",
            "B": "Modo B: escribir un valor numérico",
            "1": "En modo A: aumentar el control numérico enfocado en 0.5",
            "2": "En modo A: mover el foco hacia arriba",
            "3": "En modo A: reducir el control numérico enfocado en 0.5",
            "4": "En modo A: mover el foco a la izquierda",
            "6": "En modo A: mover el foco a la derecha",
            "8": "En modo A: mover el foco hacia abajo",
            "C": "Iniciar el ciclo térmico hacia la temperatura mínima",
            "D": "Detener el ciclo y las salidas",
            "*": "En modo B: escribir el separador decimal",
            "#": "Seleccionar, abrir un menú o aceptar un valor",
        }
        for fila, teclas_fila in enumerate(teclas):
            for columna, tecla in enumerate(teclas_fila):
                boton = QPushButton(tecla)
                boton.setMinimumHeight(36)
                boton.setFocusPolicy(Qt.NoFocus)
                boton.setToolTip(acciones_teclas.get(
                    tecla, f"Introducir el dígito {tecla}"
                ))
                boton.setEnabled(False)
                boton.clicked.connect(
                    partial(self.procesar_tecla_interfaz, tecla)
                )
                self.teclas_virtuales[tecla] = boton
                if tecla.isdigit():
                    boton.setObjectName("secundario")
                distribucion_teclado.addWidget(boton, fila, columna)
        leyenda_teclado = QLabel(
            "A: mover · 2/4/6/8: navegar · 1/3: ±0.5 · "
            "B: números · #: seleccionar/aceptar · C: ciclo · D: detener"
        )
        leyenda_teclado.setWordWrap(True)
        self.lbl_estado_teclado = QLabel()
        self.lbl_estado_teclado.setWordWrap(True)
        self.actualizar_estado_modo_teclado()
        
        self.lbl_rango = QLabel("RANGO DE TEMPERATURA")
        self.lbl_temp_minima = QLabel("Temperatura mínima")
        self.spin_temp_minima = QDoubleSpinBox()
        self.spin_temp_minima.setRange(20.0, 48.0)
        self.spin_temp_minima.setValue(28.0)
        self.spin_temp_minima.setSingleStep(0.5)
        self.spin_temp_minima.setSuffix(" °C")
        self.spin_temp_minima.setToolTip(
            "Rango permitido: 20–48 °C; deja al menos 2 °C hasta la máxima"
        )
        self.spin_temp_minima.valueChanged.connect(
            self.actualizar_temperatura_minima
        )
        self.lbl_temp_maxima = QLabel("Temperatura máxima")
        self.spin_temp_maxima = QDoubleSpinBox()
        self.spin_temp_maxima.setRange(22.0, 50.0)
        self.spin_temp_maxima.setValue(35.0)
        self.spin_temp_maxima.setSingleStep(0.5)
        self.spin_temp_maxima.setSuffix(" °C")
        self.spin_temp_maxima.setToolTip(
            "Rango permitido: 22–50 °C; deja al menos 2 °C desde la mínima"
        )
        self.spin_temp_maxima.valueChanged.connect(
            self.actualizar_temperatura_maxima
        )
        rango_layout = QHBoxLayout()
        minimo_layout = QVBoxLayout()
        minimo_layout.addWidget(self.lbl_temp_minima)
        minimo_layout.addWidget(self.spin_temp_minima)
        maximo_layout = QVBoxLayout()
        maximo_layout.addWidget(self.lbl_temp_maxima)
        maximo_layout.addWidget(self.spin_temp_maxima)
        rango_layout.addLayout(minimo_layout)
        rango_layout.addLayout(maximo_layout)

        # --- Controles PID y gráfica ---
        pid_group = QGroupBox("Sintonización PID")
        pid_layout = QVBoxLayout(pid_group)
        self.spin_kp = QDoubleSpinBox()
        self.spin_ki = QDoubleSpinBox()
        self.spin_kd = QDoubleSpinBox()
        for control, valor in (
            (self.spin_kp, 2.0),
            (self.spin_ki, 0.5),
            (self.spin_kd, 1.0),
        ):
            control.setRange(0.0, 10.0)
            control.setSingleStep(0.1)
            control.setValue(valor)
        pid_layout.addWidget(QLabel("Kp"))
        pid_layout.addWidget(self.spin_kp)
        pid_layout.addWidget(QLabel("Ki"))
        pid_layout.addWidget(self.spin_ki)
        pid_layout.addWidget(QLabel("Kd"))
        pid_layout.addWidget(self.spin_kd)
        self.boton_aplicar_pid = QPushButton("Aplicar Tuning PID")
        self.boton_aplicar_pid.clicked.connect(self.aplicar_tuning_pid)
        pid_layout.addWidget(self.boton_aplicar_pid)

        self.spin_temp_objetivo = QDoubleSpinBox()
        self.spin_temp_objetivo.setRange(20.0, 50.0)
        self.spin_temp_objetivo.setValue(28.0)
        self.spin_temp_objetivo.setSingleStep(0.5)
        self.spin_temp_objetivo.setSuffix(" °C")
        pid_layout.addWidget(QLabel("Temperatura objetivo"))
        pid_layout.addWidget(self.spin_temp_objetivo)
        self.boton_mantener_temp = QPushButton("Mantener temperatura (PID)")
        self.boton_mantener_temp.setToolTip(
            "Calienta con el dimmer de GPIO 21 o enfría con la Peltier de "
            "GPIO 19 según el error. Detén primero el ciclo o las pruebas."
        )
        self.boton_mantener_temp.clicked.connect(self.mantener_temperatura_pid)
        pid_layout.addWidget(self.boton_mantener_temp)
        for control in (
            self.spin_temp_minima,
            self.spin_temp_maxima,
            self.spin_kp,
            self.spin_ki,
            self.spin_kd,
            self.spin_temp_objetivo,
        ):
            control.setKeyboardTracking(False)

        self.plot_widget = pg.PlotWidget(title="Temperatura vs Tiempo")
        self.plot_widget.setLabel("left", "Temperatura", units="°C")
        self.plot_widget.setLabel("bottom", "Tiempo", units="s")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.addLegend()
        self.linea_temp = self.plot_widget.plot(
            pen=pg.mkPen("c", width=2), name="Temp Actual"
        )
        self.linea_setpoint = self.plot_widget.plot(
            pen=pg.mkPen("y", style=Qt.PenStyle.DashLine), name="Setpoint"
        )
        self.spin_temp_objetivo.valueChanged.connect(self.actualizar_grafica)

        control_layout.addWidget(titulo)
        control_layout.addWidget(subtitulo)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.lbl_temp_actual)
        control_layout.addWidget(self.lbl_estado)
        control_layout.addWidget(self.lbl_rango_actual)
        control_layout.addLayout(humedad_layout)
        control_layout.addWidget(self.lbl_dimmer)
        control_layout.addSpacing(8)
        control_layout.addWidget(QLabel("PUERTO DEL ESP32"))
        control_layout.addWidget(self.combo_puertos)
        control_layout.addWidget(self.boton_conexion)
        control_layout.addWidget(self.boton_actualizar_puertos)
        control_layout.addWidget(self.boton_prueba_conexion)
        control_layout.addWidget(self.boton_prueba_dimmer)
        control_layout.addWidget(self.boton_purga)
        control_layout.addLayout(ciclo_layout)
        control_layout.addWidget(QLabel("TECLADO"))
        control_layout.addLayout(distribucion_teclado)
        control_layout.addWidget(leyenda_teclado)
        control_layout.addWidget(self.lbl_estado_teclado)
        control_layout.addSpacing(8)
        control_layout.addWidget(self.lbl_rango)
        control_layout.addLayout(rango_layout)
        control_layout.addWidget(pid_group)
        control_layout.addWidget(cast(QWidget, self.plot_widget))
        control_layout.addStretch()

        # --- Dibujar la Simulación ---
        self.dibujar_caja()
        self.dibujar_componentes()

        # Timer para actualizar la interfaz y leer serial
        self.timer_serial = QTimer()
        self.timer_serial.timeout.connect(self.leer_serial)
        self.timer_serial.start(50)

        self.timer_animacion = QTimer()
        self.timer_animacion.timeout.connect(self.animar_ventiladores)
        self.timer_animacion.start(30)

        self.timer_modo_teclado = QTimer(self)
        self.timer_modo_teclado.timeout.connect(
            self.enviar_heartbeat_teclado
        )
        self.timer_modo_teclado.start(1000)

        self.cargar_puertos()

    def dibujar_caja(self):
        self.scene.setSceneRect(0, 0, 500, 500)
        self.scene.setBackgroundBrush(QBrush(QColor(16, 25, 35)))

        self.caja = QGraphicsRectItem(35, 35, 430, 430)
        madera = QLinearGradient(35, 35, 465, 465)
        madera.setColorAt(0, QColor(114, 74, 49))
        madera.setColorAt(0.5, QColor(75, 48, 37))
        madera.setColorAt(1, QColor(46, 39, 37))
        self.caja.setBrush(QBrush(madera))
        self.caja.setPen(QPen(QColor(190, 143, 93), 2))
        self.scene.addItem(self.caja)

        self.interior = QGraphicsRectItem(50, 50, 400, 400)
        interior_gradiente = QLinearGradient(50, 50, 450, 450)
        interior_gradiente.setColorAt(0, QColor(203, 209, 207))
        interior_gradiente.setColorAt(1, QColor(133, 151, 154))
        self.interior.setBrush(QBrush(interior_gradiente))
        self.interior.setPen(QPen(QColor(202, 219, 224), 2))
        self.scene.addItem(self.interior)

        resplandor = QRadialGradient(QPointF(250, 250), 240)
        resplandor.setColorAt(0, QColor(255, 255, 255, 0))
        resplandor.setColorAt(1, QColor(4, 12, 20, 105))
        sombra_interior = QGraphicsRectItem(57, 57, 386, 386)
        sombra_interior.setBrush(QBrush(resplandor))
        sombra_interior.setPen(QPen(Qt.NoPen))
        self.scene.addItem(sombra_interior)

        self.resplandor_ambiente = QGraphicsEllipseItem(95, 95, 310, 310)
        self.resplandor_ambiente.setPen(QPen(Qt.NoPen))
        self.resplandor_ambiente.setZValue(1)
        self.scene.addItem(self.resplandor_ambiente)
        self.actualizar_resplandor()

        for x, y in ((43, 43), (449, 43), (43, 449), (449, 449)):
            tornillo = QGraphicsEllipseItem(x, y, 8, 8)
            tornillo.setBrush(QBrush(QColor(218, 186, 143)))
            tornillo.setPen(QPen(QColor(48, 38, 34), 1))
            self.scene.addItem(tornillo)

        etiqueta = QGraphicsTextItem("THERMAL CHAMBER  /  LIVE")
        etiqueta.setDefaultTextColor(QColor(221, 235, 239))
        etiqueta.setPos(135, 14)
        etiqueta.setZValue(10)
        self.scene.addItem(etiqueta)

    def actualizar_resplandor(self):
        if self.temperatura_actual is None:
            color = QColor(99, 180, 194, 28)
        elif self.temperatura_actual < 25.0:
            color = QColor(46, 151, 255, 92)
        elif self.temperatura_actual < 30.0:
            color = QColor(100, 205, 190, 42)
        else:
            color = QColor(255, 83, 49, 105)

        gradiente = QRadialGradient(QPointF(250, 250), 185)
        gradiente.setColorAt(0, color)
        gradiente.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        self.resplandor_ambiente.setBrush(QBrush(gradiente))

    def crear_icono_gota(self):
        pixmap = QPixmap(20, 26)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.moveTo(10, 1)
        path.cubicTo(7, 6, 2, 12, 2, 17)
        path.cubicTo(2, 22, 5, 25, 10, 25)
        path.cubicTo(15, 25, 18, 22, 18, 17)
        path.cubicTo(18, 12, 13, 6, 10, 1)
        path.closeSubpath()
        painter.setPen(QPen(QColor(31, 132, 169), 1))
        painter.setBrush(QBrush(QColor(65, 174, 207)))
        painter.drawPath(path)
        painter.end()
        return pixmap

    def interpolar_color(self, inicio, fin, proporcion):
        proporcion = max(0.0, min(1.0, proporcion))
        return QColor(
            round(inicio.red() + (fin.red() - inicio.red()) * proporcion),
            round(inicio.green() + (fin.green() - inicio.green()) * proporcion),
            round(inicio.blue() + (fin.blue() - inicio.blue()) * proporcion),
        )

    def actualizar_ambiente(self):
        if self.temperatura_actual is not None:
            if self.temperatura_actual < 25.0:
                self.color_ambiente_objetivo = QColor(143, 202, 229)
            elif self.temperatura_actual < 30.0:
                self.color_ambiente_objetivo = QColor(203, 209, 207)
            else:
                self.color_ambiente_objetivo = QColor(239, 151, 143)

        self.color_ambiente = self.interpolar_color(
            self.color_ambiente, self.color_ambiente_objetivo, 0.08
        )
        gradiente = QLinearGradient(0, 0, 386, 386)
        gradiente.setColorAt(0, self.color_ambiente.lighter(112))
        gradiente.setColorAt(1, self.color_ambiente.darker(106))
        self.interior.setBrush(QBrush(gradiente))
        self.actualizar_resplandor()

    def color_aire_entrada(self):
        if self.temperatura_actual is None:
            return QColor(145, 153, 151)
        if self.temperatura_actual < 25.0:
            return QColor(57, 157, 218)
        if self.temperatura_actual < 30.0:
            return QColor(145, 153, 151)
        return QColor(224, 65, 55)

    def dibujar_componentes(self):
        # Foco y halo (arriba)
        self.halo_foco = QGraphicsEllipseItem(188, 58, 84, 84)
        self.halo_foco.setPen(QPen(Qt.NoPen))
        self.halo_foco.setBrush(QBrush(QColor(255, 194, 62, 0)))
        self.halo_foco.setZValue(1)
        self.scene.addItem(self.halo_foco)

        self.foco = QGraphicsEllipseItem(200, 70, 60, 60)
        self.foco.setBrush(QBrush(QColor(50, 61, 69)))
        self.foco.setPen(QPen(QColor(194, 210, 216), 2))
        self.foco.setZValue(3)
        self.scene.addItem(self.foco)
        self.lbl_foco = QGraphicsTextItem("Foco")
        self.lbl_foco.setDefaultTextColor(QColor(234, 241, 243))
        self.lbl_foco.setPos(210, 140)
        self.lbl_foco.setZValue(3)
        self.scene.addItem(self.lbl_foco)

        # Celda Peltier (abajo)
        self.halo_peltier = QGraphicsEllipseItem(165, 365, 130, 70)
        self.halo_peltier.setPen(QPen(Qt.NoPen))
        self.halo_peltier.setBrush(QBrush(QColor(42, 179, 255, 0)))
        self.halo_peltier.setZValue(1)
        self.scene.addItem(self.halo_peltier)

        self.peltier = QGraphicsRectItem(180, 380, 100, 40)
        self.peltier.setBrush(QBrush(QColor(50, 61, 69)))
        self.peltier.setPen(QPen(QColor(194, 210, 216), 2))
        self.peltier.setZValue(3)
        self.scene.addItem(self.peltier)
        for x in range(190, 278, 12):
            linea = QGraphicsLineItem(x, 385, x, 415)
            linea.setPen(QPen(QColor(128, 155, 164), 1))
            linea.setZValue(4)
            self.scene.addItem(linea)
        self.lbl_peltier = QGraphicsTextItem("Peltier")
        self.lbl_peltier.setDefaultTextColor(QColor(234, 241, 243))
        self.lbl_peltier.setPos(190, 430)
        self.lbl_peltier.setZValue(3)
        self.scene.addItem(self.lbl_peltier)

        # Ventiladores (Izquierda y Derecha)
        self.fan1 = self.crear_ventilador(80, 200)
        self.fan2 = self.crear_ventilador(380, 200)
        self.puerta_izquierda = self.crear_puerta(82, 202, False)
        self.puerta_derecha = self.crear_puerta(382, 202, True)
        self.crear_particulas()

    def crear_ventilador(self, x, y):
        carcasa = QGraphicsRectItem(x, y, 60, 60)
        carcasa.setBrush(QBrush(QColor(35, 52, 62)))
        carcasa.setPen(QPen(QColor(177, 207, 214), 2))
        self.scene.addItem(carcasa)

        aro = QGraphicsEllipseItem(x + 6, y + 6, 48, 48)
        aro.setBrush(QBrush(QColor(83, 111, 119)))
        aro.setPen(QPen(QColor(187, 221, 226), 1))
        self.scene.addItem(aro)

        rotor = QGraphicsItemGroup()
        formas = (
            ((30, 30), (25, 27), (23, 13), (26, 7), (32, 10), (35, 25)),
            ((30, 30), (31, 35), (22, 48), (16, 51), (12, 47), (24, 32)),
            ((30, 30), (35, 29), (49, 35), (52, 40), (47, 45), (32, 35)),
        )
        for forma in formas:
            pala = QGraphicsPolygonItem(
                QPolygonF([QPointF(px, py) for px, py in forma])
            )
            pala.setBrush(QBrush(QColor(34, 64, 72)))
            pala.setPen(QPen(QColor(155, 203, 209), 1))
            rotor.addToGroup(pala)

        rotor.setPos(x, y)
        rotor.setTransformOriginPoint(30, 30)
        self.scene.addItem(rotor)

        centro = QGraphicsEllipseItem(x + 24, y + 24, 12, 12)
        centro.setBrush(QBrush(QColor(78, 207, 214)))
        centro.setPen(QPen(QColor(222, 245, 242), 1))
        self.scene.addItem(centro)
        return rotor

    def crear_puerta(self, x, y, bisagra_derecha):
        puerta = QGraphicsItemGroup()
        hoja = QGraphicsRectItem(0, 0, 56, 56)
        hoja.setBrush(QBrush(QColor(115, 130, 128)))
        hoja.setPen(QPen(QColor(49, 66, 65), 2))
        puerta.addToGroup(hoja)

        manija = QGraphicsRectItem(8 if bisagra_derecha else 44, 24, 5, 8)
        manija.setBrush(QBrush(QColor(231, 183, 96)))
        manija.setPen(QPen(Qt.NoPen))
        puerta.addToGroup(manija)
        puerta.setPos(x, y)
        puerta.setTransformOriginPoint(56 if bisagra_derecha else 0, 28)
        puerta.setZValue(5)
        puerta.setOpacity(0.48)
        self.scene.addItem(puerta)
        return puerta

    def crear_particulas(self):
        self.particulas = []
        for indice in range(12):
            radio = 4 + indice % 3
            calor = QGraphicsEllipseItem(-radio, -radio, radio * 2, radio * 2)
            calor.setPen(QPen(Qt.NoPen))
            calor.setZValue(2)
            calor.setVisible(False)
            self.scene.addItem(calor)

            copo = QGraphicsItemGroup()
            for angulo in range(0, 180, 60):
                radianes = math.radians(angulo)
                dx = math.cos(radianes) * radio * 1.5
                dy = math.sin(radianes) * radio * 1.5
                rayo = QGraphicsLineItem(-dx, -dy, dx, dy)
                rayo.setPen(QPen(QColor(220, 247, 255), 1.5))
                copo.addToGroup(rayo)
            copo.setZValue(2)
            copo.setVisible(False)
            self.scene.addItem(copo)

            self.particulas.append({
                "calor": calor,
                "copo": copo,
                "x": 145 + (indice % 6) * 48,
                "y": 150 + (indice * 47) % 205,
                "fase": indice * 0.8,
                "velocidad": 1.2 + (indice % 3) * 0.3,
            })

    def animar_ventiladores(self):
        if self.ventiladores_activos:
            self.angulo_fan = (self.angulo_fan + 18) % 360
            self.fan1.setRotation(self.angulo_fan)
            self.fan2.setRotation(self.angulo_fan)

        for puerta, angulo_objetivo in (
            (self.puerta_izquierda, -88 if self.puertas_abiertas else 0),
            (self.puerta_derecha, 88 if self.puertas_abiertas else 0),
        ):
            diferencia = angulo_objetivo - puerta.rotation()
            if abs(diferencia) <= 6:
                puerta.setRotation(angulo_objetivo)
            else:
                puerta.setRotation(puerta.rotation() + (6 if diferencia > 0 else -6))

        self.fase_particulas += 1
        self.actualizar_ambiente()

        if self.modo_termico == "CALENTANDO":
            direccion = -1
        elif self.modo_termico == "ENFRIANDO":
            direccion = 1
        elif self.modo_termico != "PURGA":
            for particula in self.particulas:
                particula["calor"].setVisible(False)
                particula["copo"].setVisible(False)
            return

        if self.modo_termico == "PURGA" and not self.ventiladores_activos:
            for particula in self.particulas:
                particula["calor"].setVisible(False)
                particula["copo"].setVisible(False)
            return

        for particula in self.particulas:
            calor = particula["calor"]
            copo = particula["copo"]
            if self.modo_termico == "PURGA":
                calor.setVisible(True)
                copo.setVisible(False)
                particula["x"] += particula["velocidad"] * 2.4
                if particula["x"] > 462:
                    particula["x"] = 145
                particula["y"] = 170 + (particula["fase"] * 29) % 205
                progreso = (particula["x"] - 145) / (462 - 145)
                color_flujo = self.interpolar_color(
                    self.color_aire_entrada(), QColor(145, 153, 151), progreso
                )
                calor.setBrush(QBrush(color_flujo))
            else:
                es_calor = self.modo_termico == "CALENTANDO"
                calor.setVisible(es_calor)
                copo.setVisible(not es_calor)
                particula["y"] += direccion * particula["velocidad"]
                if direccion < 0 and particula["y"] < 150:
                    particula["y"] = 360
                elif direccion > 0 and particula["y"] > 360:
                    particula["y"] = 150

                if es_calor:
                    gradiente = QRadialGradient(QPointF(0, 0), 10)
                    gradiente.setColorAt(0, QColor(255, 246, 151, 245))
                    gradiente.setColorAt(0.45, QColor(255, 67, 39, 220))
                    gradiente.setColorAt(1, QColor(190, 0, 0, 0))
                    calor.setBrush(QBrush(gradiente))

            desplazamiento = math.sin(
                self.fase_particulas * 0.08 + particula["fase"]
            ) * 8
            posicion = QPointF(particula["x"] + desplazamiento, particula["y"])
            calor.setPos(posicion)
            copo.setPos(posicion)

    def cargar_puertos(self):
        puerto_actual = self.combo_puertos.currentData()
        self.combo_puertos.clear()
        puertos = sorted(list_ports.comports(), key=lambda puerto: puerto.device)

        for puerto in puertos:
            self.combo_puertos.addItem(
                f"{puerto.device} - {puerto.description}", puerto.device
            )

        if puerto_actual:
            indice = self.combo_puertos.findData(puerto_actual)
            if indice >= 0:
                self.combo_puertos.setCurrentIndex(indice)
        else:
            for indice, puerto in enumerate(puertos):
                descripcion = f"{puerto.description} {puerto.manufacturer or ''}".lower()
                if any(nombre in descripcion for nombre in ("cp210", "ch340", "usb", "uart")):
                    self.combo_puertos.setCurrentIndex(indice)
                    break

        if not puertos:
            self.lbl_estado.setText("Estado: No se detectaron puertos seriales")

    def conectar_serial(self):
        if self.arduino and self.arduino.is_open:
            if self.ciclo_soportado and not self.enviar_comando_detener():
                return
            if self.prueba_dimmer_activa and not self.ciclo_soportado:
                if not self.enviar_comando_detener():
                    return
            self.cancelar_cuenta_regresiva_purga()
            if self.prueba_conexion_activa:
                self.enviar_modo_prueba(False)
            self.enviar_modo_teclado_interfaz(False)
            self.arduino.close()
            self.arduino = None
            self.sensor_valido = False
            self.purga_soportada = False
            self.ciclo_soportado = False
            self.ciclo_activo = False
            self.prueba_dimmer_activa = False
            self.control_pid_activo = False
            self.edicion_teclado_activa = False
            self.modo_teclado_matriz = "A"
            self.actualizar_estado_modo_teclado()
            self.boton_prueba_dimmer.setText("Probar servo dimmer (GPIO 21)")
            self.boton_conexion.setText("Conectar")
            self.combo_puertos.setEnabled(True)
            self.boton_prueba_conexion.setEnabled(False)
            self.boton_purga.setEnabled(False)
            self.actualizar_botones_ciclo()
            self.actualizar_boton_prueba_dimmer()
            self.lbl_estado.setText("Estado: Desconectado")
            self.potencia_foco = None
            self.angulo_servo_dimmer = None
            self.dimmer_soportado = False
            self.lbl_dimmer.setText("Foco/dimmer: sin conexión")
            return

        puerto = self.combo_puertos.currentData()
        if not puerto:
            self.lbl_estado.setText("Estado: Selecciona el puerto del ESP32")
            return

        try:
            self.arduino = serial.Serial(
                puerto, 115200, timeout=0, write_timeout=0.2
            )
            self.arduino.reset_input_buffer()
            self.buffer_serial.clear()
            self.boton_conexion.setText("Desconectar")
            self.combo_puertos.setEnabled(False)
            self.boton_prueba_conexion.setEnabled(True)
            self.boton_purga.setEnabled(False)
            self.lbl_estado.setText(f"Estado: Conectado a {puerto}; esperando datos")
            self.potencia_foco = None
            self.angulo_servo_dimmer = None
            self.dimmer_soportado = False
            self.lbl_dimmer.setText("Foco/dimmer: esperando firmware")
            self.purga_soportada = False
            self.ciclo_soportado = False
            self.ciclo_activo = False
            self.prueba_dimmer_activa = False
            self.control_pid_activo = False
            self.edicion_teclado_activa = False
            self.modo_teclado_matriz = "A"
            self.actualizar_estado_modo_teclado()
            self.boton_prueba_dimmer.setText("Probar servo dimmer (GPIO 21)")
            self.actualizar_botones_ciclo()
            self.actualizar_boton_prueba_dimmer()
            self.enviar_modo_teclado_interfaz(True)
        except (serial.SerialException, OSError) as error:
            self.arduino = None
            self.lbl_estado.setText(f"Estado: No se pudo abrir {puerto}: {error}")

    def leer_serial(self):
        if self.arduino and self.arduino.is_open:
            try:
                cantidad = self.arduino.in_waiting
                if cantidad:
                    self.buffer_serial.extend(self.arduino.read(cantidad))

                while b"\n" in self.buffer_serial:
                    linea, _, resto = self.buffer_serial.partition(b"\n")
                    self.buffer_serial = bytearray(resto)
                    linea = linea.decode("utf-8", errors="replace").strip()
                    if linea.startswith("TEMP_CURRENT:"):
                        try:
                            temperatura = float(linea.split(":", 1)[1])
                        except ValueError:
                            continue
                        if math.isfinite(temperatura) and 0.0 <= temperatura <= 50.0:
                            self.temperatura_actual = temperatura
                            self.lbl_temp_actual.setText(
                                f"{temperatura:.0f} °C"
                            )
                            self.buffer_temp.append(temperatura)
                            self.tiempo_actual += 1
                            self.buffer_time.append(self.tiempo_actual)
                            self.actualizar_grafica()
                    else:
                        self.procesar_linea(linea)
            except (serial.SerialException, OSError) as error:
                self.lbl_estado.setText(f"Estado: Error de comunicación: {error}")
                self.potencia_foco = None
                self.angulo_servo_dimmer = None
                self.dimmer_soportado = False
                self.lbl_dimmer.setText("Foco/dimmer: sin conexión")
                self.cancelar_cuenta_regresiva_purga()
                self.arduino.close()
                self.arduino = None
                self.sensor_valido = False
                self.purga_soportada = False
                self.ciclo_soportado = False
                self.ciclo_activo = False
                self.prueba_dimmer_activa = False
                self.control_pid_activo = False
                self.edicion_teclado_activa = False
                self.modo_teclado_matriz = "A"
                self.actualizar_estado_modo_teclado()
                self.boton_prueba_dimmer.setText("Probar servo dimmer (GPIO 21)")
                self.boton_conexion.setText("Conectar")
                self.combo_puertos.setEnabled(True)
                self.boton_prueba_conexion.setEnabled(False)
                self.boton_purga.setEnabled(False)
                self.actualizar_botones_ciclo()
                self.prueba_conexion_activa = False
                self.actualizar_boton_prueba()
                self.actualizar_boton_prueba_dimmer()
        self.actualizar_botones_teclado()

    def actualizar_grafica(self):
        self.linea_temp.setData(
            x=list(self.buffer_time), y=list(self.buffer_temp)
        )
        self.linea_setpoint.setData(
            x=list(self.buffer_time),
            y=[self.spin_temp_objetivo.value()] * len(self.buffer_time),
        )

    def aplicar_tuning_pid(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para aplicar el PID")
            return
        try:
            self.arduino.write(
                f"PID_TUNE,{self.spin_kp.value()},{self.spin_ki.value()},"
                f"{self.spin_kd.value()}\n".encode("utf-8")
            )
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo enviar el tuning PID: {error}"
            )

    def mantener_temperatura_pid(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText(
                "Estado: Conecta el ESP32 para mantener la temperatura"
            )
            return
        if not self.sensor_valido:
            self.lbl_estado.setText(
                "Estado: Esperando una lectura válida del DHT11"
            )
            return
        if (
            self.ciclo_activo
            or self.prueba_conexion_activa
            or self.prueba_dimmer_activa
            or self.modo_termico in ("PURGA", "ERROR")
        ):
            self.lbl_estado.setText(
                "Estado: Detén el ciclo o la prueba activa antes de iniciar el PID"
            )
            return
        try:
            self.arduino.write(
                f"TEMP_TARGET:{self.spin_temp_objetivo.value()}\n".encode("utf-8")
            )
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo enviar la temperatura objetivo: {error}"
            )

    def actualizar_botones_teclado(self):
        conectado = self.arduino is not None and self.arduino.is_open
        for tecla, boton in self.teclas_virtuales.items():
            boton.setEnabled(conectado if tecla in ("C", "D") else True)

    def actualizar_rango_interfaz(self, temp_minima, temp_maxima):
        if (
            not math.isfinite(temp_minima)
            or not math.isfinite(temp_maxima)
            or temp_minima < 20.0
            or temp_maxima > 50.0
            or temp_minima + 2.0 > temp_maxima
        ):
            return

        self.lbl_rango_actual.setText(
            f"Rango: {temp_minima:.1f} °C - {temp_maxima:.1f} °C"
        )
        for control, valor in (
            (self.spin_temp_minima, temp_minima),
            (self.spin_temp_maxima, temp_maxima),
        ):
            anterior = control.blockSignals(True)
            control.setValue(valor)
            control.blockSignals(anterior)

    def actualizar_estado_dimmer(self, partes):
        self.potencia_foco = None
        self.angulo_servo_dimmer = None
        self.dimmer_soportado = len(partes) == 13
        if len(partes) != 13:
            self.lbl_dimmer.setText(
                "Foco/dimmer: sin telemetría (firmware anterior)"
            )
            return

        try:
            potencia_foco = float(partes[11])
            angulo_dimmer = int(partes[12])
        except ValueError:
            self.lbl_dimmer.setText("Foco/dimmer: telemetría inválida")
            return

        if (
            not math.isfinite(potencia_foco)
            or not 0.0 <= potencia_foco <= 100.0
            or not 0 <= angulo_dimmer <= 180
        ):
            self.lbl_dimmer.setText(
                "Foco/dimmer: telemetría fuera de rango"
            )
            return

        self.potencia_foco = potencia_foco
        self.angulo_servo_dimmer = angulo_dimmer
        self.lbl_dimmer.setText(
            f"Potencia solicitada al dimmer: {potencia_foco:.0f}% · "
            f"Servo comandado: {angulo_dimmer}°"
        )

    def procesar_linea(self, linea):
        partes = linea.split(",")
        if partes == ["ACK", "KEYPAD_UI", "ON"]:
            self.lbl_estado_teclado.setText(
                "Matriz conectada: Modo A listo"
            )
            return
        if (
            len(partes) == 2
            and partes[0] == "KEYPAD_KEY"
            and len(partes[1]) == 1
            and partes[1] in "0123456789ABCD*#"
        ):
            self.procesar_tecla_interfaz(partes[1])
            return

        if len(partes) >= 3 and partes[:2] == ["INFO", "KEYPAD"]:
            if partes[2] == "EDIT" and len(partes) == 5:
                self.edicion_teclado_activa = True
                etiqueta = (
                    "mínima" if partes[3] == "MIN" else "máxima"
                )
                valor = partes[4] or "--"
                self.lbl_estado_teclado.setText(
                    f"Editando temperatura {etiqueta}: {valor} °C; "
                    "# para aceptar"
                )
            elif partes[2] == "CANCELLED":
                self.edicion_teclado_activa = False
                self.lbl_estado_teclado.setText("Teclado: edición cancelada")
            elif partes[2] == "SAVED":
                self.edicion_teclado_activa = False
                etiqueta = (
                    "mínima" if len(partes) > 3 and partes[3] == "MIN"
                    else "máxima"
                )
                self.lbl_estado_teclado.setText(
                    f"Temperatura {etiqueta} guardada"
                )
            self.actualizar_botones_teclado()
            return
        if len(partes) >= 3 and partes[0] == "ERR" and partes[1] == "KEYPAD":
            errores_teclado = {
                "BUSY": "No se puede editar durante el ciclo, purga o prueba",
                "ENTRY_FULL": "Máximo dos enteros y un decimal",
                "FINISH_ENTRY": "Confirma o cancela el valor antes de iniciar",
                "FORMAT": "Entrada decimal no válida",
            }
            self.lbl_estado_teclado.setText(
                errores_teclado.get(partes[2], f"Error de teclado: {partes[2]}")
            )
            return
        if len(partes) >= 3 and partes[:2] == ["ERR", "SETRANGE"]:
            self.lbl_estado_teclado.setText(
                "Rango inválido: debe estar entre 20 y 50 °C "
                "y separado al menos 2 °C"
            )
            return
        if partes[:2] == ["ACK", "PID_TUNE"]:
            self.lbl_estado.setText("Estado: Parámetros PID aplicados")
            return
        if len(partes) >= 3 and partes[:2] == ["ERR", "PID_TUNE"]:
            self.lbl_estado.setText(
                f"Estado: No se pudo aplicar el PID ({partes[2]})"
            )
            return
        if len(partes) == 3 and partes[:2] == ["ACK", "TEMP_TARGET"]:
            try:
                setpoint = float(partes[2])
            except ValueError:
                return
            if math.isfinite(setpoint):
                self.control_pid_activo = True
                self.lbl_estado.setText(
                    f"Estado: Control PID activo a {setpoint:.1f} °C"
                )
                self.actualizar_boton_prueba()
                self.actualizar_boton_prueba_dimmer()
            return
        if len(partes) >= 3 and partes[:2] == ["ERR", "TEMP_TARGET"]:
            if partes[2] == "SENSOR":
                self.lbl_estado.setText(
                    "Estado: Esperando una lectura válida del DHT11"
                )
                return
            if partes[2] == "BUSY":
                self.lbl_estado.setText(
                    "Estado: Detén el ciclo o la prueba activa antes de iniciar el PID"
                )
                return
            self.lbl_estado.setText(
                f"Estado: No se pudo iniciar el PID ({partes[2]})"
            )
            return
        if len(partes) >= 3 and partes[0] == "WARN" and partes[1] == "DEWPOINT":
            if partes[2] == "RISK" and len(partes) == 5:
                try:
                    punto_rocio = float(partes[3])
                    temp_minima = float(partes[4])
                except ValueError:
                    return
                if math.isfinite(punto_rocio) and math.isfinite(temp_minima):
                    self.mostrar_alerta_purga(punto_rocio, temp_minima)
            return
        if len(partes) == 4 and partes[:2] == ["ACK", "SETRANGE"]:
            try:
                temp_minima = float(partes[2])
                temp_maxima = float(partes[3])
            except ValueError:
                return
            self.edicion_teclado_activa = False
            self.actualizar_rango_interfaz(temp_minima, temp_maxima)
            self.actualizar_botones_teclado()
            return
        if len(partes) >= 3 and partes[0] == "ACK" and partes[1] == "PURGE":
            self.lbl_estado.setText("Estado: Purga de aire iniciada")
            if self.lbl_cuenta_purga is not None:
                self.lbl_cuenta_purga.setText(
                    "Purga iniciada; extracción durante 20 segundos."
                )
            if self.boton_iniciar_purga is not None:
                self.boton_iniciar_purga.setEnabled(False)
            return
        if len(partes) >= 3 and partes[0] == "ERR" and partes[1] == "PURGE":
            self.lbl_estado.setText(
                f"Estado: No se pudo iniciar la purga ({partes[2]})"
            )
            if self.boton_iniciar_purga is not None:
                self.boton_iniciar_purga.setEnabled(True)
            return

        if len(partes) == 3 and partes[:2] == ["ACK", "DIMMER_TEST"]:
            self.prueba_dimmer_activa = partes[2] == "STARTED"
            self.boton_prueba_dimmer.setText(
                "Probando servo dimmer…" if self.prueba_dimmer_activa
                else "Probar servo dimmer (GPIO 21)"
            )
            self.actualizar_boton_prueba()
            self.actualizar_botones_ciclo()
            self.actualizar_boton_prueba_dimmer()
            self.lbl_estado.setText(
                "Prueba: dimmer a 50%; regresando a 0° al terminar"
                if self.prueba_dimmer_activa else
                "Prueba del dimmer terminada; servo en 0°"
            )
            return
        if len(partes) >= 3 and partes[:2] == ["ERR", "DIMMER_TEST"]:
            self.prueba_dimmer_activa = False
            self.boton_prueba_dimmer.setText("Probar servo dimmer (GPIO 21)")
            self.actualizar_boton_prueba_dimmer()
            motivos = {
                "SENSOR": "No se puede probar sin lectura válida del DHT11",
                "BUSY": "Detén el ciclo/prueba y apaga la Peltier antes",
            }
            self.lbl_estado.setText(
                motivos.get(
                    partes[2], f"No se pudo probar el dimmer ({partes[2]})"
                )
            )
            return

        if len(partes) >= 3 and partes[0] == "ACK" and partes[1] == "CYCLE":
            self.ciclo_activo = True
            self.control_pid_activo = False
            self.actualizar_boton_prueba()
            self.actualizar_botones_ciclo()
            self.actualizar_boton_prueba_dimmer()
            self.lbl_estado.setText("Estado: Ciclo térmico iniciado")
            return
        if len(partes) >= 3 and partes[0] == "ERR" and partes[1] == "CYCLE":
            self.lbl_estado.setText(
                f"Estado: No se pudo iniciar el ciclo ({partes[2]})"
            )
            return
        if len(partes) >= 3 and partes[0] == "ERR" and partes[1] == "TEST":
            self.lbl_estado.setText(
                f"Estado: No se pudo iniciar la prueba ({partes[2]})"
            )
            return
        if len(partes) == 3 and partes[:2] == ["ACK", "TEST"]:
            self.prueba_conexion_activa = partes[2] == "ON"
            self.actualizar_boton_prueba()
            self.lbl_estado.setText(
                "Estado: Prueba de conexión activa"
                if self.prueba_conexion_activa else
                "Estado: Prueba de conexión detenida"
            )
            return
        if len(partes) >= 2 and partes[0] == "ACK" and partes[1] == "STOP":
            self.ciclo_activo = False
            self.control_pid_activo = False
            self.prueba_dimmer_activa = False
            self.boton_prueba_dimmer.setText("Probar servo dimmer (GPIO 21)")
            self.edicion_teclado_activa = False
            self.lbl_estado_teclado.setText("Teclado: control detenido")
            self.actualizar_boton_prueba()
            self.actualizar_botones_ciclo()
            self.actualizar_boton_prueba_dimmer()
            self.lbl_estado.setText("Estado: Ciclo detenido; salidas apagadas")
            return

        if len(partes) >= 2 and partes[0] == "STATUS" and partes[1] == "ERROR":
            sensor_venia_valido = self.sensor_valido
            self.cancelar_cuenta_regresiva_purga()
            self.sensor_valido = False
            self.prueba_dimmer_activa = False
            self.control_pid_activo = False
            self.boton_prueba_dimmer.setText("Probar servo dimmer (GPIO 21)")
            self.temperatura_actual = None
            self.potencia_foco = None
            self.angulo_servo_dimmer = None
            self.dimmer_soportado = len(partes) == 13
            self.lbl_temp_actual.setText("--.- °C")
            self.lbl_humedad.setText("Humedad: --%")
            self.lbl_dimmer.setText("Foco: 0% · dimmer en retorno al mínimo")
            if sensor_venia_valido:
                self.buffer_temp.append(float("nan"))
                self.tiempo_actual += 1
                self.buffer_time.append(self.tiempo_actual)
                self.actualizar_grafica()
            self.purga_soportada = len(partes) in (10, 11, 13)
            self.ciclo_soportado = len(partes) in (11, 13)
            self.ciclo_activo = (
                len(partes) in (11, 13) and partes[10] == "1"
            )
            if len(partes) in (10, 11, 13):
                try:
                    temp_minima = float(partes[8])
                    temp_maxima = float(partes[9])
                except ValueError:
                    pass
                else:
                    self.actualizar_rango_interfaz(temp_minima, temp_maxima)
            else:
                self.lbl_rango_actual.setText(
                    "Rango: no disponible (firmware anterior)"
                )
            self.prueba_conexion_activa = (
                len(partes) >= 7 and partes[6] == "TESTING"
            )
            self.actualizar_estado_dimmer(partes)
            self.ventiladores_activos = (
                len(partes) >= 5 and partes[4] == "1"
            )
            self.puertas_abiertas = (
                len(partes) >= 6 and partes[5] == "1"
            )
            self.modo_termico = (
                "PRUEBA" if self.prueba_conexion_activa else "ERROR"
            )
            self.boton_purga.setEnabled(False)
            self.lbl_estado.setText(
                "Estado: Prueba activa; lectura DHT11 inválida"
                if self.prueba_conexion_activa else
                "Estado: Error de lectura DHT11; salidas apagadas"
            )
            self.actualizar_boton_prueba()
            self.actualizar_botones_ciclo()
            self.actualizar_boton_prueba_dimmer()
            return

        if not partes or partes[0] != "STATUS" or len(partes) not in (
            4, 9, 10, 11, 13
        ):
            return

        try:
            temp = float(partes[1])
            if not math.isfinite(temp) or not 0.0 <= temp <= 50.0:
                self.procesar_linea("STATUS,ERROR")
                return
            foco_on = partes[2] == "1"
            peltier_on = partes[3] == "1"
            if len(partes) in (9, 10, 11, 13):
                self.ventiladores_activos = partes[4] == "1"
                self.puertas_abiertas = partes[5] == "1"
                fase = partes[6]
                humedad = float(partes[7])
                if not math.isfinite(humedad) or not 0.0 <= humedad <= 100.0:
                    humedad = None
                self.prueba_conexion_activa = fase == "TESTING"
                if len(partes) in (10, 11, 13):
                    temp_minima = float(partes[8])
                    temp_maxima = float(partes[9])
                    if not math.isfinite(temp_minima) or not math.isfinite(
                        temp_maxima
                    ) or temp_minima >= temp_maxima:
                        return
                else:
                    temp_minima = None
                    temp_maxima = None
            else:
                self.ventiladores_activos = False
                self.puertas_abiertas = False
                fase = "HEATING" if foco_on else "COOLING" if peltier_on else "HOLD"
                humedad = None
                temp_minima = None
                temp_maxima = None
                self.prueba_conexion_activa = False
        except ValueError:
            return
        self.sensor_valido = True
        self.purga_soportada = len(partes) in (10, 11, 13)
        self.ciclo_soportado = len(partes) in (11, 13)
        self.ciclo_activo = (
            len(partes) in (11, 13) and partes[10] == "1"
        )
        self.prueba_dimmer_activa = fase == "DIMMER_TEST"
        self.control_pid_activo = (
            not self.ciclo_activo
            and fase in ("HEATING", "COOLING", "HOLD")
        )
        self.boton_prueba_dimmer.setText(
            "Probando servo dimmer…" if self.prueba_dimmer_activa
            else "Probar servo dimmer (GPIO 21)"
        )
        if temp_minima is None or temp_maxima is None:
            self.lbl_rango_actual.setText(
                "Rango: no disponible (firmware anterior)"
            )
        else:
            self.actualizar_rango_interfaz(temp_minima, temp_maxima)

        self.lbl_temp_actual.setText(
            f"{temp:.0f} °C"
        )
        self.temperatura_actual = temp
        self.lbl_humedad.setText(
            "Humedad: --%" if humedad is None
            else f"Humedad: {humedad:.0f}%"
        )
        self.actualizar_estado_dimmer(partes)
        estados = {
            "HEATING": ("CALENTANDO", "Calentando"),
            "COOLING": ("ENFRIANDO", "Enfriando"),
            "HOLD": ("MANTENIENDO", "Manteniendo"),
            "CYCLE_HEATING_MIN": ("CALENTANDO", "Ciclo: calentando hasta la mínima"),
            "CYCLE_HEATING_MAX": ("CALENTANDO", "Ciclo: calentando hasta la máxima"),
            "CYCLE_COOLING_MIN": ("ENFRIANDO", "Ciclo: enfriando hasta la mínima"),
            "CYCLE_COOLING_MAX": ("ENFRIANDO", "Ciclo: enfriando hasta la máxima"),
            "STOPPED": ("MANTENIENDO", "Ciclo detenido; salidas apagadas"),
            "PURGE_OPENING": ("PURGA", "Abriendo tapas"),
            "PURGE_RUNNING": ("PURGA", "Extrayendo aire"),
            "PURGE_CLOSING": ("PURGA", "Cerrando tapas"),
            "TESTING": ("PRUEBA", "Prueba: compuertas abiertas y ventiladores activos"),
            "DIMMER_TEST": ("PRUEBA_DIMER", "Prueba del dimmer: servo a 50°"),
            "SENSOR_ERROR": ("ERROR", "Error del sensor"),
        }
        self.modo_termico, texto_estado = estados.get(
            fase,
            ("CALENTANDO", "Calentando") if foco_on else
            ("ENFRIANDO", "Enfriando") if peltier_on else
            ("MANTENIENDO", "Manteniendo"),
        )
        if fase.startswith("PURGE_"):
            self.modo_termico = "PURGA"
        elif fase == "SENSOR_ERROR":
            self.modo_termico = "ERROR"
        self.lbl_estado.setText(f"Estado: {texto_estado}")
        self.actualizar_boton_prueba()
        self.actualizar_botones_ciclo()
        self.actualizar_boton_prueba_dimmer()
        self.boton_purga.setEnabled(
            self.arduino is not None
            and self.arduino.is_open
            and self.sensor_valido
            and self.purga_soportada
            and not self.prueba_conexion_activa
            and not self.prueba_dimmer_activa
            and not fase.startswith("PURGE_")
        )
        self.foco.setBrush(
            QBrush(QColor(255, 220, 107) if foco_on else QColor(50, 61, 69))
        )
        brillo_foco = QRadialGradient(QPointF(230, 100), 48)
        brillo_foco.setColorAt(
            0, QColor(255, 196, 62, 145 if foco_on else 0)
        )
        brillo_foco.setColorAt(1, QColor(255, 196, 62, 0))
        self.halo_foco.setBrush(QBrush(brillo_foco))

        self.peltier.setBrush(
            QBrush(QColor(62, 190, 255) if peltier_on else QColor(50, 61, 69))
        )
        brillo_peltier = QRadialGradient(QPointF(230, 400), 72)
        brillo_peltier.setColorAt(
            0, QColor(42, 179, 255, 125 if peltier_on else 0)
        )
        brillo_peltier.setColorAt(1, QColor(42, 179, 255, 0))
        self.halo_peltier.setBrush(QBrush(brillo_peltier))

    def actualizar_temperatura_minima(self, valor):
        if valor + 2.0 > self.spin_temp_maxima.value():
            anterior = self.spin_temp_maxima.blockSignals(True)
            self.spin_temp_maxima.setValue(min(valor + 2.0, 50.0))
            self.spin_temp_maxima.blockSignals(anterior)
        self.enviar_rango_temperatura()

    def actualizar_temperatura_maxima(self, valor):
        if valor - 2.0 < self.spin_temp_minima.value():
            anterior = self.spin_temp_minima.blockSignals(True)
            self.spin_temp_minima.setValue(max(valor - 2.0, 20.0))
            self.spin_temp_minima.blockSignals(anterior)
        self.enviar_rango_temperatura()

    def actualizar_botones_ciclo(self):
        conectado = self.arduino is not None and self.arduino.is_open
        self.boton_iniciar_ciclo.setEnabled(
            conectado
            and self.sensor_valido
            and self.ciclo_soportado
            and not self.ciclo_activo
            and not self.prueba_conexion_activa
            and not self.prueba_dimmer_activa
            and not self.control_pid_activo
            and self.modo_termico != "PURGA"
        )
        self.boton_detener_ciclo.setEnabled(conectado and self.ciclo_soportado)
        self.boton_mantener_temp.setEnabled(
            conectado
            and self.sensor_valido
            and not self.prueba_conexion_activa
            and not self.prueba_dimmer_activa
            and not self.ciclo_activo
            and self.modo_termico not in ("PURGA", "ERROR")
        )
        self.spin_temp_minima.setEnabled(not self.ciclo_activo)
        self.spin_temp_maxima.setEnabled(not self.ciclo_activo)

    def solicitar_inicio_ciclo(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para iniciar el ciclo")
            return
        if not self.sensor_valido or not self.ciclo_soportado:
            self.lbl_estado.setText(
                "Estado: Esperando sensor y firmware compatible con ciclos"
            )
            return

        dialogo = QMessageBox(self)
        dialogo.setWindowTitle("Iniciar ciclo térmico")
        dialogo.setText("¿A qué temperatura debe llegar primero?")
        boton_minima = dialogo.addButton(
            "Temperatura mínima", QMessageBox.AcceptRole
        )
        boton_maxima = dialogo.addButton(
            "Temperatura máxima", QMessageBox.AcceptRole
        )
        dialogo.addButton("Cancelar", QMessageBox.RejectRole)
        dialogo.exec_()
        boton_elegido = dialogo.clickedButton()
        if boton_elegido not in (boton_minima, boton_maxima):
            return

        primero = "MIN" if boton_elegido is boton_minima else "MAX"
        temp_minima = self.spin_temp_minima.value()
        temp_maxima = self.spin_temp_maxima.value()
        if self.temperatura_actual is not None:
            if self.temperatura_actual < temp_minima:
                QMessageBox.warning(
                    self,
                    "Temperatura por debajo del rango",
                    f"La caja está a {self.temperatura_actual:.1f} °C, por "
                    f"debajo de la mínima ({temp_minima:.1f} °C). Primero "
                    f"alcanzará la temperatura {'mínima' if primero == 'MIN' else 'máxima'} "
                    "elegida; después alternará entre ambos límites.",
                )
            elif self.temperatura_actual > temp_maxima:
                QMessageBox.warning(
                    self,
                    "Temperatura por encima del rango",
                    f"La caja está a {self.temperatura_actual:.1f} °C, por "
                    f"encima de la máxima ({temp_maxima:.1f} °C). Primero "
                    f"alcanzará la temperatura {'mínima' if primero == 'MIN' else 'máxima'} "
                    "elegida; después alternará entre ambos límites.",
                )

        if not self.enviar_rango_temperatura():
            return
        try:
            self.arduino.write(f"CYCLE,{primero}\n".encode("utf-8"))
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo iniciar el ciclo: {error}"
            )

    def detener_ciclo(self):
        self.enviar_comando_detener()

    def enviar_comando_detener(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para detener el ciclo")
            return False
        try:
            self.arduino.write(b"STOP\n")
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo detener el ciclo: {error}"
            )
            return False
        return True

    def solicitar_purga_manual(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para solicitar la purga")
            return
        self.mostrar_alerta_purga()

    def mostrar_alerta_purga(self, punto_rocio=None, temp_minima=None):
        if self.dialogo_purga is None:
            dialogo = QDialog(self)
            dialogo.setWindowTitle("Recomendación de purga")
            dialogo.setModal(False)
            layout = QVBoxLayout(dialogo)

            mensaje = QLabel("Se recomienda purga del aire")
            mensaje.setWordWrap(True)
            dialogo.lbl_mensaje_purga = mensaje
            layout.addWidget(mensaje)

            detalle = QLabel()
            detalle.setWordWrap(True)
            self.lbl_detalle_purga = detalle
            layout.addWidget(detalle)

            cuenta = QLabel(
                "Al iniciar, la purga comienza de inmediato y la extracción "
                "dura 20 segundos."
            )
            self.lbl_cuenta_purga = cuenta
            layout.addWidget(cuenta)

            botones = QHBoxLayout()
            iniciar = QPushButton("Iniciar purga")
            iniciar.clicked.connect(self.iniciar_purga_manual)
            self.boton_iniciar_purga = iniciar
            botones.addWidget(iniciar)
            cancelar = QPushButton("Cerrar")
            cancelar.clicked.connect(self.cancelar_cuenta_regresiva_purga)
            self.boton_cancelar_purga = cancelar
            botones.addWidget(cancelar)
            layout.addLayout(botones)
            dialogo.finished.connect(self.al_cerrar_dialogo_purga)
            self.dialogo_purga = dialogo

        assert self.dialogo_purga is not None
        assert self.lbl_detalle_purga is not None
        if punto_rocio is None or temp_minima is None:
            self.lbl_detalle_purga.setText(
                "La recomendación es manual; la purga solo inicia al pulsar "
                "“Iniciar purga”."
            )
        else:
            self.lbl_detalle_purga.setText(
                f"Punto de rocío: {punto_rocio:.1f} °C; temperatura mínima "
                f"configurada: {temp_minima:.1f} °C."
            )
        self.dialogo_purga.show()
        self.dialogo_purga.raise_()
        self.dialogo_purga.activateWindow()

    def iniciar_purga_manual(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para solicitar la purga")
            self.cancelar_cuenta_regresiva_purga()
            return

        assert self.boton_iniciar_purga is not None
        assert self.lbl_cuenta_purga is not None
        if self.enviar_comando_purga():
            self.boton_iniciar_purga.setEnabled(False)
            self.lbl_cuenta_purga.setText(
                "Solicitud enviada; la extracción durará 20 segundos."
            )

    def enviar_comando_purga(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para solicitar la purga")
            return False
        try:
            self.arduino.write(b"PURGE\n")
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo solicitar la purga: {error}"
            )
            return False
        return True

    def actualizar_estado_modo_teclado(self):
        if not hasattr(self, "lbl_estado_teclado"):
            return
        if self.modo_teclado_matriz == "A":
            self.lbl_estado_teclado.setText(
                "Matriz: Modo A (mover) · 2/4/6/8 navegar · "
                "1/3 ±0.5 · # seleccionar · B números"
            )
        else:
            self.lbl_estado_teclado.setText(
                "Matriz: Modo B (numérico) · dígitos y * decimal · "
                "# aceptar · A volver a mover"
            )

    def _widget_interactivo_enfocado(self):
        widget = QApplication.focusWidget()
        while widget is not None and widget is not self:
            if isinstance(
                widget, (QDoubleSpinBox, QComboBox, QAbstractButton)
            ):
                if widget not in self.teclas_virtuales.values():
                    return widget
            widget = widget.parentWidget()
        return None

    def _combo_desplegado(self):
        for combo in self.findChildren(QComboBox):
            if combo.view().isVisible():
                return combo
        return None

    def _mover_seleccion_combo(self, combo, tecla):
        fila_actual = combo.view().currentIndex().row()
        cantidad = combo.model().rowCount(combo.rootModelIndex())
        if cantidad <= 0:
            return
        if fila_actual < 0:
            fila_actual = combo.currentIndex()
        direccion = -1 if tecla in ("2", "4") else 1
        fila_nueva = max(0, min(cantidad - 1, fila_actual + direccion))
        indice = combo.model().index(
            fila_nueva, combo.modelColumn(), combo.rootModelIndex()
        )
        combo.view().setCurrentIndex(indice)

    def _controles_navegables(self, ventana):
        controles = []
        botones_virtuales = set(self.teclas_virtuales.values())
        for widget in self.findChildren(QWidget):
            if not isinstance(
                widget, (QDoubleSpinBox, QComboBox, QAbstractButton)
            ):
                continue
            if (
                widget in botones_virtuales
                or not widget.isVisible()
                or not widget.isEnabled()
                or widget.focusPolicy() == Qt.NoFocus
                or widget.window() != ventana
            ):
                continue
            controles.append(widget)
        return controles

    def _mover_foco_matriz(self, tecla):
        actual = self._widget_interactivo_enfocado()
        ventana = (
            actual.window() if actual is not None
            else QApplication.activeWindow() or self
        )
        controles = self._controles_navegables(ventana)
        if not controles:
            return
        if actual not in controles:
            destino = min(
                controles,
                key=lambda widget: (
                    widget.mapToGlobal(widget.rect().center()).y(),
                    widget.mapToGlobal(widget.rect().center()).x(),
                ),
            )
        else:
            centro_actual = actual.mapToGlobal(actual.rect().center())
            candidatos = []
            vertical = tecla in ("2", "8")
            signo = -1 if tecla in ("2", "4") else 1
            for widget in controles:
                if widget is actual:
                    continue
                centro = widget.mapToGlobal(widget.rect().center())
                dx = centro.x() - centro_actual.x()
                dy = centro.y() - centro_actual.y()
                principal = dy if vertical else dx
                secundario = abs(dx) if vertical else abs(dy)
                if principal * signo <= 0:
                    continue
                distancia = abs(principal) + 1.5 * secundario
                candidatos.append((distancia, secundario, widget))
            if not candidatos:
                self.lbl_estado_teclado.setText(
                    "Matriz: no hay otro control en esa dirección"
                )
                return
            dimension_transversal = (
                actual.width() if vertical else actual.height()
            )
            tolerancia_alineacion = max(12, dimension_transversal * 0.55)
            alineados = [
                candidato for candidato in candidatos
                if candidato[1] <= tolerancia_alineacion
            ]
            if alineados:
                candidatos = alineados
            destino = min(candidatos, key=lambda candidato: candidato[0])[2]

        destino.setFocus(Qt.OtherFocusReason)
        contenido = self.control_scroll.widget()
        if contenido is not None and contenido.isAncestorOf(destino):
            self.control_scroll.ensureWidgetVisible(destino, 24, 24)

    def _spinbox_enfocado(self):
        widget = self._widget_interactivo_enfocado()
        return widget if isinstance(widget, QDoubleSpinBox) else None

    def _cambiar_modo_teclado(self, modo, spinbox=None):
        self.modo_teclado_matriz = modo
        if modo == "B" and spinbox is not None:
            spinbox.setFocus(Qt.OtherFocusReason)
            spinbox.lineEdit().selectAll()
        self.actualizar_estado_modo_teclado()

    def _insertar_caracter_spinbox(self, spinbox, caracter):
        if caracter == "*":
            caracter = spinbox.locale().decimalPoint()
            tecla = (
                Qt.Key_Period if caracter == "." else Qt.Key_Comma
            )
        else:
            tecla = Qt.Key_0 + int(caracter)

        QApplication.sendEvent(
            spinbox,
            QKeyEvent(QEvent.KeyPress, tecla, Qt.NoModifier, caracter),
        )
        QApplication.sendEvent(
            spinbox,
            QKeyEvent(QEvent.KeyRelease, tecla, Qt.NoModifier, caracter),
        )

    def _aceptar_modo_numerico(self):
        spinbox = self._spinbox_enfocado()
        if spinbox is not None:
            spinbox.interpretText()
        self._cambiar_modo_teclado("A")

    def _aceptar_combo_desplegado(self, combo):
        indice = combo.view().currentIndex()
        if indice.isValid():
            combo.setCurrentIndex(indice.row())
        combo.hidePopup()
        self._cambiar_modo_teclado("A")

    def procesar_tecla_interfaz(self, tecla, checked=False):
        if checked:
            return

        if tecla == "A":
            if self.modo_teclado_matriz == "B":
                spinbox = self._spinbox_enfocado()
                if spinbox is not None:
                    spinbox.interpretText()
            self._cambiar_modo_teclado("A")
            return
        if tecla == "B":
            self._cambiar_modo_teclado(
                "B", self._spinbox_enfocado()
            )
            return

        combo = self._combo_desplegado()
        if tecla == "#" and combo is not None:
            self._aceptar_combo_desplegado(combo)
            return
        if self.modo_teclado_matriz == "A" and tecla in (
            "2", "4", "6", "8"
        ):
            if combo is not None:
                self._mover_seleccion_combo(combo, tecla)
            else:
                self._mover_foco_matriz(tecla)
            return
        if self.modo_teclado_matriz == "A" and tecla in ("1", "3"):
            spinbox = self._spinbox_enfocado()
            if spinbox is None:
                self.lbl_estado_teclado.setText(
                    "Matriz: selecciona primero un control numérico"
                )
                return
            cambio = 0.5 if tecla == "1" else -0.5
            spinbox.setValue(spinbox.value() + cambio)
            return
        if tecla == "#":
            if self.modo_teclado_matriz == "B":
                self._aceptar_modo_numerico()
                return
            widget = self._widget_interactivo_enfocado()
            if isinstance(widget, QDoubleSpinBox):
                self._cambiar_modo_teclado("B", widget)
            elif isinstance(widget, QComboBox):
                widget.showPopup()
            elif isinstance(widget, QAbstractButton):
                widget.click()
            else:
                self.lbl_estado_teclado.setText(
                    "Matriz: enfoca un control y pulsa #"
                )
            return

        if tecla == "C" and self.modo_teclado_matriz == "A":
            self.iniciar_ciclo_desde_matriz()
            return
        if tecla == "D":
            self.enviar_comando_detener()
            return

        if self.modo_teclado_matriz == "B":
            spinbox = self._spinbox_enfocado()
            if spinbox is None:
                self.lbl_estado_teclado.setText(
                    "Matriz: enfoca una caja numérica para escribir"
                )
                return
            if tecla.isdigit() or tecla == "*":
                self._insertar_caracter_spinbox(spinbox, tecla)
            return

    def enviar_modo_teclado_interfaz(self, activar):
        if not self.arduino or not self.arduino.is_open:
            return False
        comando = b"KEYPAD_UI,1\n" if activar else b"KEYPAD_UI,0\n"
        try:
            self.arduino.write(comando)
        except (serial.SerialException, OSError) as error:
            self.lbl_estado_teclado.setText(
                f"Matriz: no se pudo cambiar el modo del ESP32: {error}"
            )
            return False
        return True

    def enviar_heartbeat_teclado(self):
        if self.arduino and self.arduino.is_open:
            self.enviar_modo_teclado_interfaz(True)

    def iniciar_ciclo_desde_matriz(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText(
                "Estado: Conecta el ESP32 para iniciar el ciclo"
            )
            return
        if not self.sensor_valido or not self.ciclo_soportado:
            self.lbl_estado.setText(
                "Estado: Se requiere sensor válido y firmware compatible"
            )
            return
        if (
            self.ciclo_activo
            or self.control_pid_activo
            or self.prueba_conexion_activa
            or self.prueba_dimmer_activa
            or self.modo_termico in ("PURGA", "ERROR")
        ):
            self.lbl_estado.setText(
                "Estado: Detén el control o prueba activa antes del ciclo"
            )
            return
        if not self.enviar_rango_temperatura():
            return
        try:
            self.arduino.write(b"CYCLE,MIN\n")
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo iniciar el ciclo: {error}"
            )

    def cancelar_cuenta_regresiva_purga(self):
        if self.dialogo_purga is not None:
            self.dialogo_purga.close()

    def al_cerrar_dialogo_purga(self):
        self.dialogo_purga = None
        self.lbl_detalle_purga = None
        self.lbl_cuenta_purga = None
        self.boton_iniciar_purga = None
        self.boton_cancelar_purga = None

    def enviar_rango_temperatura(self):
        if not self.arduino or not self.arduino.is_open:
            return False
        temp_minima = self.spin_temp_minima.value()
        temp_maxima = self.spin_temp_maxima.value()
        comando = f"SETRANGE,{temp_minima:.1f},{temp_maxima:.1f}\n"
        try:
            self.arduino.write(comando.encode("utf-8"))
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo enviar el rango: {error}"
            )
            return False
        return True

    def alternar_prueba_conexion(self):
        self.enviar_modo_prueba(not self.prueba_conexion_activa)

    def enviar_modo_prueba(self, activar):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para iniciar la prueba")
            return

        comando = f"TEST,{1 if activar else 0}\n"
        try:
            self.arduino.write(comando.encode("utf-8"))
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(f"Estado: No se pudo enviar la prueba: {error}")
            return

        self.prueba_conexion_activa = activar
        self.actualizar_boton_prueba()
        self.lbl_estado.setText(
            "Estado: Prueba de conexión activa"
            if activar else "Estado: Prueba de conexión detenida"
        )

    def solicitar_prueba_dimmer(self):
        if not self.arduino or not self.arduino.is_open:
            self.lbl_estado.setText("Estado: Conecta el ESP32 para probar el dimmer")
            return
        if not self.sensor_valido:
            self.lbl_estado.setText(
                "Estado: Se requiere una lectura válida del DHT11"
            )
            return
        if not self.dimmer_soportado:
            self.lbl_estado.setText(
                "Estado: Carga el firmware con soporte de prueba del dimmer"
            )
            return

        try:
            self.arduino.write(b"DIMMER_TEST\n")
        except (serial.SerialException, OSError) as error:
            self.lbl_estado.setText(
                f"Estado: No se pudo probar el dimmer: {error}"
            )
            return

        self.prueba_dimmer_activa = True
        self.boton_prueba_dimmer.setText("Probando servo dimmer…")
        self.actualizar_boton_prueba_dimmer()
        self.lbl_estado.setText(
            "Estado: Prueba del dimmer iniciada; volverá a 0° automáticamente"
        )

    def actualizar_boton_prueba(self):
        self.boton_prueba_conexion.setText(
            "Detener prueba de tapas/ventiladores"
            if self.prueba_conexion_activa else
            "Probar tapas y ventiladores"
        )
        conectado = self.arduino is not None and self.arduino.is_open
        self.boton_prueba_conexion.setEnabled(
            conectado
            and not self.prueba_dimmer_activa
            and (
                self.prueba_conexion_activa
                or (
                    not self.control_pid_activo
                    and not self.ciclo_activo
                    and self.modo_termico != "PURGA"
                )
            )
        )

    def actualizar_boton_prueba_dimmer(self):
        if not hasattr(self, "boton_prueba_dimmer"):
            return
        conectado = self.arduino is not None and self.arduino.is_open
        self.boton_prueba_dimmer.setEnabled(
            conectado
            and self.dimmer_soportado
            and self.sensor_valido
            and not self.prueba_dimmer_activa
            and not self.prueba_conexion_activa
            and not self.control_pid_activo
            and not self.ciclo_activo
            and self.modo_termico not in ("PURGA", "ERROR")
        )

    def closeEvent(self, event):
        self.cancelar_cuenta_regresiva_purga()
        if self.arduino and self.arduino.is_open:
            if self.ciclo_soportado and not self.enviar_comando_detener():
                event.ignore()
                return
            if self.prueba_conexion_activa:
                self.enviar_modo_prueba(False)
            self.enviar_modo_teclado_interfaz(False)
            self.arduino.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimulacionCuarto()
    window.show()
    sys.exit(app.exec_())