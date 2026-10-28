/*
 * Firmware del bebé animatrónico IME 702 para ESP32 DevKit V1 (30 pines).
 *
 * En Arduino IDE, selecciona "ESP32 Dev Module" en Herramientas > Placa.
 * Si no aparece, instala el soporte ESP32 desde Preferencias > URLs
 * adicionales del Gestor de placas:
 * https://dl.espressif.com/dl/package_esp32_index.json
 *
 * Bibliotecas del IDE Arduino:
 *   - ESP32Servo
 *   - DFRobotDFPlayerMini
 *
 * Use una fuente externa de 5 V dimensionada para los servos y conecte las
 * tierras de fuente, ESP32 y DFPlayer. No alimente los servos desde el pin 3V3.
 * Conecta DFPlayer TX -> GPIO 16 (RX2). Recordatorio: resistencia 1K en RX
 * del DFPlayer (GPIO 17 (TX2) -> 1K -> RX DFPlayer).
 */

#include <Arduino.h>
#include <ESP32Servo.h>
#include <DFRobotDFPlayerMini.h>

static constexpr uint32_t DFPLAYER_BAUD = 115200;
static constexpr uint8_t PIN_NECK = 18;
static constexpr uint8_t PIN_R_ARM = 19;
static constexpr uint8_t PIN_L_ARM = 21;
static constexpr uint8_t PIN_WAIST = 22;
static constexpr uint8_t PIN_GLOBO = 23;
static constexpr uint8_t PIN_DF_TX = 17;
static constexpr uint8_t PIN_DF_RX = 16;
static constexpr uint32_t SERVO_TICK_MS = 20;
static constexpr int SERVO_MIN_PULSE_US = 500;
static constexpr int SERVO_MAX_PULSE_US = 2500;
static constexpr uint32_t GLOBO_POP_HOLD_MS = 500;

struct ServoMotion {
  Servo servo;
  const char *name;
  uint8_t pin;
  float startAngle;
  float targetAngle;
  float currentAngle;
  uint32_t startedAt;
  uint32_t durationMs;
  bool moving;
};

ServoMotion servos[] = {
    {Servo(), "NECK", PIN_NECK, 90, 90, 90, 0, 500, false},
    {Servo(), "R_ARM", PIN_R_ARM, 90, 90, 90, 0, 500, false},
    {Servo(), "L_ARM", PIN_L_ARM, 90, 90, 90, 0, 500, false},
    {Servo(), "WAIST", PIN_WAIST, 90, 90, 90, 0, 500, false},
    {Servo(), "GLOBO", PIN_GLOBO, 0, 0, 0, 0, 1000, false},
};

static constexpr size_t BODY_SERVO_COUNT = 4;
static constexpr size_t SERVO_COUNT = sizeof(servos) / sizeof(servos[0]);
HardwareSerial dfSerial(2);
DFRobotDFPlayerMini player;
bool playerReady = false;
uint32_t activeMoveDurationMs = 350;
uint32_t lastServoTick = 0;
bool popHolding = false;
uint32_t popStartedAt = 0;
String commandBuffer;

/**
 * Find a body servo by its protocol name; the GLOBO is intentionally excluded.
 */
ServoMotion *findBodyServo(const String &part) {
  for (size_t i = 0; i < BODY_SERVO_COUNT; ++i) {
    if (part.equals(servos[i].name)) {
      return &servos[i];
    }
  }
  return nullptr;
}

/**
 * Start a timed, non-blocking transition to a validated servo angle.
 */
void moveServo(ServoMotion &motion, int angle, uint32_t durationMs) {
  if (angle < 0 || angle > 180) {
    return;
  }
  motion.startAngle = motion.currentAngle;
  motion.targetAngle = static_cast<float>(angle);
  motion.startedAt = millis();
  motion.durationMs = max(static_cast<uint32_t>(100), durationMs);
  motion.moving = true;
}

/**
 * Convert a fractional angle to a pulse, preserving sub-degree motion steps.
 */
int angleToPulseUs(float angle) {
  const float pulseRange =
      static_cast<float>(SERVO_MAX_PULSE_US - SERVO_MIN_PULSE_US);
  const float pulse = SERVO_MIN_PULSE_US + angle * pulseRange / 180.0f;
  return static_cast<int>(pulse + 0.5f);
}

/**
 * Advance one servo with quintic easing for gentle starts and stops.
 */
void updateServo(ServoMotion &motion, uint32_t now) {
  if (!motion.moving) {
    return;
  }
  const uint32_t elapsed = now - motion.startedAt;
  const float progress = min(1.0f, static_cast<float>(elapsed) /
                                      static_cast<float>(motion.durationMs));
  const float progressSquared = progress * progress;
  const float progressCubed = progressSquared * progress;
  const float easedProgress =
      progressCubed * (progress * (progress * 6.0f - 15.0f) + 10.0f);
  motion.currentAngle =
      motion.startAngle +
      (motion.targetAngle - motion.startAngle) * easedProgress;
  motion.servo.writeMicroseconds(angleToPulseUs(motion.currentAngle));
  if (progress >= 1.0f) {
    motion.currentAngle = motion.targetAngle;
    motion.moving = false;
  }
}

