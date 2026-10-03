#include <DHT.h>
#include <ESP32Servo.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifdef DEBUG_MODE
#define DEBUG_PRINT(...) Serial.printf(__VA_ARGS__)
#else
#define DEBUG_PRINT(...) do {} while (0)
#endif

const uint8_t DHTPIN = 4;
const uint8_t PIN_FOCO = 5;
const uint8_t PIN_PELTIER = 19;
const uint8_t PIN_FANS = 18;
const uint8_t PIN_SERVO_TAPA_1 = 22;
const uint8_t PIN_SERVO_TAPA_2 = 23;

const uint8_t SERVO_CERRADO = 0;
const uint8_t SERVO_ABIERTO = 160;
const float CAMBIO_PARA_PURGA = 2.0f;
const float TEMPERATURA_CONFIG_MINIMA = 20.0f;
const float TEMPERATURA_CONFIG_MAXIMA = 50.0f;
const float TEMPERATURA_SENSOR_MINIMA = 10.0f;
const float TEMPERATURA_SENSOR_MAXIMA = 60.0f;
const float HUMEDAD_RIESGO_CONDENSACION = 90.0f;

const unsigned long INTERVALO_SENSOR_MS = 2000;
const unsigned long INTERVALO_ESTADO_MS = 500;
const unsigned long ESPERA_APERTURA_MS = 1250;
const unsigned long TIEMPO_VENTILACION_MS = 10000;
const unsigned long ESPERA_CIERRE_MS = 10000;
const unsigned long TIEMPO_SERVO_MS = 400;
const unsigned long TIMEOUT_COMUNICACION_MS = 30000;
const unsigned long TIEMPO_MAXIMO_FOCO_MS = 10UL * 60UL * 1000UL;
const unsigned long DESCANSO_FOCO_MS = 1UL * 60UL * 1000UL;
const unsigned long TIEMPO_MAXIMO_PELTIER_MS = 15UL * 60UL * 1000UL;
const unsigned long DESCANSO_PELTIER_MS = 2UL * 60UL * 1000UL;

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
float tempMinima = 28.0f;
float tempMaxima = 35.0f;
float temperaturaActual = NAN;
float humedadActual = NAN;
bool sensorValido = false;
bool primeraLectura = true;
bool modoPrueba = false;
bool humedadAlta = false;
bool timeoutComunicacionReportado = false;
bool focoEnDescanso = false;
bool peltierEnDescanso = false;
char bufferComando[48];
size_t indiceComando = 0;
unsigned long ultimoSensorMs = 0;
unsigned long ultimoEstadoMs = 0;
unsigned long inicioFaseMs = 0;
unsigned long ultimoComandoMs = 0;
unsigned long inicioFocoMs = 0;
unsigned long inicioPeltierMs = 0;
unsigned long inicioDescansoFocoMs = 0;
unsigned long inicioDescansoPeltierMs = 0;

const char *nombreFaseBase(Fase valor) {
  switch (valor) {
    case NORMAL: return "NORMAL";
    case PURGA_APERTURA: return "PURGA_APERTURA";
    case PURGA_VENTILACION: return "PURGA_VENTILACION";
    case PURGA_ESPERA: return "PURGA_ESPERA";
    case PURGA_CIERRE: return "PURGA_CIERRE";
    case ERROR_SENSOR: return "ERROR_SENSOR";
  }
  return "DESCONOCIDA";
}

void cambiarFase(Fase nuevaFase) {
  if (fase != nuevaFase) {
    DEBUG_PRINT("DEBUG,FASE,%s,%s\n",
                nombreFaseBase(fase), nombreFaseBase(nuevaFase));
    fase = nuevaFase;
  }
}

const char *nombreModoTermico(ModoTermico modo) {
  switch (modo) {
    case MODO_MANTENER: return "MANTENER";
    case MODO_CALENTAR: return "CALENTAR";
    case MODO_ENFRIAR: return "ENFRIAR";
  }
  return "DESCONOCIDO";
}

