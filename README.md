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
- **NFC:** læs kort-UID'er (PN532)
- **Wi-Fi-scanner**, **LED-effekter**, **batteri-detaljer**, **SD-browser**, **indstillinger**

## Forbedringer i forhold til fabriksfirmwaren
- Ladestrøm begrænset til 512 mA (LilyGO anbefaler maks. 600 mA til 1300 mAh-batteriet); kan ændres
- Dyb dvale slukker CC1101/LED/NFC og holder dem slukket → meget længere batteritid
- Skærmen dæmpes automatisk, og enheden går selv i dvale (ikke mens USB er tilsluttet)
- Justerbar lysstyrke (PWM) og indstillinger gemt i flash
- Encoderen læses via interrupt, så der ikke tabes trin
- Watchdog genstarter enheden, hvis den hænger
- Rettet valg af antennevej (315/433/868-915 MHz)
