#pragma once
#include <Arduino.h>

namespace power {

struct Battery {
    bool valid = false;
    int soc = 0;            // %
    int voltageMv = 0;
    int currentMa = 0;      // + charging, - discharging
    float tempC = 0;
    int remainingMah = 0;
    int fullMah = 0;
    int timeToEmptyMin = -1;
    int timeToFullMin = -1;
    int health = 0;         // %
    bool charging = false;
    bool usbPresent = false;
    uint8_t chargeStage = 0;  // 0 none, 1 pre, 2 fast, 3 done
};

struct Settings {
    uint8_t brightness = 180;    // 10..255
    uint8_t dimAfterS = 30;      // 0 = never
    uint16_t sleepAfterS = 180;  // 0 = never
    uint8_t ledBrightness = 40;
    bool reverseEncoder = false;
    uint16_t chargeLimitMa = 512;  // battery is 1300 mAh, LilyGO recommends <= 600 mA
};

void begin();
void update();  // call every loop: refresh battery, handle dim / auto-sleep

const Battery& battery();
Settings& settings();
void saveSettings();
void applyChargeLimit();

void setBacklight(uint8_t level);
void setPeripheralPower(bool on);
[[noreturn]] void deepSleep();

}  // namespace power
