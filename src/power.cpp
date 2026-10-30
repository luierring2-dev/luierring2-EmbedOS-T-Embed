#include "power.h"

#include <Preferences.h>
#include <Wire.h>
#include <driver/rtc_io.h>
#include <esp_sleep.h>

#include "board.h"
#include "ui.h"

namespace {
constexpr int kBacklightChannel = 0;

power::Battery gBattery;
power::Settings gSettings;
Preferences gPrefs;
uint32_t gLastRead = 0;
bool gDimmed = false;

bool readReg8(uint8_t addr, uint8_t reg, uint8_t& out)
{
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(addr, (uint8_t)1) != 1) return false;
    out = Wire.read();
    return true;
}

bool writeReg8(uint8_t addr, uint8_t reg, uint8_t val)
{
    Wire.beginTransmission(addr);
    Wire.write(reg);
    Wire.write(val);
    return Wire.endTransmission() == 0;
}

bool readReg16(uint8_t addr, uint8_t reg, uint16_t& out)
{
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(addr, (uint8_t)2) != 2) return false;
    out = Wire.read();
    out |= Wire.read() << 8;
    return true;
}

// ---- BQ25896 charger ----
namespace bq25896 {
constexpr uint8_t kReg02 = 0x02;  // ADC control
constexpr uint8_t kReg04 = 0x04;  // ICHG (bits 6:0, 64 mA/LSB)
constexpr uint8_t kReg07 = 0x07;  // watchdog (bits 5:4)
constexpr uint8_t kReg0B = 0x0B;  // status

void configure(uint16_t chargeMa)
{
    uint8_t v;
    // Disable the I2C watchdog so our settings are not reset to defaults after 40 s.
    if (readReg8(i2c_addr::kBq25896, kReg07, v)) writeReg8(i2c_addr::kBq25896, kReg07, v & ~0x30);
    // Charge current limit.
    const uint8_t ichg = constrain(chargeMa / 64, 1, 0x7F);
    if (readReg8(i2c_addr::kBq25896, kReg04, v))
        writeReg8(i2c_addr::kBq25896, kReg04, (v & 0x80) | ichg);
    // Continuous ADC conversion (CONV_START | CONV_RATE).
    if (readReg8(i2c_addr::kBq25896, kReg02, v)) writeReg8(i2c_addr::kBq25896, kReg02, v | 0xC0);
}

void readStatus(power::Battery& b)
{
    uint8_t st;
    if (!readReg8(i2c_addr::kBq25896, kReg0B, st)) return;
    b.chargeStage = (st >> 3) & 0x03;
    b.usbPresent = ((st >> 5) & 0x07) != 0 || (st & 0x04);  // VBUS_STAT or PG_STAT
    b.charging = b.chargeStage == 1 || b.chargeStage == 2;
}
}  // namespace bq25896

// ---- BQ27220 fuel gauge (standard command set) ----
void readGauge(power::Battery& b)
{
    uint16_t v;
    const uint8_t a = i2c_addr::kBq27220;
    if (!readReg16(a, 0x2C, v)) {
        b.valid = false;
        return;
    }
    b.valid = true;
    b.soc = constrain((int)v, 0, 100);
    if (readReg16(a, 0x08, v)) b.voltageMv = v;
    if (readReg16(a, 0x0C, v)) b.currentMa = (int16_t)v;
    if (readReg16(a, 0x06, v)) b.tempC = v / 10.0f - 273.15f;
    if (readReg16(a, 0x10, v)) b.remainingMah = v;
    if (readReg16(a, 0x12, v)) b.fullMah = v;
    if (readReg16(a, 0x16, v)) b.timeToEmptyMin = v == 0xFFFF ? -1 : v;
    if (readReg16(a, 0x18, v)) b.timeToFullMin = v == 0xFFFF ? -1 : v;
    if (readReg16(a, 0x2E, v)) b.health = v;
}

