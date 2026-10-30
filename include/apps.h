#pragma once
#include "ui.h"

// An app owns the screen while active. loop() is called continuously and
// returns false to go back to the main menu.
struct App {
    const char* name;
    void (*enter)();
    bool (*loop)(Key key);
    void (*exit)();
};

namespace apps {
extern const App kSubGhz;
extern const App kInfrared;
extern const App kUniversalIr;
extern const App kNfc;
extern const App kWifiScan;
extern const App kLeds;
extern const App kBattery;
extern const App kSdCard;
extern const App kSettings;
}  // namespace apps