void cambiarModoTermico(ModoTermico nuevoModo) {
  if (modoTermico != nuevoModo) {
    DEBUG_PRINT("DEBUG,CONTROL,%s,%s\n",
                nombreModoTermico(modoTermico), nombreModoTermico(nuevoModo));
    modoTermico = nuevoModo;
  }
}

void limitarTiempoSalidas(bool &foco, bool &peltier, unsigned long ahora) {
  if (foco && peltier) {
    peltier = false;
  }

  bool focoActivo = digitalRead(PIN_FOCO) == HIGH;
  if (focoActivo && ahora - inicioFocoMs >= TIEMPO_MAXIMO_FOCO_MS) {
    focoEnDescanso = true;
    inicioDescansoFocoMs = ahora;
    focoActivo = false;
    DEBUG_PRINT("DEBUG,SEGURIDAD,FOCO_TIEMPO_MAXIMO\n");
  }
  if (focoEnDescanso &&
      ahora - inicioDescansoFocoMs >= DESCANSO_FOCO_MS) {
    focoEnDescanso = false;
    DEBUG_PRINT("DEBUG,SEGURIDAD,FOCO_DESCANSO_COMPLETO\n");
  }
  if (!focoActivo && foco && !focoEnDescanso) {
    inicioFocoMs = ahora;
    focoActivo = true;
  }
  if (!foco) {
    focoActivo = false;
  }

  bool peltierActiva = digitalRead(PIN_PELTIER) == HIGH;
  if (peltierActiva &&
      ahora - inicioPeltierMs >= TIEMPO_MAXIMO_PELTIER_MS) {
    peltierEnDescanso = true;
    inicioDescansoPeltierMs = ahora;
    peltierActiva = false;
    DEBUG_PRINT("DEBUG,SEGURIDAD,PELTIER_TIEMPO_MAXIMO\n");
  }
  if (peltierEnDescanso &&
      ahora - inicioDescansoPeltierMs >= DESCANSO_PELTIER_MS) {
    peltierEnDescanso = false;
    DEBUG_PRINT("DEBUG,SEGURIDAD,PELTIER_DESCANSO_COMPLETO\n");
  }
  if (!peltierActiva && peltier && !peltierEnDescanso) {
    inicioPeltierMs = ahora;
    peltierActiva = true;
  }
  if (!peltier) {
    peltierActiva = false;
  }

  foco = foco && !focoEnDescanso;
  peltier = peltier && !peltierEnDescanso;
}

void escribirSalidas(bool foco, bool peltier, bool ventiladores) {
  unsigned long ahora = millis();
  limitarTiempoSalidas(foco, peltier, ahora);
  bool focoEstabaActivo = digitalRead(PIN_FOCO) == HIGH;
  bool peltierEstabaActiva = digitalRead(PIN_PELTIER) == HIGH;
  digitalWrite(PIN_FOCO, foco ? HIGH : LOW);
  digitalWrite(PIN_PELTIER, peltier ? HIGH : LOW);
  digitalWrite(PIN_FANS, ventiladores ? HIGH : LOW);
  if (focoEstabaActivo != foco) {
    DEBUG_PRINT("DEBUG,SALIDA,FOCO,%s\n", foco ? "ON" : "OFF");
  }
  if (peltierEstabaActiva != peltier) {
    DEBUG_PRINT("DEBUG,SALIDA,PELTIER,%s\n", peltier ? "ON" : "OFF");
  }
}

void iniciarPurga(unsigned long ahora) {
  escribirSalidas(false, false, false);
  servoTapa1.write(SERVO_ABIERTO);
  servoTapa2.write(SERVO_ABIERTO);
  cambiarFase(PURGA_APERTURA);
  inicioFaseMs = ahora;
}

