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

## Session 2 — 15/10/2026 (PC Windows 11 de l'utilisateur, FM26 Steam installé)

| Suite / test | Résultat | Détail |
|---|---|---|
| A-1 audit (`scripts/audit_windows.ps1`) | **OK** (après correctif) | FM26 Steam build 23583635, Unity 6000.0.52f1, IL2CPP, BepInEx absent ; le script perdait l'entrée FM26 sans `doorstop_config.ini` |
| R-1 lecture d'une vraie carrière (AS Roma, build 26.3.0) | **OK** | club, manager, date 21/10/2025, 3e (14 pts), effectif équipe première 24 joueurs réels ; sauvegarde originale intacte (SHA-256 identique avant/après) |
| Équipes du club | **OK** | 24 (équipe première) / 26 (Primavera) / 24 (U18) — avant : 74 mélangés |
| Statuts des clubs (fork fmsave) | **OK** | réputation + dernière position : 29 765 / 29 800 clubs (avant : 2) ; Roma 7942, 5e |
| Coups de pied arrêtés | **OK** | 61 routines (avant : lecteur en échec) |
| Tactiques (26.3.0) | **échec documenté** | blocs lus, enregistrements de signature inconnue → 0 tactique |
| `uv run pytest -q` (backend) | **77 / 77** | + tests équipes, migration 2, relecture après révision du lecteur, inventaire |
| fmsave (fork) `uv run pytest` | **2 950 réussis**, 1 échec d'environnement | `test_guard` : liens symboliques non autorisés sous Windows (sans rapport avec la lecture) |
| `dotnet test` (cœur du plugin) | **9 / 9** | — |
| Synchronisation réelle | 108–118 s | 73 658 joueurs, 41 220 matchs, 210 376 lignes de stats : **à optimiser** |

### Session 2 (suite) — lecture intégrale
| Test | Résultat | Détail |
|---|---|---|
| Miroir des tables fmsave | **OK** | 28 tables `fm_*` remplies sur la vraie carrière ; +18 s de synchronisation ; base ≈ 800 Mo |
| Accès IA (`query_game_table`) | **OK** | staff de la Roma, xG/passes progressives/distance par joueur ; colonnes cachées refusées en mode réaliste ; injection refusée |
| Noms de compétitions | **OK** | 39 noms (dont « Italian Serie A ») ; matchs et classements nommés |
| Historique des championnats | **OK** | Roma 2018/19 → 2024/25 identique à la réalité (positions, V/N/D, buts, points) |
| Doublons à la relecture | **corrigé** | classements dupliqués à chaque relecture d'un relevé → migration 3 + test |
| `pytest` backend | **91 / 91** | fmsave (fork) : **2 961** réussis, 1 échec d'environnement (liens symboliques) |

### Session 2 (suite) — IA locale réelle (Gemma 4 26B-A4B, llama.cpp b11658 Vulkan, RX 9070 XT)
| Question (carrière AS Roma, 21/10/2025) | Route | Durée | Outils | Vérification |
|---|---|---:|---|---|
| Bilan complet de l'effectif | niveau 1 | 37 s | analyze_squad, identify_weak_positions, analyze_contract_risks, evaluate_youth_prospects, budgets | chiffres conformes (24 joueurs, contrats Pellegrini/Dybala, budget 0) |
| Prise de poste | niveau 1 | — | dossier du club | état des lieux conforme (3e, 14 pts, buteurs, contrats, finances) |
| Joueurs dangereux xG / xA | niveau 1 | 23 s | get_top_players_stat ×2 | xG et xA identiques à fm_player_season_stats |
| 5 ailiers droits < 24 ans | niveau 1 | 47 s | get_club_squad, budgets, find_recruitment_targets | joueurs réels ; budget 0 signalé |
| Serie A, 5 dernières saisons | niveau 1 | 9 s | get_club_league_history | conforme à la réalité |
| Staff et contrats | niveau 1 | 31 s | get_club_staff | noms et dates conformes ; rôle non inventé |
| Recrue à 200 M | niveau 1 | 15 s | dossier | refus argumenté (budget 0) |
| Prochain match + quoi surveiller (API, mode jeu) | niveau 1 | 65 s | get_upcoming_matches, get_injured_players, get_alerts | conforme |
| Mesures | — | — | — | pleine puissance 14,9 Go / 116 tok/s ; mode jeu 11,4 Go / 41 tok/s |
| `pytest` backend | — | — | — | **103 / 103** |

Défauts corrigés pendant les tests : xA non disponible (outil étendu à 104 stats), staff (outil
implémenté), question fait + avis traitée sans IA (routage), préférences avec BOM.
Restant : montants en unité brute tant que la devise n'est pas étalonnée (R-3).
