# Guide: sådan får du Pirate Token HUD til at virke

Du skal bruge en Windows-pc med Fortnite og filen `pirate-hud.zip`.

## Den nemme vej (ca. 3 minutter)

1. Højreklik på `pirate-hud.zip` og vælg **Udpak alle …**. Vælg fx `C:\Users\<dit navn>`, ikke en OneDrive-mappe.
2. Åbn den udpakkede mappe, og dobbeltklik **`installer.bat`**.
   Viser Windows *"Windows beskyttede din pc"*: klik **Flere oplysninger** og så **Kør alligevel**.
3. Svar **J** (eller tryk Enter) på spørgsmålene. Installeren:
   - finder Python, eller installerer Python 3.13 kun for din bruger (ingen admin)
   - sætter Fortnite til **Windowed Fullscreen**, med backup af dine indstillinger. Fortnite skal være lukket
   - laver genvejen **Pirate Token HUD** på skrivebordet
   - viser demoen
4. Fortsæt ved **trin 5** herunder.

Går installeren i stå eller fejler, så tag et billede af vinduet. Du kan også følge trin 1–4 i hånden.

---

## Den manuelle vej

Trin 1–5 er nødvendige. Trin 6–9 gør den bedre.

## Trin 1 – Installér Python (kun én gang)

1. Gå til **python.org**, vælg **Downloads**, og klik på den gule knap til Windows.
2. Kør filen. Er der et flueben **"Add python.exe to PATH"** nederst, så sæt det. Klik **Install Now**.
3. Tjek at det virker: tryk på Windows-tasten, skriv `cmd` og tryk Enter. Skriv så:
   ```
   py -c "import tkinter; print('ok')"
   ```
   - **`ok`**: færdig.
   - **Den spørger om den skal installere en Python-version**: svar `y` og kør linjen igen.
   - **"'py' genkendes ikke …"**: genstart pc'en og prøv igen. Virker det stadig ikke, så
     installér igen og husk fluebenet.

## Trin 2 – Pak HUD'en ud

1. Gem `pirate-hud.zip`, fx i **Overførsler**.
2. Højreklik på zip-filen, vælg **Egenskaber**, sæt flueben i **Fjern blokering** (hvis den findes)
   og klik **OK**. Så spørger Windows ikke hver gang du starter en `.bat`.
3. Højreklik igen og vælg **Udpak alle …**. Vælg en mappe der **ikke** synkroniseres med OneDrive,
   fx `C:\Users\<dit navn>`. Dokumenter og Skrivebord ligger tit i OneDrive, og så kan
   gemningen drille.
4. Åbn mappen indtil du kan se `start.bat`, `hud.py` og `config.json`. Det er HUD-mappen.

> Kør aldrig `.bat`-filerne direkte inde fra zip-filen uden at pakke ud. Så bliver intet gemt.

Viser Windows **"Windows beskyttede din pc"**: klik **Flere oplysninger** og så **Kør alligevel**.

## Trin 3 – Indstil Fortnite (kun én gang)

**Settings** (tandhjulet) → **Video** → **Window Mode** → **Windowed Fullscreen** → **Apply**.

I almindelig *Fullscreen* kan intet overlay vises oven på spillet. Det gælder også Discord og Steam.

> **F7, F8, F9 og F10** går til HUD'en mens den kører, og Fortnite får dem ikke.
> Bruger du dem i spillet, så skift HUD'ens taster (trin 8).

## Trin 4 – Prøv demoen

Dobbeltklik **`demo.bat`**.

- Et sort vindue åbner med teksten *"HUD kører …"*, og HUD'en dukker op øverst til venstre med 2.318.
- Tryk **F8**: tallet bliver 2.319 og blinker grønt. **F7** tæller ned igen. **Ctrl+F9** flytter HUD'en.
- Demoen rører ikke dine rigtige tal.
- Stop demoen: klik i det sorte vindue og tryk **Ctrl+C**, eller luk vinduet.

Sker der ingen ting, eller blinker vinduet og lukker? Se **Fejlfinding** nederst.

## Trin 5 – Brug den

