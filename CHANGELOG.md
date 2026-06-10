# Changelog

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
