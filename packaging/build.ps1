# build.ps1 — Construit fsmods-gui.exe pour Windows via Nuitka.
#
# Usage (depuis la racine du dépôt) :
#   .\packaging\build.ps1
#
# Options :
#   -Clean      Supprime dist/ et build/ avant de compiler (par défaut activé)
#   -NoClean    Conserve les artefacts précédents
#   -Install    Installe / met à jour les dépendances (incl. nuitka) avant de compiler
#   -Standalone Crée un dossier `fsmods-gui.dist/` (lancement plus rapide) au lieu d'un
#               .exe onefile autonome. Onefile par défaut.
#   -DebugConsole Active la console Windows pour voir les logs print()
#
# Pré-requis : .venv doit exister (python -m venv .venv) et contenir les deps
#              du projet + nuitka. Pour onefile, .venv313 est recommandé.
#              Lance avec -Install la première fois.

param(
    [switch]$Clean = $true,
    [switch]$NoClean = $false,
    [switch]$Install = $false,
    [switch]$Standalone = $false,
    [switch]$UsePy313 = $false,
    [switch]$DebugConsole = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Chemins ──────────────────────────────────────────────────────────────────
$root = Split-Path $PSScriptRoot -Parent
$venvDefault = Join-Path $root ".venv"
$venvPy313 = Join-Path $root ".venv313"
$venv = $venvDefault

if ((-not $Standalone) -and ((Test-Path (Join-Path $venvPy313 "Scripts\python.exe")) -or $UsePy313)) {
    $venv = $venvPy313
}

$pip = Join-Path $venv "Scripts\pip.exe"
$python = Join-Path $venv "Scripts\python.exe"
$entry = Join-Path $PSScriptRoot "fsmods_gui_entry.py"
$outDir = Join-Path $root "dist"
$pysideDir = Join-Path $venv "Lib\site-packages\PySide6"
$appIcon = Join-Path $PSScriptRoot "assets\fsmods-gui.ico"
$logDir = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "fs25-profile-switcher\build-logs"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$buildLog = Join-Path $logDir "nuitka-build-$stamp.log"
$reportXml = Join-Path $logDir "nuitka-report-$stamp.xml"

Push-Location $root

# ── Nettoyage des processus en cours ─────────────────────────────────────────
$processes = Get-Process -Name "fsmods-gui" -ErrorAction SilentlyContinue
if ($processes) {
    Write-Host "Fermeture des instances de fsmods-gui.exe en cours…" -ForegroundColor Yellow
    $processes | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

# ── Vérification du venv ─────────────────────────────────────────────────────
if (-not (Test-Path $python)) {
    Write-Error "$venv introuvable. Crée-le puis installe les dépendances build (pip install -e .[build])."
    Pop-Location
    exit 1
}

# ── Mise à jour des dépendances si demandé ───────────────────────────────────
if ($Install) {
    Write-Host "Installation des dépendances + nuitka…" -ForegroundColor Cyan
    & $pip install -e ".[build]"
}

# ── Vérifier que Nuitka est dispo ────────────────────────────────────────────
& $python -c "import nuitka" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka introuvable dans le venv. Installation…" -ForegroundColor Yellow
    & $pip install nuitka
}

# ── Synchroniser le package editable avec la version actuelle ─────────────────
Write-Host "Synchronisation du package editable avec la version du code source…" -ForegroundColor Cyan
& $pip install -e $root --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Erreur lors de la réinstallation du package editable." -ForegroundColor Red
    exit 1
}

