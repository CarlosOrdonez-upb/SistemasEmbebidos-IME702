/*
 * Práctica 02: Control de Motorreductor con Relé
 * Equipo: Negrete, Iván, Karol, Francisco, Carlos
 * Descripción: Encendido y apagado de motor DC usando relé y pulsadores
 * Hardware: ESP32, módulo de relé, motorreductor 3V-5V, 2 botones
 */

// Definición de pines
const int relayPin = 2;    // GPIO 2 conectado a la entrada del relé
const int btnOn = 4;       // GPIO 4 conectado al botón ON
const int btnOff = 16;     // GPIO 16 conectado al botón OFF

void setup() {
  // Configurar pines
  pinMode(relayPin, OUTPUT);         // Relé como salida
  pinMode(btnOn, INPUT_PULLUP);      // Botón ON con pull-up interna
  pinMode(btnOff, INPUT_PULLUP);     // Botón OFF con pull-up interna
  
  // Estado inicial: Relé desactivado (motor apagado)
  // NOTA: LOW activa el relé, HIGH lo desactiva (depende del módulo)
  digitalWrite(relayPin, HIGH);      // Motor apagado inicialmente
}

void loop() {
  // Leer estado de los botones
  if (digitalRead(btnOn) == LOW) {
    // Botón ON presionado: activar relé (encender motor)
    digitalWrite(relayPin, LOW);     // LOW activa el relé
  }
  
  if (digitalRead(btnOff) == LOW) {
    // Botón OFF presionado: desactivar relé (apagar motor)
    digitalWrite(relayPin, HIGH);    // HIGH desactiva el relé
  }
}