1. Dobbeltklik genvejen **Pirate Token HUD** på skrivebordet (eller `start.bat` i mappen). Det er lige meget om Fortnite allerede kører.
2. **Lad det sorte vindue være åbent.** Minimér det. Lukker du det, lukker HUD'en.
3. Start Fortnite. HUD'en vises når Fortnite har fokus og skjuler sig når du Alt+Tabber.
   De første 8 sekunder vises den altid, så du kan se at den kører.
4. Taster under kampen:

   | Tast | Hvornår |
   |---|---|
   | **F8** | hver gang du åbner en kiste, lige når den åbner |
   | **F7** | du trykkede forkert (fortryder også et forkert "fundet") |
   | **Ctrl+F8** | du fandt den! |
   | **F9** | skjul/vis |
   | **Ctrl+F9** | flyt HUD'en hvis den dækker noget |
   | **F10** | ny kamp, men kun hvis HUD'en ikke selv ser at en kamp starter (trin 6) |

5. Sådan læser du HUD'en:
   - **Det store gule tal**: kister siden sidste fund.
   - **Prikken øverst til højre**: grøn betyder at loggen læses. Grå betyder ingen nye linjer i 30 sek, hvilket er normalt i menuen. Orange betyder at loggen ikke er fundet.
   - **Nederst**: *"kamp 4:12"* under en kamp, ellers *"lobby / venter på kamp"*.
   - **Tempo og "kampe til 50 %"** kommer først når en kamp er spillet færdig og registreret.

Tælleren gemmes efter hvert tryk. Du kan lukke alt og fortsætte i morgen.

## Trin 6 – Tjek at kampstart bliver opdaget (kun én gang)

1. Spil en hel kamp færdig og gå tilbage til lobbyen. HUD'en behøver ikke køre.
2. Dobbeltklik **`tjek-log.bat`**.
3. Kig under **"Hits i alt pr. event"**:
   - **`MATCH_START … OK`** og enten **`MATCH_END`** eller **`LOBBY`** med **`OK`**: det virker. Gå til trin 7.
   - **`MATCH_START … RAMMER IKKE`**: du har to muligheder.
     - **a)** Tryk **F10** ved starten af hver kamp. Alt andet virker stadig.
     - **b)** Ret mønstret. Under *"Linjer med relevante ord"* står rigtige linjer fra din log.
       Find en der kommer når en kamp starter, og brug den del der altid er ens. Eksempel:
       ```
       loglinje:  [2026.11.10-20.14.03:512][ 88]LogGameState: Match State Changed from WaitingToStart to InProgress
       mønster:   "Match State Changed from \\w+ to InProgress"
       ```
       `\\w+` betyder "et vilkårligt ord". Sæt mønstret ind i `config.json` (se trin 8), og kør
       `tjek-log.bat` igen. Når der står `OK`, virker det.

   Du kan også sende mig filen `kalibrering\tjek.txt`. **Søg først efter dit Epic-navn og
   slet det.** Logs kan indeholde det.

## Trin 7 – Kan kisterne tælles automatisk? (valgfrit)

1. Spil som normalt med HUD'en kørende, og tryk **F8 ved hver kiste**. Jo mere præcist, jo bedre.
2. Når du har mindst 10 tryk (gerne 30+ over flere kampe): stop HUD'en med **Ctrl+C** og dobbeltklik
   **`analyser-kister.bat`**.
3. Der kan komme tre svar:
   - **"… sandsynligvis ikke"**: Fortnite skriver ikke kister i loggen. Bliv ved med F8, og så er du færdig.
   - **"God kandidat"**: den viser en linje som `"CHEST": ["…"]`. Åbn `config.json`, find
     `"CHEST": []` og erstat den med linjen. Gem. Nu tæller HUD'en selv, og tallet blinker blåt.
     **Stop med F8 for kister**, ellers tæller de dobbelt.
   - **"Ingen sikker kandidat"**: optag flere tryk og kør den igen.

## Trin 8 – Tilpas den (config.json)

Højreklik på `config.json`, vælg **Åbn med** og så **Notesblok**. Gem med **Ctrl+S**. HUD'en læser filen igen
efter ca. 2 sekunder. Laver du en tastefejl, skriver HUD'en *"config.json ikke indlæst: linje X"* og
bruger de gamle indstillinger, indtil fejlen er rettet.

