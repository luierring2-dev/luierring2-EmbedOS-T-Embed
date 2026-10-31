// Battery details and settings.
#include <esp_chip_info.h>

#include "apps.h"
#include "multiboot.h"
#include "board.h"
#include "power.h"

// ======================= Battery =======================
namespace battapp {
uint32_t gLastDraw = 0;

void enter() { gLastDraw = 0; }

const char* stageName(uint8_t s)
{
    switch (s) {
        case 1: return "Pre-charge";
        case 2: return "Fast charging";
        case 3: return "Charge done";
        default: return "Not charging";
    }
}

bool loop(Key k)
{
    if (k == Key::Back) return false;
    if (millis() - gLastDraw < 1000) return true;
    gLastDraw = millis();

    const power::Battery& b = power::battery();
    auto& g = ui::gfx();
    ui::clear();
    ui::header("Battery");
    if (!b.valid) {
        g.setTextDatum(MC_DATUM);
        g.setTextColor(ui::kBad);
        g.drawString("Fuel gauge (BQ27220) not found", ui::kW / 2, ui::kH / 2, 2);
        ui::footer("USER: back");
        ui::present();
        return true;
    }
    g.setTextDatum(TL_DATUM);
    g.setTextColor(b.soc > 20 ? ui::kGood : ui::kBad);
    g.drawString(String(b.soc) + "%", 12, ui::kHeaderH + 10, 7);

    char line[48];
    int y = ui::kHeaderH + 8;
    const auto row = [&](const char* text, uint16_t colour = ui::kText) {
        g.setTextColor(colour);
        g.drawString(text, 150, y, 2);
        y += 17;
    };
    snprintf(line, sizeof(line), "%.3f V   %+d mA", b.voltageMv / 1000.0f, b.currentMa);
    row(line);
    snprintf(line, sizeof(line), "%d / %d mAh", b.remainingMah, b.fullMah);
    row(line);
    snprintf(line, sizeof(line), "Temp %.1f C   Health %d%%", b.tempC, b.health);
    row(line);
    row(b.usbPresent ? "USB power connected" : "On battery", b.usbPresent ? ui::kGood : ui::kMuted);
    row(stageName(b.chargeStage), b.charging ? ui::kAccent : ui::kMuted);
    if (b.charging && b.timeToFullMin >= 0) snprintf(line, sizeof(line), "Full in %d min", b.timeToFullMin);
    else if (!b.usbPresent && b.timeToEmptyMin >= 0)
        snprintf(line, sizeof(line), "Empty in %dh %02dm", b.timeToEmptyMin / 60, b.timeToEmptyMin % 60);
    else line[0] = 0;
    row(line, ui::kMuted);

    snprintf(line, sizeof(line), "Charge limit %u mA (Settings)", power::settings().chargeLimitMa);
    ui::footer(line);
    ui::present();
    return true;
}

void exit() {}
}  // namespace battapp

const App apps::kBattery = {"Battery", battapp::enter, battapp::loop, battapp::exit};

