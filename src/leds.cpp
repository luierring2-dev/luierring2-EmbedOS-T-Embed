#include "leds.h"

#include <Adafruit_NeoPixel.h>

#include "board.h"
#include "power.h"

namespace {
Adafruit_NeoPixel gStrip(pins::kLedCount, pins::kLedData, NEO_GRB + NEO_KHZ800);
leds::Mode gMode = leds::Mode::Off;
uint8_t gHue = 128;

enum class Overlay : uint8_t { None, Flash, Level };
Overlay gOverlay = Overlay::None;
uint32_t gOverlayUntil = 0;
uint32_t gLastFrame = 0;

void fill(uint32_t c)
{
    gStrip.fill(c);
}

uint32_t hsv(uint8_t h, uint8_t v = 255) { return gStrip.gamma32(gStrip.ColorHSV(h * 256u, 255, v)); }
}  // namespace

namespace leds {
void begin()
{
    gStrip.begin();
    gStrip.clear();
    gStrip.show();
}

void tick()
{
    const uint32_t now = millis();
    if (now - gLastFrame < 20) return;
    gLastFrame = now;

    gStrip.setBrightness(power::settings().ledBrightness);
    if (gOverlay == Overlay::Flash && now < gOverlayUntil) return;
    if (gOverlay == Overlay::Level && now < gOverlayUntil) return;
    gOverlay = Overlay::None;

    switch (gMode) {
        case Mode::Off: gStrip.clear(); break;
        case Mode::Solid: fill(hsv(gHue)); break;
        case Mode::Rainbow:
            for (int i = 0; i < pins::kLedCount; ++i)
                gStrip.setPixelColor(i, hsv((now / 12 + i * 32) & 0xFF));
            break;
        case Mode::Breathe: {
            const float p = (sinf(now / 600.0f) + 1.0f) * 0.5f;
            fill(hsv(gHue, 10 + p * 245));
            break;
        }
        case Mode::Torch:
            gStrip.setBrightness(255);
            fill(gStrip.Color(255, 255, 255));
            break;
        default: break;
    }
    gStrip.show();
}

Mode mode() { return gMode; }
void setMode(Mode m) { gMode = m; }

const char* modeName(Mode m)
{
    switch (m) {
        case Mode::Off: return "Off";
        case Mode::Solid: return "Solid colour";
        case Mode::Rainbow: return "Rainbow";
        case Mode::Breathe: return "Breathe";
        case Mode::Torch: return "Torch (white)";
        default: return "?";
    }
}

uint8_t hue() { return gHue; }
void setHue(uint8_t h) { gHue = h; }

void flash(uint32_t rgb, uint16_t ms)
{
    gStrip.setBrightness(power::settings().ledBrightness);
    fill(rgb);
    gStrip.show();
    gOverlay = Overlay::Flash;
    gOverlayUntil = millis() + ms;
}

void level(uint8_t lit, uint32_t rgb)
{
    gStrip.setBrightness(power::settings().ledBrightness);
    for (int i = 0; i < pins::kLedCount; ++i) gStrip.setPixelColor(i, i < lit ? rgb : 0);
    gStrip.show();
    gOverlay = Overlay::Level;
    gOverlayUntil = millis() + 250;
}

void clearOverlay() { gOverlayUntil = 0; }
}  // namespace leds
