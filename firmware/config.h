#pragma once
#include <Arduino.h>
constexpr uint8_t GPIO_DHT = 15;
constexpr uint8_t GPIO_IR_A = 13;  // Outside beam, active LOW / open collector.
constexpr uint8_t GPIO_IR_B = 27;  // Inside beam, active LOW / open collector.
constexpr uint32_t IR_DEBOUNCE_MS = 30;
constexpr uint32_t IR_CROSSING_TIMEOUT_MS = 8000;
constexpr uint8_t GPIO_LIGHTS[4] = {16, 17, 18, 19};
constexpr uint8_t GPIO_FAN = 23;
constexpr unsigned long SAMPLE_PERIOD_MS = 5000;
constexpr unsigned long FAN_HOLD_MS = 15000;
constexpr uint16_t MQTT_BUFFER_SIZE = 2048;
constexpr char FIRMWARE_VERSION[] = "2.0.1";

