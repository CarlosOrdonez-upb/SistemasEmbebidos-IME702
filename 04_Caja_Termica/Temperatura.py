import sys
import math
import serial
from serial.tools import list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QDoubleSpinBox, QPushButton, 
                             QComboBox,
                             QGraphicsView, QGraphicsScene, QGraphicsRectItem, 
                             QGraphicsEllipseItem, QGraphicsTextItem,
                             QGraphicsItemGroup, QGraphicsPolygonItem,
                             QGraphicsLineItem)
from PyQt5.QtCore import QTimer, Qt, QPointF
from PyQt5.QtGui import (QBrush, QPen, QColor, QPainter, QPolygonF,
                         QRadialGradient, QLinearGradient, QPainterPath, QPixmap)

class SimulacionCuarto(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control de Cámara Térmica - Simulación")
        self.resize(900, 600)

        self.arduino = None
        self.buffer_serial = bytearray()
        self.modo_termico = "MANTENIENDO"
        self.fase_particulas = 0
        self.angulo_fan = 0
        self.ventiladores_activos = False
        self.puertas_abiertas = False
        self.prueba_conexion_activa = False
        self.temperatura_actual = None
        self.color_ambiente = QColor(203, 209, 207)
        self.color_ambiente_objetivo = QColor(203, 209, 207)

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
        main_layout.addWidget(control_panel, 1)

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

        self.combo_puertos = QComboBox()
        self.boton_conexion = QPushButton("Conectar")
        self.boton_conexion.clicked.connect(self.conectar_serial)
        self.boton_actualizar_puertos = QPushButton("Actualizar puertos")
        self.boton_actualizar_puertos.setObjectName("secundario")
        self.boton_actualizar_puertos.clicked.connect(self.cargar_puertos)
        self.boton_prueba_conexion = QPushButton("Iniciar prueba de conexión")
        self.boton_prueba_conexion.setObjectName("secundario")
        self.boton_prueba_conexion.setToolTip(
            "Abre las compuertas y activa los ventiladores; "
            "mantiene apagados el calefactor y el Peltier."
        )
        self.boton_prueba_conexion.setEnabled(False)
        self.boton_prueba_conexion.clicked.connect(self.alternar_prueba_conexion)
        
        self.lbl_rango = QLabel("RANGO DE TEMPERATURA")
        self.lbl_temp_minima = QLabel("Temperatura mínima")
        self.spin_temp_minima = QDoubleSpinBox()
        self.spin_temp_minima.setRange(20.0, 45.0)
        self.spin_temp_minima.setValue(28.0)
        self.spin_temp_minima.setSingleStep(0.5)
        self.spin_temp_minima.setSuffix(" °C")
        self.spin_temp_minima.setToolTip("Rango permitido: 20–45 °C")
        self.spin_temp_minima.valueChanged.connect(
            self.actualizar_temperatura_minima
        )
        self.lbl_temp_maxima = QLabel("Temperatura máxima")
        self.spin_temp_maxima = QDoubleSpinBox()
        self.spin_temp_maxima.setRange(25.0, 50.0)
        self.spin_temp_maxima.setValue(35.0)
        self.spin_temp_maxima.setSingleStep(0.5)
        self.spin_temp_maxima.setSuffix(" °C")
        self.spin_temp_maxima.setToolTip("Rango permitido: 25–50 °C")
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

        control_layout.addWidget(titulo)
        control_layout.addWidget(subtitulo)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.lbl_temp_actual)
        control_layout.addWidget(self.lbl_estado)
        control_layout.addWidget(self.lbl_rango_actual)
        control_layout.addLayout(humedad_layout)
        control_layout.addSpacing(8)
        control_layout.addWidget(QLabel("PUERTO DEL ESP32"))
        control_layout.addWidget(self.combo_puertos)
        control_layout.addWidget(self.boton_conexion)
        control_layout.addWidget(self.boton_actualizar_puertos)
        control_layout.addWidget(self.boton_prueba_conexion)
        control_layout.addSpacing(8)
        control_layout.addWidget(self.lbl_rango)
        control_layout.addLayout(rango_layout)
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

        self.cargar_puertos()
        if self.combo_puertos.count():
            self.conectar_serial()

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
            if self.prueba_conexion_activa:
                self.enviar_modo_prueba(False)
            self.arduino.close()
            self.arduino = None
            self.boton_conexion.setText("Conectar")
            self.combo_puertos.setEnabled(True)
            self.boton_prueba_conexion.setEnabled(False)
            self.lbl_estado.setText("Estado: Desconectado")
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
            self.lbl_estado.setText(f"Estado: Conectado a {puerto}; esperando datos")
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
                    self.procesar_linea(linea.decode("utf-8", errors="replace").strip())
            except (serial.SerialException, OSError) as error:
                self.lbl_estado.setText(f"Estado: Error de comunicación: {error}")
                self.arduino.close()
                self.arduino = None
                self.boton_conexion.setText("Conectar")
                self.combo_puertos.setEnabled(True)
                self.boton_prueba_conexion.setEnabled(False)
                self.prueba_conexion_activa = False
                self.actualizar_boton_prueba()

    def procesar_linea(self, linea):
        partes = linea.split(",")
        if len(partes) >= 2 and partes[0] == "STATUS" and partes[1] == "ERROR":
            if len(partes) == 10:
                try:
                    temp_minima = float(partes[8])
                    temp_maxima = float(partes[9])
                except ValueError:
                    pass
                else:
                    if (
                        math.isfinite(temp_minima)
                        and math.isfinite(temp_maxima)
                        and temp_minima < temp_maxima
                    ):
                        self.lbl_rango_actual.setText(
                            f"Rango: {temp_minima:.1f} °C - "
                            f"{temp_maxima:.1f} °C"
                        )
            else:
                self.lbl_rango_actual.setText(
                    "Rango: no disponible (firmware anterior)"
                )
            self.prueba_conexion_activa = (
                len(partes) >= 7 and partes[6] == "TESTING"
            )
            self.ventiladores_activos = (
                len(partes) >= 5 and partes[4] == "1"
            )
            self.puertas_abiertas = (
                len(partes) >= 6 and partes[5] == "1"
            )
            self.modo_termico = (
                "PRUEBA" if self.prueba_conexion_activa else "ERROR"
            )
            self.actualizar_boton_prueba()
            self.lbl_estado.setText(
                "Estado: Prueba activa; error del sensor"
                if self.prueba_conexion_activa else
                "Estado: Error del sensor; salidas apagadas"
            )
            return

        if not partes or partes[0] != "STATUS" or len(partes) not in (4, 9, 10):
            return

        try:
            temp = float(partes[1])
            foco_on = partes[2] == "1"
            peltier_on = partes[3] == "1"
            if len(partes) in (9, 10):
                self.ventiladores_activos = partes[4] == "1"
                self.puertas_abiertas = partes[5] == "1"
                fase = partes[6]
                humedad = float(partes[7])
                self.prueba_conexion_activa = fase == "TESTING"
                if len(partes) == 10:
                    temp_minima = float(partes[8])
                    temp_maxima = float(partes[9])
                    if (
                        not math.isfinite(temp_minima)
                        or not math.isfinite(temp_maxima)
                        or temp_minima >= temp_maxima
                    ):
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
        self.actualizar_boton_prueba()
        if temp_minima is None or temp_maxima is None:
            self.lbl_rango_actual.setText(
                "Rango: no disponible (firmware anterior)"
            )
        else:
            self.lbl_rango_actual.setText(
                f"Rango: {temp_minima:.1f} °C - {temp_maxima:.1f} °C"
            )

        self.lbl_temp_actual.setText(
            f"{temp:.1f} °C"
        )
        self.temperatura_actual = temp
        self.lbl_humedad.setText(
            "Humedad: --%" if humedad is None
            else f"Humedad: {humedad:.0f}%"
        )
        estados = {
            "HEATING": ("CALENTANDO", "Calentando"),
            "COOLING": ("ENFRIANDO", "Enfriando"),
            "HOLD": ("MANTENIENDO", "Manteniendo"),
            "PURGE_OPENING": ("PURGA", "Abriendo tapas"),
            "PURGE_RUNNING": ("PURGA", "Extrayendo aire"),
            "PURGE_WAIT": ("PURGA", "Estabilizando con tapas abiertas"),
            "PURGE_CLOSING": ("PURGA", "Cerrando tapas"),
            "TESTING": ("PRUEBA", "Prueba: compuertas abiertas y ventiladores activos"),
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
        if valor >= self.spin_temp_maxima.value():
            anterior = self.spin_temp_maxima.blockSignals(True)
            self.spin_temp_maxima.setValue(valor + 0.5)
            self.spin_temp_maxima.blockSignals(anterior)
        self.enviar_rango_temperatura()

    def actualizar_temperatura_maxima(self, valor):
        if valor <= self.spin_temp_minima.value():
            anterior = self.spin_temp_minima.blockSignals(True)
            self.spin_temp_minima.setValue(valor - 0.5)
            self.spin_temp_minima.blockSignals(anterior)
        self.enviar_rango_temperatura()

    def enviar_rango_temperatura(self):
        if self.arduino and self.arduino.is_open:
            temp_minima = self.spin_temp_minima.value()
            temp_maxima = self.spin_temp_maxima.value()
            comando = f"SETRANGE,{temp_minima:.1f},{temp_maxima:.1f}\n"
            try:
                self.arduino.write(comando.encode("utf-8"))
            except (serial.SerialException, OSError) as error:
                self.lbl_estado.setText(
                    f"Estado: No se pudo enviar el rango: {error}"
                )

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

    def actualizar_boton_prueba(self):
        self.boton_prueba_conexion.setText(
            "Detener prueba de conexión"
            if self.prueba_conexion_activa else
            "Iniciar prueba de conexión"
        )

    def closeEvent(self, event):
        if self.arduino and self.arduino.is_open:
            if self.prueba_conexion_activa:
                self.enviar_modo_prueba(False)
            self.arduino.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimulacionCuarto()
    window.show()
    sys.exit(app.exec_())