// Sub-GHz tools built on the CC1101. Receive-only:
//   * Spectrum analyser  – RSSI sweep across a band with peak hold
//   * Frequency finder   – watches common remote/sensor frequencies, logs hits
//   * RAW recorder       – captures OOK pulse trains, saves Flipper-compatible .sub files
#include <RadioLib.h>

#include "apps.h"
#include "board.h"
#include "leds.h"
#include "power.h"
#include "storage.h"

namespace {

// ---------------- Radio ----------------
CC1101* gRadio = nullptr;
bool gRadioOk = false;
float gFreq = 433.92f;

void setRfPath(float mhz)
{
    // SW1:1 SW0:0 -> 315 MHz path, SW1:1 SW0:1 -> 433 MHz path, SW1:0 SW0:1 -> 868/915 MHz path
    pinMode(pins::kCcSw0, OUTPUT);
    pinMode(pins::kCcSw1, OUTPUT);
    const bool sw1 = mhz < 600.0f;
    const bool sw0 = mhz >= 380.0f;
    digitalWrite(pins::kCcSw1, sw1);
    digitalWrite(pins::kCcSw0, sw0);
}

bool radioBegin()
{
    if (gRadio == nullptr) {
        // Shares the display's SPIClass so both drivers agree on bus state.
        static Module mod(pins::kCcCs, pins::kCcGdo0, RADIOLIB_NC, pins::kCcGdo2,
                          ui::tft().getSPIinstance());
        static CC1101 radio(&mod);
        gRadio = &radio;
    }
    boardDeselectSpi();
    setRfPath(gFreq);
    int st = gRadio->begin(gFreq);
    if (st == RADIOLIB_ERR_NONE) st = gRadio->setOOK(true);
    if (st == RADIOLIB_ERR_NONE) st = gRadio->setRxBandwidth(270.0f);
    if (st == RADIOLIB_ERR_NONE) st = gRadio->receiveDirectAsync();
    gRadioOk = st == RADIOLIB_ERR_NONE;
    if (!gRadioOk) Serial.printf("[cc1101] init failed: %d\n", st);
    boardDeselectSpi();
    return gRadioOk;
}

bool tune(float mhz)
{
    if (!gRadioOk) return false;
    setRfPath(mhz);
    if (gRadio->setFrequency(mhz) != RADIOLIB_ERR_NONE) return false;
    gFreq = mhz;
    gRadio->receiveDirectAsync();  // back to RX after setFrequency() idled the chip
    return true;
}

// RSSI is valid ~1 ms after entering RX (auto-calibration + AGC settle).
float rssiAt(float mhz)
{
    if (!tune(mhz)) return -120.0f;
    delayMicroseconds(1100);
    return gRadio->getRSSI();
}

float rssiNow() { return gRadioOk ? gRadio->getRSSI() : -120.0f; }

uint32_t rssiColour(float dbm)
{
    if (dbm > -50) return 0xFF0000;
    if (dbm > -65) return 0xFF8000;
    return 0x00FF40;
}

void ledMeter(float dbm)
{
    const int lit = constrain((int)((dbm + 100.0f) / 6.0f), 0, 8);
    leds::level(lit, rssiColour(dbm));
}

// ---------------- Spectrum analyser ----------------
struct Band {
    const char* name;
    float lo, hi;
};
constexpr Band kBands[] = {
    {"300-348 MHz", 300.0f, 348.0f}, {"387-464 MHz", 387.0f, 464.0f},
    {"433 zoom", 430.0f, 438.0f},    {"779-928 MHz", 779.0f, 928.0f},
    {"868 zoom", 863.0f, 870.0f},    {"915 zoom", 902.0f, 928.0f},
};
constexpr int kBandCount = sizeof(kBands) / sizeof(kBands[0]);
constexpr int kBins = 150;  // 2 px per bin

int gBand = 2;
float gLive[kBins];
float gPeak[kBins];

void spectrumReset()
{
    for (int i = 0; i < kBins; ++i) gLive[i] = gPeak[i] = -110.0f;
}

void spectrumLoop(Key k)
{
    if (k == Key::Up) gBand = (gBand + 1) % kBandCount, spectrumReset();
    if (k == Key::Down) gBand = (gBand - 1 + kBandCount) % kBandCount, spectrumReset();
    if (k == Key::Select) spectrumReset();

    const Band& b = kBands[gBand];
    const float step = (b.hi - b.lo) / (kBins - 1);
    int peakBin = 0;
    for (int i = 0; i < kBins; ++i) {
        const float r = rssiAt(b.lo + i * step);
        gLive[i] = r;
        gPeak[i] = max(gPeak[i], r);
        if (gLive[i] > gLive[peakBin]) peakBin = i;
    }
    ledMeter(gLive[peakBin]);

    auto& g = ui::gfx();
    ui::clear();
    ui::header("Spectrum");
    constexpr int16_t top = ui::kHeaderH + 18, bottom = ui::kH - ui::kFooterH - 12, x0 = 10;
    const auto toY = [&](float dbm) {
        return (int16_t)map(constrain((int)dbm, -110, -20), -110, -20, bottom, top);
    };
    for (int db = -100; db <= -30; db += 20) {
        const int16_t y = toY(db);
        g.drawFastHLine(x0, y, kBins * 2, ui::kPanel);
        g.setTextDatum(ML_DATUM);
        g.setTextColor(ui::kMuted);
        g.drawString(String(db), x0 + kBins * 2 + 4, y, 1);
    }
    for (int i = 0; i < kBins; ++i) {
        const int16_t x = x0 + i * 2;
        const int16_t y = toY(gLive[i]);
        const uint16_t c = gLive[i] > -50 ? ui::kBad : (gLive[i] > -70 ? ui::kAccent2 : ui::kAccent);
        g.drawFastVLine(x, y, bottom - y, c);
        g.drawPixel(x, toY(gPeak[i]), ui::kText);
        g.drawPixel(x + 1, toY(gPeak[i]), ui::kText);
    }
    char line[64];
    snprintf(line, sizeof(line), "%s   peak %.2f MHz  %d dBm", b.name, b.lo + peakBin * step,
             (int)gLive[peakBin]);
    g.setTextDatum(ML_DATUM);
    g.setTextColor(ui::kText);
    g.drawString(line, x0, ui::kHeaderH + 8, 1);
    snprintf(line, sizeof(line), "%.1f", b.lo);
    g.setTextColor(ui::kMuted);
    g.drawString(line, x0, bottom + 7, 1);
    snprintf(line, sizeof(line), "%.1f", b.hi);
    g.setTextDatum(MR_DATUM);
    g.drawString(line, x0 + kBins * 2, bottom + 7, 1);
    ui::footer("Turn: band   Press: clear peaks   USER: back");
    ui::present();
}

// ---------------- Frequency finder ----------------
constexpr float kCommonFreqs[] = {300.00f, 303.87f, 304.25f, 310.00f, 315.00f, 318.00f,
                                  390.00f, 418.00f, 433.07f, 433.42f, 433.92f, 434.42f,
                                  434.77f, 438.90f, 868.35f, 868.95f, 915.00f};
constexpr int kCommonCount = sizeof(kCommonFreqs) / sizeof(kCommonFreqs[0]);

struct Hit {
    float mhz;
    int dbm;
    uint32_t atMs;
};
Hit gHits[6];
int gHitCount = 0;
int gFinderThreshold = -65;
uint32_t gLastHitMs = 0;

void finderLoop(Key k)
{
    if (k == Key::Up) gFinderThreshold = min(gFinderThreshold + 5, -30);
    if (k == Key::Down) gFinderThreshold = max(gFinderThreshold - 5, -100);
    if (k == Key::Select) gHitCount = 0;

    int best = 0;
    float bestRssi = -120.0f;
    for (int i = 0; i < kCommonCount; ++i) {
        float r = -120.0f;
        for (int s = 0; s < 3; ++s) r = max(r, rssiAt(kCommonFreqs[i]));
        if (r > bestRssi) bestRssi = r, best = i;
    }
    ledMeter(bestRssi);

    const uint32_t now = millis();
    if (bestRssi >= gFinderThreshold && now - gLastHitMs > 400) {
        gLastHitMs = now;
        if (gHitCount > 0 && gHits[0].mhz == kCommonFreqs[best] && now - gHits[0].atMs < 1500) {
            gHits[0].dbm = max(gHits[0].dbm, (int)bestRssi);
            gHits[0].atMs = now;
        } else {
            memmove(&gHits[1], &gHits[0], sizeof(Hit) * 5);
            gHits[0] = {kCommonFreqs[best], (int)bestRssi, now};
            gHitCount = min(gHitCount + 1, 6);
        }
    }

    auto& g = ui::gfx();
    ui::clear();
    ui::header("Frequency finder");
    char line[48];
    g.setTextDatum(TL_DATUM);
    g.setTextColor(bestRssi >= gFinderThreshold ? ui::kGood : ui::kMuted);
    snprintf(line, sizeof(line), "%.2f", kCommonFreqs[best]);
    g.drawString(line, 10, ui::kHeaderH + 8, 4);
    g.setTextColor(ui::kText);
    snprintf(line, sizeof(line), "MHz  %d dBm", (int)bestRssi);
    g.drawString(line, 10, ui::kHeaderH + 36, 2);
    snprintf(line, sizeof(line), "Threshold %d dBm", gFinderThreshold);
    g.setTextColor(ui::kMuted);
    g.drawString(line, 10, ui::kHeaderH + 56, 2);

    g.setTextColor(ui::kAccent);
    g.drawString("Recent hits", 170, ui::kHeaderH + 6, 2);
    for (int i = 0; i < gHitCount; ++i) {
        snprintf(line, sizeof(line), "%7.2f %4d dBm %3lus", gHits[i].mhz, gHits[i].dbm,
                 (unsigned long)((now - gHits[i].atMs) / 1000));
        g.setTextColor(i == 0 ? ui::kText : ui::kMuted);
        g.drawString(line, 170, ui::kHeaderH + 26 + i * 14, 1);
    }
    ui::footer("Turn: threshold   Press: clear   USER: back");
    ui::present();
}

// ---------------- RAW recorder ----------------
constexpr size_t kRingSize = 2048;
constexpr size_t kCaptureMax = 4096;
constexpr uint32_t kMaxPulseUs = 60000;

volatile int32_t gRing[kRingSize];
volatile uint16_t gRingHead = 0, gRingTail = 0;
volatile uint32_t gLastEdgeUs = 0;

int32_t* gCapture = nullptr;  // signed µs: + = carrier on, - = off (Flipper RAW convention)
size_t gCaptureLen = 0;
size_t gLastLen = 0;
float gLastCaptureFreq = 0;
int gLastCaptureRssi = 0;

enum class RecState : uint8_t { Listening, Recording };
RecState gRecState = RecState::Listening;
uint32_t gQuietSince = 0;
int gRecThreshold = -75;
int gFreqPreset = 10;  // 433.92
uint32_t gLastDraw = 0;

void IRAM_ATTR onGdo0Edge()
{
    const uint32_t now = micros();
    uint32_t d = now - gLastEdgeUs;
    gLastEdgeUs = now;
    if (d > kMaxPulseUs) d = kMaxPulseUs;
    // The level that just ended is the inverse of the level now on the pin.
    const bool nowHigh = gpio_get_level((gpio_num_t)pins::kCcGdo0);
    const int32_t v = nowHigh ? -(int32_t)d : (int32_t)d;
    const uint16_t next = (gRingHead + 1) % kRingSize;
    if (next != gRingTail) {
        gRing[gRingHead] = v;
        gRingHead = next;
    }
}

void recorderStart()
{
    if (gCapture == nullptr)
        gCapture = static_cast<int32_t*>(ps_malloc(sizeof(int32_t) * kCaptureMax * 2));
    if (gCapture == nullptr)
        gCapture = static_cast<int32_t*>(malloc(sizeof(int32_t) * kCaptureMax * 2));
    tune(kCommonFreqs[gFreqPreset]);
    gRingHead = gRingTail = 0;
    gLastEdgeUs = micros();
    gRecState = RecState::Listening;
    pinMode(pins::kCcGdo0, INPUT);
    attachInterrupt(digitalPinToInterrupt(pins::kCcGdo0), onGdo0Edge, CHANGE);
}

void recorderStop() { detachInterrupt(digitalPinToInterrupt(pins::kCcGdo0)); }

// The second half of gCapture holds the last finished capture.
int32_t* lastCapture() { return gCapture + kCaptureMax; }

bool saveCapture()
{
    if (gLastLen == 0) return false;
    if (!storage::mount()) return false;
    const String path = storage::nextFile("/subghz", "raw", "sub");
    File f = SD.open(path, FILE_WRITE);
    if (!f) return false;
    f.println("Filetype: Flipper SubGhz RAW File");
    f.println("Version: 1");
    f.printf("Frequency: %lu\n", (unsigned long)(gLastCaptureFreq * 1e6f + 0.5f));
    f.println("Preset: FuriHalSubGhzPresetOok270Async");
    f.println("Protocol: RAW");
    const int32_t* c = lastCapture();
    for (size_t i = 0; i < gLastLen; ++i) {
        if (i % 512 == 0) f.print(i == 0 ? "RAW_Data:" : "\nRAW_Data:");
        f.printf(" %ld", (long)c[i]);
    }
    f.println();
    f.close();
    boardDeselectSpi();
    Serial.printf("[subghz] saved %s (%u pulses)\n", path.c_str(), (unsigned)gLastLen);
    return true;
}

void drawWaveform(int16_t x, int16_t y, int16_t w, int16_t h)
{
    auto& g = ui::gfx();
    g.drawRect(x, y, w, h, ui::kPanel);
    if (gLastLen == 0) {
        g.setTextDatum(MC_DATUM);
        g.setTextColor(ui::kMuted);
        g.drawString("No capture yet", x + w / 2, y + h / 2, 2);
        return;
    }
    const int32_t* c = lastCapture();
    uint64_t total = 0;
    for (size_t i = 0; i < gLastLen; ++i) total += abs(c[i]);
    const float usPerPx = max(1.0f, (float)total / (w - 4));
    float t = 0;
    int16_t px = x + 2;
    const int16_t hi = y + 4, lo = y + h - 5;
    for (size_t i = 0; i < gLastLen && px < x + w - 2; ++i) {
        t += abs(c[i]);
        const int16_t nx = min<int16_t>(x + w - 2, x + 2 + (int16_t)(t / usPerPx));
        const int16_t ly = c[i] > 0 ? hi : lo;
        g.drawFastHLine(px, ly, max<int16_t>(1, nx - px), ui::kGood);
        if (i + 1 < gLastLen) g.drawFastVLine(nx, hi, lo - hi, 0x03E0);
        px = nx;
    }
}

void recorderLoop(Key k)
{
    // Drain pulses from the ISR ring.
    while (gRingTail != gRingHead) {
        const int32_t v = gRing[gRingTail];
        gRingTail = (gRingTail + 1) % kRingSize;
        if (gRecState == RecState::Recording && gCaptureLen < kCaptureMax) {
            if (gCaptureLen == 0 && v < 0) continue;  // RAW data must start with a high pulse
            gCapture[gCaptureLen++] = v;
        }
    }

    const float rssi = rssiNow();
    const uint32_t now = millis();
    if (gRecState == RecState::Listening) {
        if (rssi >= gRecThreshold) {
            gRecState = RecState::Recording;
            gCaptureLen = 0;
            gQuietSince = 0;
            leds::flash(0xFF0000, 60);
        }
    } else {
        if (rssi < gRecThreshold) {
            if (gQuietSince == 0) gQuietSince = now;
            if (now - gQuietSince > 60 || gCaptureLen >= kCaptureMax) {
                gRecState = RecState::Listening;
                if (gCaptureLen >= 16) {
                    memcpy(lastCapture(), gCapture, gCaptureLen * sizeof(int32_t));
                    gLastLen = gCaptureLen;
                    gLastCaptureFreq = gFreq;
                    gLastCaptureRssi = (int)rssi;
                    leds::flash(0x00FF00, 200);
                }
            }
        } else {
            gQuietSince = 0;
            gLastCaptureRssi = max(gLastCaptureRssi, (int)rssi);
        }
        return;  // don't redraw mid-capture: SPI to the display would delay RSSI polling
    }

    bool force = false;
    if (k == Key::Up) gFreqPreset = (gFreqPreset + 1) % kCommonCount, tune(kCommonFreqs[gFreqPreset]), force = true;
    if (k == Key::Down) gFreqPreset = (gFreqPreset - 1 + kCommonCount) % kCommonCount, tune(kCommonFreqs[gFreqPreset]), force = true;
    if (k == Key::LongSelect) {
        gRecThreshold = gRecThreshold >= -45 ? -90 : gRecThreshold + 15;
        force = true;
    }
    if (k == Key::Select) {
        recorderStop();
        const bool ok = saveCapture();
        ui::toast(ok ? "Saved to SD:/subghz" : (gLastLen ? "SD card error" : "Nothing to save"),
                  ok ? ui::kGood : ui::kBad);
        recorderStart();
    }
    if (!force && now - gLastDraw < 100) return;
    gLastDraw = now;

    auto& g = ui::gfx();
    ui::clear();
    ui::header("RAW recorder");
    char line[64];
    g.setTextDatum(TL_DATUM);
    g.setTextColor(ui::kText);
    snprintf(line, sizeof(line), "%.2f MHz", gFreq);
    g.drawString(line, 10, ui::kHeaderH + 6, 4);
    // RSSI meter with threshold marker
    const int16_t mx = 170, my = ui::kHeaderH + 10, mw = 140, mh = 12;
    const int16_t fillW = map(constrain((int)rssi, -110, -20), -110, -20, 0, mw);
    const int16_t thrX = mx + map(gRecThreshold, -110, -20, 0, mw);
    g.drawRect(mx, my, mw, mh, ui::kMuted);
    g.fillRect(mx + 1, my + 1, max<int16_t>(0, fillW - 2), mh - 2, rssi >= gRecThreshold ? ui::kBad : ui::kAccent);
    g.drawFastVLine(thrX, my - 3, mh + 6, ui::kAccent2);
    snprintf(line, sizeof(line), "%d dBm  (trigger %d)", (int)rssi, gRecThreshold);
    g.setTextColor(ui::kMuted);
    g.drawString(line, mx, my + mh + 4, 1);

    if (gLastLen) {
        snprintf(line, sizeof(line), "Last: %u pulses @ %.2f MHz, %d dBm", (unsigned)gLastLen,
                 gLastCaptureFreq, gLastCaptureRssi);
        g.setTextColor(ui::kText);
        g.drawString(line, 10, ui::kHeaderH + 40, 1);
    }
    drawWaveform(8, ui::kHeaderH + 54, ui::kW - 16, 70);
    ui::footer("Turn: freq  Press: save .sub  Hold: trigger  USER: back");
    ui::present();
}

// ---------------- Sub menu ----------------
enum class View : uint8_t { Menu, Spectrum, Finder, Recorder };
View gView = View::Menu;
ui::ListView gMenu;
const char* const kMenuItems[] = {"Spectrum analyser", "Frequency finder", "RAW recorder (.sub)"};

void enter()
{
    gView = View::Menu;
    power::setPeripheralPower(true);
    delay(10);
    radioBegin();
    spectrumReset();
}

bool loop(Key k)
{
    if (!gRadioOk) {
        ui::clear();
        ui::header("Sub-GHz");
        ui::gfx().setTextDatum(MC_DATUM);
        ui::gfx().setTextColor(ui::kBad);
        ui::gfx().drawString("CC1101 not responding", ui::kW / 2, ui::kH / 2, 2);
        ui::footer("Press: retry   USER: back");
        ui::present();
        if (k == Key::Select) radioBegin();
        return k != Key::Back;
    }

    if (gView != View::Menu) {
        if (k == Key::Back) {
            if (gView == View::Recorder) recorderStop();
            gView = View::Menu;
            leds::clearOverlay();
            return true;
        }
        if (gView == View::Spectrum) spectrumLoop(k);
        else if (gView == View::Finder) finderLoop(k);
        else recorderLoop(k);
        return true;
    }

    if (k == Key::Back) return false;
    gMenu.handle(k, 3);
    if (k == Key::Select) {
        gView = static_cast<View>(gMenu.selected + 1);
        if (gView == View::Recorder) recorderStart();
        return true;
    }
    ui::clear();
    ui::header("Sub-GHz (CC1101)");
    gMenu.draw(kMenuItems, 3);
    ui::footer("Receive only.  Press: open   USER: back");
    ui::present();
    return true;
}

void exit()
{
    recorderStop();
    if (gRadioOk) gRadio->sleep();
    boardDeselectSpi();
    leds::clearOverlay();
}
}  // namespace

const App apps::kSubGhz = {"Sub-GHz", enter, loop, exit};
