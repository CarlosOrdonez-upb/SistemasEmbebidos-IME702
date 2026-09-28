# Práctica 03: Control Automatizado de Llenado y Vaciado de Líquidos

## 📋 Objetivo
Implementar un sistema de control de nivel de líquidos bidireccional utilizando un ESP32, sensor ultrasónico y bombas externas. El sistema garantiza la seguridad operativa mediante paradas automáticas por nivel (80% llenado ), exclusión mutua de actuadores y timeout de protección, todo monitoreado desde una interfaz gráfica de escritorio.

> 💡 **Nota del Equipo:**  
> Ante la indisponibilidad de una pantalla LCD con módulo I2C, el equipo diseñó e implementó una **Interfaz Gráfica de Usuario (GUI) nativa en Python (Tkinter)**. Esta solución no solo suple la falta de hardware, sino que ofrece capacidades superiores: simulación visual en tiempo real, cambio dinámico de colores por estado y control de precisión por mililitros, funcionando como un verdadero panel de control SCADA a escala.

---

## 🛠️ Arquitectura del Sistema

### Hardware
- **Microcontrolador:** ESP32 DevKit V1.
- **Sensores:** HC-SR04 (Ultrasonido) con filtro de mediana (5 lecturas) para eliminar ruido por turbulencia.
- **Actuadores:** 2x Bombas de agua DC R385 controladas mediante módulo de relé de 2 canales.
- **Alimentación:** Fuente segregada (12V para bombas, 5V para lógica) con tierras (GND) unidas en punto común para evitar activaciones fantasma.

### Lógica del Firmware (ESP32)
1. **Exclusión Mutua Estricta:** Nunca se permiten ambas bombas activas simultáneamente.
2. **Paradas Automáticas Inteligentes:** 
   - Llenado: Se detiene al alcanzar el **80%** (evita rebotes del sensor por tensión superficial).
   - Vaciado: Se detiene al llegar al **2%** (protege la bomba contra funcionamiento en seco).
3. **Timeout de Seguridad:** Apagado forzoso si una bomba opera más de **60 segundos** sin intervención.
4. **Gestión de Fallos:** Si el sensor ultrasónico falla, el sistema entra en modo seguro y solo responde a comandos manuales.

### Aplicación de Escritorio (Python + Tkinter)
- **Simulación Visual:** Canvas que representa el nivel del tanque con cambio de color dinámico (🔵 Azul = Normal, 🔴 Rojo = Crítico ≤20%, 🟠 Naranja = Lleno ≥80%).
- **Control Dual:** 
  - *Modo Automático:* Ciclos completos hasta los límites seguros.
  - *Modo Precisión:* Sliders para transferir cantidades exactas en mililitros.
- **Robustez Serial:** Implementa pausa de 2.5s post-conexión y limpieza de buffer (`reset_input_buffer`) para manejar el reinicio automático del ESP32 y evitar errores `PermissionError`.

---

## 📐 Diagrama de Conexiones

| Componente | Pin ESP32 | Nota |
| :--- | :---: | :--- |
| **HC-SR04 (Trig)** | GPIO 5 | Salida de pulso |
| **HC-SR04 (Echo)** | GPIO 18 | Entrada de lectura |
| **Relé Bomba Llenado** | GPIO 22 | Lógica gestionada por firmware |
| **Relé Bomba Vaciado** | GPIO 23 | Lógica gestionada por firmware |
| **GND** | GND | Tierra común con fuente de bombas |

---

## 🔄 Protocolo de Comunicación Serial

La interfaz Python y el ESP32 se comunican mediante un protocolo de texto plano robusto:

| Dirección | Comando / Formato | Descripción |
| :--- | :--- | :--- |
| **PC → ESP32** | `EMPEZAR_LLENAR` | Activa bomba de llenado y temporizador. |
| **PC → ESP32** | `EMPEZAR_VACIAR` | Activa bomba de vaciado y temporizador. |
| **PC → ESP32** | `DETENER_TODO` | Desactiva ambas bombas inmediatamente. |
| **ESP32 → PC** | `DATA:distancia,porcentaje` | Envío continuo de telemetría (ej: `DATA:5.2,45.0`). |
| **ESP32 → PC** | `AUTO_STOP: MOTIVO` | Notifica a la GUI que el hardware detuvo el proceso por seguridad. |

---

## 🚀 Instrucciones de Ejecución

1. **Preparación del Entorno:**
   - Asegúrate de tener Python 3.10 instalado.
   - Instala la librería serial: `pip install pyserial`
2. **Configuración del Hardware:**
   - Conecta el ESP32 por USB.
   - **¡IMPORTANTE!** Cierra el "Monitor Serie" del Arduino IDE o cualquier otro programa que esté usando el puerto COM, de lo contrario Python no podrá conectarse.
3. **Ejecución:**
   - Abre una terminal en la carpeta del proyecto.
   - Ejecuta: `python Practica_Bomba.py` (o el nombre exacto de tu archivo `.py`).
   - La interfaz se conectará automáticamente, esperará el reinicio del ESP32 y comenzará a mostrar los datos en tiempo real.

---

## 📂 Archivos de la Práctica
- `codigo/control_bomba.ino` - Firmware del ESP32 con lógica de seguridad.
- `codigo/Practica_Bomba.py` - Interfaz gráfica de control en Python (Tkinter).
- `materiales.md` - Lista detallada de componentes y cantidades.
- `imagenes/` - Capturas de pantalla de la interfaz gráfica y montaje físico.

---
##  Ver simulación

  ![Simulación en Visual](./SistemasEmbebidos-IME702/sources/Practica3.gif)

---  
## ⚠️ Consideraciones de Seguridad
- Calibrar la constante de caudal (`ML_POR_SEGUNDO`) en el código Python midiendo el volumen real bombeado.
