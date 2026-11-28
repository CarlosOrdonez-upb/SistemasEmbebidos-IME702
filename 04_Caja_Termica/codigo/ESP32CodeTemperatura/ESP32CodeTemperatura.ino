#include <Arduino.h>
#include <ESP32Servo.h>
#include <DHT.h>
#include <PID_v1.h>
#include <WiFi.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

const char *const WIFI_SSID = "TU_WIFI";
const char *const WIFI_PASSWORD = "TU_CONTRASENA";

WiFiServer server(8888);
WiFiClient client;
HardwareSerial &serialUsb = Serial;

class SalidaDual : public Print {
 public:
  void begin(unsigned long velocidad) {
    serialUsb.begin(velocidad);
  }

  int available() {
    return serialUsb.available();
  }

  int read() {
    return serialUsb.read();
  }

  size_t write(uint8_t valor) override {
    size_t enviados = serialUsb.write(valor);
    if (client && client.connected()) {
      client.write(valor);
    }
    return enviados;
  }

  size_t write(const uint8_t *datos, size_t longitud) override {
    size_t enviados = serialUsb.write(datos, longitud);
    if (client && client.connected()) {
      client.write(datos, longitud);
    }
    return enviados;
  }
};

SalidaDual salidaDual;
#define Serial salidaDual

#define DHTPIN 15
#define DHTTYPE DHT11

#ifdef DEBUG_MODE
#define DEBUG_PRINT(...) serialUsb.printf(__VA_ARGS__)
#else
#define DEBUG_PRINT(...) do {} while (0)
#endif



const uint8_t PIN_PELTIER = 19;
const uint8_t PIN_FANS = 18;
const uint8_t PIN_SERVO_TAPA_1 = 22;
const uint8_t PIN_SERVO_TAPA_2 = 23;
const uint8_t PIN_SERVO_DIMER = 21;
const uint8_t PIN_TECLADO_FILAS[4] = {13, 14, 26, 27};
const uint8_t PIN_TECLADO_COLUMNAS[4] = {25, 33, 32, 4};

const uint8_t SERVO_CERRADO = 0;
const uint8_t SERVO_ABIERTO = 160;
// CALIBRACION DEL DIMMER: ajustar al recorrido mecanico del mando.
const int ANGULO_DIMER_MINIMO = 0;  // Posicion de dimmer apagado.
const int ANGULO_DIMER_MAXIMO = 100;  // Aumentar gradualmente si hace falta.
// No superar 180 grados ni forzar el tope mecanico del dimmer.
const int PASO_SERVO_DIMER_GRADOS = 5;
const float POTENCIA_DIMER_PRUEBA = 50.0f;
const float TEMPERATURA_CONFIG_MINIMA = 20.0f;
const float TEMPERATURA_CONFIG_MAXIMA = 50.0f;
const float TEMPERATURA_SENSOR_MINIMA = 0.0f;
const float TEMPERATURA_SENSOR_MAXIMA = 50.0f;
const float DIFERENCIA_PURGA_AUTOMATICA = 2.5f;

const unsigned long INTERVALO_SENSOR_MS = 2000;
const unsigned long INTERVALO_ESTADO_MS = 250;
const unsigned long INTERVALO_TEMPERATURA_SERIAL_MS = 2000;
const unsigned long VENTANA_PID_MS = 60000;
const unsigned long INTERVALO_TECLADO_MS = 5;
const unsigned long INTERVALO_PASO_SERVO_DIMER_MS = 20;
const unsigned long DURACION_PRUEBA_DIMER_MS = 1000;
const unsigned long ANTIRREBOTE_TECLADO_MS = 35;
const unsigned long ESPERA_APERTURA_MS = 1250;
const unsigned long TIEMPO_VENTILACION_MS = 20000;
const unsigned long TIEMPO_SERVO_MS = 400;
const unsigned long TIMEOUT_COMUNICACION_MS = 30000;
const unsigned long TIMEOUT_TECLADO_UI_MS = 5000;
const unsigned long TIEMPO_MAXIMO_FOCO_MS = 10UL * 60UL * 1000UL;
const unsigned long DESCANSO_FOCO_MS = 1UL * 60UL * 1000UL;
const unsigned long TIEMPO_MAXIMO_PELTIER_MS = 15UL * 60UL * 1000UL;
const unsigned long DESCANSO_PELTIER_MS = 2UL * 60UL * 1000UL;

enum Fase {
  NORMAL,
  PURGA_APERTURA,
  PURGA_VENTILACION,
  PURGA_CIERRE,
  ERROR_SENSOR
};

enum ModoTermico {
  MODO_MANTENER,
  MODO_CALENTAR,
  MODO_ENFRIAR
};

enum CampoRango {
  SIN_EDICION,
  EDITANDO_MINIMO,
  EDITANDO_MAXIMO
};

enum ModoPID {
  PID_INACTIVO,
  PID_CALENTAR,
  PID_ENFRIAR
};

enum EstadoPruebaDimer {
  PRUEBA_DIMER_INACTIVA,
  PRUEBA_DIMER_SUBIENDO,
  PRUEBA_DIMER_MANTENIENDO,
  PRUEBA_DIMER_REGRESANDO
};

Servo servoTapa1;
Servo servoTapa2;
Servo servoDimer;
DHT dht(DHTPIN, DHTTYPE);
double Setpoint = 28.0;
double Input = 0.0;
double salidaPIDCalentar = 0.0;
double salidaPIDEnfriar = 0.0;
double Kp = 2.0;
double Ki = 0.5;
double Kd = 1.0;
float potenciaFocoAplicada = 0.0f;
int anguloServoDimerActual = ANGULO_DIMER_MINIMO;
int anguloServoDimerObjetivo = ANGULO_DIMER_MINIMO;
PID pidCalentar(&Input, &salidaPIDCalentar, &Setpoint, Kp, Ki, Kd, DIRECT);
PID pidEnfriar(&Input, &salidaPIDEnfriar, &Setpoint, Kp, Ki, Kd, REVERSE);

