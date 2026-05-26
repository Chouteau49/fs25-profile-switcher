# GUI — gestionnaire de profils

L'interface graphique `fsmods-gui` (du projet **fs25-profile-switcher**) permet de gérer une bibliothèque centrale de mods Farming Simulator et d'activer un ensemble différent par partie (montagne, plaines, no man's land, etc.) sans relancer manuellement le copier-coller.

## Vue d'ensemble

```
┌─ Profils ───────┬─ Détails du profil ───────────────────────┐
│ ► Montagne      │  ▶ Activer & lancer FS25                  │
│   Plaines       │  Nom    : Montagne                        │
│   No Man's Land │  Carte  : FS25_Alpenland                  │
│   + Nouveau     │  Notes  : …                               │
│                 │  ─────────────────────────────────────────│
│                 │  Bibliothèque    │   Mods du profil       │
│                 │  (table + filtre)│   (sélection courante) │
└─────────────────┴───────────────────────────────────────────┘
```

- **Profils** (gauche) : la liste de tes parties. Un fichier JSON par profil sous `library/profiles/`.
- **Éditeur** (droite) : choisir la carte, ajouter / retirer des mods. Les modifications sont sauvegardées automatiquement.
- **Activer & lancer FS25** : remplace le contenu de `Documents\My Games\FarmingSimulator2025\mods\` par les mods du profil (hardlinks NTFS instantanés), puis démarre FS25 via Steam.
- **Synchronisation auto** : à la fermeture de FS25, un dialogue liste les mods ajoutés (téléchargés via ModHub en jeu) ou retirés, et te demande comment les ranger.

## Bibliothèque centrale

Toute ta collection de `.zip` vit dans un dossier configurable, **séparé du dépôt** et **séparé du dossier `mods/` du jeu**. Layout :

```
D:\FS25-Library\
├── mods\          ← tous tes .zip (1 exemplaire chacun)
├── profiles\      ← un fichier .json par partie
└── cache\         ← cache du parsing modDesc.xml (régénéré automatiquement)
```

> Pour profiter des **hardlinks** (instantanés, sans copie ni occupation disque) ce dossier doit être sur le **même volume NTFS** que `Documents\My Games\FarmingSimulator2025\`. Sinon l'activation fonctionne quand même, mais retombe sur des copies (plus lent).

## Installation

### Pour développer ou tester (depuis le dépôt)

Sous Windows (PowerShell ou cmd) — la GUI doit tourner côté Windows pour piloter Steam et créer les hardlinks NTFS :

```powershell
git clone https://github.com/Chouteau49/fs25-profile-switcher.git
cd fs25-profile-switcher
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
fsmods-gui
```

Pour un utilisateur final, télécharge plutôt le `.exe` depuis la page [Releases](https://github.com/Chouteau49/fs25-profile-switcher/releases).

### Configuration

Copie `config.example.yaml` en `config.yaml` (à la racine du dépôt, ou à côté du `.exe` pour la version packagée) et adapte :

```yaml
default_game: fs25
games:
  fs25:
    mods_dir: "C:/Users/<toi>/Documents/My Games/FarmingSimulator2025/mods"
    library_dir: "D:/FS25-Library"
    steam_app_id: 2300320
```

Les champs `library_dir` et `steam_app_id` sont obligatoires (le premier pour stocker bibliothèque + profils, le second pour le bouton « Activer & lancer »).

| Jeu  | `steam_app_id` |
|------|----------------|
| FS25 | 2300320        |
| FS22 | 1248130        |

## Workflow type

1. **Première fois** : copie tous tes `.zip` actuels dans `D:\FS25-Library\mods\`.
2. Lance `fsmods-gui`. Un message « Bibliothèque : N mods » apparaît dans la barre de statut.
3. **Crée un profil** (bouton ➕). Choisis la carte dans la liste déroulante, double-clique les mods à ajouter depuis la table de gauche.
4. Clique **▶ Activer & lancer FS25**. Le dossier `mods/` du jeu est vidé puis re-rempli avec uniquement les mods du profil, et FS25 démarre via Steam.
5. **Joue**. Tu peux télécharger des mods en jeu via ModHub.
6. **Quitte FS25**. Quelques secondes plus tard, un dialogue apparaît :
   - les mods téléchargés en jeu → "Importer dans la bibliothèque + ce profil" (recommandé)
   - les mods que tu as supprimés du dossier du jeu → "Retirer du profil" (recommandé)

## Empaquetage en `.exe` (optionnel)

Pour distribuer un `.exe` Windows autonome (sans dépendance à Python installé) :

```powershell
.venv\Scripts\activate
pip install -e .[build]
.\packaging\build.ps1
```

Le binaire `fsmods-gui.exe` atterrit dans `dist\`. Voir [`packaging/build.ps1`](../packaging/build.ps1).

## Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| « Bibliothèque non configurée » au démarrage | `library_dir` absent du `config.yaml` | renseigne `games.fs25.library_dir` |
| Toutes les activations affichent « copy » au lieu de « hardlink » | bibliothèque sur un autre volume que le dossier du jeu | déplace la bibliothèque sur le même disque que `Documents\…\FarmingSimulator2025\` |
| Le dialogue de synchronisation ne s'ouvre jamais | `psutil` non installé ou nom du process non détecté | `pip install psutil` (déjà inclus dans les dépendances) |
| FS25 ne démarre pas après l'activation | `steam_app_id` absent ou Steam non lancé | renseigne `steam_app_id: 2300320`, lance Steam d'abord |
| Profils invisibles après changement de bibliothèque | la GUI lit `library/profiles/` du jeu courant | bouton « 🔄 Rescanner la bibliothèque » dans la barre d'outils |
