
![Banner-Inicio](./sources/Banner.gif)

# ⚙️ Sistemas Embebidos - IME702

Repositorio dedicado al desarrollo, documentación y simulación de proyectos de laboratorio de la materia de Sistemas Embebidos, impartida por el Dr. Hugo Antonio Méndez Guzmán.

## 💻 Tecnologías y Herramientas

<table>
  <tr>
    <td><img src="https://img.shields.io/badge/ESP32-DevKit_V1-blue?logo=espressif&logoColor=white" width="150"/></td>
    <td><img src="https://img.shields.io/badge/Arduino-IDE-orange?logo=arduino&logoColor=white" width="130"/></td>
    <td><img src="https://img.shields.io/badge/C%2B%2B-Programming-blue?logo=c%2B%2B&logoColor=white" width="140"/></td>
  </tr>
  <tr>
    <td><img src="https://img.shields.io/badge/Python-3.x-yellow?logo=python&logoColor=white" width="120"/></td>
    <td><img src="https://img.shields.io/badge/PyQt5-GUI-blue?logo=qt&logoColor=white" width="120"/></td>
    <td><img src="https://img.shields.io/badge/GitHub-Version_Control-gray?logo=github&logoColor=white" width="160"/></td>
  </tr>
</table>

---

## 👥 Equipo de Trabajo

| <img src="sources/carlos.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Coach (Líder)</b></sub> | <img src="sources/karol.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Documentación</b></sub> | <img src="sources/negrete.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Logística</b></sub> | <img src="sources/ivan.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Prototipador</b></sub> | <img src="sources/francisco.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Investigación</b></sub> |
| :---: | :---: | :---: | :---: | :---: |
| **Jose Carlos** | **Karol Maria** | **Jorge Alberto** | **Carlos Iván** | **José Francisco** |
| *"¡Se mira bien...!"* | *"Que son 13 !!"* | *"Ya pedí todo en MercadoLibre"* | *"Si quieres, yo lo hago"* | *"¿Alguien va al Oxxo?"* |

---

## 📚 Proyectos Realizados

| # | Proyecto | Descripción | Estado | Links Rápidos |
|---|----------|-------------|--------|---------------|
| 01 | **[Control de LED](./01_Control_LED/)** | Lógica de botones y GPIOs con pull-up interna. | ✅ Completado | [📄 Código](./01_Control_LED/codigo/) • [📦 Materiales](./01_Control_LED/materiales.md) |
| 02 | **[Control de Relé](./02_Control_Rele/)** | Etapa de potencia y aislamiento para motores DC. | ✅ Completado | [📄 Código](./02_Control_Rele/codigo/) • [📦 Materiales](./02_Control_Rele/materiales.md) |
| 03 | **[Control de Bombas + GUI](./03_Control_Bombas/)** | Sistema con sensor ultrasónico, paradas de seguridad y panel de control en Tkinter. | ✅ Completado | [📄 Código](./03_Control_Bombas/codigo/) • [📦 Materiales](./03_Control_Bombas/materiales.md) |
| 04 | **[Caja Térmica Inteligente](./04_Caja_Termica/)** | Cámara con control PID/histéresis, módulo Peltier, servos para purga y simulación en PyQt5. | 🟨 En desarrollo | [📄 Firmware](./04_Caja_Termica/firmware/) • [💻 Simulación](./04_Caja_Termica/simulacion/) |

---

## 🌟 Destacado Técnico: Caja Térmica (Proyecto 04)

Este sistema representa un salto en complejidad, implementando conceptos de control térmico real:
1. **Lógica de Purga Automática:** Si el *setpoint* cambia drásticamente (≥ 2.5°C), el sistema abre las tapas mediante servomotores, activa los ventiladores para ventilar el aire estancado y cierra las tapas para estabilizar la temperatura rápidamente.
2. **Control por Histéresis:** Evita el ciclado excesivo del foco y el módulo Peltier, protegiendo los componentes.
3. **Simulación Visual (PyQt5):** Interfaz gráfica que renderiza en tiempo real el estado de los ventiladores, el color ambiente según la temperatura y la animación de partículas de flujo de aire.

---

## 🛠️ Hardware General Utilizado
- **Microcontrolador:** ESP32 DevKit V1
- **Sensores:** DHT11 (Temperatura/Humedad), HC-SR04 (Ultrasonido).
- **Actuadores:** Relés, Motorreductores, Bombas DC, Módulo Peltier, Servomotores.

> *Este repositorio se actualizará según los avances del curso.*

--- 
*Desarrollado como parte del curso Sistemas Embebidos - IME702 - Universidad Politécnica del Bicentenario 2026.*

---
## ⚖️ Aviso Legal y Derechos de Autor

© 2026 Equipo de Sistemas Embebidos (Carlos Ordóñez, Negrete, Iván, Karol, Francisco).  
**Todos los derechos reservados.**

Este repositorio y su contenido (código fuente, diagramas, documentación y simulaciones) han sido desarrollados exclusivamente con fines académicos y evaluativos para la materia **IME702 - Sistemas Embebidos**. 

Queda estrictamente prohibida su reproducción, distribución, modificación o uso comercial sin la autorización expresa y por escrito de los autores. El acceso a este repositorio no otorga ninguna licencia sobre las obras contenidas en él.