| Indstilling | Eksempel | Betyder |
|---|---|---|
| `odds_per_chest` | `137500` | 1 ud af N pr. kiste |
| `boost` | `2.0` | under events med dobbelt chance (husk at sætte tilbage til `1.0`) |
| `corner` | `"tl"` | `tl` `tr` `ml` `mr` `bl` `br` (top/midt/bund, venstre/højre). Undgå `tr`, der sidder Fortnites minikort |
| `offset_x`, `offset_y` | `0`, `120` | flyt fint, i pixels (må være negative) |
| `scale` | `1.25` | større/mindre |
| `opacity` | `0.8` | gennemsigtighed, `0.2`–`0.98` |
| `hide_when_not_fortnite` | `false` | vis altid, også på skrivebordet |
| `show_map` | `false` | skjul kortet |
| `route` | `["Loguetown", "Arlong Park"]` | din rute |
| `hotkeys` | `"chest": "NUM+"` | andre taster. **Kræver genstart af HUD'en** |

**Taster du kan bruge:**
- F1–F11 (ikke F12)
- A–Z og 0–9
- NUM0–NUM9, NUM+, NUM-, NUM\*, NUM/
- PAGEUP, PAGEDOWN, HOME, END, INSERT, DELETE, PAUSE, SCROLLLOCK

Du kan sætte `ctrl+`, `shift+` eller `alt+` foran, fx `"ctrl+shift+K"`.

**JSON-regler:**
- Tekst skal stå i "anførselstegn".
- Der skal være komma mellem linjerne, men ikke efter den sidste.
- En backslash skrives `\\`.

## Trin 9 – Kortet (valgfrit)

Kortet viser **eksempeldata**: prikkerne er ikke rigtige kister, og der står det. Sæt
`"show_map": false` indtil du har rigtige data.

Vil du have et billede bag prikkerne, så gem et **kvadratisk PNG** (ikke JPG) af kortet i HUD-mappen,
fx `kort.png`, og sæt `"map_image": "kort.png"`.

---

## Fejlfinding

| Problem | Løsning |
|---|---|
| *"Python er ikke installeret"* | Trin 1, og genstart pc'en |
| Det sorte vindue blinker og lukker | Åbn HUD-mappen, klik i adresselinjen, skriv `cmd` og tryk Enter. Skriv `py hud.py` og tryk Enter. Nu bliver fejlen stående. Send den til mig |
| Microsoft Store åbner | Python er ikke installeret rigtigt. Installér fra python.org (trin 1) |
| *"No module named tkinter"* | Installér Python igen fra python.org (ikke Microsoft Store) |
| HUD'en ses på skrivebordet, men ikke i spillet | Windowed Fullscreen (trin 3) |
| HUD'en forsvinder når jeg Alt+Tabber | Det er meningen. Slå det fra med `"hide_when_not_fortnite": false` |
| HUD'en ses slet ikke | Tryk **F9**. Sæt `"hide_when_not_fortnite": false` og prøv igen |
| *"⚠ F8 er optaget af et andet program"* | Discord, OBS, NVIDIA/AMD-overlay eller en anden HUD der stadig kører bruger tasten. Luk det, eller vælg en anden tast |
| Tasterne gør ingenting | Kører HUD'en? (det sorte vindue). Står der advarsler nederst i HUD'en? |
| *"venter på Fortnite-loggen"* | Start Fortnite. Ligger loggen et andet sted, så sæt `"log_file": "D:\\…\\FortniteGame.log"` |
| *"kunne ikke gemme"* | Mappen ligger nok i OneDrive. Flyt hele HUD-mappen (trin 2.3) |
| Tallet står på 0 efter jeg flyttede mappen | Mappen `data` skal med, den ligger inde i HUD-mappen |
| Starte helt forfra | Luk HUD'en og slet `data\state.json` |
| *"intern fejl – se konsolvinduet"* | Send mig teksten fra det sorte vindue |

**Skal du have hjælp**, så send:
- teksten fra det sorte vindue
- eventuelt `kalibrering\tjek.txt`, men slet dit Epic-navn først
