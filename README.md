# ClubDirector AI

Directeur sportif IA pour **Football Manager 26** : il lit votre carrière (sauvegarde `.fm`),
archive son historique, répond en français à partir des vraies données, recommande des recrues
avec un score explicable, et s'affiche dans le jeu via un plugin BepInEx (expérimental).

> **État** : testé sur une vraie carrière (AS Roma) avec une IA locale (llama.cpp + Gemma 4). Le
> téléphone du coach s'affiche dans une fenêtre au-dessus de FM26 (Ctrl+Alt+D) : Messages avec trois
> membres du staff, Mercato, Calendrier, Effectif (onze type), Classement, Réglages, écran verrouillé.
> Le plugin BepInEx est bloqué par la protection du jeu ; aucune action dans FM26 n'est disponible.
> Détails : [docs/DEVELOPMENT_STATUS.md](docs/DEVELOPMENT_STATUS.md) ·
> [docs/TECHNICAL_FEASIBILITY.md](docs/TECHNICAL_FEASIBILITY.md).

## Démarrage rapide
```bash
cd backend
uv sync
uv run clubdirector sync "<chemin>/Football Manager 26/games/<carriere>.fm"
uv run clubdirector ask "Quel était notre score il y a une semaine ?"
uv run clubdirector serve        # interface diagnostique : http://127.0.0.1:8765
```
Tout lancer (IA locale, téléphone, service) : double-cliquer `Lancer ClubDirector.cmd`.
Installation Windows (menu Démarrer, lancement au démarrage en option, désinstallation) :
`powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 [-Demarrage]`.
Installation complète (IA locale, plugin) : [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Principes
- Données réelles uniquement ; « non disponible » plutôt qu'une estimation.
- Sauvegardes jamais modifiées (lecture d'une copie).
- Questions factuelles résolues sans IA (coût nul) ; IA locale par défaut ; budget mensuel bloquant pour les API.
- Actions dans le jeu interdites tant qu'elles ne sont pas prouvées.

## Crédits
- Lecture des sauvegardes : [fmsave](https://github.com/rhiever/fmsave) (MIT, Randal S. Olson).
- Techniques d'UI IL2CPP étudiées dans [FM26Access](https://github.com/GreenBeanGravy/FM26Access) (MIT).

Projet non affilié à Sports Interactive ni à SEGA. Usage solo local.
