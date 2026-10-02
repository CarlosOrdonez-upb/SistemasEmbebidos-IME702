## Lista Detallada de Materiales - Práctica 02

| Cantidad | Componente | Especificaciones |
|----------|------------|------------------|
| 1 | ESP32 DevKit V1 | Microcontrolador |
| 1 | Módulo de relé | 1 canal, 5V, con optoacoplador |
| 1 | Motorreductor | DC 3V-5V con caja reductora |
| 2 | Botón pulsador | 4 pines |
| 1 | Protoboard | 400 o 830 puntos |
| Varios | Cables Dupont | Macho-Macho |
| 1 | Fuente 5V | (Opcional) Si el motor requiere más corriente |

### Especificaciones del Módulo de Relé:
- **VCC:** 5V (puede conectarse al VIN de ESP32)
- **GND:** Tierra común con ESP32
- **IN:** Señal de control (GPIO 2)
- **COM:** Terminal común del relay
- **NO:** Normalmente abierto
- **NC:** Normalmente cerrado (no usado en esta práctica)

### Notas de seguridad:
- Verificar polaridad del motor
- No exceder el voltaje nominal del motor (5V máx)
- El relé permite controlar cargas de mayor potencia
