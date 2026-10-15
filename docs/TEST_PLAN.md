# Plan de tests

## Automatisés (exécutés à chaque session)

| Suite | Commande | Couvre |
|---|---|---|
| Backend Python (68 tests) | `cd backend && uv run pytest -q` | sauvegarde intacte, lecture `.fm`, archivage, isolation, fraîcheur, outils, modes de connaissance, refus des actions, routage, budget, API, sécurité |
| Plugin — cœur C# (8 tests) | `cd plugin && dotnet test tests/ClubDirector.Core.Tests` | client HTTP, jeton, file du thread principal, session de chat |
| Bout en bout plugin ↔ service | `scripts/e2e_plugin_backend.sh` | client C# réel contre service Python réel (carrière synthétique) |
| Performance (dev) | `uv run --project backend python scripts/bench_sync.py 100000` | import et recherches sur 100 000 joueurs générés |
| Lint | `cd backend && uv run ruff check src tests` | — |

## Sur le PC de l'utilisateur (non exécutables dans le conteneur cloud)

Toujours travailler sur une **copie** de la sauvegarde ; ClubDirector copie de toute façon le fichier
avant lecture.

| Id | Test | Procédure | Critère de réussite |
|---|---|---|---|
| A-1 | Audit environnement | `powershell -ExecutionPolicy Bypass -File scripts\audit_windows.ps1` | Rapport `audit-report.json` produit (FM26, BepInEx, saves, GPU, outils) |
| R-1 | Lecture d'une vraie carrière | `uv run clubdirector sync "<chemin>\carriere.fm"` | Club géré, date de jeu, effectif et 5 attributs identiques à l'écran du jeu |
| R-2 | Questions exactes | `clubdirector ask "Quel était notre score il y a une semaine ?"` etc. | Réponse identique au calendrier du jeu |
| R-3 | Étalonnage devise | Paramètres → Étalonnage avec la valeur affichée d'un joueur | Valeur de 3 autres joueurs identique (±1 %) à l'affichage du jeu |
| R-4 | Deux carrières | Synchroniser deux sauvegardes différentes | Deux carrières distinctes, aucune donnée mélangée |
| P-1 | Chargement du plugin | Installer BepInEx 6 BE ≥ 738, compiler `ClubDirector.Plugin` avec `/p:FMPath=…`, lancer FM26 | `LogOutput.log` contient « ClubDirector AI v0.1.0 chargé » ; jeu stable 30 min |
| P-2 | Battement de cœur | `clubdirector serve` puis FM26 | Diagnostic : « Plugin FM26 : connecte » |
| P-3 | Overlay | F10 dans le jeu | Panneau visible, saisie possible, réponse niveau 0 affichée, F10 referme ; aucune chute de FPS mesurable |
| P-4 | Relevé UI | Maj+F10 sur l'écran d'accueil | Fichier `ui-dump-*.txt` contenant `PanelManager` et le menu latéral |
| P-5 | Entrée de menu native | (après P-4) | Bouton visible dans le menu, survit aux changements d'écran |
| P-6 | Action shortlist | (phase 6) | Joueur visible dans la liste de recrutement FM26 après l'action ; journal `operations` cohérent |
| L-1 | Modèle local | llama.cpp `llama-server --jinja -m <gguf> --port 8080` (Vulkan) | `POST /api/ai/test` OK ; « Fais-moi un bilan de l'effectif » appelle `analyze_squad` |

## Tests IA à évaluer sur vraie sauvegarde (section 19.2)

Pour chaque question, vérifier automatiquement la réponse contre la base (`tool_audit`, `season_stats`) :
« Qui est notre meilleur buteur ? », « Combien X a-t-il marqué la saison dernière ? » (saison,
compétitions incluses), « Quel était notre score il y a une semaine ? » (date du jeu),
« Propose-moi trois défenseurs centraux de moins de 23 ans et à moins de 10 millions »
(âge, poste, valeur, existence — automatisé dans `test_search_results_are_verified_against_criteria`).
