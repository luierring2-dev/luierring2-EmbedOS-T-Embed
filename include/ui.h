#pragma once
#include <TFT_eSPI.h>

// ---------- Input ----------
enum class Key : uint8_t {
    None,
    Up,         // encoder turned clockwise
    Down,       // encoder turned counter-clockwise
    Select,     // encoder pressed (short)
    LongSelect, // encoder held > 600 ms
    Back,       // USER key pressed (short)
    LongBack,   // USER key held > 1.5 s  -> sleep
};

namespace input {
void begin();
Key poll();              // returns at most one event per call
uint32_t lastActivityMs();
}  // namespace input

// ---------- Display ----------
namespace ui {
constexpr int16_t kW = 320;
constexpr int16_t kH = 170;
constexpr int16_t kHeaderH = 20;
constexpr int16_t kFooterH = 14;

constexpr uint16_t kBg      = 0x0000;
constexpr uint16_t kPanel   = 0x18E3;
constexpr uint16_t kAccent  = 0x05FF;  // cyan
constexpr uint16_t kAccent2 = 0xFD20;  // orange
constexpr uint16_t kText    = 0xFFFF;
constexpr uint16_t kMuted   = 0x8410;
constexpr uint16_t kGood    = 0x07E0;
constexpr uint16_t kBad     = 0xF800;

void begin();
TFT_eSPI& tft();
TFT_eSprite& gfx();  // full-screen back buffer (in PSRAM) – draw here, then present()
void present();

void clear();
void header(const char* title);
void footer(const char* hint);
void toast(const char* msg, uint16_t color = kAccent);  // centred message, blocks briefly

// Scrolling list with selection highlight.
struct ListView {
    int selected = 0;
    int top = 0;
    void draw(const char* const* items, int count, int16_t y = kHeaderH + 2,
              int16_t h = kH - kHeaderH - kFooterH - 4);
    // Handles Up/Down. Returns true if the selection changed.
    bool handle(Key k, int count);
};
}  // namespace ui
