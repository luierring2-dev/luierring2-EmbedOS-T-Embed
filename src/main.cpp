// EmbedOS – custom firmware for the LilyGO T-Embed CC1101 (Plus).
//
// Controls (everywhere):
//   turn dial        move / change value
//   press dial       select
//   hold dial        secondary action (shown in the footer)
//   USER key         back
//   hold USER 1.5 s  deep sleep (press dial to wake)
#include <Arduino.h>
#include <esp_sleep.h>
#include <esp_task_wdt.h>

#include "apps.h"
#include "board.h"
#include "leds.h"
#include "power.h"
#include "ui.h"

namespace {
const App* const kApps[] = {
    &apps::kSubGhz,      &apps::kInfrared, &apps::kUniversalIr, &apps::kNfc,
    &apps::kWifiScan,    &apps::kLeds,     &apps::kBattery,     &apps::kSdCard,
    &apps::kSettings,
};
constexpr int kAppCount = sizeof(kApps) / sizeof(kApps[0]);
const char* const kSubtitles[] = {
    "Spectrum, frequency finder, RAW recorder",
    "Learn, replay and save remote codes",
    "Built-in TV power/volume codes + blast",
    "Read 13.56 MHz card UIDs",
    "Nearby networks, channel and signal",
    "Rainbow, breathe, torch",
    "Charge, health and time remaining",
    "Browse the TF card",
    "Brightness, sleep, charging, info",
};
const uint16_t kColours[] = {ui::kAccent2, 0xF81F, 0xFD20,    0x041F, ui::kGood,
                             0xFFE0,       ui::kGood, 0xBDF7, ui::kMuted};

const App* gActive = nullptr;
int gSelected = 0;
bool gMenuDirty = true;
uint32_t gLastMenuDraw = 0;

void drawMenu()
{
    auto& g = ui::gfx();
    ui::clear();
    ui::header("EmbedOS");

    // Carousel: previous / current / next
    const int16_t cy = 78;
    for (int off = -1; off <= 1; ++off) {
        const int idx = (gSelected + off + kAppCount) % kAppCount;
        const int16_t cx = ui::kW / 2 + off * 110;
        const bool sel = off == 0;
        const int16_t r = sel ? 30 : 20;
        g.fillCircle(cx, cy, r, sel ? kColours[idx] : ui::kPanel);
        g.setTextDatum(MC_DATUM);
        g.setTextColor(sel ? ui::kBg : ui::kMuted);
        char initial[3] = {kApps[idx]->name[0], kApps[idx]->name[1], 0};
        g.drawString(initial, cx, cy + 1, sel ? 4 : 2);
    }
    g.setTextDatum(MC_DATUM);
    g.setTextColor(ui::kText);
    g.drawString(kApps[gSelected]->name, ui::kW / 2, 124, 4);
    g.setTextColor(ui::kMuted);
    g.drawString(kSubtitles[gSelected], ui::kW / 2, 143, 2);

    // Page dots
    for (int i = 0; i < kAppCount; ++i)
        g.fillCircle(ui::kW / 2 - (kAppCount - 1) * 5 + i * 10, ui::kHeaderH + 10, 2,
                     i == gSelected ? ui::kAccent : ui::kPanel);
    ui::footer("Turn: browse   Press: open   Hold USER: sleep");
    ui::present();
}

void splash()
{
    auto& g = ui::gfx();
    ui::clear();
    g.setTextDatum(MC_DATUM);
    g.setTextColor(ui::kAccent);
    g.drawString("EmbedOS", ui::kW / 2, ui::kH / 2 - 14, 4);
    g.setTextColor(ui::kMuted);
    g.drawString("T-Embed CC1101", ui::kW / 2, ui::kH / 2 + 14, 2);
    ui::present();
    for (int i = 0; i < pins::kLedCount; ++i) {
        leds::level(i + 1, 0x00A0FF);
        delay(40);
    }
    leds::clearOverlay();
}
}  // namespace

void setup()
{
    Serial.begin(115200);
    boardDeselectSpi();
    pinMode(pins::kNrfCe, OUTPUT);
    digitalWrite(pins::kNrfCe, LOW);

    input::begin();
    ui::begin();
    power::begin();
    leds::begin();
    splash();

    // Task watchdog: reboot if the UI loop ever hangs for 10 s.
    esp_task_wdt_init(10, true);
    esp_task_wdt_add(nullptr);
    Serial.printf("[embedos] ready, wake cause %d\n", (int)esp_sleep_get_wakeup_cause());
}

void loop()
{
    esp_task_wdt_reset();
    const Key k = input::poll();
    power::update();
    leds::tick();

    if (k == Key::LongBack) {
        if (gActive) gActive->exit();
        power::saveSettings();
        power::deepSleep();
    }

    if (gActive) {
        if (!gActive->loop(k)) {
            gActive->exit();
            gActive = nullptr;
            gMenuDirty = true;
        }
        return;
    }

    if (k == Key::Up) gSelected = (gSelected + 1) % kAppCount, gMenuDirty = true;
    if (k == Key::Down) gSelected = (gSelected - 1 + kAppCount) % kAppCount, gMenuDirty = true;
    if (k == Key::Select) {
        gActive = kApps[gSelected];
        gActive->enter();
        return;
    }
    // Redraw on change, and every few seconds so the battery icon stays fresh.
    if (gMenuDirty || millis() - gLastMenuDraw > 3000) {
        gMenuDirty = false;
        gLastMenuDraw = millis();
        drawMenu();
    }
    delay(2);
}
