# Changelog

## [0.14.0] - 2026-11-09

Cinquième étape de la refonte : Carrière, Bibliothèque et Diagnostic.

### Added

- **Diagnostic en cartes** : l'espace s'ouvre sur un tableau des six outils (Log FS25, Audit de sauvegarde, Doublons, Routes AutoDrive, Tester les mods, Statistiques), chacun avec sa description et un état en une ligne (« Dernière partie : 2 erreurs », « 4 groupes (9 fichiers) », « 300 mods sur 812 ne servent à aucun profil »…). « Ouvrir » affiche l'outil ; « Tous les outils » revient au tableau.
- **Bibliothèque en trois vues** : **À ranger**, **Tous les mods** (la bibliothèque complète : recherche, filtres, détails, suppression, ajout à une collection) et **Collections** (une carte par collection avec son nombre de mods et les profils qui l'utilisent, **Modifier**, **Nouvelle collection**).

### Changed

- **Carrière en deux vues** : **Tableau de bord** (chiffres clés, progression, récompenses à verser, historique, saisie manuelle et surfaces des parcelles) et **Objectifs (N)** (filtres, tableau, modèles et objectifs perso). La vue choisie est retrouvée en revenant sur la carrière.
- Carrière : sauvegarde, ferme suivie et mode regroupés dans une carte ; **Synchroniser** à côté du titre.
- Chiffres clés de la carrière : nom lisible même sans sauvegarde associée (au lieu de `netWorth`, `money`…), valeur en grand, fiabilité indiquée par un point de couleur et un mot (Automatique, Calculée, Manuelle, Non disponible) au lieu d'emojis.

### Fixed

- Test des workers instable : il attendait 300 ms au lieu d'attendre la fin réelle du thread, et échouait au hasard sur une machine chargée.

## [0.13.0] - 2026-11-09

Quatrième étape de la refonte : la page d'un profil.

### Added

- **Glisser-déposer** : un mod (ou plusieurs) se glisse de la bibliothèque vers le contenu du profil ou de la collection.
- **Encadrés dans la page** à la place des fenêtres :
  - après l'ajout d'un mod qui en exige d'autres, « X a besoin de Y, présent dans ta bibliothèque » avec **Ajouter aussi** ;
  - dépendances introuvables, signalées en rouge (à télécharger puis rescanner) ;
  - mods du profil absents de la bibliothèque, avec **Retirer du profil** (avant, on ne l'apprenait qu'au lancement).
  Chaque encadré peut être écarté.

### Changed

- **Page Profil réorganisée** :
  - en-tête en carte : vignette de la carte du jeu, nom modifiable sur place, choix de la carte, notes, et à droite **Jouer** et **Dupliquer** ;
  - onglets **Mods (N)** et **Collections héritées (N)** ;
  - le contenu du profil et la bibliothèque sont **côte à côte** (fini la bascule « Contenu / Bibliothèque » qui masquait l'un ou l'autre).
- Une collection ouverte dans l'éditeur n'affiche ni carte, ni Jouer, ni l'onglet des collections héritées.
- Bibliothèque : recherche et filtres sur deux rangées, lisibles même dans le panneau latéral.
- Vue « À ranger » : boutons sur deux rangées.

### Fixed

- **La fenêtre s'élargissait toute seule** en ouvrant certains écrans (une rangée de boutons ou de filtres trop longue imposait sa largeur). Un test vérifie désormais qu'aucun écran n'exige plus de 1280 px.

## [0.12.0] - 2026-11-09

Troisième étape de la refonte : un vrai écran d'accueil, et plus de fenêtres qui
interrompent pour rien.

### Added

- **Accueil** (écran de démarrage) : la dernière partie en grand (vignette de la carte, nombre de mods, collections, date) avec **Jouer** et **Modifier le profil**, puis les autres profils en cartes, chacune avec son bouton **Jouer**, et une carte « Nouveau profil ». Un profil sans image de carte reçoit une vignette de champs stylisés, propre à son nom.
- **Bandeau « mods à ranger »** sur l'accueil, qui mène à Bibliothèque.
- **Notifications** en bas à droite : elles remplacent les 15 fenêtres d'information (activation réussie, mods ajoutés, export / import terminé…) et disparaissent seules.
- **« Annuler »** après avoir retiré ou exclu un mod (ou une carte) dans l'éditeur d'un profil ou d'une collection.

### Changed

- **Activation sans fenêtre modale** : la progression s'affiche dans la carte du profil (barre et étape en cours) et dans la barre de session ; les autres boutons Jouer sont désactivés pendant l'activation puis pendant la partie (« En cours »).
- La fin d'activation est résumée dans une notification ; si des mods du dossier du jeu ont été mis à l'abri, elle propose **Ranger**.
- L'éditeur d'un profil ne figure plus dans la barre latérale : on l'ouvre depuis une carte de l'accueil ou depuis la liste des profils.

### Fixed

- Liste des cartes : les cartes officielles affichaient leur nature en double (« Riverbend Springs (carte officielle) · carte officielle »), régression de 0.10.0.
- Feuille de style : la hauteur minimale imposée à tous les boutons écrasait les hauteurs voulues (gros bouton Jouer, carte « Nouveau profil »).

## [0.11.0] - 2026-11-09

Deuxième étape de la refonte : une vraie navigation à la place des neuf onglets.

### Added

- **Barre latérale** avec quatre espaces : **Profils** (éditeur), **Bibliothèque** (mods à ranger), **Carrière**, **Diagnostic** (Log FS25, Audit sauvegarde, Doublons, Routes AutoDrive, Tester les mods, Statistiques en sous-onglets).
- **Pastille « à ranger »** sur Bibliothèque : nombre de zips en attente dans `_inbox`, mise à jour après un scan, une activation, un import et la fermeture du jeu.
- **Barre de session** permanente en bas : jeu fermé / en cours / activation, profil installé dans le dossier du jeu, nombre de mods de la bibliothèque, état de la dernière sauvegarde de la config (détail en info-bulle). Les messages passagers s'affichent à sa droite.

### Changed

- Les listes **Profils** et **Collections** passent dans la barre latérale ; leurs boutons (nouveau, dupliquer, supprimer) deviennent de petites icônes à droite de chaque titre.
- La barre d'outils disparaît : rescanner, **Outils** (exporter / importer la config, journal de l'appli) et **Thème** sont en bas de la barre latérale.
- Choisir un profil ouvre son éditeur ; depuis Carrière, l'écran reste sur la carrière du profil choisi.
- La vue « À ranger » réserve une largeur minimale à son panneau de droite (profils / collections cibles), qui était écrasé.

