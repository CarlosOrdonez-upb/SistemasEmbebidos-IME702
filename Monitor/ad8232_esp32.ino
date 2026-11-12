// Pines conectados al módulo AD8232.
const int ECG_OUTPUT_PIN = 34;
const int LEAD_OFF_POSITIVE_PIN = 25;
const int LEAD_OFF_NEGATIVE_PIN = 26;
const int SHUTDOWN_PIN = 27;

bool previousLeadsOk = false;
bool leadsStatusInitialized = false;

void setup() {
  // Inicializa la comunicación serial y el ADC a 12 bits (0-4095).
  Serial.begin(115200);
  analogReadResolution(12);

  // Activa el AD8232 y configura las entradas de detección de electrodos.
  pinMode(SHUTDOWN_PIN, OUTPUT);
  digitalWrite(SHUTDOWN_PIN, HIGH);
  pinMode(LEAD_OFF_POSITIVE_PIN, INPUT);
  pinMode(LEAD_OFF_NEGATIVE_PIN, INPUT);
}

void loop() {
  // Lee y envía continuamente la señal analógica del ECG.
  const int value = analogRead(ECG_OUTPUT_PIN);
  Serial.print("valor:");
  Serial.println(value);

  // Envia el estado inicial de electrodos y luego solo los cambios.
  const bool leadsOk =
      digitalRead(LEAD_OFF_POSITIVE_PIN) == LOW &&
      digitalRead(LEAD_OFF_NEGATIVE_PIN) == LOW;
  if (!leadsStatusInitialized || leadsOk != previousLeadsOk) {
    Serial.print("leads:");
    Serial.println(leadsOk ? "OK" : "ERROR");
    previousLeadsOk = leadsOk;
    leadsStatusInitialized = true;
  }
}
