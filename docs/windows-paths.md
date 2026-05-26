# Chemins Windows / Steam

Sur Windows 11 avec une installation Steam standard, les mods de FS25 et FS22 ne sont **pas** dans le dossier d'installation Steam mais dans `Documents/My Games/`.

## Dossiers mods

| Jeu  | Chemin natif Windows                                                       |
| ---- | -------------------------------------------------------------------------- |
| FS25 | `C:\Users\<toi>\Documents\My Games\FarmingSimulator2025\mods`              |
| FS22 | `C:\Users\<toi>\Documents\My Games\FarmingSimulator2022\mods`              |

Depuis WSL (Ubuntu/Arch sous Windows), le même chemin devient :

```
/mnt/c/Users/<toi>/Documents/My Games/FarmingSimulator2025/mods
/mnt/c/Users/<toi>/Documents/My Games/FarmingSimulator2022/mods
```

C'est cette forme qu'on met dans `config.yaml` quand on travaille depuis WSL.

## Dossiers d'installation (pour référence uniquement)

Utile si tu veux consulter les fichiers de référence (modDesc XSD, scripts du jeu) :

| Jeu  | Chemin Steam par défaut                                                 |
| ---- | ----------------------------------------------------------------------- |
| FS25 | `C:\Program Files (x86)\Steam\steamapps\common\Farming Simulator 25`    |
| FS22 | `C:\Program Files (x86)\Steam\steamapps\common\Farming Simulator 22`    |

Ces dossiers ne sont **pas** modifiés par cet outil.

## Vérifier que le chemin est bon

```bash
ls "/mnt/c/Users/<toi>/Documents/My Games/FarmingSimulator2025/mods"
```

Tu dois voir une liste de `.zip` (les mods déjà installés). Si tu vois `Permission denied`, redémarre WSL ou monte avec `metadata`. Si le dossier n'existe pas, lance FS25 au moins une fois — il crée le dossier au premier démarrage.