/**
 * Send an integer track number to the DFPlayer when initialization succeeded.
 */
void playTrack(const String &trackText) {
  if (!playerReady || trackText.length() != 4) {
    return;
  }
  for (size_t i = 0; i < trackText.length(); ++i) {
    if (!isDigit(trackText[i])) {
      return;
    }
  }
  const int track = trackText.toInt();
  if (track >= 1 && track <= 9999) {
    player.play(static_cast<uint16_t>(track));
  }
}

/**
 * Trigger the explicit pop sequence; no other command moves the GLOBO servo.
 */
void startPop() {
  ServoMotion &globo = servos[BODY_SERVO_COUNT];
  popHolding = true;
  popStartedAt = millis();
  moveServo(globo, 180, 150);
}

/**
 * Parse one complete protocol line; malformed input is ignored silently.
 */
void handleCommand(const String &line) {
  if (line == "POP") {
    startPop();
    return;
  }
  if (line == "RESET_GLOBO") {
    popHolding = false;
    moveServo(servos[BODY_SERVO_COUNT], 0, 1800);
    return;
  }
  if (line.startsWith("DFP:")) {
    playTrack(line.substring(4));
    return;
  }
  if (line.startsWith("SPEED:")) {
    const int separator = line.indexOf(':', 6);
    if (separator < 0) {
      return;
    }
    const String mode = line.substring(6, separator);
    const String valueText = line.substring(separator + 1);
    const long value = valueText.toInt();
    if ((mode == "IDLE" || mode == "ACTION") &&
        valueText.length() > 0 && value >= 100 && value <= 3000) {
      activeMoveDurationMs = static_cast<uint32_t>(value);
    }
    return;
  }
  if (!line.startsWith("SERVO:")) {
    return;
  }

  const int separator = line.indexOf(':', 6);
  if (separator < 0) {
    return;
  }
  const String part = line.substring(6, separator);
  const String angleText = line.substring(separator + 1);
  if (angleText.isEmpty()) {
    return;
  }
  for (size_t i = 0; i < angleText.length(); ++i) {
    if (!isDigit(angleText[i])) {
      return;
    }
  }
  int angle = angleText.toInt();
  ServoMotion *motion = findBodyServo(part);
  if (part == "L_ARM" && angle > 120) {
    angle = 120;
  }
  if (motion != nullptr && angle >= 0 && angle <= 180) {
    moveServo(*motion, angle, activeMoveDurationMs);
  }
}

/**
 * Read serial input incrementally and dispatch only newline-terminated commands.
 */
void readCommands() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());
    if (incoming == '\n') {
      commandBuffer.trim();
      if (!commandBuffer.isEmpty()) {
        handleCommand(commandBuffer);
      }
      commandBuffer = "";
    } else if (incoming != '\r' && commandBuffer.length() < 80) {
      commandBuffer += incoming;
    } else if (commandBuffer.length() >= 80) {
      commandBuffer = "";
    }
  }
}

/**
 * Finish the pop hold after 500 ms and return the needle to its safe endpoint.
 */
void updatePop(uint32_t now) {
  if (popHolding && now - popStartedAt >= GLOBO_POP_HOLD_MS) {
    popHolding = false;
    moveServo(servos[BODY_SERVO_COUNT], 0, 250);
  }
}

/**
 * Configure serial ports and servos at their initial safe positions.
 */
void setup() {
  Serial.begin(115200);
  dfSerial.begin(DFPLAYER_BAUD, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);
  playerReady = player.begin(dfSerial, true, false);
  if (playerReady) {
    player.volume(20);
  } else {
    Serial.println("DFPLAYER:ERROR");
  }

  for (size_t i = 0; i < SERVO_COUNT; ++i) {
    servos[i].servo.setPeriodHertz(50);
    servos[i].servo.attach(servos[i].pin, SERVO_MIN_PULSE_US,
                           SERVO_MAX_PULSE_US);
    servos[i].currentAngle = (i == BODY_SERVO_COUNT) ? 0 : 90;
    servos[i].servo.writeMicroseconds(angleToPulseUs(servos[i].currentAngle));
  }
  lastServoTick = millis();
  Serial.print("ESP32:READY\n");
}

/**
 * Read commands and update servo trajectories using millis(), never delay().
 */
void loop() {
  readCommands();
  const uint32_t now = millis();
  updatePop(now);
  if (now - lastServoTick >= SERVO_TICK_MS) {
    lastServoTick = now;
    for (size_t i = 0; i < SERVO_COUNT; ++i) {
      updateServo(servos[i], now);
    }
  }
}
