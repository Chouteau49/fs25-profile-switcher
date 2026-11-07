# build.ps1 — Construit fsmods-gui.exe pour Windows via Nuitka.
#
# Usage (depuis la racine du dépôt) :
#   .\packaging\build.ps1
#
# Options :
#   -NoClean      Réutilise le cache de compilation (build plus rapide)
#   -SkipTests    Ne lance pas les tests avant de compiler
#   -Standalone   Crée un dossier `fsmods_gui_entry.dist/` (lancement plus rapide) au lieu
#                 d'un .exe onefile autonome. Onefile par défaut.
#   -DebugConsole Active la console Windows pour voir les logs print()
#
# Le script installe les versions de requirements.lock, lance les tests avec le Python qui
# compile, puis compile dans dist_staging\ et vérifie que l'exe contient bien ce code. L'exe de
# dist\ n'est remplacé qu'à la toute fin : un build raté le laisse intact, et aucune appli
# ouverte n'est fermée.
#
# Pré-requis : .venv313 (Python 3.13, recommandé pour le onefile) ou .venv doit exister.
#
# Encodage : ce fichier doit rester en UTF-8 avec BOM, sans quoi PowerShell 5.1 le lit en
# ANSI et casse les accents.

param(
    [switch]$NoClean = $false,
    [switch]$SkipTests = $false,
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

$python = Join-Path $venv "Scripts\python.exe"
$entry = Join-Path $PSScriptRoot "fsmods_gui_entry.py"
$outDir = Join-Path $root "dist"
$stagingDir = Join-Path $root "dist_staging"
$lockFile = Join-Path $root "requirements.lock"
$pysideDir = Join-Path $venv "Lib\site-packages\PySide6"
$appIcon = Join-Path $PSScriptRoot "assets\fsmods-gui.ico"
$logDir = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "fs25-profile-switcher\build-logs"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$buildLog = Join-Path $logDir "nuitka-build-$stamp.log"
$reportXml = Join-Path $logDir "nuitka-report-$stamp.xml"

function Invoke-Native {
    # PowerShell 5.1 transforme chaque ligne de stderr en erreur quand la sortie est redirigée,
    # et l'avis de mise à jour de pip ou les infos de Nuitka suffisaient à tout arrêter avec
    # $ErrorActionPreference = "Stop". Seul le code de retour dit si la commande a échoué.
    param(
        [string]$File,
        [string[]]$Arguments,
        [string]$Failure,
        [string]$LogFile = ""
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($LogFile) {
            & $File @Arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $LogFile
        }
        else {
            & $File @Arguments 2>&1 | ForEach-Object { "$_" }
        }
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        throw "$Failure (code $code)."
    }
}

Push-Location $root
try {
    if (-not (Test-Path $python)) {
        throw "$venv introuvable. Crée-le avec Python 3.13 : py -3.13 -m venv .venv313"
    }
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    # ── Dépendances : exactement les versions figées ─────────────────────────
    Write-Host "Installation des versions de requirements.lock…" -ForegroundColor Cyan
    $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
    Invoke-Native $python @("-m", "pip", "install", "--quiet", "-r", $lockFile) "Installation des dépendances échouée"
    Invoke-Native $python @("-m", "pip", "install", "--quiet", "--no-deps", "-e", $root) "Installation du package échouée"

    # ── Version : une seule source, vérifiée ─────────────────────────────────
    $version = (& $python -c "import fsmods_gui; print(fsmods_gui.__version__)").Trim()
    $declared = (Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
    if ($version -ne $declared) {
        throw "Versions différentes : fsmods_gui/__init__.py = $version, pyproject.toml = $declared."
    }

    # ── Tests, avec le Python qui compile ────────────────────────────────────
    if (-not $SkipTests) {
        Write-Host "Tests avec $(& $python --version)…" -ForegroundColor Cyan
        Invoke-Native $python @("-m", "pytest", "-q", "-p", "no:cacheprovider") "Tests en échec : build annulé, l'exe existant est conservé"
    }

    # ── Nettoyage du dossier de travail (l'exe de dist\ reste intact) ─────────
    if ((-not $NoClean) -and (Test-Path $stagingDir)) {
        Remove-Item -Recurse -Force $stagingDir
    }
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    # Jamais de dossier de build ailleurs que dans dist_staging\ : le cache de zig vérifie
    # les fichiers embarqués à leur ancien chemin, et s'il les y retrouve il ressert l'ancien
    # code compilé (voir packaging/verify_build.py).
    foreach ($leftover in @("fsmods_gui_entry.build", "fsmods_gui_entry.onefile-build")) {
        $path = Join-Path $outDir $leftover
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
        }
    }

    # ── Arguments Nuitka ─────────────────────────────────────────────────────
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
        "--output-dir=$stagingDir",
        "--output-filename=fsmods-gui.exe",
        "--company-name=Julien Chouteau",
        "--product-name=FS25 Profile Switcher",
        "--file-version=$version",
        "--product-version=$version",
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
        # Sans compression : démarrage plus rapide, et plus fiable sur certaines machines.
        $nuitkaArgs += "--onefile-no-compression"
    }

    $nuitkaArgs += $entry

    # ── Build ────────────────────────────────────────────────────────────────
    Write-Host ""
    Write-Host "==> Compilation de fsmods-gui.exe $version via Nuitka…" -ForegroundColor Green
    Write-Host "    (la première compilation prend plusieurs minutes)" -ForegroundColor DarkGray
    Write-Host "    Log build : $buildLog" -ForegroundColor DarkGray
    Write-Host "    Report XML: $reportXml" -ForegroundColor DarkGray
    Invoke-Native $python $nuitkaArgs "Nuitka a échoué" $buildLog

    # ── L'exe contient-il bien ce qui vient d'être compilé ? ─────────────────
    $verifyArgs = @((Join-Path $PSScriptRoot "verify_build.py"), $stagingDir)
    if (-not $Standalone) {
        $verifyArgs += (Join-Path $stagingDir "fsmods-gui.exe")
    }
    Invoke-Native $python $verifyArgs "Build incohérent : l'exe existant est conservé"

    # ── Remplacement de l'exe, seulement maintenant que tout a réussi ────────
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    if ($Standalone) {
        $built = Join-Path $stagingDir "fsmods_gui_entry.dist"
        $target = Join-Path $outDir "fsmods_gui_entry.dist"
        if (Test-Path $target) {
            Remove-Item -Recurse -Force $target
        }
    }
    else {
        $built = Join-Path $stagingDir "fsmods-gui.exe"
        $target = Join-Path $outDir "fsmods-gui.exe"
    }
    if (-not (Test-Path $built)) {
        throw "Build terminé mais $built est introuvable."
    }
    try {
        Move-Item -Force $built $target
    }
    catch {
        throw "Impossible de remplacer $target : ferme l'appli lancée depuis dist\. Le nouveau build reste dans $built."
    }

    $size = [math]::Round((Get-ChildItem $target -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host ""
    Write-Host "Build OK  ->  $target  ($size Mo)" -ForegroundColor Green
}
catch {
    $crashInRoot = Join-Path $root "nuitka-crash-report.xml"
    if (Test-Path $crashInRoot) {
        $crashOut = Join-Path $logDir "nuitka-crash-$stamp.xml"
        Move-Item -Force $crashInRoot $crashOut
        Write-Host "Crash report déplacé vers: $crashOut" -ForegroundColor Yellow
    }
    Write-Host "ÉCHEC : $_" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
