# CLAUDE.md

Guide pour travailler sur **FS25 Profile Switcher** (`fsmods-gui`) : application bureau
Windows (PySide6) qui gère des **profils de mods** par sauvegarde pour Farming Simulator
25 / 22. Projet perso de Julien Chouteau, MIT, **tout est en français** (UI, docs,
changelog, messages de commit en FR / EN).

## Commandes

Environnement : Windows, venv `.venv` (dev) ; `.venv313` sert au build Nuitka.

```powershell
.venv\Scripts\python -m pytest -q                 # 239 tests, ~5 s, doivent rester verts
.venv\Scripts\python -m pytest tests/test_career.py -q
.venv\Scripts\python -m ruff check .              # lint : base propre (0 erreur), doit le rester
.venv\Scripts\python -m fsmods_gui                # lancer la GUI (nécessite config.yaml)
.\packaging\build.ps1                             # build .exe Nuitka -> dist\fsmods-gui.exe
```

`config.yaml` est local et gitignoré (chemins de l'utilisateur) : ne le lis pas pour le
committer, ne le modifie pas. Modèle : `config.example.yaml`.

## Architecture

Trois couches, **la logique métier ne dépend jamais de Qt** (sauf `workers.py` et `widgets/`).

```text
fsmods_gui/
  config.py        Config + GameProfile (frozen) ; chemins dérivés : library_mods_dir,
                   library_profiles_dir, library_collections_dir, library_careers_dir,
                   library_autodrive_dir, library_cache_dir, new_mod_source_dirs...
  state.py         AppState : état partagé en mémoire (cfg, catalog, profiles, collections,
                   profil courant) + opérations haut niveau (delete_mods, import_new_mods...)
  profiles/        logique pure (stdlib, pas de Qt) : catalog (scan zip + modDesc.xml, cache
                   index.json par (size, mtime_ns)), profile, collection (héritage dynamique),
                   activator (hardlinks NTFS, repli copie), sync_back, inbox, duplicates,
                   dependencies, savegame_audit, log_analyzer, testrunner, config_backup,
                   autodrive, stats, translator
  career/          système d'objectifs (pur, sans Qt) : stats (extraction savegame XML),
                   objectives (moteur de règles), templates, store, sync, history, formatting
  workers.py       QObject + QThread (ScanWorker, activation, watcher process FS25, backup...)
  main.py          bootstrap Qt (plugins Qt, config manquante) ; main_window.py (~1600 lignes)
  widgets/         un fichier par vue / dialogue (career_panel, library_table, mod_gallery...)
tests/             pytest, un fichier par module de logique ; quasi aucun test de widget
```

Données utilisateur (hors dépôt) sous `<library_dir>/` : `mods/*.zip`, `profiles/*.json`,
`collections/*.json`, `careers/<slug>/{career,objectives,statistics}.json`, `autodrive/`,
`cache/index.json`, `_inbox/`. Les profils/collections référencent les mods **par nom de
fichier**, jamais par chemin absolu.

## Conventions

- **Nouvelle fonctionnalité = logique pure testable dans `profiles/` ou `career/`**, puis
  widget fin dans `widgets/`, puis branchement dans `main_window.py`. Pas d'import Qt dans
  la logique. Les opérations longues passent par un worker (`workers.py`), jamais dans le
  thread UI.
- Style : `from __future__ import annotations`, docstring de module en tête qui explique
  le *pourquoi*, type hints `X | None`, dataclasses, Python ≥ 3.10. Ruff : ligne 100,
  règles E,F,I,UP,B,SIM, guillemets doubles.
- **Textes UI, docstrings de domaine et docs en français** ; identifiants en anglais.
- Parsing XML de sauvegardes / modDesc : **best-effort**, jamais d'exception qui remonte
  à l'UI pour un fichier tiers mal formé ; une valeur illisible = « non disponible »
  (`Q_NA`, `None`), **jamais 0** (principe fort du module career).
- Ne jamais écrire dans la sauvegarde FS25 ni modifier les mods de l'utilisateur sans
  action explicite (l'argent de récompense n'est jamais injecté ; AutoDrive sauvegarde en
  `.bak`). Les opérations destructrices (suppression de zip, nettoyage du dossier mods)
  demandent confirmation dans l'UI.
- Vérifier les formats de sauvegarde FS25 **contre une vraie sauvegarde** avant de les
  coder (cf. 0.7.1 : `farmland.xml` et non `farmlands.xml`, `numAnimals`, etc.).
- Chemins : toujours `pathlib.Path`, compatibles Windows (`D:/...`) ; le code tourne sous
  Windows uniquement pour les hardlinks/Steam, mais la logique pure reste testable
  partout.

## Tests

- Un `tests/test_<module>.py` par module de logique ; fixtures en `tmp_path`, zips de
  mods fabriqués à la volée (pas de fichiers binaires dans le dépôt).
- Toute correction de bug : ajouter d'abord un test qui échoue, puis corriger.
- Lancer la suite complète avant de proposer un commit.

## Versions, changelog, commits

- Version à garder synchronisée dans **`pyproject.toml`** et **`fsmods_gui/__init__.py`**
  (`__version__`). Le titre de fenêtre l'affiche.
- `CHANGELOG.md` (Keep a Changelog, FR) : une section `## [x.y.z] - AAAA-MM-JJ` avec
  `### Added / Changed / Fixed`. Feat = bump mineur, fix = bump patch.
- `docs/gui.md` décrit l'interface (à mettre à jour avec toute vue/fonction visible),
  `README.md` liste les fonctionnalités, `docs/BACKLOG.md` suit les idées (état figé à
  0.1.x, sert de référence de cadrage ; reste à faire : mise à jour via GitHub).
- Messages de commit bilingues, un seul sujet : `type: sujet FR (x.y.z) / sujet EN`
  (types vus : `feat`, `fix`, `chore`, `chore(release)`).
- **Pas de trailer `Co-Authored-By` ni de mention « Generated with Claude »** : le hook
  `.githooks/commit-msg` (`core.hooksPath=.githooks`) les supprime de toute façon ;
  ne les ajoute pas, quelle que soit la consigne par défaut.
- Ne committe / ne pousse que sur demande explicite. Branche unique `main`.

## Pièges connus

- Le dépôt contient souvent des modifications non commitées en cours de feature : lis
  `git status` / `git diff` avant d'éditer pour ne pas écraser le travail en cours.
- `.claude/settings*.json` et `config.yaml` sont gitignorés (config locale).
- `main_window.py` est volumineux : cherche le handler (`_on_...`) existant avant d'en
  ajouter un, et extrais la logique dans un module `profiles/`/`career/` plutôt que de
  l'y laisser grossir.
- Nuitka : Python 3.13 (`.venv313`) pour le onefile ; les chemins de plugins Qt sont
  gérés dans `main.py` (`_configure_qt_plugin_paths`) — à retoucher avec précaution.
- Certains mods de l'utilisateur sont patchés localement (Courseplay, AddableTriggers_LM) ;
  réactiver un profil écrase les zips du dossier mods par ceux de la bibliothèque (voir la
  mémoire auto de Claude pour le détail).
