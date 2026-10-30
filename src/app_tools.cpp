// Smaller tools: Wi-Fi scanner, LED control, SD card browser.
#include <WiFi.h>

#include "apps.h"
#include "board.h"
#include "leds.h"
#include "power.h"
#include "storage.h"

// ======================= Wi-Fi scanner =======================
namespace wifiscan {
ui::ListView gList;
String gLabels[40];
const char* gItems[40];
int gCount = 0;
bool gScanning = false;
uint32_t gLastScan = 0;
bool gDirty = true;

void enter()
{
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    WiFi.scanNetworks(true, true);  // async, include hidden
    gScanning = true;
    gDirty = true;
}

bool loop(Key k)
{
    if (k == Key::Back) return false;
    if (gList.handle(k, gCount)) gDirty = true;

    if (gScanning) {
        const int n = WiFi.scanComplete();
        if (n >= 0) {
            gCount = min(n, 40);
            for (int i = 0; i < gCount; ++i) {
                const String ssid = WiFi.SSID(i).length() ? WiFi.SSID(i) : String("<hidden>");
                const bool open = WiFi.encryptionType(i) == WIFI_AUTH_OPEN;
                char row[64];
                snprintf(row, sizeof(row), "%4d  ch%-2d %s %s", WiFi.RSSI(i), WiFi.channel(i),
                         open ? "open" : "    ", ssid.substring(0, 22).c_str());
                gLabels[i] = row;
                gItems[i] = gLabels[i].c_str();
            }
            WiFi.scanDelete();
            gScanning = false;
            gLastScan = millis();
            gDirty = true;
        } else if (n == WIFI_SCAN_FAILED) {
            gScanning = false;
        }
    } else if (k == Key::Select || millis() - gLastScan > 10000) {
        WiFi.scanNetworks(true, true);
        gScanning = true;
        gDirty = true;
    }

    if (!gDirty) return true;
    gDirty = false;
    ui::clear();
    ui::header(gScanning ? "Wi-Fi scan  (scanning...)" : "Wi-Fi scan");
    if (gCount == 0) {
        ui::gfx().setTextDatum(MC_DATUM);
        ui::gfx().setTextColor(ui::kMuted);
        ui::gfx().drawString(gScanning ? "Scanning..." : "No networks", ui::kW / 2, ui::kH / 2, 2);
    } else {
        gList.draw(gItems, gCount);
    }
    ui::footer("dBm, channel, SSID.  Press: rescan   USER: back");
    ui::present();
    return true;
}

void exit()
{
    WiFi.scanDelete();
    WiFi.mode(WIFI_OFF);
}
}  // namespace wifiscan

const App apps::kWifiScan = {"Wi-Fi scanner", wifiscan::enter, wifiscan::loop, wifiscan::exit};

// ======================= LEDs =======================
namespace ledapp {
int gRow = 0;  // 0 mode, 1 hue, 2 brightness
bool gEditing = false;
bool gDirty = true;

void enter() { gDirty = true; }

bool loop(Key k)
{
    auto& s = power::settings();
    if (k == Key::Back) {
        if (gEditing) {
            gEditing = false;
            gDirty = true;
            return true;
        }
        power::saveSettings();
        return false;
    }
    if (k == Key::Select) gEditing = !gEditing, gDirty = true;
    const int d = k == Key::Up ? 1 : (k == Key::Down ? -1 : 0);
    if (d) {
        gDirty = true;
        if (!gEditing) {
            gRow = (gRow + d + 3) % 3;
        } else if (gRow == 0) {
            const int n = static_cast<int>(leds::Mode::Count);
            leds::setMode(static_cast<leds::Mode>((static_cast<int>(leds::mode()) + d + n) % n));
        } else if (gRow == 1) {
            leds::setHue(leds::hue() + d * 8);
        } else {
            s.ledBrightness = constrain(s.ledBrightness + d * 10, 5, 255);
        }
    }
    if (!gDirty) return true;
    gDirty = false;

    char rows[3][40];
    snprintf(rows[0], 40, "Mode:        %s", leds::modeName(leds::mode()));
    snprintf(rows[1], 40, "Colour hue:  %u", leds::hue());
    snprintf(rows[2], 40, "Brightness:  %u", s.ledBrightness);
    const char* items[3] = {rows[0], rows[1], rows[2]};
    ui::ListView lv;
    lv.selected = gRow;
    ui::clear();
    ui::header("LEDs");
    lv.draw(items, 3);
    ui::footer(gEditing ? "Turn: change value   Press: done" : "Turn: select   Press: edit   USER: back");
    ui::present();
    return true;
}

void exit() {}
}  // namespace ledapp

const App apps::kLeds = {"LEDs", ledapp::enter, ledapp::loop, ledapp::exit};

// ======================= SD card =======================
namespace sdapp {
ui::ListView gList;
String gDir = "/";
String gNames[64];
const char* gItems[64];
int gCount = 0;
bool gOk = false;
bool gDirty = true;

void load()
{
    gCount = 0;
    gOk = storage::mount();
    if (!gOk) return;
    File dir = SD.open(gDir);
    if (gDir != "/") {
        gNames[gCount] = "..";
        gItems[gCount] = gNames[gCount].c_str();
        gCount++;
    }
    for (File f = dir.openNextFile(); f && gCount < 64; f = dir.openNextFile()) {
        String n = f.name();
        if (f.isDirectory()) n = "[" + n + "]";
        else n += "  (" + String((unsigned long)f.size()) + " B)";
        gNames[gCount] = n;
        gItems[gCount] = gNames[gCount].c_str();
        gCount++;
        f.close();
    }
    dir.close();
    boardDeselectSpi();
    gList = ui::ListView{};
}

void enter()
{
    gDir = "/";
    load();
    gDirty = true;
}

bool loop(Key k)
{
    if (k == Key::Back) return false;
    if (gList.handle(k, gCount)) gDirty = true;
    if (k == Key::Select) {
        if (!gOk) {
            storage::unmount();
            load();
        } else if (gCount) {
            const String& n = gNames[gList.selected];
            if (n == "..") {
                gDir = gDir.substring(0, gDir.lastIndexOf('/'));
                if (gDir.isEmpty()) gDir = "/";
                load();
            } else if (n.startsWith("[")) {
                gDir = (gDir == "/" ? "" : gDir) + "/" + n.substring(1, n.length() - 1);
                load();
            }
        }
        gDirty = true;
    }
    if (!gDirty) return true;
    gDirty = false;

    ui::clear();
    if (!gOk) {
        ui::header("SD card");
        ui::gfx().setTextDatum(MC_DATUM);
        ui::gfx().setTextColor(ui::kBad);
        ui::gfx().drawString("No card (FAT32) found", ui::kW / 2, ui::kH / 2, 2);
        ui::footer("Press: retry   USER: back");
    } else {
        char title[64];
        snprintf(title, sizeof(title), "SD %s  %lu/%lu MB", gDir.c_str(),
                 (unsigned long)(SD.usedBytes() >> 20), (unsigned long)(SD.totalBytes() >> 20));
        ui::header(title);
        gList.draw(gItems, gCount);
        ui::footer("Press: open folder   USER: back");
    }
    ui::present();
    boardDeselectSpi();
    return true;
}

void exit() {}
}  // namespace sdapp

const App apps::kSdCard = {"SD card", sdapp::enter, sdapp::loop, sdapp::exit};
