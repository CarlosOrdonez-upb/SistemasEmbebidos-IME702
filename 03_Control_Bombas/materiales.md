# 📦 Lista de Materiales - Práctica 03: Control de Llenado y Vaciado de Líquidos

## 🔌 Componentes Electrónicos y Hardware

| Cantidad | Componente | Especificaciones / Notas |
| :---: | :--- | :--- |
| 1 | **Microcontrolador ESP32** | DevKit V1 (30 o 38 pines). Núcleo de procesamiento y comunicación serial. |
| 1 | **Sensor Ultrasónico** | HC-SR04. Para medición de nivel no invasiva (incluye filtro de mediana en firmware). |
| 2 | **Bombas de Agua DC** | Modelo R385 (o equivalente). *Nota: Verificar voltaje nominal para ajustar la fuente.* |
| 1 | **Módulo de Relé** | 2 canales, 5V. Preferiblemente con optoacoplador para aislamiento galvánico. |
| 1 | **Protoboard** | 830 puntos (recomendado) o 400 puntos, para el montaje de las conexiones de control. |
| 1 | **Recipiente de Prueba** | Contenedor transparente de ~1 litro (para visualizar el nivel y calibrar el sensor). |
| Varios | **Cables de Interconexión** | Cables Dupont (Macho-Macho y Macho-Hembra) para protoboard y conexiones al ESP32. |

## ⚡ Alimentación y Seguridad

| Cantidad | Componente | Especificaciones / Notas |
| :---: | :--- | :--- |
| 1 | **Fuente de Poder** | Fuente regulable (ej. SPS-H3010) o fuentes segregadas: 12V para bombas y 5V para lógica/relés. |
| 1 | **Cable USB** | USB Tipo A a Micro-USB (o USB-C, según tu ESP32) para programación y alimentación de la lógica. |

> ⚠️ **Nota Crítica de Cableado:** Todas las tierras (GND) de la fuente de las bombas, la fuente del relé y el ESP32 **deben estar unidas en un punto común**. Esto evita diferencias de potencial que causen activaciones fantasma de los relés.

## 💻 Entorno de Software

| Componente | Versión / Detalle | Propósito |
| :--- | :--- | :--- |
| **Arduino IDE** | 2.3.10 o superior | Programación y carga del firmware en el ESP32. |
| **Python** | 3.10 o superior | Ejecución de la interfaz gráfica de control (GUI). |
| **Librería `pyserial`** | Última versión | Comunicación bidireccional robusta entre Python y el ESP32. *(Instalar con: `pip install pyserial`)* |
| **Librería `tkinter`** | Incluida en Python estándar | Renderizado de la interfaz gráfica, canvas y widgets. |

## 🛠️ Herramientas e Insumos Adicionales (Opcionales pero recomendados)
- **Multímetro:** Para verificar voltajes de la fuente y continuidad en las conexiones.
- **Capacitores cerámicos (100nF):** Para instalar en los terminales de las bombas y suprimir picos de voltaje (ruido electromagnético).
- **Resistencias Pull-down (10kΩ):** Opcional, para asegurar el estado de las líneas de señal del relé si el módulo no las incluye internamente.

---

## 📝 Notas de Calibración para el Equipo
1. **Caudal Real:** La constante `ML_POR_SEGUNDO` en el código Python debe calibrarse empíricamente. Mide cuántos mililitros bombea tu sistema en 10 segundos y ajusta el valor en el código.
2. **Puerto Serial:** Asegúrate de cambiar la variable `PUERTO = 'COM5'` en el script de Python al puerto asignado por tu sistema operativo (ej. `COM3`, `COM4` en Windows, o `/dev/ttyUSB0` en Linux/Mac).
3. **Conflicto de Puerto:** El Monitor Serie del Arduino IDE **debe estar cerrado** al ejecutar la aplicación de Python, de lo contrario se generará un error de `PermissionError` por puerto ocupado.