Fase fase = NORMAL;
ModoTermico modoTermico = MODO_MANTENER;
ModoTermico modoCiclo = MODO_CALENTAR;
float tempMinima = 28.0f;
float tempMaxima = 35.0f;
float temperaturaActual = NAN;
float humedadActual = NAN;
CampoRango campoRangoEnEdicion = SIN_EDICION;
char bufferEntradaRango[6];
size_t longitudEntradaRango = 0;
ModoPID modoPid = PID_INACTIVO;
bool sensorValido = false;
bool primeraLectura = true;
bool modoPrueba = false;
bool cicloActivo = false;
bool controlDetenido = true;
bool controlPidActivo = false;
bool tecladoUiActivo = false;
bool objetivoCicloMaximo = true;
EstadoPruebaDimer estadoPruebaDimer = PRUEBA_DIMER_INACTIVA;
bool purgaAutomaticaEnBajada = false;
bool riesgoPuntoRocio = false;
bool timeoutComunicacionReportado = false;
bool focoEnDescanso = false;
bool peltierEnDescanso = false;
bool servidorWifiIniciado = false;
bool descartarComandoSerial = false;
bool descartarComandoWifi = false;
char bufferComandoSerial[48];
char bufferComandoWifi[48];
size_t indiceComandoSerial = 0;
size_t indiceComandoWifi = 0;
unsigned long ultimoSensorMs = 0;
unsigned long ultimoEstadoMs = 0;
unsigned long ultimoEnvioTemperaturaMs = 0;
unsigned long ultimoEscaneoTecladoMs = 0;
unsigned long ultimoPasoServoDimerMs = 0;
unsigned long inicioRetencionPruebaDimerMs = 0;
unsigned long inicioVentanaPidMs = 0;
unsigned long inicioFaseMs = 0;
unsigned long ultimoComandoMs = 0;
unsigned long ultimoHeartbeatTecladoUiMs = 0;
unsigned long inicioFocoMs = 0;
unsigned long inicioPeltierMs = 0;
unsigned long inicioDescansoFocoMs = 0;
unsigned long inicioDescansoPeltierMs = 0;