void procesarComando(char *comando, unsigned long ahora) {
  ultimoComandoMs = ahora;
  timeoutComunicacionReportado = false;
  if (strcmp(comando, "TEST,1") == 0 || strcmp(comando, "TEST,0") == 0) {
    bool activar = comando[5] == '1';
    if (modoPrueba != activar) {
      modoPrueba = activar;
      cambiarFase(sensorValido ? NORMAL : ERROR_SENSOR);
      cambiarModoTermico(MODO_MANTENER);
      if (modoPrueba) {
        servoTapa1.write(SERVO_ABIERTO);
        servoTapa2.write(SERVO_ABIERTO);
        escribirSalidas(false, false, true);
      } else {
        servoTapa1.write(SERVO_CERRADO);
        servoTapa2.write(SERVO_CERRADO);
        escribirSalidas(false, false, false);
      }
    }
    Serial.print("ACK,TEST,");
    Serial.println(modoPrueba ? "ON" : "OFF");
    return;
  }

  if (strncmp(comando, "SETRANGE,", 9) != 0) {
    return;
  }

  char *finMinima;
  float nuevaMinima = strtof(comando + 9, &finMinima);
  if (finMinima == comando + 9 || *finMinima != ',') {
    Serial.println("ERR,SETRANGE,FORMAT");
    return;
  }

  char *inicioMaxima = finMinima + 1;
  char *finMaxima;
  float nuevaMaxima = strtof(inicioMaxima, &finMaxima);
  if (finMaxima == inicioMaxima || *finMaxima != '\0' ||
      !isfinite(nuevaMinima) || !isfinite(nuevaMaxima) ||
      nuevaMinima < TEMPERATURA_CONFIG_MINIMA ||
      nuevaMinima > TEMPERATURA_CONFIG_MAXIMA ||
      nuevaMaxima < TEMPERATURA_CONFIG_MINIMA ||
      nuevaMaxima > TEMPERATURA_CONFIG_MAXIMA ||
      nuevaMinima >= nuevaMaxima) {
    Serial.println("ERR,SETRANGE,RANGE");
    return;
  }

  bool rangoCambio = nuevaMinima != tempMinima || nuevaMaxima != tempMaxima;
  tempMinima = nuevaMinima;
  tempMaxima = nuevaMaxima;
  Serial.print("ACK,SETRANGE,");
  Serial.print(tempMinima, 1);
  Serial.print(',');
  Serial.println(tempMaxima, 1);

  float diferenciaLimite = 0.0f;
  if (temperaturaActual < tempMinima) {
    diferenciaLimite = tempMinima - temperaturaActual;
  } else if (temperaturaActual > tempMaxima) {
    diferenciaLimite = temperaturaActual - tempMaxima;
  }
  if (rangoCambio && diferenciaLimite > CAMBIO_PARA_PURGA &&
      !modoPrueba && fase == NORMAL && sensorValido) {
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
  if (!primeraLectura && ahora - ultimoSensorMs < INTERVALO_SENSOR_MS) {
    return;
  }

  primeraLectura = false;
  ultimoSensorMs = ahora;
  float temperatura = dht.readTemperature();
  float humedad = dht.readHumidity();

  if (isnan(temperatura) || isnan(humedad)) {
    sensorValido = false;
    modoPrueba = false;
    cambiarFase(ERROR_SENSOR);
    cambiarModoTermico(MODO_MANTENER);
    escribirSalidas(false, false, false);
    servoTapa1.write(SERVO_CERRADO);
    servoTapa2.write(SERVO_CERRADO);
    return;
  }

  bool humedadAhoraAlta = humedad > HUMEDAD_RIESGO_CONDENSACION;
  if (humedadAhoraAlta && !humedadAlta) {
    Serial.println("WARN,HUMIDITY,CONDENSATION_RISK");
    DEBUG_PRINT("DEBUG,SEGURIDAD,HUMEDAD_ALTA,%.1f\n", humedad);
  } else if (!humedadAhoraAlta && humedadAlta) {
    DEBUG_PRINT("DEBUG,SEGURIDAD,HUMEDAD_NORMAL,%.1f\n", humedad);
  }
  humedadAlta = humedadAhoraAlta;

  if (temperatura < TEMPERATURA_SENSOR_MINIMA ||
      temperatura > TEMPERATURA_SENSOR_MAXIMA) {
    sensorValido = false;
    modoPrueba = false;
    cambiarFase(ERROR_SENSOR);
    cambiarModoTermico(MODO_MANTENER);
    escribirSalidas(false, false, false);
    servoTapa1.write(SERVO_CERRADO);
    servoTapa2.write(SERVO_CERRADO);
    DEBUG_PRINT("DEBUG,SEGURIDAD,TEMPERATURA_FUERA_RANGO,%.1f\n",
                temperatura);
    return;
  }

  temperaturaActual = temperatura;
  humedadActual = humedad;
  sensorValido = true;
  if (fase == ERROR_SENSOR) {
    cambiarFase(NORMAL);
  }
}

void actualizarPurga(unsigned long ahora) {
  switch (fase) {
    case PURGA_APERTURA:
      if (ahora - inicioFaseMs >= ESPERA_APERTURA_MS) {
        cambiarFase(PURGA_VENTILACION);
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_VENTILACION:
      if (ahora - inicioFaseMs >= TIEMPO_VENTILACION_MS) {
        escribirSalidas(false, false, false);
        cambiarFase(PURGA_ESPERA);
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_ESPERA:
      if (ahora - inicioFaseMs >= ESPERA_CIERRE_MS) {
        servoTapa1.write(SERVO_CERRADO);
        servoTapa2.write(SERVO_CERRADO);
        cambiarFase(PURGA_CIERRE);
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_CIERRE:
      if (ahora - inicioFaseMs >= TIEMPO_SERVO_MS) {
        cambiarFase(NORMAL);
        cambiarModoTermico(MODO_MANTENER);
      }
      break;
    default:
      break;
  }
}

void actualizarControlTermico() {
  if (modoPrueba) {
    escribirSalidas(false, false, true);
    return;
  }

  if (!sensorValido || fase != NORMAL) {
    escribirSalidas(false, false, fase == PURGA_VENTILACION);
    return;
  }

  if (temperaturaActual < tempMinima) {
    cambiarModoTermico(MODO_CALENTAR);
  } else if (temperaturaActual > tempMaxima) {
    cambiarModoTermico(MODO_ENFRIAR);
  } else {
    cambiarModoTermico(MODO_MANTENER);
  }

  bool focoSolicitado = modoTermico == MODO_CALENTAR;
  bool peltierSolicitada = modoTermico == MODO_ENFRIAR;
  escribirSalidas(
    focoSolicitado,
    peltierSolicitada,
    false
  );
  if ((focoSolicitado && digitalRead(PIN_FOCO) == LOW) ||
      (peltierSolicitada && digitalRead(PIN_PELTIER) == LOW)) {
    DEBUG_PRINT("DEBUG,CONTROL,ESPERANDO_DESCANSO\n");
  }
}

void actualizarTimeoutComunicacion(unsigned long ahora) {
  if (!timeoutComunicacionReportado &&
      ahora - ultimoComandoMs >= TIMEOUT_COMUNICACION_MS) {
    timeoutComunicacionReportado = true;
    DEBUG_PRINT("DEBUG,COMUNICACION,TIMEOUT; conservando rango y control local\n");
  }
}

const char *nombreFase() {
  if (modoPrueba) return "TESTING";

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
    Serial.print("STATUS,ERROR,0,0,");
    Serial.print(digitalRead(PIN_FANS));
    Serial.print(',');
    Serial.print(modoPrueba ? 1 : 0);
    Serial.print(',');
    Serial.print(modoPrueba ? "TESTING" : "SENSOR_ERROR");
    Serial.print(",0.0,");
    Serial.print(tempMinima, 1);
    Serial.print(',');
    Serial.println(tempMaxima, 1);
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
  bool tapasAbiertas = modoPrueba || fase == PURGA_APERTURA ||
                       fase == PURGA_VENTILACION || fase == PURGA_ESPERA ||
                       fase == PURGA_CIERRE;
  Serial.print(tapasAbiertas ? 1 : 0);
  Serial.print(',');
  Serial.print(nombreFase());
  Serial.print(',');
  Serial.print(humedadActual, 1);
  Serial.print(',');
  Serial.print(tempMinima, 1);
  Serial.print(',');
  Serial.println(tempMaxima, 1);
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
  actualizarTimeoutComunicacion(ahora);
  actualizarSensor(ahora);
  actualizarPurga(ahora);
  actualizarControlTermico();
  enviarEstado(ahora);
}