// SeatMonitorOLED: OLED extension of the supplied diagnostic sketch.
// V2.2: A timeout latches an admin-only lock, even if sensors later report IN_USE.
// Distances are UNCALIBRATED; 10-second alert remains a demo setting.
// 第二行：超時後顯示「超时待确认」，直到收到 JSON Lines 管理員釋放指令。
// 假設門檻演示版：使用真實傳感器讀值，但距離範圍未經校準。
#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <U8x8lib.h>
#include <EEPROM.h>
#include <avr/pgmspace.h>

// OLED: SSD1306 128x64; shares SDA=A4 and SCL=A5 with VL53L0X.
// Text mode avoids a 1024-byte full-screen framebuffer on UNO R3.
U8X8_SSD1306_128X64_NONAME_HW_I2C oled(U8X8_PIN_NONE);
bool oledReady = false;
unsigned long lastScreen = 0;
bool screenShown = false;

// 5 个 16x16 中文字模：「超时待确认」。
// 采用 U8x8 的 8x8 tile 格式，放在 PROGMEM 以节省 UNO SRAM。
const uint8_t LOCK_TEXT_TILES[5][32] PROGMEM = {
  { // 超
    0x00, 0x00, 0xA4, 0xA4, 0xFF, 0xFF, 0x24, 0x24,
    0xB2, 0x9E, 0x8E, 0x92, 0x9E, 0x9E, 0x00, 0x00,
    0x00, 0x00, 0x3F, 0x0E, 0x1F, 0x1F, 0x31, 0x31,
    0x37, 0x37, 0x34, 0x34, 0x37, 0x37, 0x00, 0x00
  },
  { // 时
    0x00, 0x00, 0xFE, 0x46, 0x46, 0xFE, 0xFE, 0x58,
    0xD8, 0x98, 0x18, 0xFF, 0xFF, 0x18, 0x18, 0x00,
    0x00, 0x00, 0x0F, 0x04, 0x04, 0x07, 0x07, 0x00,
    0x00, 0x33, 0x31, 0x3F, 0x1F, 0x00, 0x00, 0x00
  },
  { // 待
    0x00, 0x80, 0xCC, 0xE6, 0xFB, 0x19, 0xB6, 0xB6,
    0xB6, 0xBF, 0xBF, 0xF6, 0xF6, 0xB6, 0x30, 0x00,
    0x00, 0x00, 0x01, 0x3F, 0x3F, 0x00, 0x01, 0x07,
    0x0D, 0x11, 0x31, 0x3F, 0x1F, 0x01, 0x00, 0x00
  },
  { // 确
    0x00, 0x00, 0xC6, 0xFE, 0x4E, 0xC6, 0xD6, 0xF8,
    0xFE, 0x93, 0xFA, 0x9E, 0x96, 0xF0, 0x00, 0x00,
    0x00, 0x01, 0x03, 0x1F, 0x08, 0x0F, 0x1F, 0x3F,
    0x07, 0x02, 0x03, 0x32, 0x32, 0x3F, 0x00, 0x00
  },
  { // 认
    0x00, 0x00, 0x30, 0x33, 0xF6, 0x04, 0x00, 0x00,
    0x00, 0xFF, 0xFF, 0x80, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x18, 0x1F, 0x0C, 0x16, 0x38,
    0x1E, 0x07, 0x01, 0x0F, 0x1C, 0x38, 0x10, 0x00
  },
};



// 沿用你們已測通的接法：椅墊 D2/GND、托盤訊號 A0、測距 I2C。
// 先不改線、不接 LED。保留原始測試程式的副本。
const uint8_t SEAT_PIN = 2;
const uint8_t DESK_PIN = A0;
const int DESK_ON = 300;    // 沿用原程式，仍須核對安裝後實測
const int DESK_OFF = 500;

// 使用者設定的距離門檻；仍須在實際安裝位置驗證。
const bool ENABLE_DEMO_RULES = true;
const uint16_t PRESENT_MIN_MM = 1;    // 正的有效讀數，排除0及INVALID
const uint16_t PRESENT_MAX_MM = 139;  // 小於140mm：有人
const uint16_t ABSENT_MIN_MM = 140;   // 大於或等於140mm：無人

