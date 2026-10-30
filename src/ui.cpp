#include "ui.h"

#include "board.h"
#include "power.h"

// ===================== Input =====================
namespace {
// Quadrature decoder running in an IRAM ISR so fast turns are never lost,
// even while the main loop is busy with an RF sweep or SD write.
volatile int32_t gEncSteps = 0;
volatile uint8_t gEncState = 0;
volatile int8_t gEncAccum = 0;

constexpr int8_t kQuadTable[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};

void IRAM_ATTR onEncoderEdge()
{
    const uint8_t ab = (gpio_get_level((gpio_num_t)pins::kEncA) << 1) |
                       gpio_get_level((gpio_num_t)pins::kEncB);
    gEncState = ((gEncState << 2) | ab) & 0x0F;
    gEncAccum += kQuadTable[gEncState];
    // The T-Embed encoder latches every 2 transitions (RotaryEncoder TWO03).
    if (gEncAccum >= 2) {
        gEncSteps++;
        gEncAccum = 0;
    } else if (gEncAccum <= -2) {
        gEncSteps--;
        gEncAccum = 0;
    }
}

struct Button {
    // Explicit constructor: the ESP32 Arduino core builds as C++11, where a
    // struct with default member initialisers can't be brace-initialised.
    Button(int p, uint32_t lm) : pin(p), longMs(lm) {}

    int pin;
    uint32_t longMs;
    bool down = false;
    bool longFired = false;
    uint32_t changedAt = 0;

    // Returns 1 on short release, 2 when the long-press threshold is crossed.
    int update()
    {
        const bool pressed = digitalRead(pin) == LOW;
        const uint32_t now = millis();
        if (pressed != down && now - changedAt > 25) {  // debounce
            down = pressed;
            changedAt = now;
            if (!pressed) {
                const bool wasLong = longFired;
                longFired = false;
                return wasLong ? 0 : 1;
            }
        }
        if (down && !longFired && now - changedAt >= longMs) {
            longFired = true;
            return 2;
        }
        return 0;
    }
};

Button gEncBtn{pins::kEncKey, 600};
Button gUserBtn{pins::kUserKey, 1500};
uint32_t gLastActivity = 0;
}  // namespace

namespace input {
void begin()
{
    pinMode(pins::kEncA, INPUT_PULLUP);
    pinMode(pins::kEncB, INPUT_PULLUP);
    pinMode(pins::kEncKey, INPUT_PULLUP);
    pinMode(pins::kUserKey, INPUT_PULLUP);
    gEncState = (digitalRead(pins::kEncA) << 1) | digitalRead(pins::kEncB);
    attachInterrupt(digitalPinToInterrupt(pins::kEncA), onEncoderEdge, CHANGE);
    attachInterrupt(digitalPinToInterrupt(pins::kEncB), onEncoderEdge, CHANGE);
    gLastActivity = millis();
}

Key poll()
{
    Key k = Key::None;
    noInterrupts();
    const int32_t steps = gEncSteps;
    if (steps > 0) gEncSteps--;
    else if (steps < 0) gEncSteps++;
    interrupts();

    const bool rev = power::settings().reverseEncoder;
    if (steps > 0) k = rev ? Key::Down : Key::Up;
    else if (steps < 0) k = rev ? Key::Up : Key::Down;

    const int e = gEncBtn.update();
    const int u = gUserBtn.update();
    if (k == Key::None) {
        if (e == 1) k = Key::Select;
        else if (e == 2) k = Key::LongSelect;
        else if (u == 1) k = Key::Back;
        else if (u == 2) k = Key::LongBack;
    }

    if (k != Key::None || gEncBtn.down || gUserBtn.down) gLastActivity = millis();
    return k;
}

uint32_t lastActivityMs() { return gLastActivity; }
}  // namespace input

// ===================== Display =====================
namespace {
TFT_eSPI gTft;
TFT_eSprite gCanvas(&gTft);
bool gCanvasOk = false;
}  // namespace

