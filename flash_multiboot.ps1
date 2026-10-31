# Flashes the multiboot layout (launcher -> factory, EmbedOS -> ota_0).
# Usage (in the PlatformIO terminal, after `pio run`):
#     pip install esptool          # once
#     ./flash_multiboot.ps1 COM5   # replace COM5 with your port
param([Parameter(Mandatory = $true)][string]$Port)

$ErrorActionPreference = "Stop"
$b = ".pio/build"

python -m esptool --chip esp32s3 --port $Port --baud 921600 write_flash `
    0x0      "$b/launcher/bootloader.bin" `
    0x8000   "$b/launcher/partitions.bin" `
    0x10000  "$b/launcher/firmware.bin" `
    0x110000 "$b/t-embed-cc1101/firmware.bin"

Write-Host "`nDone. The device now boots into the EmbedOS boot menu." -ForegroundColor Green
Write-Host "Slot B (ota_1) and Slot C (ota_2) are still empty - see README." -ForegroundColor Yellow
