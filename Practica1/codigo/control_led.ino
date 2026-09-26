/*
 * Práctica 01: Control de LED con Dos Botones
 * Equipo: Negrete, Iván, Karol, Francisco, Carlos
 * Descripción: Encendido y apagado de LED mediante pulsadores
 * Hardware: ESP32, 2 botones, LED, resistencia 220Ω
 */

// Definición de pines
const int ledPin = 2;      // GPIO 2 conectado al LED
const int btnOn = 4;       // GPIO 4 conectado al botón ON
const int btnOff = 16;     // GPIO 16 conectado al botón OFF

void setup() {
  // Configurar pines
  pinMode(ledPin, OUTPUT);           // LED como salida
  pinMode(btnOn, INPUT_PULLUP);      // Botón ON con pull-up interna
  pinMode(btnOff, INPUT_PULLUP);     // Botón OFF con pull-up interna
  
  // Estado inicial: LED apagado
  digitalWrite(ledPin, LOW);
}

void loop() {
  // Leer estado de los botones (LOW = presionado por pull-up)
  if (digitalRead(btnOn) == LOW) {
    digitalWrite(ledPin, HIGH);      // Encender LED
  }
  
  if (digitalRead(btnOff) == LOW) {
    digitalWrite(ledPin, LOW);       // Apagar LED
  }
}