// 以下為待實測的工程設定，不是圖書館政策。
const unsigned long SAMPLE_MS = 300UL;
const unsigned long STABLE_MS = 2000UL;
const unsigned long FREE_CONFIRM_MS = 3000UL;
const unsigned long MAX_GAP_MS = 2000UL;
const unsigned long AWAY_LIMIT_MS = 10000UL; // 加速演示：10 秒

// 可選的普通三色 LED（不是文字顯示屏）。目前保持 false，不會操作這些腳位。
// 只有確認 LED/限流電阻與接線表後才啟用；D4/D5/D6 是預留方案。
const bool USE_LEDS = false;
const uint8_t GREEN_PIN = 4;
const uint8_t YELLOW_PIN = 5;
const uint8_t RED_PIN = 6;

Adafruit_VL53L0X distanceSensor;
bool sensorReady = false;
bool deskKnown = false;
bool deskPressed = false;

enum State { UNKNOWN, IN_USE, AWAY, FREE };  // 只描述物理状态，不承担管理员锁定
State state = UNKNOWN;
State candidate = UNKNOWN;
unsigned long candidateSince = 0;
unsigned long awaySince = 0;
bool awayRunning = false;
// 独立于物理状态的锁存告警，普通传感器变化绝不能自动清除。
const int EEPROM_LOCK_ADDR = 0;
const int EEPROM_REARM_ADDR = 1;
const int EEPROM_AWAY_ADDR = 2; // 4-byte unsigned long, 2..5
const uint8_t EEPROM_LOCK_MARKER = 0xA5;
const uint8_t EEPROM_NEEDS_REARM = 0xD3;
bool alertLocked = false;
bool alertArmed = true;  // 管理员刚释放旧事件后，等待一个新的稳定 IN_USE/FREE 周期
bool newAlert = false;
unsigned long lockedAwayMs = 0;  // 超时快照；重启后仍可显示
// Serial Protocol v1.0: JSON Lines (one UTF-8/ASCII JSON object per line).
// Only I/O encoding is changed; sensing, lock, timers, EEPROM and OLED are unchanged.
const char RELEASE_JSON[] = "{\"v\":1,\"type\":\"command\",\"action\":\"RELEASE\",\"id\":\"A01\"}";
char commandBuffer[80] = {};
uint8_t commandLength = 0;
bool commandDiscarding = false;
unsigned long telemetrySeq = 0;
unsigned long lastSample = 0;
bool haveSample = false;

bool rulesEnabled() {
  return ENABLE_DEMO_RULES && PRESENT_MIN_MM > 0 &&
         PRESENT_MAX_MM >= PRESENT_MIN_MM && ABSENT_MIN_MM > PRESENT_MAX_MM;
}

void clearEvidence() {
  state = UNKNOWN;
  candidate = UNKNOWN;
  awayRunning = false;
  // 不在这里修改 alertLocked / alertArmed / lockedAwayMs。
  // 候选状态变化或传感器异常只清除普通检测证据。
}

// 純判斷部分：valid=false 時立即中斷連續證據，不將未知時間算入。
void updateState(unsigned long now, bool valid, bool seat,
                 bool distancePresent, bool distanceAbsent, bool tray) {
  newAlert = false;
  if (!valid || (!distancePresent && !distanceAbsent) ||
      seat != distancePresent) {
    clearEvidence();
    return;
  }
  State next = seat ? IN_USE : (tray ? AWAY : FREE);
  if (next != candidate) {
    clearEvidence();
    candidate = next;
    candidateSince = now;
  }
  unsigned long stableFor = next == FREE ? FREE_CONFIRM_MS : STABLE_MS;
  if ((unsigned long)(now - candidateSince) < stableFor) {
    state = UNKNOWN;
    return;
  }
  state = next;
  if (next == AWAY) {
    if (!awayRunning) {
      awayRunning = true;
      awaySince = now;
    }
    unsigned long awayMs = (unsigned long)(now - awaySince);
    if (alertLocked && awayMs > lockedAwayMs) lockedAwayMs = awayMs;
    if (!alertLocked && alertArmed && awayMs >= AWAY_LIMIT_MS) {
      // 仅在第一次超时触发锁定，不因传感器改变而自动解锁。
      lockedAwayMs = awayMs;
      EEPROM.put(EEPROM_AWAY_ADDR, lockedAwayMs);
      EEPROM.update(EEPROM_REARM_ADDR, EEPROM_NEEDS_REARM);
      EEPROM.update(EEPROM_LOCK_ADDR, EEPROM_LOCK_MARKER); // 最后写入有效锁定标志
      alertArmed = false;
      alertLocked = true;
      newAlert = true;
    }
  } else if (!alertLocked && !alertArmed && (next == IN_USE || next == FREE)) {
    // 管理员释放旧事件后，只有新一轮稳定使用/空闲才重新启用超时。
    alertArmed = true;
    EEPROM.update(EEPROM_REARM_ADDR, 0x00);
  }
}

