# Pirate Token HUD - installation. Startes af installer.bat.
#
# Gør, i rækkefølge:
#   1. tjekker at mappen er pakket ud
#   2. fjerner Windows' "hentet fra internettet"-mærke fra filerne
#   3. finder Python 3.10+ med tkinter - eller installerer Python 3.13 (kun for din bruger, ingen admin)
#   4. sætter Fortnite til Windowed Fullscreen (spørger først, laver backup)
#   5. laver en genvej på skrivebordet
#   6. tilbyder at vise demoen
#
# Rører ikke andet end: denne mappe, Python-installationen, Fortnites GameUserSettings.ini
# (med backup) og én genvej på skrivebordet.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # gør downloads meget hurtigere i Windows PowerShell
$Here = $PSScriptRoot

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Ok([string]$Text)   { Say "  OK    $Text" 'Green' }
function Warn([string]$Text) { Say "  OBS   $Text" 'Yellow' }
function Fail([string]$Text) { Say "  FEJL  $Text" 'Red' }
function Ask([string]$Question) {
    $answer = Read-Host "  $Question [J/n]"
    return ($answer -eq '' -or $answer -match '^\s*[jJyY]')
}

# ------------------------------------------------------------------ Python
function Test-Python([string]$Exe) {
    # Fuld sti til python.exe hvis $Exe er Python 3.10+ med tkinter, ellers $null.
    $ErrorActionPreference = 'Continue'
    try {
        # 'n' på stdin: svarer nej hvis noget spørger, så scriptet aldrig hænger
        $out = 'n' | & $Exe -c "import sys, tkinter; print(sys.executable if sys.version_info >= (3, 10) else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $path = ([string]($out | Select-Object -Last 1)).Trim()
            if ($path -and (Test-Path -LiteralPath $path)) { return $path }
        }
    } catch { }
    return $null
}