void loadSettings()
{
    gPrefs.begin("embedos", true);
    gSettings.brightness = gPrefs.getUChar("bright", gSettings.brightness);
    gSettings.dimAfterS = gPrefs.getUChar("dim", gSettings.dimAfterS);
    gSettings.sleepAfterS = gPrefs.getUShort("sleep", gSettings.sleepAfterS);
    gSettings.ledBrightness = gPrefs.getUChar("led", gSettings.ledBrightness);
    gSettings.reverseEncoder = gPrefs.getBool("encrev", gSettings.reverseEncoder);
    gSettings.chargeLimitMa = gPrefs.getUShort("chg", gSettings.chargeLimitMa);
    gPrefs.end();
}
}  // namespace

namespace power {

void begin()
{
    loadSettings();

    ledcSetup(kBacklightChannel, 5000, 8);
    ledcAttachPin(pins::kBacklight, kBacklightChannel);
    setBacklight(gSettings.brightness);

    // Release any pin hold left over from deep sleep.
    gpio_hold_dis((gpio_num_t)pins::kPowerEnable);
    gpio_deep_sleep_hold_dis();
    setPeripheralPower(true);

    Wire.begin(pins::kI2cSda, pins::kI2cScl, 100000);
    Wire.setTimeOut(20);
    applyChargeLimit();
    readGauge(gBattery);
    bq25896::readStatus(gBattery);
}

void update()
{
    const uint32_t now = millis();
    if (now - gLastRead > 2000) {
        gLastRead = now;
        readGauge(gBattery);
        bq25896::readStatus(gBattery);
    }

    const uint32_t idle = (now - input::lastActivityMs()) / 1000;
    // Never auto-sleep while plugged in; dim still applies.
    if (gSettings.sleepAfterS && idle >= gSettings.sleepAfterS && !gBattery.usbPresent) deepSleep();

    const bool shouldDim = gSettings.dimAfterS && idle >= gSettings.dimAfterS;
    if (shouldDim != gDimmed) {
        gDimmed = shouldDim;
        setBacklight(shouldDim ? min<uint8_t>(15, gSettings.brightness) : gSettings.brightness);
    }
}

const Battery& battery() { return gBattery; }
Settings& settings() { return gSettings; }

void saveSettings()
{
    gPrefs.begin("embedos", false);
    gPrefs.putUChar("bright", gSettings.brightness);
    gPrefs.putUChar("dim", gSettings.dimAfterS);
    gPrefs.putUShort("sleep", gSettings.sleepAfterS);
    gPrefs.putUChar("led", gSettings.ledBrightness);
    gPrefs.putBool("encrev", gSettings.reverseEncoder);
    gPrefs.putUShort("chg", gSettings.chargeLimitMa);
    gPrefs.end();
}

void applyChargeLimit() { bq25896::configure(gSettings.chargeLimitMa); }

void setBacklight(uint8_t level) { ledcWrite(kBacklightChannel, level); }

void setPeripheralPower(bool on)
{
    pinMode(pins::kPowerEnable, OUTPUT);
    digitalWrite(pins::kPowerEnable, on ? HIGH : LOW);
}

void deepSleep()
{
    Serial.println("[power] entering deep sleep");
    auto& tft = ui::tft();
    tft.fillScreen(TFT_BLACK);
    setBacklight(0);
    tft.writecommand(0x28);  // DISPOFF
    tft.writecommand(0x10);  // SLPIN
    boardDeselectSpi();

    // Cut power to CC1101 / LEDs / NFC and keep it off while asleep.
    setPeripheralPower(false);
    gpio_hold_en((gpio_num_t)pins::kPowerEnable);
    gpio_deep_sleep_hold_en();

    // Wait for the button to be released, otherwise we wake immediately.
    while (digitalRead(pins::kEncKey) == LOW || digitalRead(pins::kUserKey) == LOW) delay(10);
    delay(50);

    rtc_gpio_pullup_en((gpio_num_t)pins::kEncKey);
    esp_sleep_enable_ext0_wakeup((gpio_num_t)pins::kEncKey, 0);  // press encoder to wake
    esp_deep_sleep_start();
}

}  // namespace power
