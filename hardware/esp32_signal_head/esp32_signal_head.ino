/*
 * SmartTraffic - hardware-in-the-loop signal head
 *
 * Drives a physical model junction from the SmartTraffic controller. The board
 * polls /api/hil/state and mirrors whatever the controller decided, so the LEDs
 * on the table are the same decision the benchmark charts are reporting.
 *
 * Wire format returned by the backend (single ASCII line, no JSON needed):
 *
 *     T42|J1:GRR|J2:RGR|J3:RRA|J4:GRR
 *
 * Aspects are NS, EW, PED in that order; G green, A amber, R red.
 *
 * Board:  ESP32 DevKit v1
 * Wiring: see hardware/README.md
 */

#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID     = "your-ssid";
const char* WIFI_PASSWORD = "your-password";

// Host running `uvicorn app.main:app`, reachable on the same LAN.
const char* API_URL = "http://192.168.1.10:8000/api/hil/state?format=wire";

const uint16_t POLL_INTERVAL_MS = 500;
const uint32_t HTTP_TIMEOUT_MS  = 1500;

// If the backend goes quiet for this long, fail safe to flashing amber rather
// than holding a stale green. This mirrors what a real controller cabinet does.
const uint32_t LINK_TIMEOUT_MS = 3000;

// Marks a head position that is not physically wired.
#define PIN_NONE 255

struct Head {
  const char* id;
  uint8_t nsGreen, nsAmber, nsRed;
  uint8_t ewGreen, ewAmber, ewRed;
  uint8_t pedGreen;
};

// One junction per row, 7 LEDs each. A bare ESP32 has enough output-capable
// GPIOs for two full heads; GPIO 34-39 are input-only and must not be used to
// drive LEDs. To build all four junctions, chain two 74HC595 shift registers
// and replace setPin() with a shift-out - see hardware/README.md.
Head heads[] = {
  {"J1", 13, 12, 14,  27, 26, 25,  33},
  {"J2", 32, 15,  2,   4, 16, 17,   5}
};

const uint8_t HEAD_COUNT = sizeof(heads) / sizeof(heads[0]);

uint32_t lastGoodResponse = 0;
bool     flashState       = false;

void setPin(uint8_t pin, bool on) {
  if (pin == PIN_NONE) return;
  digitalWrite(pin, on ? HIGH : LOW);
}

void configurePins() {
  for (uint8_t i = 0; i < HEAD_COUNT; i++) {
    uint8_t pins[] = {
      heads[i].nsGreen, heads[i].nsAmber, heads[i].nsRed,
      heads[i].ewGreen, heads[i].ewAmber, heads[i].ewRed,
      heads[i].pedGreen
    };
    for (uint8_t p = 0; p < 7; p++) {
      if (pins[p] == PIN_NONE) continue;
      pinMode(pins[p], OUTPUT);
      digitalWrite(pins[p], LOW);
    }
  }
}

void applyAspect(const Head& head, char ns, char ew, char ped) {
  setPin(head.nsGreen, ns == 'G');
  setPin(head.nsAmber, ns == 'A');
  setPin(head.nsRed,   ns == 'R');
  setPin(head.ewGreen, ew == 'G');
  setPin(head.ewAmber, ew == 'A');
  setPin(head.ewRed,   ew == 'R');
  setPin(head.pedGreen, ped == 'G');
}

// Fail-safe: flash every amber, all reds on. Never leave a green lit on a link
// we can no longer trust.
void failSafe() {
  flashState = !flashState;
  for (uint8_t i = 0; i < HEAD_COUNT; i++) {
    setPin(heads[i].nsGreen, false);
    setPin(heads[i].ewGreen, false);
    setPin(heads[i].pedGreen, false);
    setPin(heads[i].nsRed, true);
    setPin(heads[i].ewRed, true);
    setPin(heads[i].nsAmber, flashState);
    setPin(heads[i].ewAmber, flashState);
  }
}

int findHead(const char* id) {
  for (uint8_t i = 0; i < HEAD_COUNT; i++) {
    if (strcmp(heads[i].id, id) == 0) return i;
  }
  return -1;
}

// Parses "T42|J1:GRR|J2:RGR|..." in place.
bool applyWire(char* payload) {
  bool applied = false;
  char* saveOuter = nullptr;
  char* token = strtok_r(payload, "|", &saveOuter);

  while (token != nullptr) {
    if (token[0] != 'T') {                 // skip the tick field
      char* colon = strchr(token, ':');
      if (colon != nullptr && strlen(colon + 1) >= 3) {
        *colon = '\0';
        int idx = findHead(token);
        if (idx >= 0) {
          const char* code = colon + 1;
          applyAspect(heads[idx], code[0], code[1], code[2]);
          applied = true;
        }
      }
    }
    token = strtok_r(nullptr, "|", &saveOuter);
  }
  return applied;
}

void setup() {
  Serial.begin(115200);
  configurePins();

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.printf("\nconnected: %s\n", WiFi.localIP().toString().c_str());
  lastGoodResponse = millis();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);
    http.begin(API_URL);

    int status = http.GET();
    if (status == 200) {
      String body = http.getString();
      char buffer[256];
      body.toCharArray(buffer, sizeof(buffer));
      if (applyWire(buffer)) {
        lastGoodResponse = millis();
      }
      Serial.println(body);
    } else {
      Serial.printf("http %d\n", status);
    }
    http.end();
  }

  if (millis() - lastGoodResponse > LINK_TIMEOUT_MS) {
    failSafe();
  }

  delay(POLL_INTERVAL_MS);
}