namespace ui {
void begin()
{
    boardDeselectSpi();
    gTft.begin();
    gTft.setRotation(3);
    gTft.fillScreen(kBg);
    gCanvas.setColorDepth(16);
    gCanvasOk = gCanvas.createSprite(kW, kH) != nullptr;
    if (!gCanvasOk) Serial.println("[ui] sprite alloc failed, drawing direct");
}

TFT_eSPI& tft() { return gTft; }
TFT_eSprite& gfx() { return gCanvas; }

void present()
{
    if (gCanvasOk) gCanvas.pushSprite(0, 0);
    boardDeselectSpi();
}

void clear() { gCanvas.fillSprite(kBg); }

void header(const char* title)
{
    auto& g = gCanvas;
    g.fillRect(0, 0, kW, kHeaderH, kPanel);
    g.setTextDatum(ML_DATUM);
    g.setTextColor(kAccent, kPanel);
    g.drawString(title, 6, kHeaderH / 2, 2);

    const power::Battery& b = power::battery();
    // Battery glyph
    const int16_t bx = kW - 34, by = 5, bw = 24, bh = 10;
    g.drawRect(bx, by, bw, bh, kText);
    g.fillRect(bx + bw, by + 3, 2, 4, kText);
    if (b.valid) {
        const uint16_t c = b.soc > 50 ? kGood : (b.soc > 20 ? kAccent2 : kBad);
        g.fillRect(bx + 2, by + 2, (bw - 4) * b.soc / 100, bh - 4, c);
        char pct[8];
        snprintf(pct, sizeof(pct), "%d%%", b.soc);
        g.setTextDatum(MR_DATUM);
        g.setTextColor(b.charging ? kGood : kText, kPanel);
        g.drawString(pct, bx - 4, kHeaderH / 2, 2);
    }
}

void footer(const char* hint)
{
    auto& g = gCanvas;
    g.fillRect(0, kH - kFooterH, kW, kFooterH, kPanel);
    g.setTextDatum(ML_DATUM);
    g.setTextColor(kMuted, kPanel);
    g.drawString(hint, 6, kH - kFooterH / 2, 1);
}

void toast(const char* msg, uint16_t color)
{
    auto& g = gCanvas;
    const int16_t w = g.textWidth(msg, 2) + 24;
    const int16_t x = (kW - w) / 2, y = kH / 2 - 16;
    g.fillRoundRect(x, y, w, 32, 6, kPanel);
    g.drawRoundRect(x, y, w, 32, 6, color);
    g.setTextDatum(MC_DATUM);
    g.setTextColor(color, kPanel);
    g.drawString(msg, kW / 2, kH / 2, 2);
    present();
    delay(700);
}

void ListView::draw(const char* const* items, int count, int16_t y, int16_t h)
{
    constexpr int16_t kRowH = 22;
    const int visible = h / kRowH;
    if (selected < top) top = selected;
    if (selected >= top + visible) top = selected - visible + 1;

    auto& g = gCanvas;
    g.setTextDatum(ML_DATUM);
    for (int i = 0; i < visible && top + i < count; ++i) {
        const int idx = top + i;
        const int16_t ry = y + i * kRowH;
        const bool sel = idx == selected;
        if (sel) g.fillRoundRect(4, ry, kW - 14, kRowH - 2, 4, kAccent);
        g.setTextColor(sel ? kBg : kText, sel ? kAccent : kBg);
        g.drawString(items[idx], 12, ry + kRowH / 2 - 1, 2);
    }
    // Scrollbar
    if (count > visible) {
        const int16_t barH = max<int16_t>(8, h * visible / count);
        const int16_t barY = y + (h - barH) * top / (count - visible);
        g.fillRect(kW - 5, y, 3, h, kPanel);
        g.fillRect(kW - 5, barY, 3, barH, kMuted);
    }
}

bool ListView::handle(Key k, int count)
{
    if (count <= 0) return false;
    if (k == Key::Up) {
        selected = (selected + 1) % count;
        return true;
    }
    if (k == Key::Down) {
        selected = (selected - 1 + count) % count;
        return true;
    }
    return false;
}
}  // namespace ui
