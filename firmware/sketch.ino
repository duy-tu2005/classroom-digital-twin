#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHTesp.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Preferences.h>
#include "config.h"
#include "secrets.h"
#include "people-counter.h"

WiFiClient wifi;
PubSubClient mqtt(wifi);
DHTesp dht;
bool lights[4] = {false, false, false, false};
bool fanState = false;
bool fanAuto = true;
PeopleCounter people(IR_DEBOUNCE_MS, IR_CROSSING_TIMEOUT_MS);
Preferences countStorage;
bool storageReady = false;
SemaphoreHandle_t counterMutex;
SemaphoreHandle_t storageMutex;
volatile bool counterDirty = false;
bool vacancyHold = false;
unsigned long vacantSince = 0;
unsigned long lastSample = 0;
unsigned long nextWifi = 0;
unsigned long nextMqtt = 0;
unsigned long mqttBackoff = 1000;
uint32_t sequenceNo = 0;
uint32_t bootId = 0;

bool due(unsigned long now, unsigned long target) { return (long)(now - target) >= 0; }
bool publish(const char* topic, JsonDocument& doc) {
  char buffer[MQTT_BUFFER_SIZE];
  size_t n = serializeJson(doc, buffer, sizeof(buffer));
  if (!n || n >= sizeof(buffer)) return false;
  bool ok = mqtt.publish(topic, (uint8_t*)buffer, n, false);
  Serial.printf("[MQTT] topic=%s publish=%s payload=%s\n", topic, ok ? "OK" : "FAILED", buffer);
  return ok;
}
bool boolParam(JsonVariantConst p, bool& out) {
  if (p.is<bool>()) { out = p.as<bool>(); return true; }
  if (p.is<JsonObjectConst>()) {
    if (p["state"].is<bool>()) { out = p["state"].as<bool>(); return true; }
    if (p["value"].is<bool>()) { out = p["value"].as<bool>(); return true; }
  }
  return false;
}
void setFanOutput(bool on) { fanState = on; digitalWrite(GPIO_FAN, on ? HIGH : LOW); }
void saveCounts() {
  // Serialize snapshots + commits, including an RPC reset racing a gate event.
  // Keep flash I/O outside counterMutex so sampling can continue during commit.
  xSemaphoreTake(storageMutex, portMAX_DELAY);
  xSemaphoreTake(counterMutex, portMAX_DELAY);
  PeopleCounter::Snapshot snapshot = people.counts;
  xSemaphoreGive(counterMutex);
  if (storageReady) countStorage.putBytes("counts-v1", &snapshot, sizeof(snapshot));
  xSemaphoreGive(storageMutex);
}
void updateAutoFan(unsigned long now) {
  xSemaphoreTake(counterMutex, portMAX_DELAY);
  if (people.counts.occupancy > 0) vacancyHold = false;
  bool shouldRun = people.counts.occupancy > 0 || (vacancyHold && now - vacantSince < FAN_HOLD_MS);
  xSemaphoreGive(counterMutex);
  if (fanAuto) setFanOutput(shouldRun);
}
void addCounterState(JsonDocument& doc) {
  xSemaphoreTake(counterMutex, portMAX_DELAY);
  doc["occupancy"] = people.counts.occupancy;
  doc["total_entered"] = people.counts.entered;
  doc["total_exited"] = people.counts.exited;
  doc["counter_errors"] = people.counts.errors;
  doc["counter_needs_calibration"] = people.counts.uncertain;
  doc["counter_state"] = people.state();
  doc["ir_a_blocked"] = (people.blocked() & 1) != 0;
  doc["ir_b_blocked"] = (people.blocked() & 2) != 0;
  xSemaphoreGive(counterMutex);
}
void counterTask(void*) {
  // Keep sampling while Wi-Fi / MQTT connect calls block the Arduino loop.
  for (;;) {
    uint32_t now = millis();
    xSemaphoreTake(counterMutex, portMAX_DELAY);
    uint8_t oldBeams = people.blocked();
    PeopleCounter::Event event = people.update(digitalRead(GPIO_IR_A) == LOW, digitalRead(GPIO_IR_B) == LOW, now);
    if (event == PeopleCounter::EXITED && people.counts.occupancy == 0) { vacantSince = now; vacancyHold = true; }
    if (event != PeopleCounter::NONE || oldBeams != people.blocked()) counterDirty = true;
    PeopleCounter::Snapshot snapshot = people.counts;
    xSemaphoreGive(counterMutex);
    if (event != PeopleCounter::NONE) {
      saveCounts();
      Serial.printf("[COUNT] %s occupancy=%u entered=%u exited=%u errors=%u\n",
        event == PeopleCounter::ENTERED ? "IN" : event == PeopleCounter::EXITED ? "OUT" : "REJECTED",
        snapshot.occupancy, snapshot.entered, snapshot.exited, snapshot.errors);
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}
void sendTelemetry() {
  if (!mqtt.connected()) return;
  TempAndHumidity env = dht.getTempAndHumidity();
  bool valid = isfinite(env.temperature) && isfinite(env.humidity) &&
    env.temperature >= -40 && env.temperature <= 80 && env.humidity >= 0 && env.humidity <= 100;
  StaticJsonDocument<1536> doc;
  doc["sequence"] = ++sequenceNo;
  doc["boot_id"] = bootId;
  doc["uptime_s"] = millis() / 1000;
  doc["sensor_valid"] = valid;
  if (valid) { doc["temperature"] = env.temperature; doc["humidity"] = env.humidity; }
  addCounterState(doc);
  doc["rssi"] = WiFi.RSSI();
  doc["fan_state"] = digitalRead(GPIO_FAN) == HIGH;
  doc["fan_mode"] = fanAuto ? "AUTO" : "MANUAL";
  doc["fan_hold_s"] = FAN_HOLD_MS / 1000;
  doc["firmware_version"] = FIRMWARE_VERSION;
  for (int i = 0; i < 4; i++) {
    String key = "light" + String(i + 1) + "_state";
    doc[key] = digitalRead(GPIO_LIGHTS[i]) == HIGH;
  }
  publish("v1/devices/me/telemetry", doc);
}
void onRpc(char* topic, byte* payload, unsigned int length) {
  String t(topic), prefix("v1/devices/me/rpc/request/");
  if (!t.startsWith(prefix)) return;
  String responseTopic = "v1/devices/me/rpc/response/" + t.substring(prefix.length());
  StaticJsonDocument<512> req;
  StaticJsonDocument<1536> res;
  res["firmware_version"] = FIRMWARE_VERSION;
  auto err = deserializeJson(req, payload, length);
  res["success"] = false;
  bool changed = false;
  if (err) { res["error"] = "INVALID_JSON"; }
  else {
    String method = req["method"] | "";
    JsonVariantConst p = req["params"];
    int channel = -1;
    for (int i = 0; i < 4; i++) {
      if (method == "setLight" + String(i + 1) || method == "getLight" + String(i + 1)) channel = i;
    }
    bool v;
    if (channel >= 0) {
      if (method.startsWith("get")) {
        res["success"] = true; res["value"] = lights[channel];
      } else if (boolParam(p, v)) {
        lights[channel] = v;
        digitalWrite(GPIO_LIGHTS[channel], v ? HIGH : LOW);
        res["success"] = true; res["value"] = v; changed = true;
        Serial.printf("[RPC] light%d=%s\n", channel + 1, v ? "ON" : "OFF");
      } else res["error"] = "PARAMS_MUST_BE_BOOLEAN";
      res["gpio"] = GPIO_LIGHTS[channel];
      res["pin_state"] = digitalRead(GPIO_LIGHTS[channel]) == HIGH;
    } else if (method == "setFan" && boolParam(p, v)) {
      fanAuto = false; setFanOutput(v);
      res["success"] = true; res["value"] = fanState; changed = true;
    } else if (method == "setFanMode") {
      String mode = p.is<const char*>() ? String(p.as<const char*>()) : String(p["mode"] | "");
      mode.toUpperCase();
      if (mode == "AUTO" || mode == "MANUAL") {
        fanAuto = mode == "AUTO";
        updateAutoFan(millis());
        res["success"] = true; res["fan_mode"] = mode; changed = true;
      } else res["error"] = "MODE_MUST_BE_AUTO_OR_MANUAL";
    } else if (method == "resetPeopleCounter") {
      xSemaphoreTake(counterMutex, portMAX_DELAY);
      if (!p["confirmEmpty"].is<bool>() || !p["confirmEmpty"].as<bool>()) res["error"] = "CONFIRM_EMPTY_ROOM_REQUIRED";
      else if (digitalRead(GPIO_IR_A) == LOW || digitalRead(GPIO_IR_B) == LOW || !people.resetEmpty()) res["error"] = "GATES_MUST_BE_CLEAR";
      else {
        vacancyHold = false;
        res["success"] = true; changed = true;
        Serial.println("[COUNT] EMPTY ROOM CONFIRMED; counters reset");
      }
      xSemaphoreGive(counterMutex);
      if (changed) { saveCounts(); updateAutoFan(millis()); }
      addCounterState(res);
    } else if (method == "getStatus" || method == "getFan" || method == "getPeopleCounter") {
      res["success"] = true; res["value"] = fanState;
      res["fan_state"] = fanState; res["fan_mode"] = fanAuto ? "AUTO" : "MANUAL";
      for (int i = 0; i < 4; i++) res["light" + String(i + 1) + "_state"] = lights[i];
      addCounterState(res);
    } else res["error"] = "UNSUPPORTED_METHOD_OR_PARAMS";
  }
  publish(responseTopic.c_str(), res);
  if (changed) { sendTelemetry(); lastSample = millis(); }
}
void setup() {
  Serial.begin(115200);
  counterMutex = xSemaphoreCreateMutex();
  storageMutex = xSemaphoreCreateMutex();
  if (!counterMutex || !storageMutex) { Serial.println("[FATAL] Counter mutex allocation failed"); abort(); }
  pinMode(GPIO_IR_A, INPUT_PULLUP);
  pinMode(GPIO_IR_B, INPUT_PULLUP);
  storageReady = countStorage.begin("classroom-count", false);
  if (storageReady && countStorage.getBytesLength("counts-v1") == sizeof(people.counts)) {
    countStorage.getBytes("counts-v1", &people.counts, sizeof(people.counts));
  }
  pinMode(GPIO_FAN, OUTPUT); setFanOutput(false);
  for (int i = 0; i < 4; i++) { pinMode(GPIO_LIGHTS[i], OUTPUT); digitalWrite(GPIO_LIGHTS[i], LOW); }
  dht.setup(GPIO_DHT, DHTesp::DHT22);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);
  mqtt.setServer(TB_MQTT_HOST, TB_MQTT_PORT);
  mqtt.setCallback(onRpc);
  mqtt.setBufferSize(MQTT_BUFFER_SIZE);
  mqtt.setKeepAlive(30); mqtt.setSocketTimeout(5);
  bootId = (uint32_t)ESP.getEfuseMac() ^ micros();
  Serial.printf("[BOOT] Classroom %s | MQTT=%s:%u\n", FIRMWARE_VERSION, TB_MQTT_HOST, TB_MQTT_PORT);
  Serial.println("[WIRING] LED1=RX2(GPIO16), LED2=TX2(GPIO17), LED3=D18, LED4=D19, FAN LED=D23; each LED needs 220 ohm and GND");
  Serial.println("[COUNTER] A=GPIO13 outside, B=GPIO27 inside; hold A, hold B, release A, release B = IN; reverse = OUT");
  if (xTaskCreatePinnedToCore(counterTask, "IRCounter", 4096, nullptr, 2, nullptr, 0) != pdPASS) {
    Serial.println("[FATAL] Counter sampling task failed"); abort();
  }
}
void loop() {
  unsigned long now = millis();
  bool oldFan = fanState;
  xSemaphoreTake(counterMutex, portMAX_DELAY);
  bool countChanged = counterDirty; counterDirty = false;
  xSemaphoreGive(counterMutex);
  updateAutoFan(now);
  if (WiFi.status() != WL_CONNECTED) {
    if (due(now, nextWifi)) {
      Serial.println("[WIFI] connecting");
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6); nextWifi = now + 10000;
    }
  } else if (!mqtt.connected() && due(now, nextMqtt)) {
    String clientId = "Classroom-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.printf("[MQTT] connecting to %s:%u\n", TB_MQTT_HOST, TB_MQTT_PORT);
    if (mqtt.connect(clientId.c_str(), TB_DEVICE_TOKEN, "")) {
      bool subscribed = mqtt.subscribe("v1/devices/me/rpc/request/+", 1);
      Serial.printf("[MQTT] connected | RPC subscribe=%s\n", subscribed ? "OK" : "FAILED");
      if (!subscribed) mqtt.disconnect();
      else { mqttBackoff = 1000; sendTelemetry(); lastSample = millis(); }
    } else { Serial.printf("[MQTT] failed rc=%d\n", mqtt.state()); mqttBackoff = min(mqttBackoff * 2UL, 30000UL); }
    nextMqtt = millis() + mqttBackoff;
  }
  if (mqtt.connected()) {
    mqtt.loop();
    if (countChanged || oldFan != fanState || millis() - lastSample >= SAMPLE_PERIOD_MS) {
      sendTelemetry(); lastSample = millis();
    }
  }
  delay(2);
}

