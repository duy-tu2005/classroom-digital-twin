#pragma once
#include <Arduino.h>
// Copy to secrets.h only when configuring manually. setup.py generates it.
constexpr char WIFI_SSID[] = "Wokwi-GUEST";
constexpr char WIFI_PASSWORD[] = "";
constexpr char TB_MQTT_HOST[] = "YOUR_SERVER_IP";
constexpr uint16_t TB_MQTT_PORT = 1883;
constexpr char TB_DEVICE_TOKEN[] = "YOUR_CLASSROOM_DEVICE_TOKEN";

