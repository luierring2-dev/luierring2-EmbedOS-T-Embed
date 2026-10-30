// Infrared: learn codes from any remote, list them, replay them, save them to SD.
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>

#include <memory>
#include <vector>

#include "apps.h"
#include "board.h"
#include "leds.h"
#include "storage.h"

namespace {
constexpr uint16_t kCaptureBuf = 1024;
constexpr uint8_t kTimeoutMs = 50;  // long enough for A/C remotes
constexpr size_t kMaxCodes = 12;

struct IrCode {
    decode_type_t type = UNKNOWN;
    uint64_t value = 0;
    uint16_t bits = 0;
    std::vector<uint8_t> state;  // A/C protocols
    std::vector<uint16_t> raw;   // unknown protocols
    String label;
};

std::unique_ptr<IRrecv> gRecv;
std::unique_ptr<IRsend> gSend;
decode_results gResults;
std::vector<IrCode> gCodes;  // newest first
ui::ListView gList;
uint32_t gLastDraw = 0;
bool gDirty = true;

void capture()
{
    if (!gRecv->decode(&gResults)) return;
    if (gResults.overflow || gResults.rawlen < 8) {  // noise / partial frame
        gRecv->resume();
        return;
    }
    IrCode c;
    c.type = gResults.decode_type;
    c.bits = gResults.bits;
    if (hasACState(c.type)) {
        c.state.assign(gResults.state, gResults.state + gResults.bits / 8);
    } else {
        c.value = gResults.value;
    }
    if (c.type == UNKNOWN) {
        std::unique_ptr<uint16_t[]> raw(resultToRawArray(&gResults));
        c.raw.assign(raw.get(), raw.get() + getCorrectedRawLength(&gResults));
        c.label = "RAW  " + String(c.raw.size()) + " timings";
    } else {
        c.label = typeToString(c.type) + "  ";
        c.label += hasACState(c.type) ? String(c.bits) + " bit state"
                                      : "0x" + uint64ToString(c.value, 16);
    }
    gRecv->resume();

    // Holding a button repeats the same code – don't flood the list.
    if (!gCodes.empty() && gCodes.front().label == c.label) return;
    gCodes.insert(gCodes.begin(), std::move(c));
    if (gCodes.size() > kMaxCodes) gCodes.pop_back();
    gList.selected = 0;
    leds::flash(0x8000FF, 100);
    gDirty = true;
}

void transmit(const IrCode& c)
{
    gRecv->disableIRIn();  // don't receive our own transmission
    if (c.type == UNKNOWN) gSend->sendRaw(c.raw.data(), c.raw.size(), 38);
    else if (hasACState(c.type)) gSend->send(c.type, c.state.data(), c.state.size());
    else gSend->send(c.type, c.value, c.bits);
    leds::flash(0xFF0080, 100);
    delay(50);
    gRecv->enableIRIn();
}

bool save(const IrCode& c)
{
    gRecv->disableIRIn();
    bool ok = false;
    if (storage::mount()) {
        const String path = storage::nextFile("/ir", "ir", "txt");
        File f = SD.open(path, FILE_WRITE);
        if (f) {
            f.printf("protocol: %s\nbits: %u\n", typeToString(c.type).c_str(), c.bits);
            if (!c.state.empty()) {
                f.print("state:");
                for (uint8_t b : c.state) f.printf(" %02X", b);
                f.println();
            } else if (c.type != UNKNOWN) {
                f.printf("value: 0x%s\n", uint64ToString(c.value, 16).c_str());
            }
            if (!c.raw.empty()) {
                f.print("raw:");
                for (uint16_t t : c.raw) f.printf(" %u", t);
                f.println();
            }
            f.close();
            ok = true;
        }
    }
    boardDeselectSpi();
    gRecv->enableIRIn();
    return ok;
}

void enter()
{
    gSend.reset(new IRsend(pins::kIrTx));
    gSend->begin();
    gRecv.reset(new IRrecv(pins::kIrRx, kCaptureBuf, kTimeoutMs, true));
    gRecv->setUnknownThreshold(12);
    gRecv->enableIRIn();
    gDirty = true;
}

bool loop(Key k)
{
    if (k == Key::Back) return false;
    capture();

    if (gList.handle(k, gCodes.size())) gDirty = true;
    if (!gCodes.empty()) {
        if (k == Key::Select) {
            transmit(gCodes[gList.selected]);
            ui::toast("Sent");
            gDirty = true;
        } else if (k == Key::LongSelect) {
            const bool ok = save(gCodes[gList.selected]);
            ui::toast(ok ? "Saved to SD:/ir" : "SD card error", ok ? ui::kGood : ui::kBad);
            gDirty = true;
        }
    }

    if (!gDirty && millis() - gLastDraw < 500) return true;
    gDirty = false;
    gLastDraw = millis();

    ui::clear();
    ui::header("Infrared");
    if (gCodes.empty()) {
        auto& g = ui::gfx();
        g.setTextDatum(MC_DATUM);
        g.setTextColor(ui::kText);
        g.drawString("Point a remote at the top of the", ui::kW / 2, ui::kH / 2 - 12, 2);
        g.drawString("device and press a button", ui::kW / 2, ui::kH / 2 + 8, 2);
    } else {
        const char* items[kMaxCodes];
        for (size_t i = 0; i < gCodes.size(); ++i) items[i] = gCodes[i].label.c_str();
        gList.draw(items, gCodes.size());
    }
    ui::footer("Press: send   Hold: save to SD   USER: back");
    ui::present();
    return true;
}

void exit()
{
    gRecv->disableIRIn();
    gRecv.reset();
    gSend.reset();
}
}  // namespace

const App apps::kInfrared = {"Infrared", enter, loop, exit};
