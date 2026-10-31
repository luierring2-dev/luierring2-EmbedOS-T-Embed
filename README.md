# EmbedOS – egen firmware til LilyGO T-Embed CC1101 (Plus)

## Byg og flash
1. Installér VS Code + PlatformIO-udvidelsen (eller `pip install platformio`).
2. Åbn denne mappe, sæt enheden i USB, og kør:
   ```
   pio run -t upload
   pio device monitor
   ```
   Hvis upload fejler: hold BOOT (drejeknappen) nede, tryk RST, slip BOOT, og prøv igen.

## Betjening
| Handling | Effekt |
|---|---|
| Drej knappen | flyt / ændr værdi |
| Tryk knappen | vælg |
| Hold knappen | sekundær handling (se bundlinjen) |
| USER-knap | tilbage |
| Hold USER 1,5 s | dyb dvale (tryk knappen for at vække) |

## Apps
- **Sub-GHz (kun modtagelse):** spektrumanalysator, frekvensfinder, RAW-optager → `.sub` (Flipper-format) på SD
- **Infrarød:** lær, afspil og gem fjernbetjeningskoder
- **Universal IR:** indbygget database med tænd/sluk, lyd og kanal for Samsung/LG/Sony m.fl. + "Blast OFF"
- **NFC:** læs kort-UID'er (PN532)
- **Wi-Fi-scanner**, **LED-effekter**, **batteri-detaljer**, **SD-browser**, **indstillinger**

## Multiboot (valgfrit) – vælg firmware i en startmenu
Enheden kan starte i en lille **boot-menu**, hvor du vælger hvilken firmware der skal køre:
- **ota_0** = EmbedOS (bygges sammen med menuen)
- **ota_1** = Slot B (din egen firmware)
- **ota_2** = Slot C (din egen firmware)

Menuen (`src/launcher/`) ligger i `factory`-partitionen og kører først ved hver opstart.
EmbedOS vender automatisk tilbage til menuen ved næste opstart, og har også
**Indstillinger → Return to boot menu**.

### Sådan flasher du menuen + EmbedOS
```
pip install esptool
pio run
# Windows:  ./flash_multiboot.ps1 COM5     (udskift COM5 med din port)
# Mac/Linux: ./flash_multiboot.sh /dev/ttyACM0
```

### Sådan fylder du Slot B og C
Dette er den svære del, og det skal du selv gøre. **Vigtigt:** du kan ikke bare
tage en færdig `.bin` fra fx Bruce eller en Flipper-port og lægge den ind. De er
bygget til at eje hele flashen med deres egen partitionstabel. For at bo i en
slot skal firmwaren **genkompileres mod `partitions_multiboot.csv`** (app-størrelse
4 MB, offset `0x510000` for ota_1 og `0x910000` for ota_2). Når du har sådan en
app-`.bin`:
```
python -m esptool --chip esp32s3 --port COM5 write_flash 0x510000 din_firmware.bin   # Slot B
python -m esptool --chip esp32s3 --port COM5 write_flash 0x910000 din_firmware.bin   # Slot C
```

### Ærlige begrænsninger
- EmbedOS vender pænt tilbage til menuen. **Anden firmware gør det ikke af sig selv** –
  når du har booten i Slot B/C, bliver enheden i den slot ved næste opstart, indtil
  du flasher menuen tilbage eller den firmware selv understøtter at skifte.
- Nemmeste alternativ, hvis multiboot driller: kør EmbedOS normalt, og flash en anden
  firmware (fx Bruce fra https://bruce.computer/flasher.html) når du vil bruge den.
  Du kan altid flashe EmbedOS tilbage fra dette repo.

## Forbedringer i forhold til fabriksfirmwaren
- Ladestrøm begrænset til 512 mA (LilyGO anbefaler maks. 600 mA til 1300 mAh-batteriet); kan ændres
- Dyb dvale slukker CC1101/LED/NFC og holder dem slukket → meget længere batteritid
- Skærmen dæmpes automatisk, og enheden går selv i dvale (ikke mens USB er tilsluttet)
- Justerbar lysstyrke (PWM) og indstillinger gemt i flash
- Encoderen læses via interrupt, så der ikke tabes trin
- Watchdog genstarter enheden, hvis den hænger
- Rettet valg af antennevej (315/433/868-915 MHz)
