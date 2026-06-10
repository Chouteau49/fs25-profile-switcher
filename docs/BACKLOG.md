# Backlog des fonctionnalités — FS25 Profile Switcher

> Document de cadrage. Version courante de l'app : **0.1.6**. Dernière mise à jour : **2026-06-10**.
>
> Objectif : recenser les idées de fonctionnalités, leur attribuer une difficulté et une priorité, détailler chacune (objectif / approche / fichiers / risques), puis recommander un ordre de développement. **La décision finale de ce qu'on code se prend après lecture de ce document.**

## Légende

- **Difficulté de mise en place** : 🟢 Facile · 🟡 Moyen · 🔴 Élevé
- **Priorité** : **P1** (fort impact, explicitement demandé) · **P2** (utile) · **P3** (confort)

## Décisions de cadrage déjà prises

- **Sauvegarde cloud** : approche « dossier synchronisé » — on pointe la bibliothèque/config vers un dossier déjà synchronisé par Google Drive / OneDrive / Dropbox sur le PC. **Pas d'OAuth ni d'API cloud.**
- **Mise à jour web** : **GitHub uniquement** via API publique (champ « source URL » par mod). **Pas de scraping** KingMods / fs25.net (pas d'API publique, fragile, CGU).

## Tableau récapitulatif

| # | Fonctionnalité | Difficulté | Priorité | Dépend de | État |
|---|---|:---:|:---:|---|:---:|
| 1 | Analyse des logs FS25 à la fermeture | 🟡 | **P1** | — | ✅ v0.1.7 |
| 2 | Détection des doublons | 🟢 | **P1** | — | ✅ v0.1.7 |
| 3 | Détection des dépendances mods/maps | 🟡 | P2 | #2 (identité mod) | ✅ v0.1.8 |
| 4 | Sauvegarde config sur dossier cloud synchronisé | 🟢 | P2 | — | À faire |
| 5 | Mise à jour via GitHub | 🟡 | P2 | — | À faire |
| 6 | Collections héritables | 🔴 | P2 | — | À faire |
| 7 | Audit d'une sauvegarde (mods inutilisés) | 🔴 | P3 | — | À faire |
| 8 | Carte des mods avec statistiques | 🟡 | P3 | #2 (doublons) | À faire |

---

## 1. Analyse des logs FS25 à la fermeture · 🟡 P1

**Objectif.** À la fermeture du jeu, lire `Documents/My Games/FarmingSimulator2025/log.txt` et présenter un **tableau** des problèmes rencontrés : erreurs Lua, warnings, conflits, mods introuvables, doublons… Chaque ligne du tableau indique le **type**, le **statut/sévérité**, le **mod concerné** (si identifiable) et le **message traduit en français**.

**Approche technique.**
- Nouveau module **`fsmods_gui/profiles/log_analyzer.py`** (logique pure, sans Qt → testable).
- Dataclass `LogIssue(severity, kind, mod, raw_message, fr_message, line_no)` où :
  - `severity` ∈ {`error`, `warning`, `info`}
  - `kind` ∈ {`lua`, `missing_mod`, `conflict`, `duplicate`, `load`, `other`}
- Fonction `analyze_log(log_path) -> list[LogIssue]` : lecture ligne à ligne + regex sur les marqueurs FS connus :
  - `Error: ...`, `Warning: ...`
  - `Error: Running LUA method '...'`
  - `Warning: ... not found` / `Failed to ...`
  - lignes de chargement de mods (`Available dlc/mod ...`, `dataS/...`)
  - détection d'un même mod chargé deux fois.
- Table de traduction FR : dict `pattern → libellé français` (couverture incrémentale, fallback « Non classé » pour l'inconnu).

**Modèle de données / UI.**
- Nouveau **`fsmods_gui/widgets/log_report_dialog.py`** : `QTableWidget` trié par sévérité, colonnes *Sévérité · Type · Mod · Message (FR) · Ligne*, filtre par type, bouton « copier le rapport ».
- **Hook** : `GameWatcher.stopped` ([workers.py:81](../fsmods_gui/workers.py#L81)) déclenche déjà la réconciliation post-partie via `SyncDialog`. On y greffe la lecture du log — soit un onglet supplémentaire dans le dialogue de sync, soit un dialogue dédié ouvert à la suite.
- Le chemin du log se déduit du dossier utilisateur FS (parent de `mods_dir`, voir [config.py](../fsmods_gui/config.py)).

**Risques & limites.** Le format de `log.txt` n'est pas documenté officiellement → couverture par patterns à enrichir au fil des cas réels. Toujours prévoir un repli « Non classé » pour ne rien masquer.

---

## 2. Détection des doublons · 🟢 P1

**Objectif.** Repérer dans la bibliothèque — et au sein d'un profil — plusieurs `.zip` qui fournissent **le même mod** (même identité interne) ou des variantes de version d'un même mod.

**Approche technique.**
- S'appuie entièrement sur le scan de catalogue existant.
- Ajouter l'extraction de l'**identité du mod** dans [catalog.py `_read_moddesc_from_zip`](../fsmods_gui/profiles/catalog.py#L111) : le `modName` réel se déduit du nom de dossier interne référencé dans `modDesc.xml` (chemins `storeItems`, `l10n`, icônes) ou, à défaut, du nom de fichier normalisé. Nouveau champ `mod_id: str | None` sur `CatalogEntry`.
- Détection = regroupement des entrées par `mod_id` (puis par version pour distinguer doublon exact vs. variantes de version).

**Modèle de données / UI.**
- Badge/colonne « doublon » dans [library_table.py](../fsmods_gui/widgets/library_table.py), ou petit rapport listant les groupes de doublons avec leurs fichiers et versions.
- Réutilisé par la feature **#8** (statistiques).

**Risques & limites.** L'identité interne n'est pas toujours fiable (mods mal packagés) ; en repli on regroupe par nom de fichier normalisé, ce qui peut sur- ou sous-détecter à la marge → présenter comme indicatif.

---

## 3. Détection des dépendances mods/maps · 🟡 P2

**Objectif.** Si le mod A déclare nécessiter le mod B, proposer d'ajouter **A et B** au profil (pas seulement A). Idem pour une map qui requiert des mods.

**Approche technique.**
- Parser `<dependencies>` de `modDesc.xml` dans [catalog.py](../fsmods_gui/profiles/catalog.py) → nouveau champ `requires: list[str]` sur `CatalogEntry` (par **`modName`**, jamais par filename).
- Construire une table `modName → filename` à partir du `mod_id` introduit en #2.
- À l'ajout d'un mod dans l'éditeur ([profile_editor.py](../fsmods_gui/widgets/profile_editor.py)), résoudre la **fermeture transitive** des dépendances : proposer d'ajouter celles présentes en bibliothèque, **avertir** clairement pour celles absentes.

**Modèle de données / UI.** Boîte de dialogue de confirmation « Ce mod nécessite aussi : … Ajouter au profil ? » avec cases à cocher.

**Risques & limites.** Beaucoup de mods ne renseignent pas `<dependencies>` → couverture **best-effort**, à présenter comme telle. Ne jamais bloquer l'ajout si une dépendance manque.

---

## 4. Sauvegarde config sur dossier cloud synchronisé · 🟢 P2

**Objectif.** Sauvegarder profils (et futures collections) dans un dossier synchronisé par Drive/OneDrive/Dropbox, pour retrouver sa config sur un autre PC.

**Approche technique.**
- Déjà quasi gratuit : `library_dir` est configurable ([config.py](../fsmods_gui/config.py)). Documenter le fait de placer la bibliothèque (ou au moins `profiles/`) dans un dossier synchronisé.
- Ajouter une action **« Exporter / Importer la config »** : zip des dossiers `profiles/` (+ `collections/` quand #6 existera) déposable où l'utilisateur veut. Restauration par import.
- Optionnel : champ `config_backup_dir` dans `config.yaml` + export automatique après modification d'un profil.

**Modèle de données / UI.** Deux boutons dans la barre d'outils / menu : *Exporter la config…* (→ `.zip`) et *Importer la config…*.

**Risques & limites.** Conflits de synchronisation cloud si deux PC écrivent en même temps → l'export/import manuel reste le filet de sécurité. **Pas d'OAuth** (décision de cadrage).

---

## 5. Mise à jour via GitHub · 🟡 P2

**Objectif.** Vérifier l'existence d'une version plus récente pour les mods hébergés sur GitHub.

**Approche technique.**
- Champ optionnel **`source_url`** par mod, stocké **hors du zip** : side-car JSON par mod sous `cache/` ou champ additionnel persisté dans le cache catalogue (`index.json`).
- Nouveau module **`fsmods_gui/updates/github.py`** utilisant l'API *releases* GitHub via `urllib` (stdlib → **pas de nouvelle dépendance lourde**).
- Worker QThread dédié (sur le modèle de [workers.py](../fsmods_gui/workers.py)) pour ne pas bloquer l'UI.
- Comparaison de la version distante vs. `CatalogEntry.version` ; signalement « mise à jour disponible » dans la table.

**Modèle de données / UI.** Champ « URL source » éditable dans le détail du mod ([mod_detail.py](../fsmods_gui/widgets/mod_detail.py)) ; pastille « ⬆ maj dispo » dans la library table.

**Risques & limites.** Rate-limit API GitHub non authentifié = **60 req/h** → throttling + cache des résultats. Le téléchargement automatique n'est pas inclus dans ce périmètre (on signale, l'utilisateur télécharge).

---

## 6. Collections héritables · 🔴 P2

**Objectif.** Définir des groupes nommés de mods (ex. *Olympiques*, *RP*, *Viticulture*, *Matériels*) ; un profil **hérite de plusieurs collections**. Les mods effectifs d'un profil = **union(collections héritées) + mods propres**.

**Approche technique.**
- Nouveau modèle **`Collection`** : JSON sous `<library_dir>/collections/<slug>.json`, calqué sur [profile.py](../fsmods_gui/profiles/profile.py) (`name`, `mods`, `description`).
- Étendre `Profile` avec `collections: list[str]` (slugs). **Bump `PROFILE_SCHEMA_VERSION` → 2** avec migration ascendante (un profil v1 = `collections: []`).
- Calculer la liste effective des mods **avant activation** ([activator.py](../fsmods_gui/profiles/activator.py)) : nouvelle méthode `Profile.effective_mods(collections, catalog)` qui fait l'union et dédoublonne (réutiliser la logique de `all_mod_filenames`).

**Modèle de données / UI.** Nouvel écran de gestion des collections (CRUD calqué sur la liste de profils) + sélecteur multi-collections dans l'éditeur de profil ; affichage distinct « mods hérités » vs « mods propres ».

**Risques & limites.** Refonte du modèle de profil + migration de schéma + gestion de l'ordre/conflits entre collections (quel mod gagne si versions différentes ?). Chantier le plus structurant.

---

## 7. Audit d'une sauvegarde (mods inutilisés) · 🔴 P3

**Objectif.** Analyser une sauvegarde de partie pour lister les mods **réellement utilisés**, et proposer de retirer du profil ceux qui ne le sont pas, afin d'alléger.

**Approche technique.**
- Nouveau module **`fsmods_gui/profiles/savegame_audit.py`** : parser le dossier `savegameN/` (`careerSavegame.xml`, `vehicles.xml`, `items.xml`, `placeables.xml`) et collecter tous les `modName` référencés.
- Croiser avec les mods du profil (via le `mod_id` de #2) → trois statuts : *utilisé*, *probablement inutilisé*, *requis par la map/scripts*.

**Modèle de données / UI.** Sélecteur de savegame + rapport « utilisés / inutilisés » avec action « retirer du profil » (jamais de suppression de fichier).

**Risques & limites.** Un mod peut être nécessaire sans apparaître dans la save (scripts globaux, dépendances de map) → **toujours marquer « probablement inutilisé »** et ne **jamais** supprimer automatiquement.

---

## 8. Carte des mods avec statistiques · 🟡 P3

**Objectif.** Tableau de bord visuel de la bibliothèque : répartition par catégorie/marque, taille totale, nombre de mods par profil, doublons, mods orphelins (en bibliothèque mais dans aucun profil), erreurs de parsing.

**Approche technique.**
- Vue purement agrégée à partir du `Catalog` et des `Profile` déjà en mémoire ([state.py](../fsmods_gui/state.py)).
- Nouveau widget **`fsmods_gui/widgets/stats_dashboard.py`**.
- Réutilise la détection de doublons (#2) et la catégorisation existante de [catalog.py](../fsmods_gui/profiles/catalog.py).

**Modèle de données / UI.** Cartes de stats + histogrammes simples (catégorie, marque) ; liste cliquable des orphelins et des doublons.

**Risques & limites.** Faible risque technique ; surtout du travail de présentation. Les graphiques avancés peuvent nécessiter `QtCharts` (sinon barres dessinées maison pour éviter une dépendance).

---

## Ordre de développement recommandé

À valider ensemble avant de lancer un plan d'implémentation dédié par lot.

1. **#2 Détection des doublons** — 🟢 P1, autonome, fort impact immédiat, et pose le `mod_id` réutilisé par #3, #7, #8.
2. **#1 Analyse des logs FS25** — 🟡 P1, demande explicite à forte valeur ; s'enclenche proprement sur le hook `GameWatcher.stopped` existant.
3. **#4 Sauvegarde config (dossier synchronisé)** — 🟢 P2, isolé, quasi gratuit, sécurise les données utilisateur.
4. **#5 Mise à jour via GitHub** — 🟡 P2, isolé, première brique réseau (stdlib).
5. **#3 Détection des dépendances** — 🟡 P2, s'appuie sur le `mod_id` de #2.
6. **#6 Collections héritables** — 🔴 P2, chantier structurant (migration de schéma) à traiter une fois les briques simples en place.
7. **#7 Audit de sauvegarde** — 🔴 P3, dépend de la fiabilité du `mod_id` (#2).
8. **#8 Carte des mods** — 🟡 P3, capitalise sur #2 et la catégorisation ; idéal comme vitrine finale.
