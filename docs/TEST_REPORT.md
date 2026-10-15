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

### Session 3 (suite) — hiérarchie du vestiaire et moral
| Test | Résultat | Détail |
|---|---|---|
| Hiérarchie lue vs écran Dynamique de groupe (captures de l'utilisateur, 28/10/2025) | ✅ | liste la plus récente de l'équipe première (26/10) : 23 joueurs sur 23 dans le bon groupe (leaders Mancini, Cristante, Pellegrini) ; les 5 joueurs absents sont prêtés ailleurs ; listes plus anciennes (01/10, 21/07) en désaccord, comme attendu |
| `Save.squad_influence()` sur la vraie sauvegarde | ✅ | 11 listes (équipe première, U20, U18 ; actuelles et anciennes), 281 lignes, 0,44 s (joueurs déjà lus) |
| Outil get_squad_hierarchy (copie de la carrière) | ✅ | 3 leaders, 6 très influents, 7 influents, 8 autres ; évolution depuis le 01/10 : Koné influent → très influent |
| État d'esprit (moral) | ❌ non trouvé | fiches joueurs (décalages fixes, ancres variables, corrélation de rang), morale_manager (33 octets : compteurs), interaction_manager, zone de la dynamique : aucun champ qui sépare les 6 niveaux ; octet 97 (1-20, ρ = 0,71) gardé comme piste non confirmée, non exposé |
| fmsave (fork) `uv run pytest` | ✅ | 2 988 réussis, 1 échec d'environnement (liens symboliques) ; 5 nouveaux tests (`tests/test_dynamics.py`) |
| `pytest` backend | ✅ | 218 / 218 sur l'arbre de travail partagé, dont 3 nouveaux (`tests/test_dynamics.py`) |

### Session 3 (suite) — fiabilité de l'IA locale et synchronisation rapide
Mesures sur une copie de la vraie carrière (AS Roma, 117 Mo, 73 658 joueurs) dans une base temporaire ;
le service et l'IA en cours d'utilisation n'ont pas été redémarrés.

| Test | Résultat | Détail |
|---|---|---|
| Synchronisation, premier import (base vide) | ✅ 168 s → 67 s | avant : stats de saison écrites ligne à ligne 84 s, lecture + conversion 57 s, matchs 15 s, miroir 5 s ; après : lecture 39 s, écriture 22 s |
| Relecture d'une nouvelle sauvegarde de la même carrière | ✅ 175 s → 64 s (58 s) | tout le miroir réécrit : écriture 23 s ; tables inchangées sautées (empreinte) : écriture 17 s |
| Temps par lecteur fmsave (lecture / conversion miroir) | mesuré | joueurs 8,0 / 4,3 s ; stats de saison 2,5 / 5,0 s ; matchs 3,4 / 0,4 s ; staff 3,3 / 0,4 s ; stats de match 2,1 s ; contrats 0 / 1,9 s ; historique 1,1 / 0,3 s ; finances 1,2 s ; classements du marché 0,4 / 0,3 s ; offres 0,1 s ; autres < 1 s |
| Contenu identique avant / après | ✅ | 50 tables comparées ligne à ligne (hors identifiants et dates techniques) |
| Liens d'historique (`_unique_assignment`) | ✅ 8 s → 0,07 s | placement glouton au plus tôt / au plus tard (unique ⇔ égaux) ; 4 000 cas tirés au hasard identiques à l'ancien décompte |
| Ramasse-miettes suspendu pendant la synchro | ✅ | lecture 50 s → 42,5 s (mesure isolée) |
| `transfer_offers()` à froid (fork) | ✅ 8,1 s → 4,4 s | seuls les joueurs cités sont décodés ; table identique (12 253 offres, 6 845 noms) ; l'analyse de la section seule prend 0,09 s |
| Lecture parallèle dans un 2e processus | écartée | groupe indépendant : 21 s seul (index partagés reconstruits) pour 9 s gagnés, +1 Go de RAM pendant que FM26 tourne |
| `to_columns` colonne par colonne (fork) | écarté | sortie identique sur les 31 tables mais ≈ 0,9 s gagné seulement : modification annulée |
| Service pendant une relecture | ✅ | lecture de l'état précédent pendant la transaction ; une écriture (nouvelle conversation) attend la validation puis réussit (attente SQLite 60 s) |
| IA figée (faux llama-server, vrai processus) | ✅ | `/health` « ok », demande sans progrès : détectée, processus arrêté, relancé, demande refaite et réponse reçue en < 30 s (délais du test : relevé 0,3 s, blocage 2 s) ; message d'état transmis |
| Surveillance : cas simulés | ✅ | occupé qui avance jamais relancé ; `/slots` muet ; demande non traitée ; arrêt (relance seulement si déjà vu) ; 3 relances par heure au plus ; diagnostic sans relance ; paramètres relus sur la ligne de commande réelle (mode jeu 12, 32k, 8080) |
| Diagnostic sur le vrai llama-server (`clubdirector llm`, lecture seule) | ✅ | état « prêt », paramètres relevés : `--n-cpu-moe 12 -c 32768 --port 8080` |
| Erreurs claires | ✅ | serveur arrêté : « injoignable sur 127.0.0.1:8080 : serveur arrêté ou pas encore démarré » ; relance échouée : message et journaux à consulter |
| `pytest` backend | ✅ | 192 / 192 (nouveaux : `test_llm_watchdog.py` 14, `test_sync_speed.py` 5) ; au premier passage, `test_lineup.py` échouait pendant une modification en cours d'une autre session, réussi relancé |
| fmsave (fork) `uv run pytest` | ✅ | 2 981 réussis (+1 : noms des joueurs d'une offre), 1 échec d'environnement connu (`test_guard`, liens symboliques sous Windows) |
| Couches MoE sur le CPU en match 3D (`scripts/mesure_llm.ps1`, accord de l'utilisateur) | ✅ 12 gardé | 12 couches : carte 15,4 Go / 16, FM26 3,5 Go, 33,6 jetons/s ; 8 couches : carte 15,6 Go saturée, llama-server déborde en mémoire partagée (0,49 Go), FM26 repoussé à 2,8 Go, 35,5 jetons/s (gain dans le bruit) ; 6 non tenté ; retour à 12 |
| Relance par la surveillance : sorties du serveur | corrigé | au 1er essai réel, le serveur relancé écrivait dans la sortie du programme lanceur (risque de blocage si personne ne la lit) : il a désormais sa propre console réduite (test) ; journal sans codes couleur |

### Session 4 — téléphone : apps, interactions iMessage, recherche, installateur
Vérifié sur une copie de la vraie carrière (AS Roma, base copiée par l'API de sauvegarde SQLite, service de
test sur 127.0.0.1:8768, lecture automatique et surveillance de l'IA désactivées) dans le navigateur intégré
à la taille de la fenêtre (365×860) ; le service réel (8765) n'a pas été redémarré.

| Test | Résultat | Détail |
|---|---|---|
| App Mercato (copie) | ✅ | 12 offres reçues, 9 faites, états réels (sans suite, échouée, conclue, accord pour plus tard) ; budgets : 0 € restant sur 21,9 M€, marge salariale 50 k€/sem. |
| Fiche d'offre + plan de vente (copie) | ✅ | Cristian Cioffi (Lecce, 55 k€) : prix affiché 686 k€, plancher 537 k€, valeur du jeu 648 k€, 5 acheteurs avec raisons ; 1,8 s |
| Calendrier (copie) | ✅ | octobre 2025, jour du jeu (21) en rouge, points par match (victoire, nul, à venir) ; fiche du match à Samsunspor |
| Onze type (copie) | ✅ | 4-2-3-1 identique à `propose_lineup` (Svilar ; Wesley, Mancini, Gadou, Angeliño ; Koné, Cristante ; Soulé, Dybala, Malen ; Dovbyk), 9 systèmes, banc, rotation |
| Notes par poste (copie) | ✅ | Dybala : AMC 20, STC 16, AMR 16, AML 12, autres ≤ 6 |
| Écran verrouillé (copie) | ✅ | « Mardi 21 octobre », prochain match « Samsunspor – Roma, dans 2 jours, Europa League, extérieur », 4 notifications regroupées (2 contacts, cartes empilées) ; toucher une carte ouvre la discussion |
| Réponses rapides (copie) | ✅ | sous « Vous voulez que je commence à lister des profils… ? » : Oui, vas-y · Non · Dis-m'en plus |
| Réaction (copie) | ✅ | double-clic → barre de réactions → ❤️ ; enregistrée côté serveur (message 77) et relue |
| Notifications groupées | ✅ | 2 messages d'un contact → « 2 messages » ; 2 contacts → bannière « Messages, 3 nouveaux messages » ; message du staff arrivé hors réponse (inséré dans la copie) → bannière et pastille au rafraîchissement |
| Réglages | ✅ | thème clair/sombre/auto, texte grand, sons, bannières, aperçu, pastilles, verrouillage, réponses rapides |
| Recherche par nom (copie, 73 658 joueurs) | ✅ | LIKE : 200-2 300 ms → FTS5 trigramme : 2-7 ms, mêmes joueurs (dybala, pellegrini, kon, ndicka, koné, ma) ; index construit en 2,2 s à la première recherche ; vérification à chaque appel 1-2 ms |
| Installateur (dossiers temporaires) | ✅ | prérequis détectés (uv 0.12.7, .NET 8.0.417, WebView2 155) ; raccourcis menu + démarrage (powershell réduit → `start_clubdirector.ps1`), `config.toml`, `install.json` ; désinstallation : 3 raccourcis et dossier retirés, données gardées ; simulation sur la vraie machine sans modification |
| Fenêtre C# (taille demandée par la page) | ✅ Debug | `dotnet test ClubDirector.Overlay.Tests` : 10 / 10 |
| `pytest` backend | ✅ | 192 / 192 sur l'arbre de travail partagé, 180 / 180 sur le seul contenu committé (HEAD + téléphone), dont `tests/test_phone.py` (7) : Mercato, plan de vente, onze, calendrier, réactions, index des noms (+ repli LIKE) et **parcours de bout en bout dans Edge sans fenêtre** (vrai service HTTP, vraie page : écran verrouillé, déverrouillage, Mercato, plan de vente, calendrier, onze 11 joueurs, notes 15 postes, réponses rapides, réaction 👍 enregistrée, réponse diffusée, aucun texte d'outil, réglages, verrouillage) |
| `ruff check src tests` | ✅ | — |
| Poste après le nom du staff (demande de l'utilisateur, copie) | ✅ | « Paolo Maldini (Directeur technique) », « Francis Cagigao (Directeur sportif) », « Antonio Gagliardi (Entraîneur adjoint) » dans Messages, Contacts, nouveau message, fiche, bannière et écran verrouillé ; en-tête de conversation : nom puis poste en petit |
| État de l'IA locale pendant une réponse | ✅ | évènement SSE `status` (relance de llama-server figé) affiché en petit sous les trois points |
| Messages proactifs du staff | ✅ | détectés par l'identifiant du dernier message (`last.id`) au rafraîchissement : son + bannière, ou fil rechargé et lu s'il est ouvert ; `pytest` : 215 / 215 |
| Installation réelle sur le PC (`install_windows.ps1 -Demarrage`, accord de l'utilisateur) | ✅ | 3 raccourcis (menu Démarrer : lancer, désinstaller ; dossier Démarrage : `start_clubdirector.ps1` en fenêtre réduite), `install.json` ; `uv sync --inexact` sans changement (un `uv sync` simple aurait retiré anthropic, keyring et 11 dépendances : corrigé avant le lancement) ; téléphone ouvert : recompilation Release reportée |

### Session 3 (suite) — staff vivant : messages proactifs, dossiers, mémoire longue, outils
Démonstration sur une **copie** de la vraie carrière (base copiée par l'API de sauvegarde SQLite, dossier de
données séparé `CLUBDIRECTOR_HOME` + `CLUBDIRECTOR_CONFIG`, port 8775, `auto_sync = false`,
`staff_proactive = true`, surveillance de l'IA coupée ; vraies sauvegardes de la carrière AS Roma copiées depuis
`snapshots/` et relues dans l'ordre : 21/10, 25/10, 27/10/2025 ; IA locale Gemma 4). Le vrai service n'a pas été touché.

| Test | Résultat | Détail |
|---|---|---|
| Messages proactifs, sauvegarde du 21/10 | ✅ | relecture 63 s ; 2 faits, 2 messages : l'adjoint (Gagliardi) annonce Samsunspor (Ligue Europa, 23/10) avec le onze calculé (Svilar ; Wesley, Mancini, Gadou, Angeliño ; Koné, Cristante ; Soulé, Dybala, Malen ; Dovbyk) et propose de ménager des cadres ; le DT (Maldini) signale trois mois de résultat net négatif. Rien d'inventé, aucune mention de l'IA ni de la sauvegarde |
| Demande d'achat au DS (« Prépare-moi une offre pour Juanlu », « … Lewis Thomas, le gardien sans club ») | ✅ après correctif | 1er essai : le modèle chiffre Juanlu avec `evaluate_transfer_value` (aucun dossier) et répond sur Lewis Thomas SANS données (âge 28 au lieu de 23, montants inventés). Corrigé : demande d'achat reconnue sans IA (`transfers/operations.py`), plan calculé avant le modèle, homonyme choisi par les indices (« gardien », « sans club ») : 37,6 / 47,0 / 54,1 M€ pour Juanlu, offre réelle concurrente de Peterborough repérée pour Lewis Thomas ; 2 dossiers ouverts |
| Décisions (« on ne vend pas Soulé, et âge max 27 ans pour les recrues ») | ✅ | 2 souvenirs structurés ; réutilisés ensuite par le DS (« d'autres profils de moins de 27 ans ? ») |
| Suivi des dossiers, sauvegarde du 25/10 | ✅ | relecture 81 s ; Cagigao écrit de lui-même : « Séville vient de prolonger Juanlu jusqu'en juin 2030 … Pour Lewis Thomas, c'est fini : il vient de signer à Peterborough United » — deux événements réels de la carrière (contrat 2029 → 2030 ; joueur libre → Peterborough) ; dossiers : Juanlu ouvert (prolongation notée, prix réestimé), Lewis Thomas « joueur parti ailleurs » (clos) ; l'adjoint annonce Torino (26/10) avec son onze |
| Pas de doublon, sauvegarde du 27/10 | ✅ | relecture 79 s ; 1 seul fait nouveau (Parme, 29/10, à domicile) → 1 seul message, de l'adjoint, avec exactement le onze calculé (Soulé, Batrakov, Zaragoza ; Malen en pointe) ; dossiers et finances déjà signalés : rien de répété ; 6 faits signalés au total en 3 sauvegardes |
| Résumé de conversation (vrai modèle) | ✅ | fil du DS (24 messages) résumé pendant le travail de fond : 6 tirets (budget à 0 €, prolongations Pellegrini et Dybala, profondeur en attaque, décision, demande en cours, stratégie) |
| Outils sur la vraie carrière | ✅ < 1 s | `analyze_player_performance` (Dovbyk : 0,55 but/90, 83e percentile ; xA/90 99e ; 412 attaquants) ; `generate_scout_report` (Juanlu : rôles, percentiles, marché 47,0 M€, 38e/6834 au poste, « hors budget actuel ») ; `plan_transfer_window` (budget 0 €, enveloppe si ventes, Dybala à prolonger, Pellegrini à vendre ou laisser partir, cibles filtrées par l'enveloppe). Défauts corrigés pendant l'essai : comparaison faite sur le championnat des U19 du club (équipe réserve) et budget à 0 € qui désactivait le filtre de prix (Haaland proposé) |
| `pytest` backend | ✅ | `tests/test_staff_live.py` (13 tests : un fait = un message, rédaction par le modèle, blessures et retours, poste vacant, cycle d'un dossier sur trois sauvegardes, cible qui prolonge puis signe ailleurs, changement gardé jusqu'au signalement, décisions sans IA, décision partagée et appliquée par les outils, résumé, outils, routes) ; suite complète 215 / 215 |