const char *nombreFaseBase(Fase valor) {
  switch (valor) {
    case NORMAL: return "NORMAL";
    case PURGA_APERTURA: return "PURGA_APERTURA";
    case PURGA_VENTILACION: return "PURGA_VENTILACION";
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

float calcularPuntoRocio(float temperatura, float humedad) {
  if (!isfinite(temperatura) || !isfinite(humedad) ||
      humedad <= 0.0f || humedad > 100.0f) {
    return NAN;
  }

  float gamma = log(humedad / 100.0f) +
                (17.67f * temperatura) / (243.5f + temperatura);
  float denominador = 17.67f - gamma;
  if (denominador <= 0.0f) {
    return NAN;
  }
  return (243.5f * gamma) / denominador;
}

void actualizarRiesgoPuntoRocio(float temperatura, float humedad) {
  if (!isfinite(humedad)) {
    if (riesgoPuntoRocio) {
      Serial.println("WARN,DEWPOINT,CLEAR");
      riesgoPuntoRocio = false;
    }
    return;
  }

  float puntoRocio = calcularPuntoRocio(temperatura, humedad);
  bool riesgoActual = isfinite(puntoRocio) && puntoRocio >= tempMinima;
  if (riesgoActual && !riesgoPuntoRocio) {
    Serial.print("WARN,DEWPOINT,RISK,");
    Serial.print(puntoRocio, 1);
    Serial.print(',');
    Serial.println(tempMinima, 1);
  } else if (!riesgoActual && riesgoPuntoRocio) {
    Serial.println("WARN,DEWPOINT,CLEAR");
  }
  riesgoPuntoRocio = riesgoActual;
}

void limitarTiempoSalidas(bool &foco, bool &peltier, unsigned long ahora) {
  if (foco && peltier) {
    peltier = false;
  }

  bool focoActivo = potenciaFocoAplicada > 0.0f;
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

int anguloDimerParaPotencia(float potencia) {
  if (potencia <= 0.0f) {
    return ANGULO_DIMER_MINIMO;
  }

  int recorrido = static_cast<int>(ceilf(
      (ANGULO_DIMER_MAXIMO - ANGULO_DIMER_MINIMO) * potencia / 100.0f
  ));
  if (recorrido < 1) {
    recorrido = 1;
  }
  return ANGULO_DIMER_MINIMO + recorrido;
}

void escribirSalidasConPotencia(
    float potenciaFoco, bool peltier, bool ventiladores
) {
  if (!isfinite(potenciaFoco)) {
    potenciaFoco = 0.0f;
  }
  potenciaFoco = fminf(100.0f, fmaxf(0.0f, potenciaFoco));
  bool foco = potenciaFoco > 0.0f;
  unsigned long ahora = millis();
  limitarTiempoSalidas(foco, peltier, ahora);
  bool focoEstabaActivo = potenciaFocoAplicada > 0.0f;
  bool peltierEstabaActiva = digitalRead(PIN_PELTIER) == HIGH;
  if (!foco) {
    potenciaFoco = 0.0f;
  }
  anguloServoDimerObjetivo = anguloDimerParaPotencia(potenciaFoco);
  if (peltier && anguloServoDimerActual != ANGULO_DIMER_MINIMO) {
    peltier = false;
  }
  potenciaFocoAplicada = potenciaFoco;
  digitalWrite(PIN_PELTIER, peltier ? HIGH : LOW);
  digitalWrite(PIN_FANS, ventiladores ? HIGH : LOW);
  if (focoEstabaActivo != foco) {
    DEBUG_PRINT("DEBUG,SALIDA,FOCO,%s\n", foco ? "ON" : "OFF");
  }
  if (peltierEstabaActiva != peltier) {
    DEBUG_PRINT("DEBUG,SALIDA,PELTIER,%s\n", peltier ? "ON" : "OFF");
  }
}

void escribirSalidas(bool foco, bool peltier, bool ventiladores) {
  escribirSalidasConPotencia(foco ? 100.0f : 0.0f, peltier, ventiladores);
}

void actualizarServoDimer(unsigned long ahora) {
  if (ahora - ultimoPasoServoDimerMs < INTERVALO_PASO_SERVO_DIMER_MS) {
    return;
  }
  ultimoPasoServoDimerMs = ahora;

  if (anguloServoDimerActual == anguloServoDimerObjetivo) {
    return;
  }

  int diferencia = anguloServoDimerObjetivo - anguloServoDimerActual;
  int paso = min(abs(diferencia), PASO_SERVO_DIMER_GRADOS);
  anguloServoDimerActual += diferencia > 0 ? paso : -paso;
  servoDimer.write(anguloServoDimerActual);
}

void actualizarPruebaDimer(unsigned long ahora) {
  if (!sensorValido) {
    estadoPruebaDimer = PRUEBA_DIMER_INACTIVA;
    controlDetenido = true;
    escribirSalidasConPotencia(0.0f, false, false);
    Serial.println("ERR,DIMMER_TEST,SENSOR");
    return;
  }

  switch (estadoPruebaDimer) {
    case PRUEBA_DIMER_SUBIENDO:
      escribirSalidasConPotencia(
          POTENCIA_DIMER_PRUEBA, false, false
      );
      if (anguloServoDimerActual >=
          anguloDimerParaPotencia(POTENCIA_DIMER_PRUEBA)) {
        estadoPruebaDimer = PRUEBA_DIMER_MANTENIENDO;
        inicioRetencionPruebaDimerMs = ahora;
      }
      break;
    case PRUEBA_DIMER_MANTENIENDO:
      escribirSalidasConPotencia(
          POTENCIA_DIMER_PRUEBA, false, false
      );
      if (ahora - inicioRetencionPruebaDimerMs >=
          DURACION_PRUEBA_DIMER_MS) {
        estadoPruebaDimer = PRUEBA_DIMER_REGRESANDO;
      }
      break;
    case PRUEBA_DIMER_REGRESANDO:
      escribirSalidasConPotencia(0.0f, false, false);
      if (anguloServoDimerActual == ANGULO_DIMER_MINIMO) {
        estadoPruebaDimer = PRUEBA_DIMER_INACTIVA;
        controlDetenido = true;
        cambiarModoTermico(MODO_MANTENER);
        Serial.println("ACK,DIMMER_TEST,DONE");
      }
      break;
    case PRUEBA_DIMER_INACTIVA:
      break;
  }
}

void iniciarPurga(unsigned long ahora) {
  escribirSalidas(false, false, false);
  servoTapa1.write(SERVO_ABIERTO);
  servoTapa2.write(SERVO_ABIERTO);
  cambiarFase(PURGA_APERTURA);
  inicioFaseMs = ahora;
}

void iniciarCiclo(bool objetivoMaximo) {
  cicloActivo = true;
  controlPidActivo = false;
  controlDetenido = false;
  objetivoCicloMaximo = objetivoMaximo;
  purgaAutomaticaEnBajada = false;
  cambiarFase(NORMAL);

  float objetivo = objetivoMaximo ? tempMaxima : tempMinima;
  if (temperaturaActual == objetivo) {
    objetivoCicloMaximo = !objetivoMaximo;
    modoCiclo = objetivoMaximo ? MODO_ENFRIAR : MODO_CALENTAR;
  } else if (temperaturaActual < objetivo) {
    modoCiclo = MODO_CALENTAR;
  } else {
    modoCiclo = MODO_ENFRIAR;
  }
  cambiarModoTermico(modoCiclo);
  escribirSalidas(false, false, false);
}

void detenerControl() {
  cicloActivo = false;
  controlPidActivo = false;
  controlDetenido = true;
  modoPrueba = false;
  estadoPruebaDimer = PRUEBA_DIMER_INACTIVA;
  purgaAutomaticaEnBajada = false;
  cambiarModoTermico(MODO_MANTENER);
  cambiarFase(sensorValido ? NORMAL : ERROR_SENSOR);
  servoTapa1.write(SERVO_CERRADO);
  servoTapa2.write(SERVO_CERRADO);
  escribirSalidas(false, false, false);
}

const char *nombreCampoRango(CampoRango campo) {
  return campo == EDITANDO_MINIMO ? "MIN" : "MAX";
}

void informarEdicionRango() {
  Serial.print("INFO,KEYPAD,EDIT,");
  Serial.print(nombreCampoRango(campoRangoEnEdicion));
  Serial.print(',');
  Serial.println(bufferEntradaRango);
}

void cancelarEdicionRango() {
  if (campoRangoEnEdicion == SIN_EDICION) {
    return;
  }
  campoRangoEnEdicion = SIN_EDICION;
  longitudEntradaRango = 0;
  bufferEntradaRango[0] = '\0';
  Serial.println("INFO,KEYPAD,CANCELLED");
}

void iniciarEdicionRango(CampoRango campo) {
  if (cicloActivo || controlPidActivo || modoPrueba || fase != NORMAL) {
    Serial.println("ERR,KEYPAD,BUSY");
    return;
  }
  campoRangoEnEdicion = campo;
  longitudEntradaRango = 0;
  bufferEntradaRango[0] = '\0';
  informarEdicionRango();
}

void agregarDigitoRango(char digito) {
  if (campoRangoEnEdicion == SIN_EDICION) {
    return;
  }

  const char *decimal = strchr(bufferEntradaRango, '.');
  size_t digitosEnteros = decimal == NULL
      ? longitudEntradaRango
      : static_cast<size_t>(decimal - bufferEntradaRango);
  size_t digitosDecimales = decimal == NULL
      ? 0
      : longitudEntradaRango - digitosEnteros - 1;
  if ((decimal == NULL && digitosEnteros >= 2) ||
      (decimal != NULL && digitosDecimales >= 1)) {
    Serial.println("ERR,KEYPAD,ENTRY_FULL");
    return;
  }

  bufferEntradaRango[longitudEntradaRango++] = digito;
  bufferEntradaRango[longitudEntradaRango] = '\0';
  informarEdicionRango();
}

void agregarDecimalRango() {
  if (campoRangoEnEdicion == SIN_EDICION) {
    return;
  }
  if (longitudEntradaRango == 0 ||
      strchr(bufferEntradaRango, '.') != NULL ||
      longitudEntradaRango >= sizeof(bufferEntradaRango) - 1) {
    Serial.println("ERR,KEYPAD,FORMAT");
    return;
  }
  bufferEntradaRango[longitudEntradaRango++] = '.';
  bufferEntradaRango[longitudEntradaRango] = '\0';
  informarEdicionRango();
}

void confirmarEdicionRango() {
  if (campoRangoEnEdicion == SIN_EDICION) {
    return;
  }

  const char *decimal = strchr(bufferEntradaRango, '.');
  char *finValor;
  float nuevoValor = strtof(bufferEntradaRango, &finValor);
  if (longitudEntradaRango == 0 || finValor == bufferEntradaRango ||
      *finValor != '\0' ||
      (decimal != NULL && decimal[1] == '\0') ||
      !isfinite(nuevoValor) ||
      nuevoValor < TEMPERATURA_CONFIG_MINIMA ||
      nuevoValor > TEMPERATURA_CONFIG_MAXIMA) {
    Serial.println("ERR,SETRANGE,FORMAT");
    return;
  }

  float nuevaMinima = campoRangoEnEdicion == EDITANDO_MINIMO
      ? nuevoValor : tempMinima;
  float nuevaMaxima = campoRangoEnEdicion == EDITANDO_MAXIMO
      ? nuevoValor : tempMaxima;
  if (nuevaMinima + 2.0f > nuevaMaxima) {
    Serial.println("ERR,SETRANGE,RANGE");
    return;
  }

  CampoRango campoConfirmado = campoRangoEnEdicion;
  tempMinima = nuevaMinima;
  tempMaxima = nuevaMaxima;
  campoRangoEnEdicion = SIN_EDICION;
  longitudEntradaRango = 0;
  bufferEntradaRango[0] = '\0';
  Serial.print("ACK,SETRANGE,");
  Serial.print(tempMinima, 1);
  Serial.print(',');
  Serial.println(tempMaxima, 1);
  Serial.print("INFO,KEYPAD,SAVED,");
  Serial.println(nombreCampoRango(campoConfirmado));
}

char leerTeclaMatriz() {
  const char teclas[4][4] = {
    {'1', '2', '3', 'A'},
    {'4', '5', '6', 'B'},
    {'7', '8', '9', 'C'},
    {'*', '0', '#', 'D'}
  };
  char teclaDetectada = '\0';
  uint8_t teclasPresionadas = 0;

  for (uint8_t fila = 0; fila < 4; fila++) {
    for (uint8_t otraFila = 0; otraFila < 4; otraFila++) {
      pinMode(PIN_TECLADO_FILAS[otraFila], INPUT);
    }
    pinMode(PIN_TECLADO_FILAS[fila], OUTPUT);
    digitalWrite(PIN_TECLADO_FILAS[fila], LOW);
    delayMicroseconds(3);

    for (uint8_t columna = 0; columna < 4; columna++) {
      if (digitalRead(PIN_TECLADO_COLUMNAS[columna]) == LOW) {
        teclaDetectada = teclas[fila][columna];
        teclasPresionadas++;
      }
    }
  }

  for (uint8_t fila = 0; fila < 4; fila++) {
    pinMode(PIN_TECLADO_FILAS[fila], INPUT);
  }
  return teclasPresionadas == 1 ? teclaDetectada : '\0';
}

void procesarComando(char *comando, unsigned long ahora);

void procesarTecla(char tecla, unsigned long ahora) {
  if (tecladoUiActivo) {
    Serial.print("KEYPAD_KEY,");
    Serial.println(tecla);
    return;
  }

  char comando[16];
  switch (tecla) {
    case 'A':
      iniciarEdicionRango(EDITANDO_MINIMO);
      return;
    case 'B':
      iniciarEdicionRango(EDITANDO_MAXIMO);
      return;
    case 'C':
      if (campoRangoEnEdicion != SIN_EDICION) {
        Serial.println("ERR,KEYPAD,FINISH_ENTRY");
        return;
      }
      strcpy(comando, "CYCLE,MIN");
      break;
    case 'D':
      cancelarEdicionRango();
      strcpy(comando, "STOP");
      break;
    case '*':
      agregarDecimalRango();
      return;
    case '#':
      confirmarEdicionRango();
      return;
    default:
      if (tecla >= '0' && tecla <= '9') {
        agregarDigitoRango(tecla);
      }
      return;
  }
  procesarComando(comando, ahora);
}

void escanearTeclado(unsigned long ahora) {
  static char teclaCandidata = '\0';
  static char teclaEstable = '\0';
  static unsigned long inicioCandidataMs = 0;

  if (ahora - ultimoEscaneoTecladoMs < INTERVALO_TECLADO_MS) {
    return;
  }
  ultimoEscaneoTecladoMs = ahora;

  char lectura = leerTeclaMatriz();
  if (lectura != teclaCandidata) {
    teclaCandidata = lectura;
    inicioCandidataMs = ahora;
  }
  if (lectura == teclaEstable ||
      ahora - inicioCandidataMs < ANTIRREBOTE_TECLADO_MS) {
    return;
  }

  teclaEstable = lectura;
  if (teclaEstable != '\0') {
    procesarTecla(teclaEstable, ahora);
  }
}

void restablecerSalidasPid() {
  pidCalentar.SetMode(MANUAL);
  salidaPIDCalentar = 0.0;
  pidCalentar.SetMode(AUTOMATIC);
  pidEnfriar.SetMode(MANUAL);
  salidaPIDEnfriar = 0.0;
  pidEnfriar.SetMode(AUTOMATIC);
  modoPid = PID_INACTIVO;
  inicioVentanaPidMs = millis();
}

void procesarComando(char *comando, unsigned long ahora) {
  ultimoComandoMs = ahora;
  timeoutComunicacionReportado = false;
  if (strcmp(comando, "KEYPAD_UI,1") == 0) {
    bool yaActivo = tecladoUiActivo;
    tecladoUiActivo = true;
    ultimoHeartbeatTecladoUiMs = ahora;
    cancelarEdicionRango();
    if (!yaActivo) {
      Serial.println("ACK,KEYPAD_UI,ON");
    }
    return;
  }
  if (strcmp(comando, "KEYPAD_UI,0") == 0) {
    bool yaActivo = tecladoUiActivo;
    tecladoUiActivo = false;
    if (yaActivo) {
      Serial.println("ACK,KEYPAD_UI,OFF");
    }
    return;
  }
  if (strncmp(comando, "KEY,", 4) == 0 && comando[5] == '\0') {
    procesarTecla(comando[4], ahora);
    return;
  }

  if (strncmp(comando, "PID_TUNE,", 9) == 0) {
    char *inicioKp = comando + 9;
    char *separadorKi = strchr(inicioKp, ',');
    char *separadorKd = separadorKi == NULL
        ? NULL : strchr(separadorKi + 1, ',');
    if (separadorKi == NULL || separadorKd == NULL) {
      Serial.println("ERR,PID_TUNE,FORMAT");
      return;
    }

    *separadorKi = '\0';
    *separadorKd = '\0';
    char *finKp;
    char *finKi;
    char *finKd;
    double nuevoKp = strtod(inicioKp, &finKp);
    double nuevoKi = strtod(separadorKi + 1, &finKi);
    double nuevoKd = strtod(separadorKd + 1, &finKd);
    if (finKp == inicioKp || *finKp != '\0' ||
        finKi == separadorKi + 1 || *finKi != '\0' ||
        finKd == separadorKd + 1 || *finKd != '\0' ||
        !isfinite(nuevoKp) || !isfinite(nuevoKi) || !isfinite(nuevoKd) ||
        nuevoKp < 0.0 || nuevoKp > 10.0 ||
        nuevoKi < 0.0 || nuevoKi > 10.0 ||
        nuevoKd < 0.0 || nuevoKd > 10.0) {
      Serial.println("ERR,PID_TUNE,RANGE");
      return;
    }

    Kp = nuevoKp;
    Ki = nuevoKi;
    Kd = nuevoKd;
    pidCalentar.SetTunings(Kp, Ki, Kd);
    pidEnfriar.SetTunings(Kp, Ki, Kd);
    restablecerSalidasPid();
    Serial.println("ACK,PID_TUNE");
    return;
  }

  if (strncmp(comando, "TEMP_TARGET:", 12) == 0) {
    char *inicioObjetivo = comando + 12;
    char *finObjetivo;
    double nuevoSetpoint = strtod(inicioObjetivo, &finObjetivo);
    if (finObjetivo == inicioObjetivo || *finObjetivo != '\0' ||
        !isfinite(nuevoSetpoint) ||
        nuevoSetpoint < TEMPERATURA_CONFIG_MINIMA ||
        nuevoSetpoint > TEMPERATURA_CONFIG_MAXIMA) {
      Serial.println("ERR,TEMP_TARGET,RANGE");
      return;
    }
    if (!sensorValido) {
      Serial.println("ERR,TEMP_TARGET,SENSOR");
      return;
    }
    if (cicloActivo || modoPrueba ||
        estadoPruebaDimer != PRUEBA_DIMER_INACTIVA || fase != NORMAL ||
        campoRangoEnEdicion != SIN_EDICION) {
      Serial.println("ERR,TEMP_TARGET,BUSY");
      return;
    }

    Setpoint = nuevoSetpoint;
    restablecerSalidasPid();
    controlPidActivo = true;
    controlDetenido = false;
    cambiarModoTermico(MODO_MANTENER);
    Serial.print("ACK,TEMP_TARGET,");
    Serial.println(Setpoint, 1);
    return;
  }

  if (strcmp(comando, "DIMMER_TEST") == 0) {
    if (!sensorValido) {
      Serial.println("ERR,DIMMER_TEST,SENSOR");
      return;
    }
    if (cicloActivo || controlPidActivo || modoPrueba || !controlDetenido ||
        fase != NORMAL || campoRangoEnEdicion != SIN_EDICION ||
        estadoPruebaDimer != PRUEBA_DIMER_INACTIVA ||
        focoEnDescanso || digitalRead(PIN_PELTIER) == HIGH) {
      Serial.println("ERR,DIMMER_TEST,BUSY");
      return;
    }
    estadoPruebaDimer = PRUEBA_DIMER_SUBIENDO;
    Serial.println("ACK,DIMMER_TEST,STARTED");
    return;
  }

  if (strcmp(comando, "TEST,1") == 0 || strcmp(comando, "TEST,0") == 0) {
    bool activar = comando[5] == '1';
    if (activar &&
        (cicloActivo || controlPidActivo ||
         estadoPruebaDimer != PRUEBA_DIMER_INACTIVA ||
         (fase != NORMAL && fase != ERROR_SENSOR) ||
         campoRangoEnEdicion != SIN_EDICION)) {
      Serial.println("ERR,TEST,BUSY");
      return;
    }
    if (modoPrueba != activar) {
      modoPrueba = activar;
      cambiarFase(sensorValido ? NORMAL : ERROR_SENSOR);
      cambiarModoTermico(MODO_MANTENER);
      if (modoPrueba || estadoPruebaDimer != PRUEBA_DIMER_INACTIVA) {
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

  if (strcmp(comando, "PURGE") == 0) {
    if (campoRangoEnEdicion != SIN_EDICION) {
      Serial.println("ERR,PURGE,BUSY");
      return;
    }
    if (!sensorValido) {
      Serial.println("ERR,PURGE,SENSOR");
      return;
    }
    if (modoPrueba || estadoPruebaDimer != PRUEBA_DIMER_INACTIVA) {
      Serial.println("ERR,PURGE,TESTING");
      return;
    }
    if (fase != NORMAL) {
      Serial.println("ERR,PURGE,BUSY");
      return;
    }
    iniciarPurga(ahora);
    Serial.println("ACK,PURGE,STARTED");
    return;
  }

  if (strcmp(comando, "STOP") == 0) {
    cancelarEdicionRango();
    detenerControl();
    Serial.println("ACK,STOP,OK");
    return;
  }

  if (strcmp(comando, "CYCLE,MIN") == 0 ||
      strcmp(comando, "CYCLE,MAX") == 0) {
    if (!sensorValido) {
      Serial.println("ERR,CYCLE,SENSOR");
      return;
    }
    if (modoPrueba) {
      Serial.println("ERR,CYCLE,TESTING");
      return;
    }
    if (fase != NORMAL || cicloActivo ||
        campoRangoEnEdicion != SIN_EDICION) {
      Serial.println("ERR,CYCLE,BUSY");
      return;
    }
    bool objetivoMaximo = comando[7] == 'A';
    iniciarCiclo(objetivoMaximo);
    Serial.print("ACK,CYCLE,STARTED,");
    Serial.println(objetivoMaximo ? "MAX" : "MIN");
    return;
  }

  if (strncmp(comando, "SETRANGE,", 9) != 0) {
    return;
  }
  if (cicloActivo) {
    Serial.println("ERR,SETRANGE,BUSY");
    return;
  }
  cancelarEdicionRango();

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
      nuevaMinima + 2.0f > nuevaMaxima) {
    Serial.println("ERR,SETRANGE,RANGE");
    return;
  }

  tempMinima = nuevaMinima;
  tempMaxima = nuevaMaxima;
  Serial.print("ACK,SETRANGE,");
  Serial.print(tempMinima, 1);
  Serial.print(',');
  Serial.println(tempMaxima, 1);
}

void leerCanalComandos(Stream &canal, char *buffer, size_t capacidad,
                       size_t &indice, bool &descartar,
                       unsigned long ahora) {
  while (canal.available() > 0) {
    int byteRecibido = canal.read();
    if (byteRecibido < 0) {
      break;
    }
    char caracter = static_cast<char>(byteRecibido);
    if (caracter == '\r') {
      continue;
    }

    if (caracter == '\n') {
      buffer[indice] = '\0';
      if (!descartar && indice > 0) {
        procesarComando(buffer, ahora);
      }
      indice = 0;
      descartar = false;
    } else if (descartar) {
      continue;
    } else if (indice < capacidad - 1) {
      buffer[indice++] = caracter;
    } else {
      indice = 0;
      descartar = true;
    }
  }
}

void leerComandos(unsigned long ahora) {
  leerCanalComandos(serialUsb, bufferComandoSerial,
                    sizeof(bufferComandoSerial), indiceComandoSerial,
                    descartarComandoSerial, ahora);
  if (client && client.connected()) {
    leerCanalComandos(client, bufferComandoWifi,
                      sizeof(bufferComandoWifi), indiceComandoWifi,
                      descartarComandoWifi, ahora);
  } else {
    indiceComandoWifi = 0;
    descartarComandoWifi = false;
  }
}

void actualizarServidorWifi() {
  if (WiFi.status() != WL_CONNECTED) {
    if (servidorWifiIniciado) {
      if (client) {
        client.stop();
      }
      indiceComandoWifi = 0;
      servidorWifiIniciado = false;
      Serial.println("INFO,WIFI,DISCONNECTED");
    }
    return;
  }

  if (!servidorWifiIniciado) {
    server.begin();
    servidorWifiIniciado = true;
    Serial.print("INFO,WIFI,READY,");
    Serial.println(WiFi.localIP());
  }

  WiFiClient nuevoCliente = server.available();
  if (nuevoCliente) {
    if (client && client.connected()) {
      client.stop();
    }
    client = nuevoCliente;
    indiceComandoWifi = 0;
    Serial.println("INFO,WIFI,CLIENT_CONNECTED");
  }

  if (client && !client.connected()) {
    client.stop();
    indiceComandoWifi = 0;
    Serial.println("INFO,WIFI,CLIENT_DISCONNECTED");
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

  if (!isfinite(temperatura) ||
      temperatura < TEMPERATURA_SENSOR_MINIMA ||
      temperatura > TEMPERATURA_SENSOR_MAXIMA) {
    actualizarRiesgoPuntoRocio(NAN, NAN);
    sensorValido = false;
    modoPrueba = false;
    cambiarFase(ERROR_SENSOR);
    cambiarModoTermico(MODO_MANTENER);
    escribirSalidas(false, false, false);
    servoTapa1.write(SERVO_CERRADO);
    servoTapa2.write(SERVO_CERRADO);
    DEBUG_PRINT("DEBUG,SEGURIDAD,DHT11_INVALIDO,TEMP=%.1f,HUM=%.1f\n",
                temperatura, humedad);
    return;
  }

  if (!isfinite(humedad) || humedad < 0.0f || humedad > 100.0f) {
    humedad = NAN;
  }
  humedadActual = humedad;
  actualizarRiesgoPuntoRocio(temperatura, humedadActual);
  temperaturaActual = temperatura;
  Input = temperatura;
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
        servoTapa1.write(SERVO_CERRADO);
        servoTapa2.write(SERVO_CERRADO);
        cambiarFase(PURGA_CIERRE);
        inicioFaseMs = ahora;
      }
      break;
    case PURGA_CIERRE:
      if (ahora - inicioFaseMs >= TIEMPO_SERVO_MS) {
        cambiarFase(NORMAL);
        if (!cicloActivo && !controlDetenido) {
          cambiarModoTermico(MODO_MANTENER);
        }
      }
      break;
    default:
      break;
  }
}

void actualizarControlTermico() {
  if (estadoPruebaDimer != PRUEBA_DIMER_INACTIVA) {
    actualizarPruebaDimer(millis());
    return;
  }

  if (modoPrueba) {
    escribirSalidas(false, false, true);
    return;
  }

  if (!sensorValido || fase != NORMAL) {
    escribirSalidas(false, false, fase == PURGA_VENTILACION);
    return;
  }

  if (controlPidActivo) {
    if (fabs(Input - Setpoint) <= 1.0) {
      if (modoPid != PID_INACTIVO) {
        restablecerSalidasPid();
      }
      cambiarModoTermico(MODO_MANTENER);
      escribirSalidas(false, false, false);
      return;
    }

    bool calentar = Input < Setpoint;
    ModoPID modoSolicitado = calentar ? PID_CALENTAR : PID_ENFRIAR;
    if (modoPid != modoSolicitado) {
      restablecerSalidasPid();
      modoPid = modoSolicitado;
      inicioVentanaPidMs = millis();
    }

    PID &control = calentar ? pidCalentar : pidEnfriar;
    control.Compute();
    double salida = calentar ? salidaPIDCalentar : salidaPIDEnfriar;
    unsigned long ahora = millis();
    unsigned long transcurrido = ahora - inicioVentanaPidMs;
    if (transcurrido >= VENTANA_PID_MS) {
      inicioVentanaPidMs +=
          (transcurrido / VENTANA_PID_MS) * VENTANA_PID_MS;
      transcurrido = ahora - inicioVentanaPidMs;
    }
    unsigned long tiempoActivo = static_cast<unsigned long>(
        VENTANA_PID_MS * fmin(100.0, fmax(0.0, salida)) / 100.0
    );
    cambiarModoTermico(
        calentar ? MODO_CALENTAR : MODO_ENFRIAR
    );
    if (calentar) {
        escribirSalidasConPotencia(static_cast<float>(salida), false, false);
    } else {
        bool salidaActiva = transcurrido < tiempoActivo;
        escribirSalidasConPotencia(
            0.0f, salidaActiva, false
        );
    }
    return;
  }

  if (controlDetenido) {
    cambiarModoTermico(MODO_MANTENER);
    escribirSalidas(false, false, false);
    return;
  }

  if (cicloActivo) {
    float objetivo = objetivoCicloMaximo ? tempMaxima : tempMinima;
    bool objetivoAlcanzado = modoCiclo == MODO_CALENTAR
        ? temperaturaActual >= objetivo
        : temperaturaActual <= objetivo;
    if (objetivoAlcanzado) {
      bool alcanzoMaxima = objetivoCicloMaximo;
      objetivoCicloMaximo = !objetivoCicloMaximo;
      modoCiclo = objetivoCicloMaximo ? MODO_CALENTAR : MODO_ENFRIAR;
      purgaAutomaticaEnBajada = alcanzoMaxima;
      if (alcanzoMaxima) {
        iniciarPurga(millis());
        return;
      }
    }

    if (!objetivoCicloMaximo && modoCiclo == MODO_ENFRIAR &&
        !purgaAutomaticaEnBajada &&
        temperaturaActual <= tempMaxima - DIFERENCIA_PURGA_AUTOMATICA) {
      purgaAutomaticaEnBajada = true;
      iniciarPurga(millis());
      return;
    }
    cambiarModoTermico(modoCiclo);
  } else if (temperaturaActual <= tempMinima) {
    cambiarModoTermico(MODO_CALENTAR);
  } else if (temperaturaActual >= tempMaxima) {
    cambiarModoTermico(MODO_ENFRIAR);
  } else if (modoTermico == MODO_MANTENER) {
    cambiarModoTermico(MODO_CALENTAR);
  }

  bool focoSolicitado = modoTermico == MODO_CALENTAR;
  bool peltierSolicitada = modoTermico == MODO_ENFRIAR;
  escribirSalidas(
    focoSolicitado,
    peltierSolicitada,
    false
  );
  if ((focoSolicitado && potenciaFocoAplicada <= 0.0f) ||
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

void actualizarTimeoutTecladoUi(unsigned long ahora) {
  if (tecladoUiActivo &&
      ahora - ultimoHeartbeatTecladoUiMs >= TIMEOUT_TECLADO_UI_MS) {
    tecladoUiActivo = false;
    DEBUG_PRINT("DEBUG,KEYPAD,UI_TIMEOUT,restableciendo control local\n");
  }
}

const char *nombreFase() {
  if (estadoPruebaDimer != PRUEBA_DIMER_INACTIVA) return "DIMMER_TEST";
  if (modoPrueba) return "TESTING";

  switch (fase) {
    case PURGA_APERTURA: return "PURGE_OPENING";
    case PURGA_VENTILACION: return "PURGE_RUNNING";
    case PURGA_CIERRE: return "PURGE_CLOSING";
    case ERROR_SENSOR: return "SENSOR_ERROR";
    case NORMAL:
      if (controlDetenido) return "STOPPED";
      if (cicloActivo) {
        if (modoCiclo == MODO_CALENTAR) {
          return objetivoCicloMaximo
              ? "CYCLE_HEATING_MAX" : "CYCLE_HEATING_MIN";
        }
        return objetivoCicloMaximo
            ? "CYCLE_COOLING_MAX" : "CYCLE_COOLING_MIN";
      }
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
    Serial.print(tempMaxima, 1);
    Serial.print(',');
    Serial.print(cicloActivo ? 1 : 0);
    Serial.print(',');
    Serial.print(potenciaFocoAplicada, 1);
    Serial.print(',');
    Serial.println(anguloServoDimerActual);
    return;
  }

  Serial.print("STATUS,");
  Serial.print(temperaturaActual, 0);
  Serial.print(',');
  Serial.print(
      anguloServoDimerActual > ANGULO_DIMER_MINIMO ? 1 : 0
  );
  Serial.print(',');
  Serial.print(digitalRead(PIN_PELTIER));
  Serial.print(',');
  Serial.print(digitalRead(PIN_FANS));
  Serial.print(',');
  bool tapasAbiertas = modoPrueba || fase == PURGA_APERTURA ||
                       fase == PURGA_VENTILACION || fase == PURGA_CIERRE;
  Serial.print(tapasAbiertas ? 1 : 0);
  Serial.print(',');
  Serial.print(nombreFase());
  Serial.print(',');
  Serial.print(humedadActual, 1);
  Serial.print(',');
  Serial.print(tempMinima, 1);
  Serial.print(',');
  Serial.print(tempMaxima, 1);
  Serial.print(',');
  Serial.print(cicloActivo ? 1 : 0);
  Serial.print(',');
  Serial.print(potenciaFocoAplicada, 1);
  Serial.print(',');
  Serial.println(anguloServoDimerActual);
}

void enviarTemperaturaActual(unsigned long ahora) {
  if (!sensorValido ||
      ahora - ultimoEnvioTemperaturaMs < INTERVALO_TEMPERATURA_SERIAL_MS) {
    return;
  }
  ultimoEnvioTemperaturaMs = ahora;
  Serial.print("TEMP_CURRENT:");
  Serial.println(temperaturaActual, 0);
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("INFO,WIFI,CONNECTING");

  for (uint8_t fila = 0; fila < 4; fila++) {
    pinMode(PIN_TECLADO_FILAS[fila], INPUT);
  }
  for (uint8_t columna = 0; columna < 4; columna++) {
    pinMode(PIN_TECLADO_COLUMNAS[columna], INPUT_PULLUP);
  }

  pinMode(PIN_PELTIER, OUTPUT);
  pinMode(PIN_FANS, OUTPUT);
  escribirSalidas(false, false, false);

  servoTapa1.setPeriodHertz(50);
  servoTapa2.setPeriodHertz(50);
  servoTapa1.attach(PIN_SERVO_TAPA_1, 500, 2400);
  servoTapa2.attach(PIN_SERVO_TAPA_2, 500, 2400);
  servoDimer.setPeriodHertz(50);
  servoDimer.attach(PIN_SERVO_DIMER, 500, 2400);
  servoTapa1.write(SERVO_CERRADO);
  servoTapa2.write(SERVO_CERRADO);
  servoDimer.write(ANGULO_DIMER_MINIMO);

  dht.begin();
  pidCalentar.SetOutputLimits(0.0, 100.0);
  pidEnfriar.SetOutputLimits(0.0, 100.0);
  pidCalentar.SetSampleTime(INTERVALO_SENSOR_MS);
  pidEnfriar.SetSampleTime(INTERVALO_SENSOR_MS);
  pidCalentar.SetMode(AUTOMATIC);
  pidEnfriar.SetMode(AUTOMATIC);
  delay(INTERVALO_SENSOR_MS);
}

void loop() {
  unsigned long ahora = millis();
  actualizarServidorWifi();
  leerComandos(ahora);
  actualizarTimeoutTecladoUi(ahora);
  escanearTeclado(ahora);
  actualizarTimeoutComunicacion(ahora);
  actualizarSensor(ahora);
  enviarTemperaturaActual(ahora);
  actualizarPurga(ahora);
  actualizarControlTermico();
  actualizarServoDimer(millis());
  enviarEstado(ahora);
}