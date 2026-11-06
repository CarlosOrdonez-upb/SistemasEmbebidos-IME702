# Animatrónico IME 702

Sistema ciberfísico que integra inteligencia artificial local, visión artificial, síntesis de voz, reconocimiento de voz y control electromecánico en un prototipo de bebé animatrónico. El proyecto combina una aplicación de escritorio desarrollada en Python con un ESP32 DevKit V1, permitiendo una interacción autónoma, segura y adaptable sin dependencia de servicios de IA en la nube.

## Características principales

- **Inferencia de lenguaje natural local:** procesamiento conversacional con Qwen 2.5 7B mediante Ollama, utilizando el modelo `qwen2.5:7b`.
- **Síntesis de voz clonada en tiempo real:** generación de voz mediante Coqui XTTS, con archivos locales de referencia disponibles en el proyecto.
- **Reconocimiento de voz local:** transcripción mediante Faster-Whisper.
- **Visión artificial eficiente:** detección de personas y contexto visual con YOLOv8n. El procesamiento se ejecuta en CPU para preservar la VRAM de la GPU destinada principalmente a los modelos de lenguaje y síntesis de voz.
- **Control de hardware en tiempo real:** comunicación serie con ESP32 DevKit V1 para el movimiento coordinado de servomotores y la reproducción de audio mediante DFPlayer Mini.
- **Interfaz gráfica de operación y respaldo:** controles manuales para servos, pistas de audio, movimientos automáticos y conexión serial.
![Interfaz](InterfazAnimatronico.png)
## Arquitectura del proyecto

- [`animatronico_control.py`](./animatronico_control.py): aplicación principal con interfaz gráfica, captura de audio, visión por computadora, interacción con IA, síntesis de voz y comunicación con el ESP32.
- [`bebe_esp32.ino`](./bebe_esp32.ino): firmware para ESP32 DevKit V1 con control de servos y DFPlayer Mini.
- [`requirements.txt`](./requirements.txt): dependencias Python del sistema.
- [`yolov8n.pt`](./yolov8n.pt): modelo local de detección utilizado por YOLOv8n.
- [`config.json`](./config.json): configuración persistente de movimientos, velocidad y controles de la interfaz.
- [`sources/`](./sources): recursos multimedia usados durante el desarrollo y la depuración.
- Archivos `reference*.wav`: muestras locales utilizadas por el sistema de síntesis de voz clonada.

## Requisitos de hardware

- Laptop o equipo de cómputo con GPU NVIDIA.
  - Se recomienda NVIDIA RTX serie 30, 40 o 50.
  - Se recomienda un mínimo de 8 GB de VRAM para ejecutar el conjunto completo de modelos.
- ESP32 DevKit V1.
- Servomotores compatibles con una alimentación separada y controlados desde los pines definidos en el firmware.
- Módulo DFPlayer Mini y tarjeta microSD con las pistas configuradas.
- Cámara web compatible con OpenCV.
- Micrófono.
- Altavoz o sistema de amplificación.
- Fuente externa de 5 V dimensionada para los servos.

> Los servomotores deben compartir masa eléctrica con el ESP32 y con la fuente externa. No se deben alimentar directamente desde los pines de 3.3 V o 5 V del ESP32.

## Requisitos de software

### Python

El proyecto requiere **Python 3.11**. Python 3.12 y Python 3.13 pueden provocar incompatibilidades con dependencias como Coqui TTS y PyTorch, por lo que no se consideran compatibles para esta implementación.

### Windows y compilación CUDA

Instale las **Microsoft Visual C++ Build Tools** con la carga de trabajo de Desarrollo para escritorio con C++.

Si utiliza una GPU NVIDIA RTX 5060 o, en general, una GPU con arquitectura CUDA `sm_120`, configure previamente la siguiente variable de entorno:

```powershell
setx TORCH_CUDA_ARCH_LIST "8.9"
```

Esta configuración evita errores asociados con NVRTC y la compilación de extensiones incompatibles. Cierre y vuelva a abrir la terminal después de establecer la variable para que esté disponible en las nuevas sesiones.

### Dependencias adicionales

- Ollama instalado y operativo, con el modelo Qwen 2.5 7B disponible:

```powershell
ollama pull qwen2.5:7b
```

- Arduino IDE con soporte para ESP32.
- Librerías de Arduino `ESP32Servo` y `DFRobotDFPlayerMini`.

## Instalación

Desde la raíz del repositorio, cree el entorno virtual dentro de la carpeta del proyecto:

```powershell
cd Animatronico
py -3.11 -m venv .venv
```

Active el entorno virtual en Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Instale las dependencias:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

En caso de restricciones de ejecución en PowerShell, el entorno también puede activarse con:

```powershell
.venv\Scripts\activate.bat
```

## Preparación del ESP32

1. Abra `bebe_esp32.ino` en Arduino IDE.
2. Seleccione la placa **ESP32 Dev Module**.
3. Instale las librerías `ESP32Servo` y `DFRobotDFPlayerMini`.
4. Conecte los servos y el DFPlayer según los pines definidos en el firmware y confirme las conexiones de masa.
5. Compile y cargue el programa en el ESP32 DevKit V1.

## Modo de uso

1. Confirme que Ollama esté en ejecución.
2. Desde la carpeta `Animatronico`, active el entorno virtual.
3. Inicie la aplicación principal:

```powershell
python animatronico_control.py
```

4. Espere a que carguen los modelos locales, la interfaz gráfica y la cámara.
5. En la pestaña de controles, seleccione el puerto serie correspondiente al ESP32 y pulse **CONECTAR**.
6. Utilice el reconocimiento por voz, el campo de texto o los controles manuales disponibles en la interfaz.

El movimiento de los servos por parte de la IA puede habilitarse o deshabilitarse desde el control **MOVIMIENTO IA**. Asimismo, la interfaz permite controlar individualmente los servos, reproducir pistas del DFPlayer, ajustar velocidades y activar movimientos de reposo.

### Modo manual de respaldo

Si la carga simultánea de modelos excede los recursos disponibles, desactive las funciones de procesamiento de IA intensivo o utilice exclusivamente los controles manuales de la interfaz. Este modo permite operar los servos, reproducir pistas y mantener el prototipo funcional sin recurrir a la inferencia conversacional ni a la síntesis durante pruebas mecánicas o demostraciones de hardware.

## Consideraciones de rendimiento

Para reducir el uso de memoria gráfica, la detección visual YOLOv8n se ejecuta en CPU y el modelo `yolov8n.pt` se carga desde la carpeta local del proyecto. Esta distribución de tareas conserva VRAM para Qwen 2.5 y Coqui XTTS. Las cargas de IA pueden ajustarse según la capacidad de la computadora, priorizando la estabilidad y la respuesta en tiempo real sobre la concurrencia de modelos.
