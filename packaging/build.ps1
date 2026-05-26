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
#
# Pré-requis : .venv doit exister (python -m venv .venv) et contenir les deps
#              du projet + nuitka. Lance avec -Install la première fois.

param(
    [switch]$Clean      = $true,
    [switch]$NoClean    = $false,
    [switch]$Install    = $false,
    [switch]$Standalone = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Chemins ──────────────────────────────────────────────────────────────────
$root   = Split-Path $PSScriptRoot -Parent
$venv   = Join-Path $root ".venv"
$pip    = Join-Path $venv "Scripts\pip.exe"
$python = Join-Path $venv "Scripts\python.exe"
$entry  = Join-Path $PSScriptRoot "fsmods_gui_entry.py"
$outDir = Join-Path $root "dist"

Push-Location $root

# ── Vérification du venv ─────────────────────────────────────────────────────
if (-not (Test-Path $python)) {
    Write-Error ".venv introuvable. Crée-le avec : python -m venv .venv ; .venv\Scripts\activate ; pip install -e .[build]"
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

# ── Arguments Nuitka ─────────────────────────────────────────────────────────
$nuitkaArgs = @(
    "-m", "nuitka",
    "--assume-yes-for-downloads",          # télécharge ccache / dépendant-walker silencieusement
    "--windows-console-mode=disable",      # pas de console au lancement
    "--enable-plugin=pyside6",
    "--include-package=fsmods_gui",
    "--include-package=psutil",
    "--include-package=yaml",
    "--include-package=PIL",
    "--output-dir=$outDir",
    "--output-filename=fsmods-gui.exe",
    "--company-name=Julien Chouteau",
    "--product-name=FS25 Profile Switcher",
    "--file-version=0.1.0",
    "--product-version=0.1.0",
    "--file-description=Manage per-save mod profiles for Farming Simulator 25"
)

if ($Standalone) {
    $nuitkaArgs += "--standalone"
} else {
    $nuitkaArgs += "--onefile"
}

$nuitkaArgs += $entry

# ── Build ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==> Compilation de fsmods-gui.exe via Nuitka…" -ForegroundColor Green
Write-Host "    (la première compilation prend plusieurs minutes)" -ForegroundColor DarkGray
& $python @nuitkaArgs

if ($LASTEXITCODE -ne 0) {
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
} else {
    Write-Warning "Build terminé mais l'exe est introuvable sous $outDir."
}

Pop-Location
