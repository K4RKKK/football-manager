---
name: fm26-save-data
description: Travailler sur la lecture des sauvegardes FM26 (fmsave), l'archivage SQLite et les outils de données de ClubDirector. À utiliser pour ajouter un champ, un lecteur, un outil de lecture/analyse, ou diagnostiquer une valeur incorrecte.
---

# Données de sauvegarde FM26 dans ClubDirector

1. **Source unique** : `backend/src/clubdirector/game/fmsave_reader.py` convertit fmsave → modèles
   `domain/models.py`. Ne jamais lire la sauvegarde originale : passer par `game/snapshot.take_snapshot`.
2. **Avant d'utiliser un champ fmsave**, vérifier son statut :
   `uv run python -c "import fmsave; print(fmsave.field_status(fmsave.Player, 'contract.wage'))"`.
   Un champ `unconfirmed` doit être ajouté à `TRACKED_FIELDS` pour que l'IA le sache.
3. **Valeurs inconnues** : garder `None`. Pas de valeur par défaut numérique, pas d'estimation.
4. **Argent** : unité interne de la sauvegarde. Toute comparaison en devise passe par
   `prefs.currency` (étalonnage) et lève `UncalibratedCurrency` sinon.
5. **Archivage** (`sync/service.py`) : les données que FM oublie (saisons passées, scores) sont
   fusionnées par upsert ; ne jamais écraser une valeur connue par `None` (`func.coalesce`).
6. **Nouvel outil** : l'ajouter dans `tools/catalog.py` avec un modèle d'arguments `ToolArgs`
   (champs inconnus refusés), renvoyer `ToolResult(..., limitations=[...])` dès qu'une donnée manque,
   et ajouter un test dans `backend/tests/test_tools.py` vérifiant la valeur contre la base.
7. **Tests** : sauvegardes synthétiques au vrai format dans `backend/tests/fixtures/saves/`
   (régénération : `scripts/generate_synthetic_saves.py`). Ce ne sont pas de vraies carrières :
   ne jamais écrire dans la doc qu'une lecture est « validée dans FM26 » sur cette seule base.
