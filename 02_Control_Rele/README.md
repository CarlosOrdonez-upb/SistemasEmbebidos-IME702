# Práctica 02: Control de Motorreductor con Relé

## 📋 Objetivo
Controlar el encendido y apagado de un motorreductor de 3V-5V utilizando un módulo de relé activado por una ESP32, implementando aislamiento eléctrico entre el circuito de control y el circuito de potencia.

##  Materiales Utilizados
- 1x ESP32 DevKit V1
- 1x Módulo de relé de 5V (1 canal)
- 1x Motorreductor DC 3V-5V
- 2x Botones pulsadores de 4 pines
- Cables Dupont
- 1x Protoboard
- Fuente de alimentación externa (si el motor requiere más corriente)

## 📐 Diagrama de Conexiones

### Conexiones ESP32:
- **GPIO 2** → Entrada IN del Relé
- **GPIO 4** → Botón ON → GND
- **GPIO 16** → Botón OFF → GND
- **GND** → GND del módulo de relé
- **VIN o 5V** → VCC del módulo de relé

### Conexiones del Relé al Motor:
- **COM (Común)** → VCC de alimentación del motor
- **NO (Normalmente Abierto)** → Terminal positivo del motor
- **Terminal negativo del motor** → GND

### Esquema:
```text
ESP32 MÓDULO RELÉ MOTOR
│ │ │
├── GPIO 2 ──────────── IN │ │
├── GPIO 4 ──(BTN ON) │ COM ────── VCC 5V ──┤+
├── GPIO 16 ─(BTN OFF) │ │
├── GND ─────────────── GND │ NO ────────────────┤-
└── 5V ──────────────── VCC │ │
│ │
```
> 🌐 **Prueba tu mismo los entornos:** Todos los proyectos cuentan con un [Gemelo Digital para interactuar ](https://coe-embedded-lab.streamlit.app).

## 💡 Funcionamiento
- **Botón ON (GPIO 4):** Activa el relé (GPIO 2 en LOW), cerrando el circuito del motor
- **Botón OFF (GPIO 16):** Desactiva el relé (GPIO 2 en HIGH), abriendo el circuito
- El relé permite controlar el motor (que puede consumir más corriente) sin dañar la ESP32
- **Nota:** El relé se activa con nivel LOW en este código

## ️ Consideraciones Importantes
1. **Aislamiento:** El relé separa eléctricamente la ESP32 del motor
2. **Corriente:** Si el motor consume más de 500mA, usar fuente externa
3. **Diodo de protección:** El módulo de relé ya incluye diodo de protección (flyback)
4. **Ruido eléctrico:** Se recomienda capacitor de 100µF en paralelo con el motor

## 📂 Archivos
- `codigo/control_motor_rele.ino` - Código principal en Arduino IDE
