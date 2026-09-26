# Práctica 01: Control de LED con Dos Botones

## 📋 Objetivo
Implementar un circuito que permita encender y apagar un LED utilizando dos botones pulsadores conectados a una ESP32, configurando correctamente los pines GPIO y utilizando resistencias de pull-up internas.

## 🔧 Materiales Utilizados
- 1x ESP32 DevKit V1
- 1x LED (cualquier color)
- 2x Botones pulsadores de 4 pines
- 1x Resistencia de 220Ω (para el LED)
- Cables Dupont
- 1x Protoboard

## 📐 Diagrama de Conexiones

### Conexiones ESP32:
- **GPIO 2** → Resistencia 220Ω → LED → GND
- **GPIO 4** → Botón ON → GND
- **GPIO 16** → Botón OFF → GND
- **3.3V/GND** → Alimentación del circuito

### Esquema:
ESP32
│
├── GPIO 2 ─[220Ω]───(LED)─── GND
│
├── GPIO 4 ──(Botón ON)─── GND
│
└── GPIO 16 ──(Botón OFF)─── GND


## 💡 Funcionamiento
- **Botón ON (GPIO 4):** Al presionarlo, el LED se enciende
- **Botón OFF (GPIO 16):** Al presionarlo, el LED se apaga
- Se utilizan **resistencias de pull-up internas** (`INPUT_PULLUP`), por lo que los botones conectan a GND cuando se presionan (activo en LOW)

## 📂 Archivos
- `codigo/control_led.ino` - Código principal en Arduino IDE

##  Ver simulación
*(Aquí puedes subir la imagen que me mostraste o poner un link si la subes a imgur)*