function Find-Python {
    $candidates = @()
    $candidates += Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    if ($env:ProgramFiles) {
        $candidates += Get-ChildItem -Path "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    }
    $candidates += @('py', 'python')
    foreach ($c in $candidates) {
        $found = Test-Python $c
        if ($found) { return $found }
    }
    return $null
}

function Install-PythonWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    Say '  Installerer Python 3.13 med winget ...'
    $ErrorActionPreference = 'Continue'
    # Out-Host: vis winget's fremskridt i stedet for at det bliver funktionens returværdi
    & winget install --id Python.Python.3.13 --exact --scope user --silent `
        --accept-package-agreements --accept-source-agreements | Out-Host
    return ($LASTEXITCODE -eq 0)
}

function Install-PythonDownload {
    $arch = 'amd64'
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'arm64' }
    $version = '3.13.3'
    $url = "https://www.python.org/ftp/python/$version/python-$version-$arch.exe"
    $file = Join-Path $env:TEMP "python-$version-$arch.exe"
    Say "  Henter $url ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
    $sig = Get-AuthenticodeSignature -FilePath $file
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue
        throw 'Python-installeren har ikke en gyldig signatur fra Python Software Foundation - den bruges ikke.'
    }
    Say '  Installerer (kun for din bruger, uden admin) ...'
    $installArgs = @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_tcltk=1', 'Include_launcher=1',
                     'InstallLauncherAllUsers=0', 'Include_test=0')
    $proc = Start-Process -FilePath $file -ArgumentList $installArgs -Wait -PassThru
    Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue
    return ($proc.ExitCode -eq 0)
}

function Update-PathFromRegistry {
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $env:Path = "$machine;$user"
}

# ------------------------------------------------------------------ Fortnite
function Set-FortniteWindowedFullscreen {
    $ini = Join-Path $env:LOCALAPPDATA 'FortniteGame\Saved\Config\WindowsClient\GameUserSettings.ini'
    if (-not (Test-Path -LiteralPath $ini)) {
        Warn 'Fortnites indstillingsfil findes ikke endnu (er Fortnite startet på denne pc?).'
        Warn 'Sæt det selv i spillet: Settings -> Video -> Window Mode -> Windowed Fullscreen.'
        return
    }
    $text = [IO.File]::ReadAllText($ini)
    if ($text -match '(?m)^FullscreenMode=1\s*$') {
        Ok 'Fortnite står allerede på Windowed Fullscreen'
        return
    }
    if ($text -notmatch '(?m)^FullscreenMode=\d+') {
        Warn 'Fandt ikke FullscreenMode i Fortnites indstillinger. Sæt det selv i spillet:'
        Warn 'Settings -> Video -> Window Mode -> Windowed Fullscreen.'
        return
    }
    if (-not (Ask 'Skal Fortnite sættes til Windowed Fullscreen? (kræves for at HUD''en kan ses i spillet)')) {
        Warn 'Sprunget over. Husk at gøre det selv i spillet.'
        return
    }
    while (Get-Process -Name 'FortniteClient-Win64-Shipping' -ErrorAction SilentlyContinue) {
        Warn 'Fortnite kører. Luk spillet helt (ellers overskriver det ændringen), og tryk Enter.'
        [void](Read-Host)
    }
    if ((Get-Item -LiteralPath $ini).IsReadOnly) {
        Warn 'Fortnites indstillingsfil er skrivebeskyttet. Sæt det selv i spillet: Settings -> Video -> Window Mode.'
        return
    }
    $bytes = [IO.File]::ReadAllBytes($ini)
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        $encoding = New-Object Text.UnicodeEncoding($false, $true)
    } elseif ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $encoding = New-Object Text.UTF8Encoding($true)
    } else {
        $encoding = New-Object Text.UTF8Encoding($false)
    }
    $backup = "$ini.foer-pirate-hud.bak"
    Copy-Item -LiteralPath $ini -Destination $backup -Force
    $new = [regex]::Replace($text, '(?m)^(FullscreenMode|LastConfirmedFullscreenMode|PreferredFullscreenMode)=\d+', '${1}=1')
    [IO.File]::WriteAllText($ini, $new, $encoding)
    Ok 'Fortnite er sat til Windowed Fullscreen'
    Say "        (backup: $backup)"
}

# ------------------------------------------------------------------ genvej
function New-DesktopShortcut {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $desktop 'Pirate Token HUD.lnk'))
    $link.TargetPath = Join-Path $Here 'start.bat'
    $link.WorkingDirectory = $Here
    $link.WindowStyle = 7          # sort vindue starter minimeret
    $link.Description = 'Start Pirate Token HUD'
    $link.Save()
    Ok "genvej på skrivebordet: Pirate Token HUD"
}

# ------------------------------------------------------------------ hovedforløb
try {
    Say ''
    Say '=== Pirate Token HUD - installation ===' 'Cyan'
    Say ''

    Say '[1/5] Tjekker mappen'
    if (-not (Test-Path -LiteralPath (Join-Path $Here 'hud.py'))) {
        Fail 'hud.py ligger ikke ved siden af installer.bat.'
        Say  '        Du har nok startet den inde fra zip-filen. Højreklik zip-filen -> "Udpak alle",'
        Say  '        og kør installer.bat i den udpakkede mappe.'
        exit 1
    }
    Ok $Here
    if ($Here -match 'OneDrive') {
        Warn 'Mappen ligger i OneDrive. Det virker som regel, men skriver HUD''en "kunne ikke gemme",'
        Warn 'så flyt hele mappen til C:\Users\<dit navn> og kør installer.bat igen.'
    }

    Say '[2/5] Låser filerne op'
    try {
        Get-ChildItem -LiteralPath $Here -Recurse -File | Unblock-File
        Ok 'Windows spørger ikke længere ved hver .bat'
    } catch {
        Warn "kunne ikke låse op ($($_.Exception.Message)) - ikke vigtigt"
    }

    Say '[3/5] Python'
    $python = Find-Python
    if ($python) {
        Ok "fundet: $python"
    } else {
        Say '  Python 3.10+ mangler. Installerer Python 3.13 - det kan tage et par minutter.'
        $done = $false
        try { $done = Install-PythonWinget } catch { Warn "winget fejlede: $($_.Exception.Message)" }
        Update-PathFromRegistry
        $python = Find-Python
        if (-not $python) {
            try { $done = Install-PythonDownload } catch { Warn "download fejlede: $($_.Exception.Message)" }
            Update-PathFromRegistry
            $python = Find-Python
        }
        if (-not $python) {
            Fail 'Python kunne ikke installeres automatisk.'
            Say  '        Følg trin 1 i GUIDE.md (installér fra python.org), og kør installer.bat igen.'
            exit 1
        }
        Ok "installeret: $python"
    }

    Say '[4/5] Fortnite'
    try { Set-FortniteWindowedFullscreen } catch { Warn "kunne ikke ændre Fortnites indstilling ($($_.Exception.Message)). Gør det i spillet." }

    Say '[5/5] Genvej'
    try { New-DesktopShortcut } catch { Warn "kunne ikke lave genvej ($($_.Exception.Message)). Brug start.bat i mappen." }

    Say ''
    Say '=== Færdig ===' 'Cyan'
    Say 'Start HUD''en med genvejen "Pirate Token HUD" på skrivebordet (eller start.bat i mappen).'
    Say 'Det sorte vindue starter minimeret. Lukker du det, lukker HUD''en.'
    Say ''
    if (Ask 'Vil du se demoen nu? (stop den med Ctrl+C eller ved at lukke vinduet)') {
        & $python (Join-Path $Here 'hud.py') --demo
    }
    exit 0
} catch {
    Say ''
    Fail "Uventet fejl: $($_.Exception.Message)"
    Say  '        Tag et billede af dette vindue og send det til Claude.'
    exit 1
}
