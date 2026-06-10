# Changelog

## [0.1.8] - 2026-06-10

### Added

- **Détection des dépendances (backlog #3)** : `modDesc.xml` `<dependencies>` est désormais parsé dans le catalogue (`CatalogEntry.requires`). Lors de l'ajout d'un mod au profil, les dépendances requises présentes dans la bibliothèque sont proposées à l'ajout (fermeture transitive, gestion des cycles), et celles introuvables sont signalées. Logique pure dans `fsmods_gui/profiles/dependencies.py`.
- Les dépendances d'un mod sont affichées dans la fenêtre de détails du mod.

### Build / Release

- Version passée de `0.1.7` à `0.1.8`.
- Cache du catalogue : `CACHE_SCHEMA_VERSION` 19 → 20 (re-scan automatique pour récupérer les dépendances).

## [0.1.7] - 2026-06-10

### Added

- **Détection des doublons (backlog #2)** : nouveau bouton « 🧬 Doublons » qui liste les mods en double dans la bibliothèque, regroupés par identité — soit par nom de fichier (copies/redownloads comme `FS25_Mod (1).zip`, suffixes de version) soit par même titre + auteur. Logique pure dans `fsmods_gui/profiles/duplicates.py`.
- **Analyse du log FS25 (backlog #1)** : à la fermeture du jeu, le `log.txt` de la session est analysé et un tableau présente les problèmes (erreurs Lua, mods introuvables, conflits, doublons, XML, chargement) avec sévérité, type, mod concerné et **message traduit en français**. Filtrable par type, copiable. Accessible aussi manuellement via « 📋 Analyser le log FS25 ». Logique pure dans `fsmods_gui/profiles/log_analyzer.py`.
- Ajout d'une propriété `CatalogEntry.mod_id` (= nom du `.zip` sans extension = identité FS du mod), réutilisable pour la résolution de dépendances et la détection de doublons.

### Build / Release

- Version passée de `0.1.6` à `0.1.7`.

## [0.1.6] - 2026-06-10

### Added

- Added a profile-aware library filter with 3 modes: "Tous les mods", "Non presents dans le profil", and "Presents dans le profil".
- Added automatic default filtering to show mods not already present in the selected profile.

### Changed

- Library filtering now combines profile presence mode with existing search/category/brand/type filters.

### Build / Release

- Project version bumped from `0.1.5` to `0.1.6` in `pyproject.toml` and `fsmods_gui.__version__`.

## [0.1.5] - 2026-06-10

### Added

- Added application icon (fsmods-gui.ico) with 7 resolutions (16-256px).
- Added visible app version in window title and status bar.
- Added launch.bat for quick testing.
- Added -DebugConsole parameter to build.ps1 for troubleshooting.

### Fixed

- **Critical fix:** Catalog (index.json) is now properly saved after importing updated mods from game. Previously, updated .zip files were copied to library but the catalog wasn't persisted, causing the same updates to be proposed again on next launch.
- Fixed end-of-session update detection when mods are activated via hardlinks by using a pre-launch hash snapshot and post-game comparison.
- Fixed editable package version sync in build script to ensure __version__ matches source code.

### Changed

- Build script now auto-reinstalls editable package before Nuitka compilation.
- Build script now kills running fsmods-gui processes before compilation to avoid file locks.

### Build / Release

- Project version bumped from `0.1.3` to `0.1.5` in `pyproject.toml` and `fsmods_gui.__version__`.

## 0.1.2 - 2026-05-27

### Added

- Added post-session detection for mods updated in-game (ModHub) by comparing game zips against library zips.
- Added dedicated sync dialog actions to import updated mods back into the library after game exit.

### Changed

- Updated README feature and workflow descriptions to include end-of-session handling of in-game mod updates.

### Build / Release

- Project version bumped from `0.1.1` to `0.1.2` in `pyproject.toml`.
- Updated packaged executable metadata version in `packaging/build.ps1` to `0.1.2`.

## 0.1.1 - 2026-05-26

### Added

- Added robust Qt runtime plugin path configuration at startup to reduce platform plugin lookup failures in packaged builds.
- Added support in `packaging/build.ps1` for using `.venv313` in onefile builds (`-UsePy313`), with automatic preference for `.venv313` when available.
- Added structured Nuitka build reporting to `%LOCALAPPDATA%/fs25-profile-switcher/build-logs`.

### Changed

- Updated onefile build strategy to use `--onefile-no-compression` for improved stability on the current toolchain.
- Updated packaging version metadata in `packaging/build.ps1` to `0.1.1`.
- Updated documentation to reflect the recommended stable build flow (`.venv313`) and external build log location.

### Fixed

- Fixed onefile packaging reliability issues observed with the previous setup.
- Improved handling of missing `config.yaml` by searching multiple locations and providing clearer diagnostics.

### Build / Release

- Project version bumped from `0.1.0` to `0.1.1` in `pyproject.toml`.
- Expanded `.gitignore` for local build artifacts and environments:
  - `dist_*/`
  - `.venv313/`
  - existing Nuitka local log patterns retained.
