#pragma once
// Pin map for LilyGO T-Embed CC1101 (ESP32-S3-WROOM-1, 16MB flash / 8MB PSRAM).
// Source: Xinyuan-LilyGO/T-Embed-CC1101 examples/utilities.h

#include <Arduino.h>

namespace pins {
constexpr int kPowerEnable = 15;  // powers CC1101 + WS2812 (+ PN532)
constexpr int kUserKey     = 6;

constexpr int kEncA   = 4;
constexpr int kEncB   = 5;
constexpr int kEncKey = 0;  // also BOOT strap pin, used as deep-sleep wake source

constexpr int kBacklight = 21;
constexpr int kTftCs     = 41;

constexpr int kSpiSck  = 11;
constexpr int kSpiMosi = 9;
constexpr int kSpiMiso = 10;

constexpr int kSdCs = 13;

constexpr int kCcCs   = 12;
constexpr int kCcGdo0 = 3;
constexpr int kCcGdo2 = 38;
constexpr int kCcSw0  = 48;  // RF switch: selects the antenna matching network
constexpr int kCcSw1  = 47;

constexpr int kNrfCs = 44;  // optional nRF24 expansion module
constexpr int kNrfCe = 43;

constexpr int kI2cSda = 8;
constexpr int kI2cScl = 18;

constexpr int kPn532Irq   = 17;
constexpr int kPn532Reset = 45;

constexpr int kIrTx = 2;
constexpr int kIrRx = 1;

constexpr int kLedData = 14;
constexpr int kLedCount = 8;
}  // namespace pins

namespace i2c_addr {
constexpr uint8_t kPn532   = 0x24;
constexpr uint8_t kBq27220 = 0x55;  // fuel gauge
constexpr uint8_t kBq25896 = 0x6B;  // charger
}  // namespace i2c_addr

// Display, SD card and CC1101 share one SPI bus. Every chip select must be high
// before another device is addressed.
inline void boardDeselectSpi()
{
    for (int cs : {pins::kTftCs, pins::kSdCs, pins::kCcCs, pins::kNrfCs}) {
        pinMode(cs, OUTPUT);
        digitalWrite(cs, HIGH);
    }
}
