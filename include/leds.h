#pragma once
#include <Arduino.h>

namespace leds {
enum class Mode : uint8_t { Off, Solid, Rainbow, Breathe, Torch, Count };

void begin();
void tick();  // call from the main loop

Mode mode();
void setMode(Mode m);
const char* modeName(Mode m);
uint8_t hue();
void setHue(uint8_t h);

// Short overlay effects used by the apps; they temporarily override the mode.
void flash(uint32_t rgb, uint16_t ms = 120);
void level(uint8_t lit, uint32_t rgb);  // VU-meter style: light `lit` of 8 LEDs
void clearOverlay();
}  // namespace leds
