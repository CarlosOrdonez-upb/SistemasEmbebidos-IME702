#include <DHT.h>
#include <ESP32Servo.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

const uint8_t DHTPIN = 4;
const uint8_t PIN_FOCO = 16;
const uint8_t PIN_PELTIER = 19;
const uint8_t PIN_FANS = 18;
const uint8_t PIN_SERVO_TAPA_1 = 22;
const uint8_t PIN_SERVO_TAPA_2 = 23;

const uint8_t SERVO_CERRADO = 0;
const uint8_t SERVO_ABIERTO = 90;
const float HISTERESIS = 0.5f;
const float CAMBIO_PARA_PURGA = 2.5f;
const float SETPOINT_MINIMO = 20.0f;
const float SETPOINT_MAXIMO = 50.0f;

const unsigned long INTERVALO_SENSOR_MS = 2000;
const unsigned long INTERVALO_ESTADO_MS = 500;
const unsigned long ESPERA_APERTURA_MS = 1250;
const unsigned long TIEMPO_VENTILACION_MS = 10000;
const unsigned long ESPERA_CIERRE_MS = 10000;
const unsigned long TIEMPO_SERVO_MS = 400;

enum Fase {
  NORMAL,
  PURGA_APERTURA,
  PURGA_VENTILACION,
  PURGA_ESPERA,
  PURGA_CIERRE,
  ERROR_SENSOR
};

enum ModoTermico {
  MODO_MANTENER,
  MODO_CALENTAR,
  MODO_ENFRIAR
};

DHT dht(DHTPIN, DHT11);
Servo servoTapa1;
Servo servoTapa2;

Fase fase = NORMAL;
ModoTermico modoTermico = MODO_MANTENER;
float temperaturaObjetivo = 35.0f;
float temperaturaActual = NAN;
float humedadActual = NAN;
bool sensorValido = false;
bool primeraLectura = true;
char bufferComando[48];
size_t indiceComando = 0;
unsigned long ultimoSensorMs = 0;
unsigned long ultimoEstadoMs = 0;
unsigned long inicioFaseMs = 0;

void escribirSalidas(bool foco, bool peltier, bool ventiladores) {
  if (foco && peltier) {
    peltier = false;
  }
  digitalWrite(PIN_FOCO, foco ? HIGH : LOW);
  digitalWrite(PIN_PELTIER, peltier ? HIGH : LOW);
  digitalWrite(PIN_FANS, ventiladores ? HIGH : LOW);
}

void iniciarPurga(unsigned long ahora) {
  escribirSalidas(false, false, false);
  servoTapa1.write(SERVO_ABIERTO);
  servoTapa2.write(SERVO_ABIERTO);
  fase = PURGA_APERTURA;
  inicioFaseMs = ahora;
}

void procesarComando(char *comando, unsigned long ahora) {
  if (strncmp(comando, "SETPOINT,", 9) != 0) {
    return;
  }

  char *fin;
  float nuevoObjetivo = strtof(comando + 9, &fin);
  if (fin == comando + 9 || *fin != '\0' || !isfinite(nuevoObjetivo) ||
      nuevoObjetivo < SETPOINT_MINIMO || nuevoObjetivo > SETPOINT_MAXIMO) {
    Serial.println("ERR,SETPOINT,RANGE");
    return;
  }

  float objetivoAnterior = temperaturaObjetivo;
  temperaturaObjetivo = nuevoObjetivo;
  Serial.print("ACK,SETPOINT,");
  Serial.println(temperaturaObjetivo, 1);

  if (fase == NORMAL && sensorValido &&
      objetivoAnterior - nuevoObjetivo >= CAMBIO_PARA_PURGA) {
    iniciarPurga(ahora);
  }
}

void leerComandos(unsigned long ahora) {
  while (Serial.available() > 0) {
    char caracter = static_cast<char>(Serial.read());
    if (caracter == '\r') {
      continue;
    }

    if (caracter == '\n') {
      bufferComando[indiceComando] = '\0';
      procesarComando(bufferComando, ahora);
      indiceComando = 0;
    } else if (indiceComando < sizeof(bufferComando) - 1) {
      bufferComando[indiceComando++] = caracter;
    } else {
      indiceComando = 0;
    }
  }
}

void actualizarSensor(unsigned long ahora) {
  if (fase == PURGA_APERTURA || fase == PURGA_VENTILACION ||
      fase == PURGA_ESPERA || fase == PURGA_CIERRE) {
    return;
  }

  if (!primeraLectura && ahora - ultimoSensorMs < INTERVALO_SENSOR_MS) {
    return;
  }

  primeraLectura = false;
  ultimoSensorMs = ahora;
  float temperatura = dht.readTemperature();
  float humedad = dht.readHumidity();

  if (isnan(temperatura) || isnan(humedad)) {
    sensorValido = false;
    fase = ERROR_SENSOR;
    modoTermico = MODO_MANTENER;
    escribirSalidas(false, false, false);
    servoTapa1.write(SERVO_CERRADO);
    servoTapa2.write(SERVO_CERRADO);
    return;
  }

  temperaturaActual = temperatura;
  humedadActual = humedad;
  sensorValido = true;
  if (fase == ERROR_SENSOR) {
    fase = NORMAL;
  }
}

