# ⚙️ Sistemas Embebidos - IME702

Repositorio dedicado al desarrollo, documentación y simulación de las prácticas de laboratorio de la materia de Sistemas Embebidos.

## 💻 Tecnologías y Herramientas

<div align="center">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/arduino/arduino-original.svg" width="50" title="Arduino IDE"/>
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/cplusplus/cplusplus-original.svg" width="50" title="C++"/>
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/espressif/espressif-original.svg" width="50" title="ESP32"/>
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/github/github-original.svg" width="50" title="GitHub"/>
</div>

---

## 👥 Equipo de Trabajo
- **Carlos Ordóñez**
- **Negrete**
- **Iván**
- **Karol**
- **Francisco**

---

## 📚 Prácticas Realizadas

| # | Práctica | Descripción | Estado | Links Rápidos |
|---|----------|-------------|--------|---------------|
| 01 | **[Control de LED con Botones](./Practica1/)** | Encendido y apagado de un LED mediante dos pulsadores con pull-up interna. | ✅ Completada | [📄 Código](./Practica1/codigo/control_led.ino) • [📦 Materiales](./Practica1/materiales.md) |
| 02 | **[Control de Motorreductor con Relé](./Practica2/)** | Activación de un motor DC 3V-5V usando un módulo de relé como etapa de potencia. | ✅ Completada | [📄 Código](./Practica2/codigo/control_motor_rele.ino) • [📦 Materiales](./Practica2/materiales.md) |

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
*Desarrollado como parte del curso IME702 - Sistemas Embebidos - Universidad Politécnica del Bicentenario 2026.*
