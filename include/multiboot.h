#pragma once
#include <Arduino.h>

// Helpers shared by the launcher and by EmbedOS for switching OTA slots.
// All are safe to call even when the device was flashed WITHOUT the multiboot
// partition table (they just report "not available" and do nothing).
namespace multiboot {

enum class Slot : uint8_t { Launcher, OtaA, OtaB, OtaC };

// True when this firmware is running under the multiboot partition table
// (i.e. a 'factory' app partition exists).
bool available();

// Does the slot hold a valid, bootable app image?
bool slotHasApp(Slot slot);

// Set the given slot as the boot target and reboot into it. Returns false
// (without rebooting) if the slot is empty or multiboot is unavailable.
bool bootSlot(Slot slot);

// Make the NEXT cold boot land in the launcher again, without rebooting now.
// EmbedOS calls this at startup so the boot menu returns on every power-on.
void returnToLauncherNextBoot();

}  // namespace multiboot
