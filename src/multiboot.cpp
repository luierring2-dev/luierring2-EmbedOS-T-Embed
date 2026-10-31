#include "multiboot.h"

#include <esp_ota_ops.h>
#include <esp_partition.h>

namespace {
const esp_partition_t* find(multiboot::Slot slot)
{
    esp_partition_subtype_t sub;
    switch (slot) {
        case multiboot::Slot::Launcher: sub = ESP_PARTITION_SUBTYPE_APP_FACTORY; break;
        case multiboot::Slot::OtaA: sub = ESP_PARTITION_SUBTYPE_APP_OTA_0; break;
        case multiboot::Slot::OtaB: sub = ESP_PARTITION_SUBTYPE_APP_OTA_1; break;
        case multiboot::Slot::OtaC: sub = ESP_PARTITION_SUBTYPE_APP_OTA_2; break;
        default: return nullptr;
    }
    return esp_partition_find_first(ESP_PARTITION_TYPE_APP, sub, nullptr);
}
}  // namespace

namespace multiboot {

bool available() { return find(Slot::Launcher) != nullptr; }

bool slotHasApp(Slot slot)
{
    const esp_partition_t* p = find(slot);
    if (!p) return false;
    esp_app_desc_t desc;
    // Succeeds only when the partition starts with a valid app image header.
    return esp_ota_get_partition_description(p, &desc) == ESP_OK;
}

bool bootSlot(Slot slot)
{
    const esp_partition_t* p = find(slot);
    if (!p) return false;
    if (slot != Slot::Launcher && !slotHasApp(slot)) return false;
    if (esp_ota_set_boot_partition(p) != ESP_OK) return false;
    delay(60);
    esp_restart();
    return true;  // not reached
}

void returnToLauncherNextBoot()
{
    const esp_partition_t* p = find(Slot::Launcher);
    if (p) esp_ota_set_boot_partition(p);
}

}  // namespace multiboot
