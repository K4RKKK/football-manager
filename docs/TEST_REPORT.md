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

### Session 2 (suite) — devises
| Test | Résultat | Détail |
|---|---|---|
| `Save.currencies()` sur la vraie sauvegarde | ✅ | 173 devises, index 0-172 vérifiés, 0,02 s ; livre = 1,0 ; euro = 1,15713 (« € ») |
| Conversion automatique (`/api/status`, outils) | ✅ | budget transferts 21,9 M€, marge salariale 50 k€/sem., Lamine Yamal 312,4 M€ |
| fmsave (fork) `uv run pytest` | ✅ | 2 970 réussis, 1 échec d'environnement (liens symboliques) |
| `pytest` backend | ✅ | 112 / 112 |

### Session 2 (suite) — intégration dans FM26
| Test | Résultat | Détail |
|---|---|---|
| P-1 BepInEx dans FM26 | **chargé** | 159 assemblages interop générés, « Chainloader startup complete », ErrorLog vide |
| Compilation du plugin contre les interop réels | **OK** | 2 corrections (surcharge `Q`, attributs de nullabilité) ; tests du cœur 9/9 |
| Démarrage de FM26 avec BepInEx | **échec** | protection anti-falsification : serveur inaccessible puis activation hors ligne, fermeture |
| FM26 avec BepInEx désactivé, `winhttp.dll` présent | **échec** | même message (journal BepInEx inchangé : le mod n'a pas tourné) |
| FM26 sans `winhttp.dll` | **OK** | démarrage normal, aucune fenêtre de protection |
| Conclusion | — | le chargeur Doorstop suffit à déclencher la protection ; injection suspendue, aucun contournement |

### Session 2 (suite) — fenêtre externe, synchronisation automatique, identité du directeur
| Test | Résultat | Détail |
|---|---|---|
| Fenêtre au-dessus de FM26 (FM26 ouvert) | **OK** | 460 px à droite, WS_EX_TOPMOST, rendu vérifié par capture ; reconnexion automatique au service |
| Discussion dans la fenêtre (vraie carrière) | **OK** | prise de poste rendue (titres, listes, gras), 62 s en mode jeu |
| Synchronisation automatique | **OK (tests)** | stabilité 20 s, sauvegardes `*backup*` ignorées, erreurs non bloquantes ; active sur le dossier `games` |
| Détection du directeur sportif | **OK** | 11/11 directeurs réels = code 10 hors départements ; AS Roma → Francis Cagigao (confirmé par l'utilisateur) |
| Présentation du directeur (vrai modèle) | **OK** | 63 s : identité, âge, arrivée, contrat, méthode issue de son profil, état des lieux conforme, 3 priorités |
| Réponse à la bienvenue | **OK** | 35 s : remerciement bref, prêt à travailler, première étape concrète |
| `pytest` backend | **112 / 112** | tests fenêtre (C#) 6/6, cœur du plugin 9/9 |

### Session 3 — téléphone, trois contacts, rapidité
| Test | Résultat | Détail |
|---|---|---|
| Détection DT / adjoint (vraie carrière) | ✅ | Paolo Maldini (DT, code 88), Antonio Gagliardi (adjoint) ; photos trouvées pour les trois |
| Bonne photo | ✅ | le pack est indexé par `unique_id` (Dybala 14044150, Maldini 45 vérifiés à l'image) |
| Cause des 105 s sur « Comment ça va Francis ? » | corrigé | prise de poste forcée sur la question + 8 consultations + réflexion du modèle |
| Réflexion du modèle (mesure) | — | 1 200-1 500 tokens, 40-54 s ; coupée par défaut |
| Cache du prompt par contact | ✅ | changement de contact : 0,5 s au lieu de 13 s (cache mémoire de llama-server) |
| « Salut Francis, ça va ? » (téléphone, copie de test) | ✅ **1,7 s** | premiers mots 1,2 s ; une bulle |
| « Combien il nous reste sur la marge salariale ? » | ✅ **1,9 s** | 50 k€/semaine, juste |
| « Prépare-moi la prolongation de Dybala » | ✅ 20 s | 3 consultations (fiche, contrat, stats) ; plan chiffré + gestes à faire dans FM26 |
| Types de messages | ✅ | 19/19 exemples (politesse, discussion, question, demande, réponse) |
| Fenêtre téléphone (C#) | ✅ | 10/10 tests ; rendu vérifié par capture d'écran |
| `pytest` backend | ✅ | 122 / 122 |
| Défaut constaté | ouvert | llama-server bloqué une fois (relancé avec journal) ; préchauffage limité aux prompts modifiés |

### Session 3 (suite) — téléphone v2
| Test | Résultat | Détail |
|---|---|---|
| Classement : doublon d'équipe | corrigé | Bologne apparaissait deux fois (ligne d'une phase antérieure) ; une ligne par club, la plus avancée (test) |
| Apps sur la vraie carrière (copie) | ✅ | Calendrier 10 matchs à venir + résultats ; Classement Serie A (Roma 3e, +8) ; Effectif 24 joueurs, 24 photos |
| Premier message de l'adjoint (vrai modèle) | ✅ 3,9 s | tutoiement, prochain match et rotation tirés du dossier |
| Fiche contact | ✅ | bloc « Profil » retiré (demande de l'utilisateur) ; salaire en € par semaine |
| Défilement parasite de l'écran | corrigé | `focus({preventScroll})` + `overflow: clip` |
| `pytest` backend | ✅ | 123 / 123 |

### Session 3 (suite) — marché des transferts
| Test | Résultat | Détail |
|---|---|---|
| `Save.transfer_offers()` sur la vraie sauvegarde | ✅ | 12 253 offres en 7,3 s ; Batrakov Lokomotiv → Roma 12,96 M£ (offre 28/07, arrivée 31/07), Gadou Salzburg → Roma, Hugo López (accord pour le 02/01/2026) |
| Champs vérifiés statistiquement | ✅ | transfert conclu → joueur au club acheteur 1 855/1 857 ; prêt conclu → club prêteur = club du joueur 505/532 ; type 10 = mouvement interne (Braga → Braga B) |
| `Save.player_rankings()` | ✅ | 229 361 entrées en 1,5 s ; classement des gardiens = 300/300 gardiens, etc. ; Svilar 10e gardien du monde |
| Outils marché (copie de la carrière) | ✅ | offres reçues (12), acheteurs d'Hermoso (Napoli : offre réelle 8,5 M€, Tottenham), vente de Rensch, achat d'Hugo López (notre accord détecté), contre-offre, prolongations Dybala / Pellegrini |
| Directeur sportif, IA locale : « Vends-moi Mario Hermoso… » | ✅ | 4 consultations (fiche, historique, valeur, acheteurs) ; prix 13,8-15,8 M€, plancher 12,4 M€, Napoli puis Tottenham, geste à faire dans FM26 ; 118 s (prompt recalculé + 4 consultations) |
| Tests fork / backend | ✅ | fork : 6 nouveaux tests (`tests/test_transfers.py`) ; backend : 6 nouveaux (`tests/test_transfers.py`) |
| « On veut faire venir Hugo López : prépare-moi l'offre, le plafond et le contrat » | ✅ après correctif | 1er essai : pris pour une discussion (demande après « : »), aucun calcul ; corrigé (détection des demandes) : 43 s, plan d'achat, accord existant détecté (5,3 M€ au 02/01/2026), structure 40 % + 2 versements, contrat 5 ans |
| « Prépare-moi la prolongation de Lorenzo Pellegrini » | ✅ après correctif | 1er essai : 5 échecs de fiche (deux homonymes) puis chiffres inventés ; corrigé (homonyme du club d'abord, outils nommés dans le script) : 18 s, 3 ans, 131 k€ cible / 150 k€ plafond, +6 k€/sem. |

### Session 3 (suite) — joueurs réels et compositions
| Test | Résultat | Détail |
|---|---|---|
| Joueur inventé (« Rui Patrício ») | corrigé | effectif COMPLET nominatif dans le dossier + règle commune ; onze contre Samsunspor 100 % tiré de l'effectif |
| Joueur hors poste (Pellegrini ailier droit) | corrigé | `propose_lineup` : Pellegrini MC 20/AMC 20 jamais ailier ; onze réel 4-2-3-1 : Svilar ; Wesley, Mancini, Gadou, Angeliño ; Koné, Cristante ; Soulé, Dybala, Malen ; Dovbyk (postes notés 18-20) |
| Demande de onze (vrai modèle, copie) | ✅ 6,8 s | composition calculée reprise telle quelle, absents demandés |
| Détection (« onze », « compo », « en 4-3-3 », « sans X », rotation) | ✅ | tests `test_lineup.py` |
| `pytest` backend | ✅ | 138 / 138 |

### Session 3 (suite) — disponibilité du jour
| Test | Résultat | Détail |
|---|---|---|
| Règle des blessures vérifiée dans FM26 par l'utilisateur | ✅ | Gabriel Jesus : « entorse des ligaments croisés », retour prévu au 07/11 (jeu : « 6 jours - 2 semaines ») ; Barcola (date passée) non blessé ; Roma : aucun blessé, aucune ligne |
| Outil get_injured_players (copie de la carrière) | ✅ | Roma : vide ; Arsenal : Gabriel Jesus (17 jours) ; Samsunspor : 3 retours récents ; club homonyme féminin écarté ; 0,6 s |
| `pytest` backend | ✅ | 3 nouveaux tests (`tests/test_availability.py`) ; suite complète : 155 réussis, 2 échecs dans le travail en cours de la session Fiabilité (surveillance de l'IA), sans lien |