# ── Nettoyage ─────────────────────────────────────────────────────────────────
$doClean = $Clean -and (-not $NoClean)
if ($doClean) {
    foreach ($p in @("dist", "build", "fsmods_gui_entry.dist", "fsmods_gui_entry.build", "fsmods_gui_entry.onefile-build")) {
        $full = Join-Path $root $p
        if (Test-Path $full) {
            Write-Host "Suppression $p\…" -ForegroundColor DarkGray
            Remove-Item -Recurse -Force $full
        }
    }
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# ── Arguments Nuitka ─────────────────────────────────────────────────────────
$consoleMode = if ($DebugConsole) { "force" } else { "disable" }
$nuitkaArgs = @(
    "-m", "nuitka",
    "--assume-yes-for-downloads",          # télécharge ccache / dépendant-walker silencieusement
    "--windows-console-mode=$consoleMode", # console pour debug ou pas
    "--enable-plugin=pyside6",
    "--include-qt-plugins=platforms,styles,iconengines,imageformats,tls",
    "--include-package=fsmods_gui",
    "--include-package=psutil",
    "--include-package=yaml",
    "--include-package=PIL",
    "--report=$reportXml",
    "--output-dir=$outDir",
    "--output-filename=fsmods-gui.exe",
    "--company-name=Julien Chouteau",
    "--product-name=FS25 Profile Switcher",
    # Détecte dynamiquement la version du paquet (installé en editable) via Python.
    # Préfère `fsmods_gui.__version__` si disponible.
    $(
        $ver = & $python -c "import importlib; import fsmods_gui as pkg; print(getattr(pkg, '__version__', '0.0.0'))"; 
        "--file-version=$ver"
    ),
    $(
        $ver = & $python -c "import importlib; import fsmods_gui as pkg; print(getattr(pkg, '__version__', '0.0.0'))"; 
        "--product-version=$ver"
    ),
    "--file-description=Manage per-save mod profiles for Farming Simulator 25"
)

$openglSoftware = Join-Path $pysideDir "opengl32sw.dll"
if (Test-Path $openglSoftware) {
    # Fallback software OpenGL used by Qt on systems without compatible GPU drivers.
    $nuitkaArgs += "--include-data-files=$openglSoftware=opengl32sw.dll"
}

if (Test-Path $appIcon) {
    $nuitkaArgs += "--include-data-files=$appIcon=fsmods-gui.ico"
    $nuitkaArgs += "--windows-icon-from-ico=$appIcon"
}

if ($Standalone) {
    $nuitkaArgs += "--standalone"
}
else {
    $nuitkaArgs += "--onefile"
    # Python 3.14 + Nuitka 4.1.1 est encore expérimental; sans compression,
    # le binaire onefile est plus fiable sur certaines machines Windows.
    $nuitkaArgs += "--onefile-no-compression"
}

$nuitkaArgs += $entry

# ── Build ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==> Compilation de fsmods-gui.exe via Nuitka…" -ForegroundColor Green
Write-Host "    (la première compilation prend plusieurs minutes)" -ForegroundColor DarkGray
Write-Host "    Log build : $buildLog" -ForegroundColor DarkGray
Write-Host "    Report XML: $reportXml" -ForegroundColor DarkGray
$transcriptStarted = $false
try {
    Start-Transcript -Path $buildLog -Force | Out-Null
    $transcriptStarted = $true
}
catch {
    Write-Warning "Impossible d'ouvrir le log transcript: $buildLog"
}

& $python @nuitkaArgs

if ($transcriptStarted) {
    Stop-Transcript | Out-Null
}

if ($LASTEXITCODE -ne 0) {
    $crashInRoot = Join-Path $root "nuitka-crash-report.xml"
    if (Test-Path $crashInRoot) {
        $crashOut = Join-Path $logDir "nuitka-crash-$stamp.xml"
        Move-Item -Force $crashInRoot $crashOut
        Write-Host "Crash report déplacé vers: $crashOut" -ForegroundColor Yellow
    }
    Write-Error "Nuitka a échoué (code $LASTEXITCODE)."
    Pop-Location
    exit $LASTEXITCODE
}

# ── Résultat ──────────────────────────────────────────────────────────────────
$exe = Join-Path $outDir "fsmods-gui.exe"
if (Test-Path $exe) {
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host ""
    Write-Host "Build OK  ->  $exe  ($size Mo)" -ForegroundColor Green
}
else {
    Write-Warning "Build terminé mais l'exe est introuvable sous $outDir."
}

Pop-Location
