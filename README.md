# ClubDirector AI

Directeur sportif IA pour **Football Manager 26** : il lit votre carrière (sauvegarde `.fm`),
archive son historique, répond en français à partir des vraies données, recommande des recrues
avec un score explicable, et s'affiche dans le jeu via un plugin BepInEx (expérimental).

> **État (session 1)** : backend complet et testé sur des sauvegardes synthétiques au vrai format
> FM26 ; plugin écrit mais **pas encore validé dans le jeu** ; aucune action dans FM26 disponible.
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