unsigned long displayAwayMs(unsigned long now) {
  if (alertLocked) {
    if (awayRunning && state == AWAY) {
      unsigned long measured = (unsigned long)(now - awaySince);
      return measured > lockedAwayMs ? measured : lockedAwayMs;
    }
    return lockedAwayMs;
  }
  return awayRunning && state == AWAY ? (unsigned long)(now - awaySince) : 0UL;
}

// Outbound serial messages must ALL be one valid JSON object per line.
void printJsonBool(bool value) {
  Serial.print(value ? F("true") : F("false"));
}

void printJsonPhysicalState() {
  switch (state) {
    case IN_USE: Serial.print(F("IN_USE")); break;
    case AWAY:   Serial.print(F("AWAY")); break;
    case FREE:   Serial.print(F("FREE")); break;
    default:     Serial.print(F("UNKNOWN")); break;
  }
}

void printJsonReason(bool distanceValid, bool distancePresent,
                     bool distanceAbsent, bool seat) {
  if (alertLocked) Serial.print(F("WAIT_ADMIN"));
  else if (!rulesEnabled()) Serial.print(F("CONFIG_INVALID"));
  else if (!deskKnown) Serial.print(F("TRAY_UNKNOWN"));
  else if (!sensorReady) Serial.print(F("DISTANCE_INIT_FAILED"));
  else if (!distanceValid) Serial.print(F("DISTANCE_INVALID"));
  else if (!distancePresent && !distanceAbsent) Serial.print(F("DISTANCE_UNCERTAIN"));
  else if (seat != distancePresent) Serial.print(F("SENSOR_CONFLICT"));
  else if (state == UNKNOWN) Serial.print(F("STABILIZING"));
  else Serial.print(F("NORMAL"));
}

void emitBoot() {
  Serial.print(F("{\"v\":1,\"type\":\"boot\",\"id\":\"A01\",\"locked\":"));
  printJsonBool(alertLocked);
  Serial.print(F(",\"armed\":"));
  printJsonBool(alertArmed);
  Serial.print(F(",\"away_ms\":"));
  Serial.print(alertLocked ? lockedAwayMs : 0UL);
  Serial.println('}');
}

void emitError(const __FlashStringHelper *code) {
  Serial.print(F("{\"v\":1,\"type\":\"error\",\"id\":\"A01\",\"code\":\""));
  Serial.print(code);
  Serial.println(F("\"}"));
}

void emitReleaseAck(const __FlashStringHelper *result) {
  Serial.print(F("{\"v\":1,\"type\":\"ack\",\"id\":\"A01\",\"action\":\"RELEASE\",\"result\":\""));
  Serial.print(result);
  Serial.print(F("\",\"locked\":"));
  printJsonBool(alertLocked);
  Serial.println('}');
}

// Only encoding of the admin command changes. The previous release behavior is preserved.
void releaseSeatByAdmin() {
  if (!alertLocked) {
    emitReleaseAck(F("NO_ACTIVE_LOCK"));
    return;
  }
  EEPROM.update(EEPROM_REARM_ADDR, EEPROM_NEEDS_REARM);
  EEPROM.update(EEPROM_LOCK_ADDR, 0x00);
  alertLocked = false;
  alertArmed = false;
  lockedAwayMs = 0;
  clearEvidence();
  screenShown = false;
  emitReleaseAck(F("RELEASED"));
}

// Fixed canonical command format keeps UNO memory usage low (no extra JSON library).
// A line with other whitespace, order or fields is rejected with BAD_COMMAND.
// A too-long line is discarded in full until newline, never executed in pieces.
void pollAdminCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (commandDiscarding) {
        commandDiscarding = false;
      } else if (commandLength != 0) {
        commandBuffer[commandLength] = '\0';
        if (strcmp(commandBuffer, RELEASE_JSON) == 0) releaseSeatByAdmin();
        else emitError(F("BAD_COMMAND"));
      }
      commandLength = 0;
    } else if (commandDiscarding) {
      // Discard characters until the terminating newline.
    } else if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = c;
    } else {
      commandLength = 0;
      commandDiscarding = true;
      emitError(F("COMMAND_TOO_LONG"));
    }
  }
}