void actualizarPurga(unsigned long ahora) {
  switch (fase) {
    case PURGA_APERTURA:
      if (ahora - inicioFaseMs >= ESPERA_APERTURA_MS) {
        fase = PURGA_VENTILACION;
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_VENTILACION:
      if (ahora - inicioFaseMs >= TIEMPO_VENTILACION_MS) {
        escribirSalidas(false, false, false);
        fase = PURGA_ESPERA;
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_ESPERA:
      if (ahora - inicioFaseMs >= ESPERA_CIERRE_MS) {
        servoTapa1.write(SERVO_CERRADO);
        servoTapa2.write(SERVO_CERRADO);
        fase = PURGA_CIERRE;
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_CIERRE:
      if (ahora - inicioFaseMs >= TIEMPO_SERVO_MS) {
        fase = NORMAL;
        modoTermico = MODO_MANTENER;
      }
      break;
    default:
      break;
  }
}

void actualizarControlTermico() {
  if (!sensorValido || fase != NORMAL) {
    escribirSalidas(false, false, fase == PURGA_VENTILACION);
    return;
  }

  if (modoTermico == MODO_CALENTAR && temperaturaActual >= temperaturaObjetivo) {
    modoTermico = MODO_MANTENER;
  } else if (modoTermico == MODO_ENFRIAR && temperaturaActual <= temperaturaObjetivo) {
    modoTermico = MODO_MANTENER;
  }

  if (modoTermico == MODO_MANTENER) {
    if (temperaturaActual <= temperaturaObjetivo - HISTERESIS) {
      modoTermico = MODO_CALENTAR;
    } else if (temperaturaActual >= temperaturaObjetivo + HISTERESIS) {
      modoTermico = MODO_ENFRIAR;
    }
  }

  escribirSalidas(
    modoTermico == MODO_CALENTAR,
    modoTermico == MODO_ENFRIAR,
    false
  );
}

const char *nombreFase() {
  switch (fase) {
    case PURGA_APERTURA: return "PURGE_OPENING";
    case PURGA_VENTILACION: return "PURGE_RUNNING";
    case PURGA_ESPERA: return "PURGE_WAIT";
    case PURGA_CIERRE: return "PURGE_CLOSING";
    case ERROR_SENSOR: return "SENSOR_ERROR";
    case NORMAL:
      if (modoTermico == MODO_CALENTAR) return "HEATING";
      if (modoTermico == MODO_ENFRIAR) return "COOLING";
      return "HOLD";
  }
  return "HOLD";
}

void enviarEstado(unsigned long ahora) {
  if (ahora - ultimoEstadoMs < INTERVALO_ESTADO_MS) {
    return;
  }
  ultimoEstadoMs = ahora;

  if (!sensorValido) {
    Serial.print("STATUS,ERROR,0,0,0,0,SENSOR_ERROR,0.0,");
    Serial.println(temperaturaObjetivo, 1);
    return;
  }

  Serial.print("STATUS,");
  Serial.print(temperaturaActual, 1);
  Serial.print(',');
  Serial.print(digitalRead(PIN_FOCO));
  Serial.print(',');
  Serial.print(digitalRead(PIN_PELTIER));
  Serial.print(',');
  Serial.print(digitalRead(PIN_FANS));
  Serial.print(',');
  bool tapasAbiertas = fase == PURGA_APERTURA || fase == PURGA_VENTILACION ||
                       fase == PURGA_ESPERA || fase == PURGA_CIERRE;
  Serial.print(tapasAbiertas ? 1 : 0);
  Serial.print(',');
  Serial.print(nombreFase());
  Serial.print(',');
  Serial.print(humedadActual, 1);
  Serial.print(',');
  Serial.println(temperaturaObjetivo, 1);
}

void setup() {
  Serial.begin(115200);
  dht.begin();

  pinMode(PIN_FOCO, OUTPUT);
  pinMode(PIN_PELTIER, OUTPUT);
  pinMode(PIN_FANS, OUTPUT);
  escribirSalidas(false, false, false);

  servoTapa1.setPeriodHertz(50);
  servoTapa2.setPeriodHertz(50);
  servoTapa1.attach(PIN_SERVO_TAPA_1, 500, 2400);
  servoTapa2.attach(PIN_SERVO_TAPA_2, 500, 2400);
  servoTapa1.write(SERVO_CERRADO);
  servoTapa2.write(SERVO_CERRADO);
}

void loop() {
  unsigned long ahora = millis();
  leerComandos(ahora);
  actualizarSensor(ahora);
  actualizarPurga(ahora);
  actualizarControlTermico();
  enviarEstado(ahora);
}