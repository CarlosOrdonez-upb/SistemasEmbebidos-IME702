# 📦 Lista de Materiales - Proyecto 04: Caja Térmica Inteligente

## 🔌 Componentes Electrónicos y Hardware de Control

| Cantidad | Componente | Especificaciones / Función |
| :---: | :--- | :--- |
| 1 | **Microcontrolador** | ESP32 DevKit V1 (Cerebro del sistema). |
| 1 | **Sensor DHT11** | GPIO 15; mide temperatura (0–50 °C) y humedad. Requiere pull-up DATA a 3.3 V si no es un módulo. |
| 1 | **Teclado matricial 4×4** | Filas GPIO 13, 14, 26, 27; columnas GPIO 25, 33, 32, 4. |
| 1 | **Kit Celda Peltier** | Incluye celda y disipadores; se conmuta mediante el relé controlado por GPIO 19. |
| 1 | **Foco Incandescente** | 60 W; la potencia la regula un dimmer mecánico posicionado por el servo de GPIO 21. |
| 2 | **Ventiladores 12V** | Para circulación de aire y apoyo en el proceso de purga. |
| 3 | **Servomotores** | Dos para las tapas de purga (GPIO 22 y 23) y uno para posicionar el dimmer del foco (GPIO 21). |
| 1 | **Módulo Relé** | Conmuta la Peltier mediante GPIO 19; el foco no está conectado al relé. |
| 1 | **Mosfet** | IRFZ44N para la carga de CC que corresponda al montaje; no regula el foco. |
| 1 | **Fuente para servos** | Fuente regulada adecuada a la corriente de los tres servos, con GND común al ESP32. |
| 1 | **Protoboard y Cables** | Para el prototipado de las conexiones de control. |

## 📦 Materiales de Construcción de la Cámara

| Cantidad | Componente | Especificaciones / Función |
| :---: | :--- | :--- |
| 6 | **Caras de Triplay** | 30 x 30 cm (Estructura rígida y soporte mecánico de la caja). |
| 6 | **Caras de Unicel** | 30 x 30 cm (Aislante térmico interno para evitar pérdidas de calor/frío). |

## ⚙️ Lógica del Sistema
- **Control por Histéresis:** Evita el ciclado excesivo del foco y el Peltier.
- **Límites de temperatura:** Se ajustan desde la interfaz o el teclado entre 20 y 50 °C, con al menos 2 °C de diferencia.
- **Teclado 4×4:** Con la interfaz conectada, inicia en modo A: 2/4/6/8 mueven el foco, 1/3 cambian un control numérico en ±0.5 y # selecciona/abre. En un valor numérico, # pasa a modo B para escribir dígitos y * decimal; # confirma y vuelve a A. B activa el modo numérico y A regresa a navegación. C inicia el ciclo hacia la mínima y D detiene todo. Sin la interfaz conectada, el ESP32 conserva el control local anterior del teclado.
- **Purga Automática:** Durante el ciclo térmico, se activa al alcanzar el límite máximo o al enfriar 2.5 °C por debajo de ese límite. El punto de rocío se calcula si las lecturas de humedad del DHT11 son válidas.
- **Dimmer del foco:** El servo en GPIO 21 sigue la salida PID entre `ANGULO_DIMER_MINIMO` y `ANGULO_DIMER_MAXIMO` (configuración inicial: 0° apagado y 100° máxima potencia), avanzando hasta 5° cada 20 ms. Estos valores están al inicio del sketch para calibrarlos gradualmente sin forzar el tope mecánico. El foco no usa el relé; GPIO 19 acciona el relé de la Peltier. El firmware reporta potencia solicitada y ángulo comandado.