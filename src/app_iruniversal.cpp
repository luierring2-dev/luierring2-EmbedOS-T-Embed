// Universal IR remote: a built-in database of power / volume / channel codes
// for common TV brands, plus a "blast off" that sends every brand's power code
// in turn (TV-B-Gone style). This is a universal remote, send-only.
#include <IRsend.h>

#include <memory>

#include "apps.h"
#include "board.h"
#include "leds.h"

namespace {
enum class Proto : uint8_t { Nec, Samsung, Sony12, Pana64, Rc6, Rc5 };

struct Code {
    const char* label;
    Proto proto;
    uint64_t data;
    uint16_t bits;
};

struct Brand {
    const char* name;
    const Code* codes;
    uint8_t count;
};

// --- Samsung (SAMSUNG, 32-bit) ---
constexpr Code kSamsung[] = {
    {"Power", Proto::Samsung, 0xE0E040BF, 32}, {"Volume +", Proto::Samsung, 0xE0E0E01F, 32},
    {"Volume -", Proto::Samsung, 0xE0E0D02F, 32}, {"Mute", Proto::Samsung, 0xE0E0F00F, 32},
    {"Channel +", Proto::Samsung, 0xE0E048B7, 32}, {"Channel -", Proto::Samsung, 0xE0E008F7, 32},
    {"Source", Proto::Samsung, 0xE0E0807F, 32},
};

// --- LG (NEC-compatible, 32-bit) ---
constexpr Code kLg[] = {
    {"Power", Proto::Nec, 0x20DF10EF, 32}, {"Volume +", Proto::Nec, 0x20DF40BF, 32},
    {"Volume -", Proto::Nec, 0x20DFC03F, 32}, {"Mute", Proto::Nec, 0x20DF906F, 32},
    {"Channel +", Proto::Nec, 0x20DF00FF, 32}, {"Channel -", Proto::Nec, 0x20DF807F, 32},
    {"Input", Proto::Nec, 0x20DFD02F, 32},
};

// --- Sony (SONY, 12-bit, sent with 2 repeats) ---
constexpr Code kSony[] = {
    {"Power", Proto::Sony12, 0xA90, 12}, {"Volume +", Proto::Sony12, 0x490, 12},
    {"Volume -", Proto::Sony12, 0xC90, 12}, {"Mute", Proto::Sony12, 0x290, 12},
    {"Channel +", Proto::Sony12, 0x090, 12}, {"Channel -", Proto::Sony12, 0x890, 12},
    {"Input", Proto::Sony12, 0xA50, 12},
};

// --- Single-button brands (power only) ---
constexpr Code kPanasonic[] = {{"Power", Proto::Pana64, 0x40040100BCBD, 48}};
constexpr Code kPhilips[] = {{"Power", Proto::Rc6, 0x0C, 20}};
constexpr Code kToshiba[] = {{"Power", Proto::Nec, 0x02FD48B7, 32}};

constexpr Brand kBrands[] = {
    {"Samsung TV", kSamsung, 7}, {"LG TV", kLg, 7},
    {"Sony TV", kSony, 7},       {"Panasonic TV", kPanasonic, 1},
    {"Philips TV", kPhilips, 1}, {"Toshiba TV", kToshiba, 1},
};
constexpr int kBrandCount = sizeof(kBrands) / sizeof(kBrands[0]);

std::unique_ptr<IRsend> gIr;

void sendCode(const Code& c)
{
    switch (c.proto) {
        case Proto::Nec: gIr->sendNEC(c.data, c.bits); break;
        case Proto::Samsung: gIr->sendSAMSUNG(c.data, c.bits); break;
        case Proto::Sony12: gIr->sendSony(c.data, c.bits, 2); break;
        case Proto::Pana64: gIr->sendPanasonic64(c.data, c.bits); break;
        case Proto::Rc6: gIr->sendRC6(c.data, c.bits); break;
        case Proto::Rc5: gIr->sendRC5(c.data, c.bits); break;
    }
    leds::flash(0xFF0080, 90);
}

void blastOff()
{
    // Send the power code of every brand so most TVs in the room turn off.
    for (int b = 0; b < kBrandCount; ++b) {
        sendCode(kBrands[b].codes[0]);  // entry 0 is always Power
        leds::level(b + 1, 0xFF4000);
        delay(180);
    }
}

// ---------------- UI ----------------
enum class View : uint8_t { Brands, Buttons, Blasting };
View gView = View::Brands;
int gBrand = 0;
ui::ListView gBrandList;
ui::ListView gBtnList;
bool gDirty = true;

void enter()
{
    gIr.reset(new IRsend(pins::kIrTx));
    gIr->begin();
    gView = View::Brands;
    gDirty = true;
}

void drawBrands()
{
    const char* items[kBrandCount + 1];
    for (int i = 0; i < kBrandCount; ++i) items[i] = kBrands[i].name;
    items[kBrandCount] = "Blast OFF (all brands)";
    ui::clear();
    ui::header("Universal IR");
    gBrandList.draw(items, kBrandCount + 1);
    ui::footer("Press: open   USER: back");
    ui::present();
}

void drawButtons()
{
    const Brand& b = kBrands[gBrand];
    const char* items[8];
    for (int i = 0; i < b.count; ++i) items[i] = b.codes[i].label;
    ui::clear();
    ui::header(b.name);
    gBtnList.draw(items, b.count);
    ui::footer("Press: send   USER: back");
    ui::present();
}

bool loop(Key k)
{
    if (gView == View::Brands) {
        if (k == Key::Back) return false;
        if (gBrandList.handle(k, kBrandCount + 1)) gDirty = true;
        if (k == Key::Select) {
            if (gBrandList.selected == kBrandCount) {
                ui::toast("Blasting OFF...", ui::kAccent2);
                blastOff();
                ui::toast("Done", ui::kGood);
            } else {
                gBrand = gBrandList.selected;
                if (kBrands[gBrand].count == 1) {
                    sendCode(kBrands[gBrand].codes[0]);
                    ui::toast("Power sent");
                } else {
                    gView = View::Buttons;
                    gBtnList = ui::ListView{};
                }
            }
            gDirty = true;
        }
        if (gDirty) {
            gDirty = false;
            drawBrands();
        }
        return true;
    }

    // View::Buttons
    if (k == Key::Back) {
        gView = View::Brands;
        gDirty = true;
        return true;
    }
    const Brand& b = kBrands[gBrand];
    if (gBtnList.handle(k, b.count)) gDirty = true;
    if (k == Key::Select) {
        sendCode(b.codes[gBtnList.selected]);
        ui::toast(b.codes[gBtnList.selected].label);
        gDirty = true;
    }
    if (gDirty) {
        gDirty = false;
        drawButtons();
    }
    return true;
}

void exit()
{
    gIr.reset();
    leds::clearOverlay();
}
}  // namespace

const App apps::kUniversalIr = {"Universal IR", enter, loop, exit};
