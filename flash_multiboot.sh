#!/usr/bin/env bash
# Flashes the multiboot layout (launcher -> factory, EmbedOS -> ota_0).
# Usage (after `pio run`):
#     pip install esptool
#     ./flash_multiboot.sh /dev/ttyACM0
set -e
PORT="${1:?usage: ./flash_multiboot.sh <serial-port>}"
B=".pio/build"

python -m esptool --chip esp32s3 --port "$PORT" --baud 921600 write_flash \
    0x0      "$B/launcher/bootloader.bin" \
    0x8000   "$B/launcher/partitions.bin" \
    0x10000  "$B/launcher/firmware.bin" \
    0x110000 "$B/t-embed-cc1101/firmware.bin"

echo "Done. The device now boots into the EmbedOS boot menu."
echo "Slot B (ota_1) and Slot C (ota_2) are still empty - see README."