// ======================= Settings =======================
namespace setapp {
enum Row { Brightness, Dim, Sleep, LedBright, Reverse, Charge, BootMenu, SleepNow, Info, RowCount };
ui::ListView gList;
bool gEditing = false;
bool gDirty = true;
bool gShowInfo = false;

constexpr uint16_t kSleepSteps[] = {0, 30, 60, 120, 180, 300, 600, 1800};
constexpr uint8_t kDimSteps[] = {0, 10, 20, 30, 60, 120};
constexpr uint16_t kChargeSteps[] = {256, 384, 512, 640};  // 1300 mAh cell: stay <= 0.5C

template <typename T, size_t N>
T stepIn(const T (&arr)[N], T cur, int d)
{
    size_t i = 0;
    while (i < N && arr[i] != cur) ++i;
    if (i == N) i = 0;
    return arr[(i + d + N) % N];
}

String fmtSeconds(uint16_t s)
{
    if (s == 0) return "never";
    if (s < 60) return String(s) + " s";
    return String(s / 60) + " min";
}

void enter()
{
    gEditing = false;
    gShowInfo = false;
    gDirty = true;
}

void drawInfo()
{
    auto& g = ui::gfx();
    ui::clear();
    ui::header("System info");
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    char line[64];
    int y = ui::kHeaderH + 8;
    g.setTextDatum(TL_DATUM);
    g.setTextColor(ui::kText);
    const auto row = [&](const char* t) {
        g.drawString(t, 10, y, 2);
        y += 18;
    };
    snprintf(line, sizeof(line), "ESP32-S3 rev %d, %d cores @ %lu MHz", chip.revision, chip.cores,
             (unsigned long)getCpuFrequencyMhz());
    row(line);
    snprintf(line, sizeof(line), "Flash %lu MB   PSRAM %lu KB free", (unsigned long)(ESP.getFlashChipSize() >> 20),
             (unsigned long)(ESP.getFreePsram() >> 10));
    row(line);
    snprintf(line, sizeof(line), "Heap %lu KB free (min %lu KB)", (unsigned long)(ESP.getFreeHeap() >> 10),
             (unsigned long)(ESP.getMinFreeHeap() >> 10));
    row(line);
    const uint32_t up = millis() / 1000;
    snprintf(line, sizeof(line), "Uptime %luh %02lum %02lus", (unsigned long)(up / 3600),
             (unsigned long)(up / 60 % 60), (unsigned long)(up % 60));
    row(line);
    snprintf(line, sizeof(line), "EmbedOS built %s", __DATE__);
    row(line);
    ui::footer("USER: back");
    ui::present();
}

bool loop(Key k)
{
    auto& s = power::settings();
    if (gShowInfo) {
        if (k == Key::Back) gShowInfo = false, gDirty = true;
        else {
            static uint32_t last = 0;
            if (millis() - last > 1000) last = millis(), drawInfo();
            return true;
        }
    }
    if (k == Key::Back) {
        if (gEditing) {
            gEditing = false;
            gDirty = true;
            return true;
        }
        power::saveSettings();
        power::applyChargeLimit();
        return false;
    }

    const int d = k == Key::Up ? 1 : (k == Key::Down ? -1 : 0);
    if (!gEditing) {
        if (gList.handle(k, RowCount)) gDirty = true;
        if (k == Key::Select) {
            switch (gList.selected) {
                case Reverse: s.reverseEncoder = !s.reverseEncoder; break;
                case BootMenu:
                    if (multiboot::available()) {
                        power::saveSettings();
                        multiboot::bootSlot(multiboot::Slot::Launcher);  // reboots
                    } else {
                        ui::toast("No boot menu installed", ui::kBad);
                    }
                    break;
                case SleepNow: power::saveSettings(); power::deepSleep();
                case Info: gShowInfo = true; return true;
                default: gEditing = true; break;
            }
            gDirty = true;
        }
    } else {
        if (k == Key::Select) gEditing = false, gDirty = true;
        if (d) {
            gDirty = true;
            switch (gList.selected) {
                case Brightness:
                    s.brightness = constrain(s.brightness + d * 15, 10, 255);
                    power::setBacklight(s.brightness);
                    break;
                case Dim: s.dimAfterS = stepIn(kDimSteps, s.dimAfterS, d); break;
                case Sleep: s.sleepAfterS = stepIn(kSleepSteps, s.sleepAfterS, d); break;
                case LedBright: s.ledBrightness = constrain(s.ledBrightness + d * 10, 5, 255); break;
                case Charge: s.chargeLimitMa = stepIn(kChargeSteps, s.chargeLimitMa, d); break;
                default: break;
            }
        }
    }
    if (!gDirty) return true;
    gDirty = false;

    static String rows[RowCount];
    rows[Brightness] = "Screen brightness   " + String(s.brightness * 100 / 255) + "%";
    rows[Dim] = "Dim screen after    " + fmtSeconds(s.dimAfterS);
    rows[Sleep] = "Auto sleep after    " + fmtSeconds(s.sleepAfterS);
    rows[LedBright] = "LED brightness      " + String(s.ledBrightness);
    rows[Reverse] = String("Reverse encoder     ") + (s.reverseEncoder ? "on" : "off");
    rows[Charge] = "Charge current      " + String(s.chargeLimitMa) + " mA";
    rows[BootMenu] = multiboot::available() ? "Return to boot menu" : "Boot menu (not installed)";
    rows[SleepNow] = "Sleep now (press dial to wake)";
    rows[Info] = "System info";
    const char* items[RowCount];
    for (int i = 0; i < RowCount; ++i) items[i] = rows[i].c_str();

    ui::clear();
    ui::header(gEditing ? "Settings  (editing)" : "Settings");
    gList.draw(items, RowCount);
    ui::footer(gEditing ? "Turn: change   Press: done" : "Turn: select   Press: edit   USER: save & back");
    ui::present();
    return true;
}

void exit() {}
}  // namespace setapp

const App apps::kSettings = {"Settings", setapp::enter, setapp::loop, setapp::exit};
