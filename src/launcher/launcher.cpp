// EmbedOS boot launcher — lives in the 'factory' partition and runs first on
// every power-on. Pick a firmware slot with the dial; press to boot it.
//
//   ota_0  EmbedOS      (flashed together with this launcher)
//   ota_1  Slot B       (your own firmware, flashed by you)
//   ota_2  Slot C       (your own firmware, flashed by you)
//
// Empty slots are shown greyed out. This launcher only selects which image the
// chip boots — it contains no radio/attack code of its own.
#include <Arduino.h>
#include <TFT_eSPI.h>

#include "board.h"
#include "multiboot.h"

namespace {
TFT_eSPI tft;

constexpr uint16_t kBg = 0x0000, kPanel = 0x18E3, kAccent = 0x05FF;
constexpr uint16_t kText = 0xFFFF, kMuted = 0x8410, kGood = 0x07E0;

struct Entry {
    const char* name;
    const char* note;
    multiboot::Slot slot;
};
const Entry kEntries[] = {
    {"EmbedOS", "Sub-GHz, IR, NFC, tools", multiboot::Slot::OtaA},
    {"Slot B", "Your firmware (ota_1)", multiboot::Slot::OtaB},
    {"Slot C", "Your firmware (ota_2)", multiboot::Slot::OtaC},
};
constexpr int kCount = sizeof(kEntries) / sizeof(kEntries[0]);

int gSel = 0;
bool gHasApp[kCount];

// --- minimal encoder + button polling ---
int readEncoderDelta()
{
    static int8_t table[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
    static uint8_t state = 0;
    static int8_t accum = 0;
    const uint8_t ab = (digitalRead(pins::kEncA) << 1) | digitalRead(pins::kEncB);
    state = ((state << 2) | ab) & 0x0F;
    accum += table[state];
    if (accum >= 2) {
        accum = 0;
        return 1;
    }
    if (accum <= -2) {
        accum = 0;
        return -1;
    }
    return 0;
}

bool pressed(int pin, uint32_t& since)
{
    if (digitalRead(pin) == LOW) {
        if (since == 0) since = millis();
        return false;
    }
    const bool was = since != 0 && millis() - since > 25;
    since = 0;
    return was;
}

void draw()
{
    tft.fillScreen(kBg);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(kAccent, kBg);
    tft.drawString("EmbedOS boot menu", 160, 16, 4);

    constexpr int16_t y0 = 44, rowH = 34;
    for (int i = 0; i < kCount; ++i) {
        const int16_t y = y0 + i * rowH;
        const bool sel = i == gSel;
        const uint16_t fg = gHasApp[i] ? (sel ? kBg : kText) : kMuted;
        if (sel) tft.fillRoundRect(16, y, 288, rowH - 4, 5, gHasApp[i] ? kAccent : kPanel);
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(fg, sel ? (gHasApp[i] ? kAccent : kPanel) : kBg);
        tft.drawString(kEntries[i].name, 28, y + 9, 4);
        tft.setTextColor(sel ? fg : kMuted, sel ? (gHasApp[i] ? kAccent : kPanel) : kBg);
        tft.drawString(gHasApp[i] ? kEntries[i].note : "empty", 150, y + 11, 2);
    }
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(kMuted, kBg);
    tft.drawString("Turn: choose    Press: boot", 160, 160, 2);
}
}  // namespace

void setup()
{
    Serial.begin(115200);

    pinMode(pins::kEncA, INPUT_PULLUP);
    pinMode(pins::kEncB, INPUT_PULLUP);
    pinMode(pins::kEncKey, INPUT_PULLUP);
    pinMode(pins::kUserKey, INPUT_PULLUP);

    // Power the display rail and turn the backlight on.
    pinMode(pins::kPowerEnable, OUTPUT);
    digitalWrite(pins::kPowerEnable, HIGH);
    pinMode(pins::kBacklight, OUTPUT);
    digitalWrite(pins::kBacklight, HIGH);

    boardDeselectSpi();
    tft.begin();
    tft.setRotation(3);

    for (int i = 0; i < kCount; ++i) gHasApp[i] = multiboot::slotHasApp(kEntries[i].slot);
    // Start on the first slot that actually has an app.
    for (int i = 0; i < kCount; ++i)
        if (gHasApp[i]) {
            gSel = i;
            break;
        }
    draw();
}

void loop()
{
    static uint32_t encSince = 0;
    bool dirty = false;

    const int d = readEncoderDelta();
    if (d) {
        gSel = (gSel + d + kCount) % kCount;
        dirty = true;
    }

    if (pressed(pins::kEncKey, encSince)) {
        if (gHasApp[gSel]) {
            tft.fillScreen(kBg);
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(kGood, kBg);
            tft.drawString("Booting", 160, 70, 4);
            tft.drawString(kEntries[gSel].name, 160, 100, 4);
            delay(300);
            multiboot::bootSlot(kEntries[gSel].slot);  // reboots
        } else {
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(0xF800, kBg);
            tft.drawString("Slot is empty", 160, 135, 2);
        }
    }

    if (dirty) draw();
    delay(4);
}
