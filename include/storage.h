#pragma once
#include <Arduino.h>
#include <SD.h>

namespace storage {
bool mount();      // mounts the TF card on the shared SPI bus (idempotent)
bool mounted();
void unmount();
// Returns e.g. "/subghz/raw_0007.sub" – the first name that does not exist yet.
String nextFile(const char* dir, const char* prefix, const char* ext);
}  // namespace storage
