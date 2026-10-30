#include "storage.h"

#include "board.h"
#include "ui.h"

namespace {
bool gMounted = false;
}

namespace storage {
bool mount()
{
    if (gMounted && SD.cardType() != CARD_NONE) return true;
    gMounted = false;
    boardDeselectSpi();
    for (uint32_t hz : {20000000u, 10000000u, 4000000u}) {
        if (SD.begin(pins::kSdCs, ui::tft().getSPIinstance(), hz)) {
            gMounted = true;
            break;
        }
    }
    boardDeselectSpi();
    return gMounted;
}

bool mounted() { return gMounted; }

void unmount()
{
    if (gMounted) SD.end();
    gMounted = false;
}

String nextFile(const char* dir, const char* prefix, const char* ext)
{
    if (!SD.exists(dir)) SD.mkdir(dir);
    char path[64];
    for (int i = 0; i < 10000; ++i) {
        snprintf(path, sizeof(path), "%s/%s_%04d.%s", dir, prefix, i, ext);
        if (!SD.exists(path)) return String(path);
    }
    return String();
}
}  // namespace storage
