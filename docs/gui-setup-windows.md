# Installation pas-à-pas sous Windows

Ce document décrit deux scénarios :

1. **Utilisateur final** : tu veux juste utiliser l'app (`.exe` autonome).
2. **Développeur / contributeur** : tu veux lancer depuis les sources.

## 0. Pré-requis

| Élément | Comment vérifier | Action si manquant |
|---|---|---|
| Steam + FS25 (et/ou FS22) installés | n/a | n/a |
| Le dossier `Documents\My Games\FarmingSimulator2025\mods\` existe | s'il y a déjà des `.zip` dedans, OK | lance FS25 une fois — il crée le dossier au premier démarrage |
| Python 3.10+ (mode dev uniquement) | `python --version` | <https://www.python.org/downloads/> (cocher « Add to PATH ») |

---

## A. Mode utilisateur final (`.exe`)

### 1. Télécharger le binaire

Va sur [Releases](https://github.com/Chouteau49/fs25-profile-switcher/releases)
et récupère `fsmods-gui.exe` (~50 Mo). Pose-le où tu veux (par exemple
`D:\Tools\fsmods-gui\fsmods-gui.exe`).

### 2. Créer un `config.yaml` à côté de l'exe

Crée un fichier `config.yaml` **dans le même dossier que l'exe**, avec ce contenu (adapte les chemins) :

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

> **Astuce hardlinks** : `library_dir` doit être sur le **même volume NTFS** que `mods_dir`. Sur ce volume l'activation est instantanée ; sinon elle copie (toujours fonctionnel mais plus lent).

### 3. Peupler la bibliothèque

Copie ou déplace tous tes `.zip` existants dans `D:\FS25-Library\mods\` (ou
le `library_dir` choisi). Ne garde qu'**une version** par mod.

### 4. Lancer

Double-clique sur `fsmods-gui.exe`. La barre de statut doit afficher
« Bibliothèque : N mods ».

---

## B. Mode développeur (depuis les sources)

### 1. Récupérer le code

```powershell
git clone https://github.com/Chouteau49/fs25-profile-switcher.git
cd fs25-profile-switcher
```

### 2. Venv Windows

PySide6 + psutil doivent être installés côté Windows (pas dans WSL), pour
piloter Steam et créer des hardlinks NTFS :

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install -e .[dev]
```

L'installation prend ~1 min (PySide6 fait ~70 Mo).

### 3. Config

```powershell
copy config.example.yaml config.yaml
notepad config.yaml
```

Adapte `mods_dir`, `library_dir`, `steam_app_id`. Le format est documenté
dans [config.example.yaml](../config.example.yaml).

### 4. Peupler la bibliothèque

Copie tous tes `.zip` actuels dans le `library_dir` choisi.

### 5. Lancer

```powershell
fsmods-gui
```

ou pour voir les traces en console :

```powershell
python -m fsmods_gui
```

### Ce qu'il faut vérifier visuellement

- [ ] La fenêtre s'ouvre sans erreur
- [ ] Barre de statut : « Bibliothèque : N mods »
- [ ] La table de droite affiche les mods (Icône / Fichier / Titre / Version / Marque / Catégorie / Auteur)
- [ ] Le filtre de recherche réduit la liste à la volée
- [ ] Les icônes des mods s'affichent (DDS pris en charge via Pillow)

### Création d'un premier profil

- [ ] Bouton **➕ Nouveau** → saisir « Test » → un `test.json` apparaît dans `<library_dir>/profiles/`
- [ ] Sélectionner une carte dans le combo
- [ ] Double-cliquer 2-3 mods → ils apparaissent à droite
- [ ] Fermer/rouvrir la GUI → le profil est toujours là

### Activation + lancement

- [ ] Cliquer **▶ Activer & lancer**
- [ ] Fenêtre de progression → message « N mod(s) activé(s) (X hardlinks, Y copies) »
- [ ] Le dossier `Documents\…\FarmingSimulator2025\mods\` contient uniquement les `.zip` du profil
- [ ] Vérifier qu'il s'agit de hardlinks avec `fsutil hardlink list <file>` (au moins 2 chemins listés)
- [ ] Steam lance FS25

### Synchronisation à la fermeture

- [ ] Quitte FS25
- [ ] 3-5 s après, un dialogue « Synchronisation de fin de partie » s'ouvre s'il y a des changements
- [ ] Sinon : barre de statut « Aucune différence détectée »

---

## C. Build du `.exe` (Nuitka)

Build onefile recommandé (stable) :

```powershell
.venv313\Scripts\activate
pip install -e .[build]
.\packaging\build.ps1
```

Le binaire `fsmods-gui.exe` atterrit dans `dist\`. Voir [packaging/build.ps1](../packaging/build.ps1)
pour les options (clean, install, etc.).

Les logs et rapports Nuitka sont générés hors dépôt dans :

`%LOCALAPPDATA%\fs25-profile-switcher\build-logs`

---

## D. Dépannage rapide

Lance la GUI **depuis cmd** (pas un raccourci) pour voir la trace d'erreur :

```powershell
.venv\Scripts\activate
python -m fsmods_gui
```

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| « Config manquante » | pas de `config.yaml` à côté de l'exe (ou à la racine du dépôt) | copier `config.example.yaml` en `config.yaml` |
| « Bibliothèque non configurée » | `library_dir` non renseigné | éditer `config.yaml` |
| Tout en « copy » et rien en « hardlink » | volumes différents | déplacer la bibliothèque sur le même disque que `Documents\My Games\` |
| FS25 ne démarre pas après activation | Steam fermé ou `steam_app_id` manquant | lancer Steam, vérifier l'id (FS25 = 2300320) |
| Dialogue de sync absent | détection du process FS25 ratée | vérifier le nom du process avec le Gestionnaire des tâches (`FarmingSimulator2025.exe`) |
