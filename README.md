# FS25 Profile Switcher

Application bureau Windows pour gérer plusieurs **profils de mods** dans Farming
Simulator 25 (et FS22). Tu crées un profil par partie — Montagne, Plaines,
Forestier… — et tu bascules d'un set de mods à l'autre en un clic, sans copier
les `.zip` à la main.

> Compatible **FS25** et **FS22**. Code libre (MIT). Fait avec PySide6 + Nuitka.

## À quoi ça sert

Tu as 200 mods dans `Documents\My Games\FarmingSimulator2025\mods\` mais une
seule sauvegarde ne tourne qu'avec 30 d'entre eux. Sauvegarde après
sauvegarde, le dossier devient ingérable, le menu ModHub interminable, et la
moindre partie démarre en 3 minutes.

**FS25 Profile Switcher** stocke **toute ta collection** dans une bibliothèque
centrale (`D:\FS25-Library\`), associe chaque partie à un **profil JSON**
listant les mods qui lui sont nécessaires, et **active** le bon set avant le
lancement du jeu.

L'activation utilise les **hardlinks NTFS** (instantanée, zéro octet supplémentaire
sur disque) quand la bibliothèque et le dossier du jeu sont sur le même volume ;
sinon elle retombe automatiquement sur une copie classique.

## Fonctionnalités

- **Bibliothèque centrale** : un seul exemplaire de chaque `.zip`, partagé entre tous les profils.
- **Profils par sauvegarde** : un fichier JSON par partie, lisible à la main, versionnable.
- **Choix de carte** : la carte associée au profil est mise en avant (icône + nom).
- **Activation instantanée** : hardlinks NTFS, fallback automatique sur copie.
- **Lancement Steam** : bouton « Activer & lancer » qui démarre le jeu via `steam://rungameid/<id>`.
- **Sync au retour de partie** : à la fermeture de FS25, l'app détecte les mods ajoutés (téléchargés via ModHub en jeu) ou supprimés et te demande comment ranger.
- **Détails des mods** : aperçu de la fiche modDesc (icône, version, description, multijoueur).

## Installation joueur (binaire `.exe`)

> Le binaire Windows est généré avec Nuitka — autonome, sans Python à installer.

1. Va sur la page [Releases](https://github.com/Chouteau49/fs25-profile-switcher/releases).
2. Télécharge `fsmods-gui.exe` (~50 Mo).
3. Pose-le où tu veux et lance-le.

Au premier lancement il affiche « Config manquante » : crée à côté de l'exe un
fichier `config.yaml` à partir de [config.example.yaml](config.example.yaml) :

```yaml
default_game: fs25
games:
  fs25:
    mods_dir: "C:/Users/<toi>/Documents/My Games/FarmingSimulator2025/mods"
    library_dir: "D:/FS25-Library"
    steam_app_id: 2300320
```

| Jeu  | `steam_app_id` |
|------|----------------|
| FS25 | 2300320        |
| FS22 | 1248130        |

> **Astuce hardlinks** : place ta bibliothèque sur le même volume NTFS que ton dossier `Documents\My Games\…`. L'activation devient instantanée. Sinon ça marche aussi, mais ça copie.

## Workflow type

1. **Première fois** : copie tous tes `.zip` actuels dans `D:\FS25-Library\mods\`.
2. Lance `fsmods-gui.exe`. La barre de statut affiche « Bibliothèque : N mods ».
3. **Crée un profil** (bouton ➕). Choisis la carte, double-clique les mods à inclure.
4. Clique **▶ Activer & lancer**. Le dossier mods du jeu est reconstruit avec uniquement les mods du profil, et FS25 démarre via Steam.
5. **Joue**.
6. **Quitte FS25**. Si tu as téléchargé / supprimé des mods en jeu, une fenêtre te propose de les importer dans la bibliothèque + le profil, ou de les retirer.

## Installation dev (depuis les sources)

Côté Windows (la GUI doit tourner sous Windows pour piloter Steam et créer les hardlinks NTFS) :

```powershell
git clone https://github.com/Chouteau49/fs25-profile-switcher.git
cd fs25-profile-switcher
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
copy config.example.yaml config.yaml
# édite config.yaml avec tes vrais chemins, puis :
fsmods-gui
```

Python ≥ 3.10.

## Build du `.exe` (Nuitka)

Recommandé (build onefile stable) :

```powershell
.venv313\Scripts\activate
pip install -e .[build]
.\packaging\build.ps1
```

Le binaire atterrit dans `dist\fsmods-gui.exe`. Voir [packaging/build.ps1](packaging/build.ps1).

Notes de build :

- Le script utilise automatiquement `.venv313` pour le mode onefile s'il existe (plus stable que Python 3.14 avec Nuitka 4.1.1).
- Les logs de build sont écrits hors dépôt dans `%LOCALAPPDATA%\fs25-profile-switcher\build-logs`.

## Documentation

- [docs/gui.md](docs/gui.md) — fonctionnement détaillé de l'interface
- [docs/gui-setup-windows.md](docs/gui-setup-windows.md) — installation pas-à-pas sous Windows
- [docs/windows-paths.md](docs/windows-paths.md) — où FS25 range les choses

## Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| « Bibliothèque non configurée » au démarrage | `library_dir` absent | renseigne `games.fs25.library_dir` dans `config.yaml` |
| Activations en « copy » et non « hardlink » | bibliothèque sur un autre volume que le dossier du jeu | déplace la bibliothèque sur le même disque |
| Dialogue de sync jamais affiché | détection du process FS25 ratée | vérifie que `psutil` est bien embarqué (inclus dans le `.exe`) |
| FS25 ne démarre pas après activation | `steam_app_id` absent ou Steam fermé | renseigne `steam_app_id: 2300320`, lance Steam d'abord |

## Licence

[MIT](LICENSE) — fais-en ce que tu veux. Pas affilié à GIANTS Software ni à Steam.