## [0.10.0] - 2026-11-09

Première étape de la refonte de l'interface : même organisation des écrans, mais un
habillage cohérent et lisible, en clair comme en sombre.

### Added

- **Thème clair, sombre ou « comme Windows »** (bouton **Thème** de la barre d'outils, choix mémorisé). En mode « comme Windows », l'appli suit le changement de thème du système sans redémarrer.
- **Icônes vectorielles** à la place des emojis sur les boutons, onglets, menus et cartes de mods : rendu net à toutes les échelles d'affichage, couleur adaptée au thème.
- Cartes de mods : pastilles « Carte », « Hérité », « Exclu » à la place des emojis ; un mod sans image affiche un pictogramme neutre.

### Changed

- **Une palette unique** (`fsmods_gui/theme.py`) pour toute l'appli : fond, cartes, textes secondaires, couleurs d'état (OK, à vérifier, erreur). Tous les couples texte / fond respectent un contraste d'au moins 4,5:1 (vérifié par les tests).
- Le bouton d'activation devient **« Jouer · <profil> »**, en vert, avec l'icône lecture.
- Police Segoe UI Variable (Windows 11), style Qt « Fusion » piloté par la palette.
- Le numéro de version n'apparaît plus qu'une fois, dans le titre de la fenêtre (il était affiché 5 fois).
- Lignes colorées des vues Log FS25, Audit de sauvegarde et Tester les mods : couleurs issues du thème.

### Fixed

- **Titre invisible dans le détail d'un mod** en thème clair (texte forcé en blanc).
- **Cartes de la galerie peintes en gris foncé** sur une fenêtre claire : elles suivent maintenant le thème.

## [0.9.0] - 2026-11-07

### Added

- **📝 Journal de l'appli** : l'exe n'a pas de console, les erreurs internes étaient donc invisibles. Elles sont maintenant écrites dans `%LOCALAPPDATA%\fs25-profile-switcher\logs` (`fsmods-gui.log`, tournant, et `crash.log` pour les plantages durs), avec les messages de Qt. Un bouton de la barre d'outils ouvre le dossier, et la barre d'état signale une erreur interne.
- **Fichiers de config illisibles signalés** : un profil ou une collection endommagé(e) n'est plus ignoré(e) en silence, un message les liste au démarrage.
- **CI GitHub Actions** (ruff, mypy, tests) sur Python 3.13 et 3.14, et `requirements.lock` pour figer les versions.

### Changed

- **Plus de gel au lancement et à la fermeture du jeu** : les mods sont comparés par hardlink, taille et date au lieu de relire tout leur contenu (4 lectures complètes par partie). Mesuré sur 134 mods : 10 ms au lancement, 50 ms après la partie.
- `build.ps1` : compile à part (`dist_staging\`) et ne remplace l'exe qu'en cas de succès, ne ferme plus l'appli de force, lance les tests avec le Python qui compile, installe `requirements.lock`, vérifie que les versions concordent, contrôle que l'exe contient bien le code compilé (`packaging/verify_build.py`), et ne s'arrête plus à tort quand sa sortie est redirigée.
- **Supprimer un profil supprime aussi sa carrière** (le message de confirmation le précise) : un nouveau profil du même nom n'hérite plus d'une ancienne carrière.
- Python 3.11 minimum (exigé par Pillow 13).

### Fixed

- **Sécurité** : Pillow passe en 13.0 (52 failles connues en 12.2) et seuls les formats DDS, PNG et JPEG sont décodés. Pillow choisissait son décodeur d'après le contenu : un faux `icon.dds` dans un zip tiers pouvait atteindre n'importe lequel. Tes 1 156 mods restent décodés à l'identique.
- **Écritures atomiques** pour les profils, les collections et le cache : une coupure laisse l'ancien fichier ou le nouveau, jamais un fichier tronqué.
- **Sauvegardes** : un fichier endommagé ne remplace plus sa bonne copie dans le miroir, et n'entre plus dans les instantanés (qui resteraient impossibles à restaurer).
- **Activation refusée tant que le jeu tourne** : ses mods sont utilisés, le dossier se serait retrouvé à moitié remplacé.

### Removed

- Options `pull_overwrite` et `push_overwrite`, sans effet depuis la disparition de la CLI (encore présentes dans un `config.yaml`, elles sont ignorées).

## [0.8.1] - 2026-11-07

### Fixed

- **Surfaces des parcelles** : la touche Entrée fermait la fenêtre et enregistrait seulement ce qui était déjà tapé, sans prévenir ; elle passe maintenant à la parcelle suivante.
- **Saisie décimale** : avec une locale française, un point tapé était ignoré (`1.95` devenait `195`). La virgule et le point sont acceptés dans les surfaces, les cibles d'objectifs et les statistiques manuelles.
- **Surface possédée incomplète** : le tableau de bord affiche le minimum connu (`≥ 8,5 ha`) et la synchronisation nomme les parcelles restantes. Les objectifs restent « non disponible » tant que le total n'est pas complet.
- **Activation sans perte** : un zip du dossier du jeu absent de la bibliothèque ou différent de sa copie (téléchargé en jeu appli fermée, mise à jour ModHub, patch local) était supprimé définitivement. Il est maintenant déplacé dans `_inbox`, où « Nouveaux mods » propose de l'importer. Si un fichier ne peut pas être déplacé (jeu lancé ?), l'activation s'arrête avant de vider le dossier.
- **Import « Remplacer »** : l'archive est lue et vérifiée en entier avant toute écriture, et les anciens fichiers sont retirés en dernier. Une archive corrompue, sans config ou avec un JSON invalide ne change plus rien et l'erreur s'affiche (elle effaçait tout, sans message).
- **Sauvegarde de la config** : seule la première sauvegarde de chaque session s'exécutait (`QThread` détruit puis réutilisé).
- **Ferme suivie** : changer de ferme ne valide plus définitivement les objectifs sans ferme précise sur la ferme regardée. Ces objectifs et les statistiques manuelles restent sur la ferme où ils étaient mesurés (📌), et l'historique est tenu par ferme.
- **Collections après une partie** : les mods hérités ne sont plus présentés comme nouveaux, et importer un mod déjà lié à la bibliothèque ne provoque plus d'erreur non gérée.

### Changed

- Fenêtre « 🌾 Surfaces des parcelles » : total en direct, parcelles restantes listées, champ vide = « à saisir », `0` = vraie valeur, valeur illisible signalée (OK désactivé).

### Removed

- Bouton « Traduire (FR) » de la fiche d'un mod et `profiles/translator.py` : il ne retrouvait pas le fichier du mod, et son remplacement mot à mot pouvait produire un `modDesc.xml` invalide. Le bouton « 🌐 Google Traduction » reste disponible.

## [0.8.0] - 2026-11-03

### Added

- **💰 Case « Versé »** dans le tableau des objectifs : sur chaque objectif terminé avec une récompense en argent, coche quand tu as ajouté l'argent sur ta ferme (PowerTools). Fonctionne dans tous les modes, y compris pour une récompense « non due » ; décocher remet la récompense « à attribuer » (ou non due). Le niveau affiche « 💰 Versé : X € sur Y € gagnés ».
- **🌾 Surface possédée** calculée automatiquement : la surface de chaque parcelle est lue sur la carte du jeu (calque `infoLayer_farmlands.grle` décodé, ids déclarés par `farmlands.xml`) pour les cartes de base et les cartes mods (dossier du jeu ou bibliothèque). Décodage testé sur Le Mechet (La bergerie : 12,52 ha), Montana 4X, Les Combes, Riverbend Springs, Zielonka et Hutan Pantai ; valeurs non comparées à l'affichage en jeu.
- **Surfaces par parcelle** pour les cartes DLC chiffrées (Kinlaig) : bouton « 🌾 Surfaces des parcelles… » qui liste les parcelles possédées ; la surface saisie une fois est réutilisée, une parcelle achetée plus tard est signalée « sans surface » à la synchronisation. Une parcelle inconnue laisse le total « non disponible » plutôt qu'une somme partielle fausse.
- **Vignettes des cartes officielles** : un profil peut choisir une carte officielle (🏛 Riverbend Springs, Zielonka, Hutan Pantai, Kinlaig) dans le sélecteur de carte ; sa vignette s'affiche dans la liste des profils, l'éditeur et le bouton d'activation (aperçu `preview.dds` du jeu, ou image Steam en cache pour un DLC). Un profil sans carte reçoit automatiquement la carte officielle de la sauvegarde liée à sa carrière.

### Changed

- **Au démarrage, l'application s'ouvre sur le dernier profil joué** (champ `last_played` des profils, enregistré à chaque activation).
- La sauvegarde liée à une carrière est aussi devinée pour une carte officielle.

## [0.7.1] - 2026-10-08

### Added

- **🏡 Objectifs par ferme** : une partie multi-fermes (ex. Le Mechet : 6 fermes) peut désormais avoir des objectifs différents par ferme. Sélecteur « Ferme suivie » (tableau de bord + objectifs sans ferme précise), ferme choisie à la création d'un objectif perso ou d'un modèle (le même modèle peut être appliqué à chaque ferme, ids `modèle.clé@ferme`), colonne et filtre « Ferme » dans le tableau, statistiques manuelles par ferme (`<ferme>|<stat>`). Chaque ferme visée a son propre instantané (`farm_snapshots` dans `statistics.json`) ; une ferme disparue donne « non disponible », jamais 0.

### Fixed (vérifié contre une vraie sauvegarde FS25)

- Parcelles : le jeu écrit `farmland.xml` (et non `farmlands.xml`) — `land.count` n'était jamais lu.
- Animaux : une entrée `<animal numAnimals="72">` comptait pour 1 (132 animaux au lieu de 9 sur « La bergerie »).
- Véhicules : palettes, balles et fichiers de production (AutoloadPallets…) ne sont plus comptés ; types et marques sont lus dans le XML du véhicule (jeu installé + mods, dossier ou zip) au lieu d'être devinés ; le nom d'un mod n'est plus une « marque ».
- Revenus / dépenses : prise en compte de `purchase*`, `invoiceExpense`, `incomeBga`, `fieldSelling`, `buy*`.

## [0.7.0] - 2026-10-08

### Added

- **🎯 Onglet « Carrière » (MVP)** : chaque profil dispose de ses propres objectifs, suivis automatiquement à partir de la sauvegarde FS25 associée.
  - **Moteur générique de règles** (`fsmods_gui/career/objectives.py`) : un objectif = un arbre de conditions (`statistique opérateur cible`, combinables en `AND` / `OR` / `NOT`), statut, progression, difficulté (⭐ → ⭐⭐⭐⭐⭐), prérequis (objectifs « à étapes »), objectifs optionnels / cachés / manuels. La complétion est définitive ; une statistique illisible donne « 🔴 non disponible », jamais 0.
  - **Statistiques normalisées** (`career/stats.py`) lues dans `careerSavegame.xml`, `farms.xml`, `vehicles.xml`, `placeables.xml`, `farmlands.xml`, `fields.xml`, `environment.xml` : argent, patrimoine estimé, parcelles, véhicules (marques déduites des chemins, catégories approximatives), animaux par espèce, ruches, productions, contrats, revenus/dépenses, temps de jeu, cultures en place, travaux cumulés, plus toute statistique brute de la ferme (`raw.*`). Espèces, marques et cultures sont **découvertes dynamiquement** (maps/mods inclus).
  - **Fiabilité affichée** pour chaque valeur : 🟢 automatique, 🟠 calculée, 🔵 manuelle, 🔴 non disponible. La surface possédée n'étant pas écrite dans la sauvegarde, elle peut être saisie via **« ✏ Statistique manuelle… »** (n'écrase jamais une valeur automatique).
  - **Tableau de bord** : cartes de statistiques, pourcentage global, compteurs terminés / en cours / non commencés, niveau + XP, badges. Filtres par catégorie, statut et difficulté.
  - **Récompenses** : argent, XP, badge. Modes par profil : désactivé / objectifs seuls / récompenses manuelles / récompenses obligatoires (l'étape suivante reste verrouillée tant que la récompense n'est pas attribuée). L'argent n'est **jamais** injecté dans la sauvegarde : bouton « Attribuer la récompense » → instructions PowerTools (F12), puis confirmation. Une récompense n'est due qu'une fois, et pas pour un objectif déjà atteint au premier calcul.
  - **Modèles** : Carrière classique, ETA, Élevage, Empire agricole, Hardcore ; objectifs personnalisés (numérique ou manuel).
  - **Synchronisation** à l'ouverture de l'onglet, au bouton « 🔄 Synchroniser » et à la fermeture de FS25 : objectifs terminés / débloqués signalés. La sauvegarde est associée automatiquement si la carte du profil ne correspond qu'à une seule sauvegarde.
  - **Stockage indépendant de la sauvegarde** : `<library_dir>/careers/<profil>/{career,objectives,statistics}.json` (écriture atomique ; l'historique des valeurs clés est conservé pour de futurs graphiques).
  - Nouveaux : `GameProfile.library_careers_dir` (config), tests `tests/test_career.py`.

### Carrière — compléments

- **📈 Historique** : graphique (patrimoine, argent, revenus, surface, parcelles, animaux, véhicules, contrats, productions) construit à chaque synchronisation (`career/history.py`, `widgets/history_chart.py`).
- **🍇 Viticulture / 🫒 Oléiculture** : catégories, modèles et statistiques dédiées (`vine.*`, `olive.*`, stocks `stock.<produit>`, raisin / olives récoltés si la sauvegarde les fournit). Les volumes cumulés (vin produit, huile vendue, revenus…) ne sont pas dans la sauvegarde : **saisie manuelle** (🔵), sinon « non disponible ».
- **Autres modèles** : Production, Multiferme, Transport.
- **Éditeur d'objectifs combinés** : plusieurs conditions avec **ET / OU**, case **NON** par condition, **prérequis** (objectifs à étapes) et objectif manuel, dans « ➕ Objectif perso… ».
- **Type de carrière à la création d'un profil** : une liste (classique, ETA, élevage, viticulture, oléiculture, production, transport, multiferme, empire, personnalisé) crée les objectifs de départ.
- **Statistiques dynamiques à zéro** : un membre absent d'une famille entièrement lue (ex. aucun champ d'olives) vaut 0, pas « inconnu » ; les chiens, non détectables, restent inconnus.

### Sauvegarde de la config (Drive / NAS / les deux)

- Les **carrières** sont incluses dans l'export/import ZIP et dans le miroir (les anciennes archives s'importent toujours ; elles n'effacent pas les carrières).
- **Plusieurs cibles** : `config_backup_dirs: [...]` (en plus de `config_backup_dir`, rétrocompatible) — par exemple un dossier **Google Drive pour ordinateur** et un partage **NAS** (UNC `//nas/...` ou lecteur monté). Une cible injoignable n'empêche pas les autres ; statut dans la barre : « Sauvegarde config : 1/2 OK (…) ».
- **Sans bloquer l'interface** : la sauvegarde tourne dans un thread, regroupée (2 s) après les modifications (`ConfigBackupWorker`).
- **Garde-fous du miroir** : suppression uniquement dans un dossier créé par l'application (fichier `.fsmods-backup.json`), jamais si la source est vide (disque non monté), copies atomiques.
- **Instantanés ZIP horodatés** (`<cible>/snapshots/`, 1 par heure au plus, 10 conservés) : restaurables via « 📥 Importer config ».
- Nouveaux : `backup_all`, `snapshot_config`, `summarize_reports`, `GameProfile.backup_targets`.

### Pas encore inclus

Sauvegarde directe via l'API Google Drive, SFTP/WebDAV natifs ou rclone (utiliser Drive pour ordinateur / un montage réseau), fusion automatique de carrières modifiées sur deux PC (dernier écrivain gagnant : éviter de jouer la même carrière sur deux machines sans restaurer un instantané).

### Build / Release

- Version passée de `0.6.0` à `0.7.0`.

## [0.6.0] - 2026-06-26

### Added

- **Vue « 📦 Contenu » : retrait en masse des mods** : barre d'actions en haut de la vue contenu (profil ou collection) avec **« Tout sélectionner »** et **« 🗑 Retirer la sélection (N) »** (le compteur se met à jour selon la sélection). Confirmation au-delà de 2 mods. Aucun fichier n'est effacé de la bibliothèque : les mods sont seulement retirés du profil/de la collection (les mods hérités d'une collection sont exclus, comme avant). La sélection multiple souris (Ctrl/Maj+clic) et le menu contextuel « Retirer » restent disponibles.
- **Vue « 📦 Contenu » : recherche + filtres (comme la bibliothèque)** : barre **Recherche** (nom, titre, auteur) + filtres **catégorie**, **marque** et **type**, ces deux derniers **recherchables** (taper pour filtrer) et masqués quand il n'y a rien à filtrer. Les filtres sont peuplés à partir des mods réellement présents dans le profil/la collection, et se combinent avec le retrait en masse (ex. filtrer une marque → tout sélectionner → retirer). Compteur « N / total » quand un filtre est actif.

### Build / Release

- Version passée de `0.5.0` à `0.6.0`.

## [0.5.0] - 2026-06-23

### Added

- **Bibliothèque AutoDrive dédiée (séparée des mods)** : les packs de routes AutoDrive ont désormais leur propre dossier `<library_dir>/autodrive`, distinct de `mods/` — plus de confusion entre un mod et un pack de routes. Dans l'onglet « 🛣 Routes AutoDrive » :
  - chaque pack affiche sa **source** (📥 Téléchargements ou 🗂️ Bibliothèque) avec un décompte « X en bibliothèque, Y à importer » ;
  - nouveau bouton **« 📥 Importer dans la bibliothèque »** qui **déplace (coupe)** le pack sélectionné des Téléchargements vers la bibliothèque AutoDrive, comme l'import d'un mod (désactivé si le pack y est déjà) ;
  - le scan couvre **Téléchargements + new_mods + bibliothèque AutoDrive**, et l'installation dans une sauvegarde fonctionne aussi bien depuis un téléchargement que depuis la bibliothèque.
  - Nouveaux : `GameProfile.library_autodrive_dir` (config), `import_pack()` + `scan_packs(…, library_dir)` + champ `AutoDrivePack.in_library` (profiles/autodrive.py), handler `_import_autodrive` (fenêtre principale).

### Build / Release

- Version passée de `0.4.1` à `0.5.0`.

## [0.4.1] - 2026-06-23

### Added

- **Détail d'un mod : « 🌐 Google Traduction » pour les descriptions en anglais** : quand un mod n'a qu'une description anglaise, un bouton ouvre **Google Traduction** (détection auto → français) dans le navigateur par défaut avec le **texte pré-rempli** dans l'URL, et **copie le texte complet dans le presse-papier** en secours (à coller si la description est trop longue pour l'URL). Méthode `_open_google_translate` (ouverture via `QDesktopServices`).

### Build / Release

- Version passée de `0.4.0` à `0.4.1`.

## [0.4.0] - 2026-06-22

### Added

- **Classification des mods en types français + marques normalisées** : le scan ne se contente plus de grandes familles (Véhicule/Bâtiment/Objet). Une table de correspondance `storeData/category` (Giants) → **type FR** déduit le type précis affiché sous chaque vignette et dans le détail : *Tracteur, Remorque, Camion, Moissonneuse, Coupe, Déchaumeur, Charrue, Semoir, Pulvérisateur, Tonne à lisier, Presse, Hangar, Silo, Production…*. La lecture parcourt désormais **tous** les `storeItems` (catégorie dominante, 1er token des catégories composées) au lieu du premier seul, et les **marques** sont normalisées pour l'affichage (`johndeere` → *John Deere*, `caseih` → *Case IH*… ; `none` → aucune). Sur une bibliothèque réelle de 1044 mods : 805 véhicules, 141 bâtiments, 36 objets, 12 cartes, **2 « Divers » seulement**. Schéma de cache 20 → 21 (rescan automatique). Type affiché dans la galerie, la table et le détail (« Véhicule · Tracteur »).
- **Ajouter des mods d'une collection à un profil** : depuis le contenu d'une collection (ou d'un profil), **clic droit → « ➕ Ajouter à un profil… »** sur un ou plusieurs mods sélectionnés ; un sélecteur choisit le profil cible. Un mod de carte devient la carte du profil s'il n'en a pas.
- **Ajouter des mods à une collection depuis la bibliothèque ou un profil** : **clic droit → « 🗂️ Ajouter à une collection… »** dans la bibliothèque ou le contenu d'un profil ; un sélecteur choisit la collection. Les cartes sont ignorées (choix propre à chaque profil). **Anti-doublon systématique** : un mod déjà présent n'est jamais ajouté deux fois, ni dans un profil ni dans une collection.
- **Filtres marque / type recherchables** : les listes déroulantes *Marque* et *Type* de la bibliothèque (parfois très longues — 249 marques) deviennent **éditables** : on tape pour filtrer (insensible à la casse, « contient »). Champ vidé → revient à « Toutes/Tous » ; texte sans correspondance → revient à la sélection valide.

### Changed

- **Détail d'un mod : texte sélectionnable / copiable** : dans la fenêtre de détail (ouverte via « Voir détail » ou double-clic), la **description** et les infos (catégorie, type, version, auteur, marque, fichier, dépendances) sont désormais sélectionnables à la souris/clavier pour un copier-coller.

### Build / Release

- Version passée de `0.3.0` à `0.4.0`.

## [0.3.0] - 2026-06-22

### Added

- **« 🧪 Tester les mods » : supprimer les mods en erreur depuis les résultats** : le tableau passe en sélection multiple et deux boutons apparaissent sous la liste — **« 🗑 Supprimer tous les KO »** (efface d'un coup tous les mods en ❌ KO ; actif seulement s'il y en a) et **« 🗑 Supprimer la sélection »**. La suppression réutilise le flux existant (confirmation, retrait du `.zip` du disque + de tous les profils et collections), puis **retire les lignes effacées** du tableau. Annuler la confirmation ne retire rien. Signal `delete_requested` côté vue, handler `_delete_from_testrunner` côté fenêtre.
- **« 📥 Nouveaux mods » : tester les mods AVANT de les charger dans la bibliothèque** : nouveau bouton **« 🧪 Tester les mods »** qui valide les vignettes sélectionnées (ou toutes) directement depuis le dossier de téléchargement, sans rien importer. Chaque vignette reçoit un **badge ✅/⚠/❌**, le détail des contrôles passe dans l'**infobulle**, les KO sont colorés en rouge, et un bandeau récapitule « X OK · Y à vérifier · Z KO » en rappelant qu'on peut nettoyer les KO via le bouton **« 🗑 Supprimer le téléchargement »** déjà présent. Réutilise le `testrunner_exe` de la config si défini, sinon les contrôles intégrés. Signal `test_requested`, handler `_test_new_mods` (worker `TestRunnerWorker` en tâche de fond).

### Build / Release

- Version passée de `0.2.9` à `0.3.0`.

## [0.2.9] - 2026-06-22

### Added

- **TestRunner Giants : invocation réelle + auto-détection de l'éditeur** : « 🧪 Tester les mods » sait désormais piloter `TestRunner.exe` correctement plutôt que de simplement lui passer le chemin du mod. Il l'exécute dans un **dossier de sortie temporaire** (résultats toujours propres), demande une sortie **XML** (`--outputFormats XML`), ferme `stdin` (`DEVNULL`) pour éviter tout blocage en mode headless, puis **lit le rapport `testResult_*.xml`** et en extrait un résumé lisible (`_parse_testrunner_xml`). Le **GIANTS Editor** requis par TestRunner est **auto-détecté** (le plus récent `GIANTS_Editor_*/editor.exe` sous `C:/Program Files/GIANTS Software/`), ou forçable via config.
- **Config : chemin du GIANTS Editor paramétrable** : `games.<jeu>.editor_exe` (optionnel ; auto-détecté si absent). Voir `config.example.yaml`.

### Changed

- **Fenêtre : position et taille mémorisées d'une session à l'autre** : la géométrie est sauvegardée à la fermeture (`QSettings`) et restaurée au lancement.
- **Arrêt propre des tâches de fond** : à la fermeture de la fenêtre, le surveillant de jeu et les threads de scan / activation / test sont arrêtés et attendus (jusqu'à 3 s) — fini les avertissements Qt « QThread destroyed while still running » en quittant.

## [0.2.8] - 2026-06-21

### Added

- **Nouvelle vue « 🧪 Tester les mods » : valider un mod (OK / À vérifier / KO) avant de jouer** : un onglet qui scanne les `.zip` et signale ce que le scanner ModHub de Giants rejette le plus souvent, sans rien lancer en jeu. Deux moteurs complémentaires :
  - **Contrôles intégrés** (toujours actifs, sans dépendance) : intégrité de l'archive, **nom de fichier valide** (le jeu refuse espaces/caractères spéciaux), `modDesc.xml` **présent et bien formé** (avec `descVersion`, `<version>`, `<title>`), **icône déclarée réellement présente** dans le zip, **textures DDS en puissance de 2**, et fichiers/archives trop volumineux. Validation **XSD optionnelle** contre le `modDesc.xsd` du jeu (si `install_dir` est configuré et `lxml` installé).
  - **Giants TestRunner (optionnel)** : si on renseigne le chemin de `TestRunner.exe` (Giants Developer Network), son code de sortie et sa sortie texte sont repliés dans le verdict. Exécution défensive (timeout, capture stdout/stderr, jamais de crash) car son interface n'est pas publiquement stable.
  - **Portée** au choix : *mods du profil courant* ou *toute la bibliothèque*. Tableau de résultats coloré (✅/⚠/❌) + détail des contrôles par mod sélectionné. Traitement en tâche de fond (worker QThread) avec barre de progression.
  - **Filtre par statut** : menu « Afficher : » pour ne voir que *Problèmes (KO + à vérifier)*, *KO seulement*, *À vérifier seulement* ou *OK seulement* (le décompte global reste sur le total).
  - Nouveau module `fsmods_gui/profiles/testrunner.py` (`validate_mod`, `validate_mods`, `run_testrunner`, `ModTestResult`, `Check`) — sans Qt, testé. Nouvelle vue `fsmods_gui/widgets/testrunner_dialog.py` (`TestRunnerPanel`) et worker `TestRunnerWorker`.
- **Config : chemin de TestRunner paramétrable** : `games.<jeu>.testrunner_exe` (optionnel ; laissé vide ⇒ contrôles intégrés uniquement). Voir `config.example.yaml`.

### Changed

- **Vues secondaires en panneaux intégrés (fin de la migration) : plus aucune pop-up** : les dernières fenêtres modales (`QDialog`) — *Doublons*, *Statistiques*, *Log FS25*, *Audit sauvegarde*, *Routes AutoDrive*, *Nouveaux mods* — sont désormais des **panneaux intégrés** (`QWidget`) dans la pile d'onglets à droite, comme l'éditeur. On garde le contexte (profil sélectionné, état des cases) sans rouvrir une boîte de dialogue, et chaque onglet se **reconstruit à partir de l'état courant** quand il devient visible. Renommage `…Dialog` → `…Panel` (`DuplicatesPanel`, `StatsPanel`, `LogReportPanel`, `SavegameAuditPanel`, `AutoDrivePanel`, `NewModsPanel`), communication par **signaux** vers la fenêtre principale.

### Fixed

- **Test des mods : les textures `*Array.dds` n'étaient plus signalées à tort** : `fruitArray.dds`, `plantArray.dds`, etc. sont des **textures de données** (tables de lookup) aux dimensions volontairement arbitraires — la règle « puissance de 2 » ne s'y applique pas et le jeu les charge sans problème. Le contrôle de textures les ignore désormais pour éviter le bruit.
- **Doublons : moins de faux positifs** : la normalisation des noms regroupait à tort des mods réellement différents. Un **numéro nu** en fin de nom (`Mod1` vs `Mod2`) ou un **nombre à deux composantes** (`MAN_TGX_18.500`, un nom de modèle) n'est plus traité comme un marqueur de copie/version : on ne retire désormais que ce qui marque sans ambiguïté une copie (`(1)`, `copy`, `copie`, `old`, `backup`…) ou une vraie version (`_v1.2.3`, ou un numéro pointé à **3 composantes ou plus**). De plus, la détection par **contenu** exige maintenant *à la fois* un titre **et** un auteur réels — deux mods sans auteur partageant un titre générique (« Trailer », « Pack ») ne sont plus fusionnés.

### Build / Release

- Version passée de `0.2.7` à `0.2.8`.

## [0.2.7] - 2026-06-20

### Added

- **« Nouveaux mods » : supprimer un téléchargement depuis la vue** : maintenant que les mods déjà importés s'affichent, on peut nettoyer le dossier de téléchargement sans quitter l'app. Bouton « 🗑 Supprimer le téléchargement » (et clic droit « 🗑 Supprimer le fichier téléchargé… ») sur la sélection : après confirmation, le(s) `.zip` sont effacés de **leur dossier source** (Téléchargements / `new_mods`) et retirés de la liste. **N'affecte pas la bibliothèque** — les mods déjà importés y restent. Helper `delete_source()` dans `fsmods_gui/profiles/inbox.py`.

### Changed

- **« Nouveaux mods » : import en place sans fermer la fenêtre** : le bouton « 📥 Importer les mods cochés » importait puis **fermait** la vue, obligeant à la rouvrir pour traiter le reste. L'import se fait désormais **en place** : les mods cochés sont importés, leurs vignettes **retirées de la liste**, et les mods restants (avec leurs cases et leur classement déjà choisis) sont **conservés** — la fenêtre reste ouverte jusqu'à « Fermer ». Un message confirme chaque import sous la liste. Nouveau signal `import_requested` + `remove_imported()` / `flash_status()` côté vue, handler `_apply_new_mods_import()` côté fenêtre principale.

### Fixed

- **« Nouveaux mods » : les mods déjà téléchargés n'apparaissaient plus** : le scanner masquait silencieusement tout `.zip` dont le nom existait déjà dans la bibliothèque, si bien qu'un dossier Téléchargements rempli de mods déjà importés semblait « vide » (1 seul mod détecté sur 13 dans un cas réel). Le scan affiche désormais **tous** les zips des dossiers source avec un **statut** (comparaison par nom + taille) : *nouveau*, *mise à jour* (même nom, taille différente) ou *déjà dans la bibliothèque* (estompé). Les nouveaux et les mises à jour sont **cochés par défaut** ; les doublons restent décochés (on peut quand même les classer dans un profil/collection, ou nettoyer le téléchargement en les important — l'import écrase le fichier identique et coupe la source). Tri nouveaux → màj → doublons, avec décompte détaillé en en-tête.

### Build / Release

- Version passée de `0.2.6` à `0.2.7`.

## [0.2.6] - 2026-06-19

### Added

- **Routes AutoDrive : pré-installer un pack de routes dans une sauvegarde** : nouvelle action de barre d'outils « 🛣 Routes AutoDrive ». Certains packs communautaires fournissent un réseau de routes AutoDrive sous forme de `.zip` qui n'est **pas un mod** (pas de `modDesc.xml`) mais contient les fichiers `AutoDrive_config.xml` / `AutoDriveUsersData.xml` que le jeu lit dans le dossier d'une sauvegarde. La vue scanne les **dossiers source** (Téléchargements + `new_mods`) à la recherche de ces packs, on choisit le pack et la **sauvegarde cible** (`savegameN`, affichée avec son nom + sa carte), puis « Installer » : les XML AutoDrive déjà présents sont **renommés en `.bak`** (non destructif, retour arrière possible) avant que les fichiers du pack ne soient déposés. C'est l'équivalent automatisé de la procédure manuelle « supprimer les anciens XML, dézipper, copier les deux fichiers ».
  - Nouveau module `fsmods_gui/profiles/autodrive.py` (`AutoDrivePack`, `detect_pack`, `scan_packs`, `install_pack`) — sans Qt, testé.
  - Nouvelle vue `fsmods_gui/widgets/autodrive_dialog.py` (`AutoDriveDialog`).

### Changed

- **Analyse du log : attribution du mod fautif via la pile d'appel** : une erreur Lua (`Running LUA method 'update'`) est générique — c'est la **pile d'appel** sur les lignes suivantes (`.../mods/FS25_Xxx/....lua:NNN`) qui nomme le coupable. L'analyseur absorbe désormais ces lignes de continuation (non horodatées) rattachées à l'erreur qui précède, en **extrait le mod** (`FS25_…`) pour remplir la colonne *Mod*, **enrichit le message** avec la localisation `script.lua:ligne` (chemin absolu retiré), et **affiche la pile complète** dans l'infobulle. Bénéfice combiné avec le regroupement : un script qui plante à chaque frame passe de milliers de lignes anonymes à **une seule** ligne comptée et attribuée.

### Fixed

- **Analyse du log : le spam d'erreurs identiques n'était pas regroupé** : les lignes FS commençant par un horodatage (`2026-06-19 11:55:37.286 Error: …`), l'horodatage — unique à chaque ligne — restait dans la clé de fusion. Une erreur Lua qui plante à chaque frame (`Running LUA method 'update'`) produisait donc des milliers de lignes « Occ. 1 » au lieu d'une seule ligne comptée. L'horodatage (date + heure ou heure seule) est désormais retiré avant de construire le message, ce qui restaure le regroupement et nettoie le texte affiché.

### Build / Release

- Version passée de `0.2.5` à `0.2.6`.

## [0.2.5] - 2026-06-19

### Added

- **Vue « 📥 Nouveaux mods » : importer les mods téléchargés et les classer** : nouvelle action de barre d'outils qui scanne le **dossier Téléchargements de Windows** *et* un **dossier dédié `new_mods`** (l'« inbox ») à la recherche de `.zip` pas encore présents dans la bibliothèque. Chaque mod trouvé s'affiche en vignette (icône + titre + catégorie · version, badge 🗺 pour les cartes). On sélectionne un ou plusieurs mods, on coche les **profils** et/ou **collections** où les classer (cocher une cible marque aussi le mod « à importer »), puis « Importer » : chaque `.zip` est **déplacé (coupé)** depuis sa source vers `library/mods`, ajouté au catalogue, et ajouté aux profils/collections choisis (un mod de carte devient la carte du profil s'il n'en a pas encore). Les mods cochés sans cible sont simplement ajoutés à la bibliothèque.
  - Nouveau module `fsmods_gui/profiles/inbox.py` (`PendingMod`, `scan_sources`, `import_pending`) — sans Qt, testé.
  - Nouvelle vue `fsmods_gui/widgets/new_mods_dialog.py` (`NewModsDialog`).
  - `AppState.scan_new_mods()` / `AppState.import_new_mods()` (`ImportPlan`, `ImportNewModsResult`).
- **Config : dossiers source paramétrables** : `games.<jeu>.downloads_dir` (défaut : dossier *Téléchargements* de l'utilisateur) et `games.<jeu>.inbox_dir` (défaut : `<library_dir>/_inbox`, créé automatiquement). Voir `config.example.yaml`.

### Build / Release

- Version passée de `0.2.4` à `0.2.5`.

## [0.2.4] - 2026-06-19

### Changed

- **Interface unifiée à une seule fenêtre (fin du dialogue modal des collections)** : les collections se gèrent désormais dans la fenêtre principale, plus dans une fenêtre séparée. La barre latérale gauche liste maintenant **Profils** *et* **🗂️ Collections** (chacune avec ➕ Nouvelle / 🗐 Dupliquer / ✖ Supprimer). Sélectionner un profil ou une collection l'ouvre dans le **même éditeur** à droite.
- **Éditeur unifié profil/collection avec « plans » (bascule Contenu ↔ Bibliothèque)** : au lieu de juxtaposer bibliothèque et contenu, l'éditeur affiche une page à la fois via un commutateur **📦 Contenu** / **➕ Bibliothèque**. La page *Bibliothèque* sert à ajouter des mods à la cible courante ; la page *Contenu* montre les mods de la cible. Un profil garde sa carte et sa liste de collections héritées ; une collection les masque.

### Added

- **Vue galerie pour le contenu d'un profil/d'une collection** : le panneau « Contenu » dispose de sa propre bascule (☰ liste / ▦ galerie). En galerie, chaque mod est une grande vignette type ModHub (icône + titre + catégorie · version) — bien plus facile à identifier qu'une liste de noms de fichiers. Badges visuels : 🗺 carte, 🔗 hérité d'une collection (cadre bleu), 🚫 exclu (barré/estompé), ⚠ absent de la bibliothèque (cadre rouge). Nouveau `fsmods_gui/widgets/mod_gallery.py` (`ModListModel` + `ContentCardDelegate` + `ModContentPanel`), réutilisable pour les deux types de cible.
- **Supprimer un mod de la bibliothèque** : clic droit sur un mod (ou une sélection) dans la bibliothèque → « 🗑 Supprimer de la bibliothèque… ». Après confirmation, le(s) fichier(s) `.zip` (et l'icône en cache) sont effacés du disque, retirés du catalogue, et **délié en cascade** de tous les profils (mods propres, carte, exclusions) et collections qui les référençaient — chaque profil/collection modifié est ré-enregistré, et un rapport liste ce qui a été touché. Logique dans `AppState.delete_mods()` (`DeleteModsResult`).

### Fixed

- **Vignettes manquantes dans la bibliothèque** : ~185 mods (sur 912) n'affichaient pas leur icône à cause d'un **cache d'index périmé** — leur icône avait échoué lors d'un ancien scan et n'était jamais réextraite (le `.zip` n'ayant pas changé). Le cache est désormais **auto-réparant** : à chaque scan, une entrée qui déclare une icône mais n'a pas de vignette valide est réextraite sans re-parser tout le `modDesc.xml`. La recherche d'icône gère aussi le cas où l'icône est rangée dans un **sous-dossier** du zip (recherche par nom de base, en plus du chemin exact et du swap d'extension `.png`↔`.dds`).

### Removed

- `fsmods_gui/widgets/profile_editor.py` et `fsmods_gui/widgets/collections_manager.py` : fusionnés dans le nouvel éditeur unifié `fsmods_gui/widgets/editor_panel.py`. Le bouton de barre d'outils « 🗂️ Collections » disparaît (remplacé par la liste latérale).

### Build / Release

- Version passée de `0.2.3` à `0.2.4`.

## [0.2.3] - 2026-06-19

### Added

- **Vue galerie de la bibliothèque** : nouveau bouton de bascule (☰ tableau / ▦ galerie) dans la barre d'outils de la bibliothèque. La vue galerie affiche les mods sous forme de grandes vignettes type ModHub (icône + titre + catégorie · version), avec états survol/sélection. Nouveau `ModCardDelegate` rendant chaque mod dans un `QListView` partageant le même modèle/proxy que le tableau : recherche, filtres (catégorie, marque, type, profil), tri, sélection multiple, double-clic et menu contextuel fonctionnent à l'identique dans les deux vues. Disponible partout où la bibliothèque est réutilisée (éditeur de profil, gestionnaire de collections).

### Build / Release

- Version passée de `0.2.2` à `0.2.3`.

## [0.2.2] - 2026-06-10

### Added

- **Sauvegarde de la config (backlog #4)** : sauvegarde des profils + collections (jamais les mods).
  - Boutons « 📤 Exporter config » (zip horodaté des profils + collections) et « 📥 Importer config » (choix **fusionner** ou **remplacer** à chaque import).
  - Champ optionnel `config_backup_dir` dans `config.yaml` : un dossier synchronisé (OneDrive/Drive/Dropbox) vers lequel profils + collections sont **mirrorés automatiquement** après chaque modification (copie + purge des fichiers supprimés). Sans OAuth.
  - Logique pure dans `fsmods_gui/profiles/config_backup.py` (protection contre le zip-slip).

### Build / Release

- Version passée de `0.2.1` à `0.2.2`.

## [0.2.1] - 2026-06-10

### Added

- **Carte des mods / statistiques (backlog #8)** : nouveau bouton « 📊 Statistiques » ouvrant un tableau de bord de la bibliothèque — vue d'ensemble (nombre de mods, taille totale, cartes, profils, collections, doublons, orphelins, erreurs de lecture), répartition par catégorie (nombre + taille), top marques, mods par profil (effectifs) et par collection, liste des mods orphelins (dans aucun profil ni collection) et des erreurs de lecture. Calcul pur dans `fsmods_gui/profiles/stats.py`, réutilisant la détection de doublons (#2) et les collections (#6).

### Build / Release

- Version passée de `0.2.0` à `0.2.1`.

## [0.2.0] - 2026-06-10

### Added

- **Collections héritables (backlog #6)** : nouveau concept de *collection* = groupe nommé et réutilisable de mods (ex. « Vieux matériel », « Viticulture »). Un profil peut **hériter de plusieurs collections** ; ses mods effectifs = mods propres ∪ mods des collections héritées − exclusions.
  - Lien **dynamique** : modifier une collection se répercute sur tous les profils qui l'héritent.
  - **Exclusions par profil** : un profil peut désactiver individuellement un mod hérité (clic droit sur le mod → « Exclure de ce profil » / « Réintégrer »).
  - Nouveau bouton « 🗂️ Collections » : gestionnaire (créer / dupliquer / supprimer + éditeur bibliothèque/contenu). Supprimer une collection la délie des profils concernés (avec rapport).
  - Action « 🗂️ Ajouter à une collection… » dans le menu contextuel de la bibliothèque.
  - L'éditeur de profil affiche les collections héritées (cases à cocher) et distingue les mods hérités (bleu) et exclus (barrés).
  - L'activation, le calcul des mods manquants et l'audit de sauvegarde opèrent sur la liste **effective**.
  - Les cartes ne font pas partie des collections (choix propre au profil).

### Changed

- **Schéma de profil 1 → 2** : ajout de `collections` et `excluded_mods`. Les profils v1 sont migrés automatiquement et réécrits en v2 à la prochaine sauvegarde (non relisibles par une version antérieure de l'app).

### Build / Release

- Version passée de `0.1.9` à `0.2.0`.

## [0.1.9] - 2026-06-10

### Added

- **Audit de sauvegarde (backlog #7)** : nouveau bouton « 🔍 Auditer une sauvegarde » qui compare le profil courant au contenu réellement utilisé par une sauvegarde FS25. Chaque mod du profil est classé en 🟢 utilisé (objet placé dans le monde / carte), 🟡 chargé sans objet placé (souvent script/pack — à examiner) ou 🔴 absent de la sauvegarde. Pré-sélection prudente : seuls les mods absents sont pré-cochés pour retrait. Vue bidirectionnelle : les mods utilisés par le save mais absents du profil sont listés et peuvent être ajoutés. **Aucun fichier n'est supprimé** — seul le profil est modifié, après confirmation. Logique pure dans `fsmods_gui/profiles/savegame_audit.py`.

### Build / Release

- Version passée de `0.1.8` à `0.1.9`.

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