void showLeds(unsigned long now) {
  if (!USE_LEDS) return;
  bool blinkOn = (now / 500UL) % 2 == 0;
  if (alertLocked) {
    digitalWrite(GREEN_PIN, LOW);
    digitalWrite(YELLOW_PIN, LOW);
    digitalWrite(RED_PIN, blinkOn ? HIGH : LOW);
    return;
  }
  digitalWrite(GREEN_PIN, state == FREE ? HIGH : LOW);
  digitalWrite(YELLOW_PIN, (state == AWAY || (state == UNKNOWN && blinkOn)) ? HIGH : LOW);
  digitalWrite(RED_PIN, state == IN_USE ? HIGH : LOW);
}


// Locate OLED before initializing the ToF sensor. Addresses are 7-bit here.
bool i2cFound(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void setupOled() {
  Wire.begin();
  uint8_t address = 0;
  if (i2cFound(0x3C)) address = 0x3C;
  else if (i2cFound(0x3D)) address = 0x3D;
  if (address == 0) {
    emitError(F("OLED_NOT_FOUND"));
    return;
  }
  oled.setI2CAddress(address << 1);
  oled.setBusClock(100000UL);
  oled.begin();
  oled.setPowerSave(0);
  oled.setFont(u8x8_font_chroma48medium8_r);
  oled.clearDisplay();
  oled.drawString(0, 0, "SEAT 01");
  oled.drawString(0, 3, "Starting...");
  oledReady = true; // Address acknowledged; visible output still needs checking.
}

void screenLine(uint8_t row) {
  oled.drawString(0, row, "                ");
  oled.setCursor(0, row);
}

// 用五个自定义 16x16 中文字模显示「超时待确认」。
// 第二行占用 tile 行 3、4；普通状态需清除这两行避免残影。
void drawTimeoutChinese() {
  uint8_t tileRow[16];
  for (uint8_t glyph = 0; glyph < 5; ++glyph) {
    memcpy_P(tileRow, &LOCK_TEXT_TILES[glyph][0], 16);
    oled.drawTile((uint8_t)(3 + glyph * 2), 3, 2, tileRow);
    memcpy_P(tileRow, &LOCK_TEXT_TILES[glyph][16], 16);
    oled.drawTile((uint8_t)(3 + glyph * 2), 4, 2, tileRow);
  }
}

// Three visible lines; locked state displays 16x16 Chinese glyphs; diagnostics stay on Serial.
// Display uses English labels with the existing small-memory text font.
void showOled(unsigned long now, bool seat, int deskValue,
              bool valid, uint16_t mm) {
  if (!oledReady) return;
  if (screenShown && (unsigned long)(now - lastScreen) < 500UL) return;
  if (!screenShown) oled.clearDisplay();
  screenShown = true;
  lastScreen = now;

  screenLine(0);
  oled.print(F("SEAT 01"));

  screenLine(3);
  screenLine(4);
  if (alertLocked) {
    drawTimeoutChinese();
  } else {
    oled.setCursor(0, 3);
    switch (state) {
      case IN_USE: oled.print(F("IN USE")); break;
      case AWAY:   oled.print(F("TEMP AWAY")); break;
      case FREE:   oled.print(F("FREE")); break;
      default:     oled.print(F("CHECKING")); break;
    }
  }

  screenLine(6);
  if (alertLocked || (awayRunning && state == AWAY)) {
    unsigned long seconds = displayAwayMs(now) / 1000UL;
    oled.print(F("Away: "));
    if (seconds / 60UL < 10UL) oled.print('0');
    oled.print(seconds / 60UL);
    oled.print(':');
    if (seconds % 60UL < 10UL) oled.print('0');
    oled.print(seconds % 60UL);
  } else {
    oled.print(F("Away: --:--"));
  }
}

void setup() {
  Serial.begin(9600);  // Retained from V2.2 by request.
  alertLocked = EEPROM.read(EEPROM_LOCK_ADDR) == EEPROM_LOCK_MARKER;
  alertArmed = !alertLocked && EEPROM.read(EEPROM_REARM_ADDR) != EEPROM_NEEDS_REARM;
  if (alertLocked) EEPROM.get(EEPROM_AWAY_ADDR, lockedAwayMs);
  emitBoot();
  pinMode(SEAT_PIN, INPUT_PULLUP);
  if (USE_LEDS) {
    pinMode(GREEN_PIN, OUTPUT);
    pinMode(YELLOW_PIN, OUTPUT);
    pinMode(RED_PIN, OUTPUT);
    showLeds(0);
  }
  setupOled();
  sensorReady = distanceSensor.begin();
  if (sensorReady) {
    sensorReady = distanceSensor.configSensor(
      Adafruit_VL53L0X::VL53L0X_SENSE_HIGH_ACCURACY);
  }
  if (!sensorReady) emitError(F("DISTANCE_INIT_FAILED"));
  if (!rulesEnabled()) emitError(F("CONFIG_INVALID"));
}

void loop() {
  unsigned long now = millis();
  pollAdminCommands();
  showLeds(now);
  if (haveSample && (unsigned long)(now - lastSample) < SAMPLE_MS) return;

  bool seat = digitalRead(SEAT_PIN) == LOW;
  int deskValue = analogRead(DESK_PIN);
  if (deskValue < DESK_ON) {
    deskPressed = true;
    deskKnown = true;
  } else if (deskValue > DESK_OFF) {
    deskPressed = false;
    deskKnown = true;
  }
  // 開機落在300~500之間時仍未知；之後在這區間維持上一個有效判斷。

  VL53L0X_RangingMeasurementData_t measurement = {};
  int error = -1;
  if (sensorReady) error = distanceSensor.rangingTest(&measurement, false);
  bool distanceValid = sensorReady && error == 0 &&
                       measurement.RangeStatus == 0 && measurement.RangeMilliMeter > 0;
  uint16_t mm = measurement.RangeMilliMeter;
  bool distancePresent = distanceValid && mm >= PRESENT_MIN_MM && mm <= PRESENT_MAX_MM;
  bool distanceAbsent = distanceValid && mm >= ABSENT_MIN_MM;

  // 使用完成讀取後的時間；過長的讀取間隔會清除先前連續證據。
  now = millis();
  unsigned long gapMs = haveSample ? (unsigned long)(now - lastSample) : 0UL;
  bool gapReset = haveSample && gapMs > MAX_GAP_MS;
  if (gapReset) clearEvidence();
  haveSample = true;
  lastSample = now;
  updateState(now, rulesEnabled() && deskKnown && distanceValid,
              seat, distancePresent, distanceAbsent, deskPressed);
  showLeds(now);
  showOled(now, seat, deskValue, distanceValid, mm);

  // A single JSON object on each line, including telemetry, boot, ACK and errors.
  // Compact flat schema avoids heap allocations and expensive dynamic Strings on UNO.
  Serial.print(F("{\"v\":1,\"type\":\"telemetry\",\"id\":\"A01\",\"seq\":"));
  Serial.print(telemetrySeq++);
  Serial.print(F(",\"ms\":")); Serial.print(now);
  Serial.print(F(",\"seat\":")); printJsonBool(seat);
  Serial.print(F(",\"tray_raw\":")); Serial.print(deskValue);
  Serial.print(F(",\"tray\":"));
  if (deskKnown) printJsonBool(deskPressed); else Serial.print(F("null"));
  Serial.print(F(",\"distance_mm\":"));
  if (distanceValid) Serial.print(mm); else Serial.print(F("null"));
  Serial.print(F(",\"distance_valid\":")); printJsonBool(distanceValid);
  Serial.print(F(",\"physical\":\"")); printJsonPhysicalState();
  Serial.print(F("\",\"state\":\""));
  if (alertLocked) Serial.print(F("LOCKED")); else printJsonPhysicalState();
  Serial.print(F("\",\"locked\":")); printJsonBool(alertLocked);
  Serial.print(F(",\"armed\":")); printJsonBool(alertArmed);
  Serial.print(F(",\"away_ms\":")); Serial.print(displayAwayMs(now));
  Serial.print(F(",\"reason\":\""));
  printJsonReason(distanceValid, distancePresent, distanceAbsent, seat);
  Serial.print(F("\",\"new_alert\":")); printJsonBool(newAlert);
  Serial.println('}');
}
