# Rapport de tests

## Session 1 — 15/10/2026 (conteneur Linux cloud, sans FM26)

| Suite | Résultat | Détail |
|---|---|---|
| `uv run pytest -q` (backend) | **68 réussis / 68** | 3,5 s |
| `uv run ruff check src tests` | **OK** | — |
| `dotnet test tests/ClubDirector.Core.Tests` | **8 réussis / 8** (+1 e2e neutre hors script) | net6.0 / net8.0 |
| `scripts/e2e_plugin_backend.sh` | **1 réussi / 1** | client C# ↔ service Python réel : battement (mode silencieux en match), chat niveau 0 « 3-1 », statut plugin, refus jeton invalide |
| Captures Chromium (Playwright) | **OK** | tableau de bord, discussion, fiche joueur, outils, paramètres en 1440×900 ; tableau de bord 390×844 sans défilement horizontal ; aucune erreur JavaScript |
| Banc de performance 100 000 joueurs (données de développement générées) | voir ci-dessous | — |

### Performance (données générées, `scripts/bench_sync.py 100000`)

| Mesure | Valeur |
|---|---|
| Import initial (SQLite) | 10,6 s |
| Synchronisation suivante (1 % de transferts) | 10,8 s |
| Recherche DC < 23 ans < 10 M | 27,5 ms |
| Recherche par nom (LIKE) | 250 ms → à optimiser (FTS5) |
| Recherche multi-attributs | 166 ms |
| Cibles « ailier centreur » (400 candidats notés) | 165 ms |
| Taille de la base | 122 Mo |

Ces temps concernent le service, **hors du processus FM26**. L'impact sur les FPS du jeu n'a **pas**
été mesuré (FM26 absent).

### Non exécuté (environnement)

- Lecture d'une vraie carrière, plugin dans FM26, overlay, modèle local réel, appel API payant :
  impossibles dans ce conteneur. Voir `TEST_PLAN.md` (A-1, R-1…R-4, P-1…P-6, L-1).
- `ClubDirector.Plugin` n'a pas été compilé : il exige les assemblages interop générés par
  BepInEx sur une installation FM26.
