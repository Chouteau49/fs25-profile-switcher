# GUI — gestionnaire de profils

L'interface graphique `fsmods-gui` (du projet **fs25-profile-switcher**) permet de gérer une bibliothèque centrale de mods Farming Simulator et d'activer un ensemble différent par partie (montagne, plaines, no man's land, etc.) sans relancer manuellement le copier-coller.

## Vue d'ensemble

```
┌──────────────────┬──────────────────────────────────────────────┐
│ ⌂ Accueil        │  Tes parties                  [+ Nouveau profil]│
│ ≡ Bibliothèque 2 │  ┌ 2 mods attendent d'être rangés  [Ranger] ┐  │
│ ◎ Carrière       │  ┌──────────────┬───────────────────────────┐ │
│ ∿ Diagnostic     │  │ vignette     │ DERNIÈRE PARTIE · hier     │ │
│                  │  │ de la carte  │ Montagne   142 mods        │ │
│ PROFILS   + ⧉ 🗑 │  │              │ [▶ Jouer] [Modifier]       │ │
│  Montagne        │  └──────────────┴───────────────────────────┘ │
│  Plaines         │  Autres profils : [Plaines ▶] [No Man's ▶] [+] │
│ COLLECTIONS + ⧉ 🗑│                          ┌ Mod retiré. Annuler ┐│
│ ↻  ⚙  🎨          │                                               │
├──────────────────┴──────────────────────────────────────────────┤
│ ● FS25 fermé · Dans le dossier du jeu : Montagne · 812 mods       │
└───────────────────────────────────────────────────────────────────┘
```

- **Accueil** (au démarrage) : la dernière partie jouée en grand, puis les autres profils en cartes. Chaque carte a son bouton **Jouer** (active les mods du profil puis lance FS25) et **Modifier** (ouvre l'éditeur du profil). Pendant l'activation, la carte affiche la progression ; pendant la partie, son bouton indique « En cours » et les autres sont désactivés.
- **Barre latérale** : quatre espaces.
  - **Accueil**.
  - **Bibliothèque** : les mods **à ranger** (téléchargés via ModHub, déposés dans `_inbox`, ou mis à l'abri lors d'une activation). La pastille compte les zips en attente dans `_inbox`.
  - **Carrière** : objectifs du profil choisi. Changer de profil dans la liste reste sur la Carrière.
  - **Diagnostic** : Log FS25, Audit sauvegarde, Doublons, Routes AutoDrive, Tester les mods, Statistiques.
- **Éditeur d'un profil** : ouvert depuis une carte de l'accueil ou en cliquant un profil (ou une collection) dans la liste latérale.
- **Notifications** (en bas à droite) : les informations s'affichent sans bloquer et disparaissent seules. Après avoir retiré ou exclu un mod dans l'éditeur, **Annuler** remet le profil comme avant.
- **Listes Profils et Collections** : un fichier JSON par profil sous `library/profiles/`. Les boutons + / dupliquer / supprimer sont à droite de chaque titre.
- **Éditeur** : choisir la carte (un mod de carte, ou une carte officielle du jeu / d'un DLC, avec sa vignette), ajouter / retirer des mods. Les modifications sont sauvegardées automatiquement.
- **Bas de la barre latérale** : rescanner la bibliothèque, **Outils** (exporter / importer la config, journal de l'appli) et **Thème**.
- **Barre de session** (bas de la fenêtre) : jeu fermé / en cours / activation, profil installé dans le dossier du jeu (le dernier joué), nombre de mods, état de la sauvegarde de la config, et les messages passagers à droite.
- **Au démarrage**, l'application sélectionne le dernier profil joué (activé).
- **Jouer · <profil>** (ex-« Activer & lancer ») : remplace le contenu de `Documents\My Games\FarmingSimulator2025\mods\` par les mods du profil (hardlinks NTFS instantanés), puis démarre FS25 via Steam. Un zip du dossier du jeu absent de la bibliothèque ou différent de sa copie n'est jamais supprimé : il est déplacé dans `_inbox` et « Nouveaux mods » propose de l'importer. L'activation est refusée tant que le jeu tourne.
- **Thème** (bas de la barre latérale) : clair, sombre ou « comme Windows » (suit le thème du système). Le choix est mémorisé.
- **Journal de l'appli** (Outils, bas de la barre latérale) : ouvre `%LOCALAPPDATA%\fs25-profile-switcher\logs`. `fsmods-gui.log` garde les erreurs internes, `crash.log` les plantages durs. C'est le fichier à regarder (ou à envoyer) quand l'appli se comporte mal.
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

## Carrière / objectifs

L'espace **Carrière** transforme un profil en suivi de carrière : tu choisis la sauvegarde associée (détectée automatiquement si la carte du profil ne correspond qu'à une sauvegarde), puis tu ajoutes un **modèle** (« Ajouter un modèle… ») ou tes propres objectifs. Avec une carte à **plusieurs fermes**, choisis la « Ferme suivie » et rattache chaque objectif (ou modèle) à la ferme voulue : chacun est mesuré sur les statistiques de sa ferme. Changer de ferme suivie ne déplace rien : les objectifs sans ferme précise restent sur celle où ils étaient mesurés (📌), et l'historique affiché est celui de la ferme suivie. Les objectifs sont recalculés à chaque ouverture de l'espace, au clic sur « Synchroniser » et à la fermeture du jeu.

- **Fiabilité des valeurs** : 🟢 lue dans la sauvegarde · 🟠 calculée / estimée (ex. surface lue sur la carte, patrimoine = argent − emprunt + prix d'achat, sans la valeur des terres) · 🔵 saisie à la main · 🔴 non disponible.
- **Surface possédée** : calculée depuis la carte des parcelles du jeu (cartes de base et cartes mods). Pour une carte DLC chiffrée (ex. Kinlaig), « 🌾 Surfaces des parcelles… » liste tes parcelles : tape une fois la surface de chacune (visible sur la carte en jeu, virgule ou point, Entrée pour passer à la suivante), le total se calcule en direct. Vide = à saisir, `0` = vraie valeur. Tant qu'une parcelle manque, le tableau de bord affiche le minimum connu (`≥ 8,5 ha`), la synchronisation nomme les parcelles restantes et les objectifs de surface restent « non disponible ».
- **Modes** (par profil) : désactivé · objectifs seuls · récompenses manuelles · récompenses obligatoires.
- **Récompenses** : l'application n'écrit jamais dans la sauvegarde. Pour une récompense en argent, ajoute l'argent en jeu (PowerTools, F12) puis coche la case **💰 Versé** de l'objectif (ou « Attribuer la récompense » en mode récompenses). Un objectif déjà atteint au premier calcul est marqué terminé sans récompense due, mais tu peux quand même cocher « Versé ».
- **Données** : `<library>/careers/<profil>/career.json`, `objectives.json`, `statistics.json` — indépendantes de la sauvegarde. `objectives.json` est lisible/éditable à la main (arbres de conditions `and` / `or` / `not`, prérequis `requires`).

## Sauvegarder la config (Google Drive, NAS, ou les deux)

Seuls les petits fichiers JSON (profils, collections, carrières) sont sauvegardés — jamais les mods. Dans `config.yaml` :

```yaml
games:
  fs25:
    config_backup_dirs:
      - "G:/Mon Drive/FS25-config"     # Google Drive pour ordinateur (dossier synchronisé)
      - "//nas/backup/FS25-config"     # partage réseau du NAS (ou lecteur mappé Z:/…)
```

Chaque cible reçoit un miroir à jour + des instantanés ZIP (`snapshots/`, 10 conservés). Une cible indisponible est signalée dans la barre de statut sans bloquer les autres. Pour restaurer : « 📥 Importer config » sur un ZIP de `snapshots/` (ou copie manuelle des JSON du miroir). Évite de jouer la même carrière sur deux PC en même temps : le dernier à écrire gagne.

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

Les champs `library_dir` et `steam_app_id` sont obligatoires (le premier pour stocker bibliothèque + profils, le second pour le bouton « Jouer »).

| Jeu  | `steam_app_id` |
|------|----------------|
| FS25 | 2300320        |
| FS22 | 1248130        |

## Workflow type

1. **Première fois** : copie tous tes `.zip` actuels dans `D:\FS25-Library\mods\`.
2. Lance `fsmods-gui`. Un message « Bibliothèque : N mods » apparaît dans la barre de statut.
3. **Crée un profil** (bouton ➕). Choisis la carte dans la liste déroulante, double-clique les mods à ajouter depuis la table de gauche.
4. Clique **▶ Jouer**. Le dossier `mods/` du jeu est vidé puis re-rempli avec uniquement les mods du profil, et FS25 démarre via Steam.
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
| Profils invisibles après changement de bibliothèque | la GUI lit `library/profiles/` du jeu courant | bouton « Rescanner » en bas de la barre latérale |
