
# 🌡️ Proyecto 04: Caja Térmica Inteligente con Sistema de Purga

## 📋 Objetivo
Diseñar e implementar una cámara térmica controlada por un microcontrolador ESP32, capaz de mantener una temperatura objetivo mediante un sistema de calefacción (foco) y refrigeración (módulo Peltier). El sistema destaca por su **lógica de purga automática**, que ventila la cámara mediante servomotores cuando el punto de ajuste (setpoint) cambia drásticamente, garantizando una estabilización térmica rápida y eficiente.

---

## ⚙️ Lógica de Control y Funcionamiento

El firmware implementa un control robusto basado en tres pilares fundamentales:

1. **Control por Histéresis:** 
   Para evitar el "ciclado" excesivo (encender y apagar constantemente) del foco y el Peltier, el sistema utiliza un margen de histéresis de 0.5°C. Solo activa la calefacción si la temperatura baja de `Objetivo - 0.5°C` y la refrigeración si supera `Objetivo + 0.5°C`.
2. **Sistema de Purga Automática:** 
   Si el usuario cambia la temperatura objetivo en más de 2.5°C respecto a la lectura actual, el sistema entra en **Fase de Purga**:
   - Abre las tapas superiores mediante servomotores (SG90).
   - Activa los ventiladores de extracción para renovar el aire estancado.
   - Cierra las tapas y reanuda el control térmico normal una vez estabilizado.
3. **Gestión de Errores:** 
   Si el sensor DHT11 falla o se desconecta, el sistema corta inmediatamente todas las salidas de potencia (foco, Peltier, ventiladores) y cierra las tapas por seguridad, reportando un `STATUS,ERROR` a la interfaz.

---

## 🛠️ Hardware y Diagrama de Pines

| Componente | Pin ESP32 | Función / Nota |
| :--- | :---: | :--- |
| **Sensor DHT11** | GPIO 4 | Lectura de temperatura y humedad ambiente. |
| **Foco 60W** | GPIO 16 | Controlado vía Relé/Mosfet para calentamiento. |
| **Módulo Peltier** | GPIO 19 | Controlado vía Mosfet IRFZ44N para enfriamiento. |
| **Ventiladores 12V** | GPIO 18 | Circulación de aire y apoyo en la purga. |
| **Servo Tapa 1** | GPIO 22 | Apertura de compuerta de ventilación izquierda. |
| **Servo Tapa 2** | GPIO 23 | Apertura de compuerta de ventilación derecha. |

> ⚠️ **Nota de Seguridad:** El foco y el módulo Peltier nunca se activan simultáneamente en el firmware (`escribirSalidas`) para evitar cortocircuitos o daños a la fuente de alimentación.

---

## 💻 Interfaz Gráfica y Simulación (PyQt5)

Se desarrolló una aplicación de escritorio en Python utilizando **PyQt5** que actúa como un "Gemelo Digital" del sistema físico.

**Características de la simulación:**
- **Visualización en Tiempo Real:** Representación gráfica de la caja, con animación de los ventiladores girando y las tapas abriéndose/cerrándose suavemente.
- **Partículas de Flujo:** Animación de partículas que simulan el flujo de aire caliente (rojo) o frío (azul) dependiendo del modo térmico.
- **Cambio de Ambiente:** El color de fondo de la cámara cambia gradualmente (gradiente) reflejando la temperatura actual.
- **Comunicación Serial:** Se conecta automáticamente al puerto COM del ESP32 (115200 baudios) para enviar el `SETPOINT` y recibir el `STATUS` cada 500ms.

##  Ver simulación
  ![Simulacion](sources/caja1.gif)

> 🌐 **Prueba tu mismo los entornos:** Todos los proyectos cuentan con un [Gemelo Digital para interactuar ](https://coe-embedded-lab.streamlit.app).

---

## 🔄 Protocolo de Comunicación Serial

La interfaz y el ESP32 se comunican mediante texto plano estructurado:

| Dirección | Comando / Formato | Descripción |
| :--- | :--- | :--- |
| **PC → ESP32** | `SETPOINT,35.0` | Establece la temperatura objetivo (Rango 20.0 - 50.0 °C). |
| **ESP32 → PC** | `STATUS,temp,foco,peltier,fans,tapas,FASE,humedad,setpoint` | Paquete de telemetría completo. |
| **ESP32 → PC** | `STATUS,ERROR,0,0,0,0,SENSOR_ERROR,0.0,35.0` | Alerta crítica por fallo de sensor. |

---

## 🚀 Instrucciones de Ejecución

### 1. Cargar el Firmware
- Abre `codigo/ESP32CodeTemperatura.ino` en Arduino IDE.
- Asegúrate de tener instaladas las librerías: `DHT sensor library` (by Adafruit) y `ESP32Servo`.
- Selecciona la placa "ESP32 Dev Module" y carga el código.

### 2. Ejecutar la Interfaz Gráfica
- **Requisitos:** Python 3.13 instalado.
- Instala las dependencias necesarias abriendo una terminal:
  ```bash
  pip install PyQt5 pyserial



