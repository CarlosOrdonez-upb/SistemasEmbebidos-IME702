# 📦 Lista de Materiales - Proyecto 04: Caja Térmica Inteligente

## 🔌 Componentes Electrónicos y Hardware de Control

| Cantidad | Componente | Especificaciones / Función |
| :---: | :--- | :--- |
| 1 | **Microcontrolador** | ESP32 DevKit V1 (Cerebro del sistema). |
| 1 | **Sensor Ambiental** | DHT11 (Medición de temperatura y humedad ambiente). |
| 1 | **Kit Celda Peltier** | Incluye celda, disipadores de calor y ventiladores dedicados para enfriamiento. |
| 1 | **Foco Incandescente** | 60W con su respectivo Socket (Para calentamiento rápido). |
| 2 | **Ventiladores 12V** | Para circulación de aire y apoyo en el proceso de purga. |
| 2 | **Servomotores** | Modelo SG90 (Para la apertura y cierre automático de las tapas de purga). |
| 1 | **Módulo Relé** | Para conmutación segura de cargas de mayor potencia (Foco/Ventiladores). |
| 1 | **Mosfet** | IRFZ44N (Para control eficiente de potencia, ej. ventiladores o Peltier). |
| 1 | **Protoboard y Cables** | Para el prototipado de las conexiones de control. |

## 📦 Materiales de Construcción de la Cámara

| Cantidad | Componente | Especificaciones / Función |
| :---: | :--- | :--- |
| 6 | **Caras de Triplay** | 30 x 30 cm (Estructura rígida y soporte mecánico de la caja). |
| 6 | **Caras de Unicel** | 30 x 30 cm (Aislante térmico interno para evitar pérdidas de calor/frío). |

## ⚙️ Lógica del Sistema
- **Control por Histéresis:** Evita el ciclado excesivo del foco y el Peltier.
- **Purga Automática:** Si el *setpoint* cambia drásticamente (≥ 2.5°C), el sistema abre las tapas con los servos y activa los ventiladores para ventilar el aire estancado antes de volver a sellar y estabilizar. Esto evita condensacion del aire y esta determinado por la humedad que detecte el sensor DHT11