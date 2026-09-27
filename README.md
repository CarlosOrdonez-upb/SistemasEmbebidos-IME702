
![Banner-Inicio](./sources/Banner.gif)

# ⚙️ Sistemas Embebidos - IME702

Repositorio dedicado al desarrollo, documentación y simulación de las prácticas de laboratorio de la materia de Sistemas Embebidos impartida por el Dr.Hugo Antonio Mendez Guzman.

## 💻 Tecnologías y Herramientas

<table>
  <tr>
    <td><img src="https://img.shields.io/badge/ESP32-DevKit_V1-blue?logo=espressif&logoColor=white" width="150"/></td>
    <td><img src="https://img.shields.io/badge/Arduino-IDE-orange?logo=arduino&logoColor=white" width="130"/></td>
    <td><img src="https://img.shields.io/badge/C%2B%2B-Programming-blue?logo=c%2B%2B&logoColor=white" width="140"/></td>
  </tr>
  <tr>
    <td><img src="https://img.shields.io/badge/Wokwi-Simulation-purple?logo=google-chrome&logoColor=white" width="150"/></td>
    <td><img src="https://img.shields.io/badge/Framework-Arduino-teal?logo=arduino&logoColor=white" width="140"/></td>
    <td><img src="https://img.shields.io/badge/GitHub-Version_Control-gray?logo=github&logoColor=white" width="160"/></td>
  </tr>
</table>

---

## 👥 Equipo de Trabajo


| [<img src="sources/carlos.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>El profe (Programacion)</b></sub>](#) | [<img src="sources/karol.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Karol (Documentacion)</b></sub>](#) | [<img src="sources/negrete.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Negrete (Compras)</b></sub>](#) | [<img src="sources/ivan.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Ivan (Prototipador)</b></sub>](#) | [<img src="sources/francisco.jpg" width="120" height="120" style="border-radius:15px;"><br><sub><b>Francisco (Investigacion)</b></sub>](#) |
| :---: | :---: | :---: | :---: | :---: |
| **Jose Carlos Ordoñez Bravo** | **Karol Maria Guadalupe Carrion Villagomez** | **Jorge Alberto Negrete Garnica** | **Carlos Iván Hernandez Castro** | **José Francisco Cadena Martinez** |
| *"Se mira bien ..."* | *"Asi no lo queria el profe!! "* | *"Ya pedi todo en MercadoLibre"* | *"Si quieres yo lo hago"* | *"¿Alguien va al Oxxo?"* |
---

## 📚 Prácticas Realizadas

| # | Práctica | Descripción | Estado | Links Rápidos |
|---|----------|-------------|--------|---------------|
| 01 | **[Control de LED con Botones](./Practica1/)** | Encendido y apagado de un LED mediante dos pulsadores. | ✅ Completada | [📄 Código](./Practica1/codigo/control_led.ino) • [📦 Materiales](./Practica1/materiales.md) |
| 02 | **[Control de Motorreductor con Relé](./Practica2/)** | Activación de un motor DC 3V-5V usando un módulo de relé como etapa de potencia. | ✅ Completada | [📄 Código](./Practica2/codigo/control_motor_rele.ino) • [📦 Materiales](./Practica2/materiales.md) |
| 03 | **[Control de Llenado/Vaciado + GUI Python](./Practica3/)** | Sistema con sensor ultrasónico, paradas de seguridad y panel de control en Tkinter. | 🟨 Pendiente de revision | [📦 Materiales](./Practica3/materiales.md) |

---

## 🛠️ Hardware Utilizado
- **Microcontrolador:** ESP32 DevKit V1
- **Entorno de Desarrollo:** Arduino IDE
- **Componentes:** Botones pulsadores (4 pines), LEDs, Motorreductor 3V-5V, Módulo de Relé, Resistencias, Protoboard, Cables Dupont.

## 📋 Notas Importantes
- Cada carpeta de práctica (`Practica1`, `Practica2`) contiene su propio `README.md` con el diagrama de conexiones, objetivo y funcionamiento detallado.
- Se utiliza la configuración de **pull-up interna** de la ESP32 para los botones, por lo que se activan en estado `LOW`.
- El módulo de relé se activa con nivel `LOW` en el GPIO correspondiente.

---

## 🗺️ Roadmap (Próximas Prácticas)

- [ ] **Práctica 03:** Control de Llenado/Vaciado
- [ ] **Práctica 04:** Control de temperatura (UART)
- [ ] **Práctica 05:** Pendiente....

> *Este repositorio se actualizará según los avances del curso.*

--- 
*Desarrollado como parte del curso Sistemas Embebidos - IME702 - Universidad Politécnica del Bicentenario 2026.*

---
## ⚖️ Aviso Legal y Derechos de Autor

© 2026 Equipo de Sistemas Embebidos (Carlos Ordóñez, Negrete, Iván, Karol, Francisco).  
**Todos los derechos reservados.**

Este repositorio y su contenido (código fuente, diagramas, documentación y simulaciones) han sido desarrollados exclusivamente con fines académicos y evaluativos para la materia **IME702 - Sistemas Embebidos**. 

Queda estrictamente prohibida su reproducción, distribución, modificación o uso comercial sin la autorización expresa y por escrito de los autores. El acceso a este repositorio no otorga ninguna licencia sobre las obras contenidas en él.
