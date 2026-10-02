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
        self.temperatura_actual = None
        self.color_ambiente = QColor(203, 209, 207)
        self.color_ambiente_objetivo = QColor(203, 209, 207)

        # --- Interfaz Gráfica ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Lado Izquierdo: Simulación Visual
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing) # Requiere importar QPainter
        main_layout.addWidget(self.view, 2)

        # Lado Derecho: Controles
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        main_layout.addWidget(control_panel, 1)

        self.lbl_temp_actual = QLabel("Temp Actual: -- °C")
        self.lbl_temp_actual.setStyleSheet("font-size: 20px; font-weight: bold;")
        
        self.lbl_estado = QLabel("Estado: Esperando...")

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
        self.boton_actualizar_puertos.clicked.connect(self.cargar_puertos)
        
        self.lbl_objetivo = QLabel("Temperatura Objetivo:")
        self.spin_objetivo = QDoubleSpinBox()
        self.spin_objetivo.setRange(20.0, 50.0)
        self.spin_objetivo.setValue(35.0)
        self.spin_objetivo.setSingleStep(0.5)
        self.spin_objetivo.valueChanged.connect(self.actualizar_objetivo)

        control_layout.addWidget(self.lbl_temp_actual)
        control_layout.addWidget(self.lbl_estado)
        control_layout.addLayout(humedad_layout)
        control_layout.addWidget(QLabel("Puerto del ESP32:"))
        control_layout.addWidget(self.combo_puertos)
        control_layout.addWidget(self.boton_conexion)
        control_layout.addWidget(self.boton_actualizar_puertos)
        control_layout.addWidget(self.lbl_objetivo)
        control_layout.addWidget(self.spin_objetivo)
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
        # Caja principal (Triplay)
        self.caja = QGraphicsRectItem(50, 50, 400, 400)
        self.caja.setBrush(QBrush(QColor(139, 69, 19))) # Color madera
        self.caja.setPen(QPen(Qt.black, 3))
        self.scene.addItem(self.caja)

        self.interior = QGraphicsRectItem(57, 57, 386, 386)
        self.interior.setBrush(QBrush(self.color_ambiente))
        self.interior.setPen(QPen(QColor(91, 64, 48), 1))
        self.scene.addItem(self.interior)

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

    def color_aire_entrada(self):
        if self.temperatura_actual is None:
            return QColor(145, 153, 151)
        if self.temperatura_actual < 25.0:
            return QColor(57, 157, 218)
        if self.temperatura_actual < 30.0:
            return QColor(145, 153, 151)
        return QColor(224, 65, 55)

    def dibujar_componentes(self):
        # Foco (Arriba)
        self.foco = QGraphicsEllipseItem(200, 70, 60, 60)
        self.foco.setBrush(QBrush(QColor(50, 50, 50))) # Apagado (gris oscuro)
        self.scene.addItem(self.foco)
        self.lbl_foco = QGraphicsTextItem("Foco")
        self.lbl_foco.setPos(210, 140)
        self.scene.addItem(self.lbl_foco)

        # Celda Peltier (Abajo)
        self.peltier = QGraphicsRectItem(180, 380, 100, 40)
        self.peltier.setBrush(QBrush(QColor(50, 50, 50))) # Apagado
        self.scene.addItem(self.peltier)
        self.lbl_peltier = QGraphicsTextItem("Peltier")
        self.lbl_peltier.setPos(190, 430)
        self.scene.addItem(self.lbl_peltier)

        # Ventiladores (Izquierda y Derecha)
        self.fan1 = self.crear_ventilador(80, 200)
        self.fan2 = self.crear_ventilador(380, 200)
        self.puerta_izquierda = self.crear_puerta(82, 202, False)
        self.puerta_derecha = self.crear_puerta(382, 202, True)
        self.crear_particulas()

    def crear_ventilador(self, x, y):
        carcasa = QGraphicsRectItem(x, y, 60, 60)
        carcasa.setBrush(QBrush(QColor(205, 214, 211)))
        carcasa.setPen(QPen(QColor(62, 77, 78), 2))
        self.scene.addItem(carcasa)

        aro = QGraphicsEllipseItem(x + 6, y + 6, 48, 48)
        aro.setBrush(QBrush(QColor(183, 196, 193)))
        aro.setPen(QPen(QColor(105, 122, 120), 1))
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
            pala.setBrush(QBrush(QColor(44, 60, 63)))
            pala.setPen(QPen(QColor(30, 43, 45), 1))
            rotor.addToGroup(pala)

        rotor.setPos(x, y)
        rotor.setTransformOriginPoint(30, 30)
        self.scene.addItem(rotor)

        centro = QGraphicsEllipseItem(x + 24, y + 24, 12, 12)
        centro.setBrush(QBrush(QColor(233, 169, 79)))
        centro.setPen(QPen(QColor(62, 77, 78), 1))
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
            self.arduino.close()
            self.arduino = None
            self.boton_conexion.setText("Conectar")
            self.combo_puertos.setEnabled(True)
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

    def procesar_linea(self, linea):
        partes = linea.split(",")
        if len(partes) >= 2 and partes[0] == "STATUS" and partes[1] == "ERROR":
            self.modo_termico = "ERROR"
            self.ventiladores_activos = False
            self.puertas_abiertas = False
            self.lbl_estado.setText("Estado: Error del sensor; salidas apagadas")
            return

        if partes[0] != "STATUS" or len(partes) not in (4, 9):
            return

        try:
            temp = float(partes[1])
            foco_on = partes[2] == "1"
            peltier_on = partes[3] == "1"
            if len(partes) == 9:
                self.ventiladores_activos = partes[4] == "1"
                self.puertas_abiertas = partes[5] == "1"
                fase = partes[6]
                humedad = float(partes[7])
            else:
                self.ventiladores_activos = False
                self.puertas_abiertas = False
                fase = "HEATING" if foco_on else "COOLING" if peltier_on else "HOLD"
                humedad = None
        except ValueError:
            return

        self.lbl_temp_actual.setText(
            f"Temp Actual: {temp:.1f} °C"
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
        self.foco.setBrush(QBrush(QColor(255, 255, 0) if foco_on else QColor(50, 50, 50)))
        self.peltier.setBrush(QBrush(QColor(0, 150, 255) if peltier_on else QColor(50, 50, 50)))

    def actualizar_objetivo(self, valor):
        if self.arduino and self.arduino.is_open:
            comando = f"SETPOINT,{valor}\n"
            try:
                self.arduino.write(comando.encode("utf-8"))
            except (serial.SerialException, OSError) as error:
                self.lbl_estado.setText(f"Estado: No se pudo enviar el objetivo: {error}")

    def closeEvent(self, event):
        if self.arduino and self.arduino.is_open:
            self.arduino.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimulacionCuarto()
    window.show()
    sys.exit(app.exec_())