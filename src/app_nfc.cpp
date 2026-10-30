// NFC (PN532, 13.56 MHz): read ISO14443A card UIDs without blocking the UI.
#include <Adafruit_PN532.h>
#include <Wire.h>

#include <memory>

#include "apps.h"
#include "board.h"
#include "leds.h"
#include "storage.h"

namespace {
struct Card {
    uint8_t uid[7];
    uint8_t len;
    uint32_t seenMs;
};

std::unique_ptr<Adafruit_PN532> gNfc;
bool gReady = false;
bool gArmed = false;
uint32_t gFirmware = 0;
Card gCards[6];
int gCardCount = 0;
uint32_t gLastDraw = 0;
uint32_t gArmedAt = 0;

String uidString(const Card& c)
{
    String s;
    for (int i = 0; i < c.len; ++i) {
        char b[4];
        snprintf(b, sizeof(b), i ? ":%02X" : "%02X", c.uid[i]);
        s += b;
    }
    return s;
}

const char* guessType(uint8_t len)
{
    switch (len) {
        case 4: return "MIFARE Classic / 4-byte UID";
        case 7: return "NTAG / Ultralight / DESFire";
        default: return "ISO14443A";
    }
}

void arm()
{
    gArmed = gNfc->startPassiveTargetIDDetection(PN532_MIFARE_ISO14443A);
    gArmedAt = millis();
}

void poll()
{
    if (!gReady) return;
    // IRQ goes low when the PN532 has a card ready for us.
    if (gArmed && digitalRead(pins::kPn532Irq) == HIGH) {
        if (millis() - gArmedAt > 3000) arm();  // re-arm in case we missed the edge
        return;
    }
    if (gArmed) {
        Card c{};
        if (gNfc->readDetectedPassiveTargetID(c.uid, &c.len) && c.len <= 7) {
            c.seenMs = millis();
            const bool same = gCardCount && gCards[0].len == c.len && !memcmp(gCards[0].uid, c.uid, c.len);
            if (same) {
                gCards[0].seenMs = c.seenMs;
            } else {
                memmove(&gCards[1], &gCards[0], sizeof(Card) * 5);
                gCards[0] = c;
                gCardCount = min(gCardCount + 1, 6);
                leds::flash(0x0080FF, 150);
                Serial.printf("[nfc] UID %s\n", uidString(c).c_str());
            }
        }
        gArmed = false;
        delay(150);  // let the card leave / avoid hammering the bus
    }
    arm();
}

bool saveLog()
{
    if (!gCardCount || !storage::mount()) return false;
    File f = SD.open("/nfc_uids.txt", FILE_APPEND);
    if (!f) return false;
    for (int i = gCardCount - 1; i >= 0; --i)
        f.printf("%s  len=%u  %s\n", uidString(gCards[i]).c_str(), gCards[i].len, guessType(gCards[i].len));
    f.close();
    boardDeselectSpi();
    return true;
}

void enter()
{
    gNfc.reset(new Adafruit_PN532(pins::kPn532Irq, pins::kPn532Reset, &Wire));
    gReady = gNfc->begin() && (gFirmware = gNfc->getFirmwareVersion()) != 0 && gNfc->SAMConfig();
    if (gReady) {
        gNfc->setPassiveActivationRetries(0x01);
        arm();
    }
}

bool loop(Key k)
{
    if (k == Key::Back) return false;
    if (!gReady && k == Key::Select) enter();
    if (gReady && k == Key::Select) {
        const bool ok = saveLog();
        ui::toast(ok ? "Appended to /nfc_uids.txt" : "Nothing saved", ok ? ui::kGood : ui::kBad);
    }
    if (gReady && k == Key::LongSelect) gCardCount = 0;
    poll();

    if (millis() - gLastDraw < 200) return true;
    gLastDraw = millis();

    auto& g = ui::gfx();
    ui::clear();
    ui::header("NFC reader");
    if (!gReady) {
        g.setTextDatum(MC_DATUM);
        g.setTextColor(ui::kBad);
        g.drawString("PN532 not found", ui::kW / 2, ui::kH / 2, 2);
        ui::footer("Press: retry   USER: back");
        ui::present();
        return true;
    }
    g.setTextDatum(TL_DATUM);
    if (gCardCount == 0) {
        g.setTextColor(ui::kText);
        g.drawString("Hold a card against the back", 10, ui::kHeaderH + 30, 2);
        char fw[40];
        snprintf(fw, sizeof(fw), "PN5%02X firmware %u.%u", (unsigned)(gFirmware >> 24) & 0xFF,
                 (unsigned)(gFirmware >> 16) & 0xFF, (unsigned)(gFirmware >> 8) & 0xFF);
        g.setTextColor(ui::kMuted);
        g.drawString(fw, 10, ui::kHeaderH + 56, 2);
    } else {
        const Card& c = gCards[0];
        g.setTextColor(ui::kAccent);
        g.drawString(uidString(c), 10, ui::kHeaderH + 6, 4);
        g.setTextColor(ui::kText);
        g.drawString(guessType(c.len), 10, ui::kHeaderH + 36, 2);
        g.setTextColor(ui::kMuted);
        for (int i = 1; i < gCardCount; ++i)
            g.drawString(uidString(gCards[i]), 10, ui::kHeaderH + 56 + (i - 1) * 14, 1);
    }
    ui::footer("Press: save log   Hold: clear   USER: back");
    ui::present();
    return true;
}

void exit()
{
    gNfc.reset();
    gReady = false;
}
}  // namespace

const App apps::kNfc = {"NFC", enter, loop, exit};
