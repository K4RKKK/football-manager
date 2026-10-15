# État de développement

Légende : ✅ validé par test · 🟡 codé, non validé dans FM26 · 🧪 expérimental · ⬜ non commencé · ❌ impossible (méthodes connues).

| Domaine | Élément | État | Preuve / remarque |
|---|---|---|---|
| Phase 0 | Audit environnement cloud, étude des projets, dépôt, docs | ✅ | ce dossier `docs/` |
| Phase 0 | Audit du PC Windows | ✅ | session 2 : FM26 Steam build 23583635, Unity 6000.0.52f1 IL2CPP, BepInEx absent |
| Phase 1 | Lecture club/effectif/attributs depuis un `.fm` | ✅ vraie carrière | AS Roma (26.3.0) : club, date, effectif par équipe ; valeurs à confronter à l'écran du jeu (5 attributs) |
| Données | Fork fmsave (`third_party/fmsave`) | ✅ | statuts des clubs et coups de pied arrêtés réparés sur 26.3.0 ; tactiques 26.3.0 ❌ (signature) |
| Données | Inventaire des sections (`clubdirector inventory`) | ✅ | `docs/DATA_INVENTORY.md` : 77 sections, 35 % du volume non décodé |
| Données | Atelier de décodage (`tools/decode/workbench.py`) | ✅ outil | `docs/SECTION_MAP.md` : 65 sections cartographiées (liens, pas d'enregistrement) |
| Données | Miroir intégral des tables fmsave (`fm_*`, 28 tables) | ✅ | toutes colonnes ; outils `describe_game_tables` / `query_game_table` |
| Données | Noms de compétitions stockés dans la sauvegarde | ✅ | 39 compétitions (actualités, séance de match) ; catalogue complet = base du jeu installé ⬜ |
| Données | Historique des championnats (`tc_league_history_dt`) | ✅ format / 🟡 rattachement | 174 525 saisons ; vérifié sur la réalité (Roma 2018-2025) ; 894 clubs rattachés (ordre de l'index), reste non attribué |
| Données | Disponibilité du jour : blessés en cours (retour prévu), retours récents, suspendus | ✅ | `game/availability.py`, outil get_injured_players (notre club ou un adversaire) ; règle vérifiée dans FM26 (Gabriel Jesus, Barcola, Roma sans blessé) |
| Données | Hiérarchie du vestiaire (leaders, très influents, influents, autres) | ✅ / 🟡 seuils | `Save.squad_influence()` (fork) → `fm_squad_influence`, outil get_squad_hierarchy avec l'évolution depuis la liste précédente du jeu ; vérifié sur l'écran Dynamique de groupe du 28/10/2025 (23 joueurs sur 23) ; seuils mesurés sur une seule sauvegarde ; notre club seulement (le jeu ne la calcule pas ailleurs) |
| Données | État d'esprit (moral) des joueurs | ⬜ | introuvable à ce jour : fiches joueurs, morale_manager, interaction_manager et zone de la dynamique sondés sans champ qui reproduise l'écran du jeu ; piste non confirmée : octet 97 de la fiche joueur (1 à 20) |
| Données | Marché des transferts (`transfer_man` → `Save.transfer_offers()`) | ✅ / 🟡 états | 12 253 offres (transferts, prêts, mouvements internes) : joueur, club acheteur, club vendeur, montant, dates ; états « conclue » et « échouée » vérifiés, autres codes non identifiés |
| Données | Classements du marché par poste (`shortlist_man` → `Save.player_rankings()`) | ✅ | 30 classements (14 postes + jeunes, hommes et femmes), vérifiés par les postes des joueurs ; note interne non interprétée |
| Phase 6 | Moteur vente / achat / négociation (`transfers/market.py`) | ✅ testé / 🟡 prix | acheteurs (offres réelles, profil visé, budget, besoin, standing), prix demandé / plancher / plafond, contre-offre, contrat ; 8 outils du directeur sportif |
| Données | Table des devises (`Save.currencies()`) et montants en euros | ✅ | 173 devises ; euro 1,15713 lu dans la sauvegarde, conversion à chaque synchro, étalonnage manuel prioritaire |
| Données | Historique des coupes / stats d'historique | 🧪 | structure relevée, sens non confirmé (`docs/SECTION_MAP.md`) |
| Phase 4 | IA locale (llama.cpp b11658 Vulkan + Gemma 4 26B-A4B) | ✅ | testée sur la vraie carrière : 8 questions, outils corrects, 9-65 s ; mode jeu 11,4 Go VRAM |
| Phase 4 | Rôle du directeur sportif, dossier du club automatique, prise de poste | ✅ | `ai/persona.py`, `ai/club_brief.py` ; testé sur l'AS Roma |
| Phase 4 | Lanceur unique (IA + service) | ✅ | `Lancer ClubDirector.cmd` |
| Données | Sections non décodées (≈ 58) | ⬜ | coupes, stats joueurs passées, transferts, liste de recrutement, palmarès… (`docs/SECTION_MAP.md`) |
| Phase 1 | Plugin minimal BepInEx + détection du jeu | ❌ (bloqué) | compile contre les interop réels ; BepInEx 738 se charge, mais le chargeur Doorstop (`winhttp.dll`) déclenche la protection anti-falsification de FM26 (session 2) — aucun contournement |
| Phase 1 | Outil de diagnostic | ✅ | interface web + CLI `clubdirector tool …` |
| Phase 2 | Adaptateur fmsave, normalisation, SQLite, migrations | ✅ | |
| Phase 2 | Multi-carrières, saisons, archivage des résultats | ✅ | |
| Phase 2 | Synchronisation automatique à chaque sauvegarde | ✅ | `sync/watcher.py` : fichier stable 20 s, copie sûre, verrou commun ; état dans `/api/status` |
| Phase 2 | Synchronisation rapide | ✅ | vraie carrière : 168 s → 67 s (premier import), relecture 175 s → 58-64 s ; upserts groupés, tables du miroir inchangées non réécrites, conversion par colonne, liens d'historique en temps linéaire ; contenu identique (50 tables comparées) ; le service lit l'état précédent pendant une relecture (test) |
| Fiabilité | Surveillance de l'IA locale (`ai/llm_watchdog.py`) | ✅ testé / 🟡 vrai blocage | serveur figé (requête de test `/slots` muette, ou demande sans progrès 60 s) ou arrêté : relancé avec les mêmes paramètres, demande refaite, message d'état ; test de bout en bout sur un faux serveur figé ; diagnostic lecture seule sur le vrai serveur (`clubdirector llm`) ; pas encore éprouvée sur un vrai blocage |
| Phase 3 | Overlay dans FM26 (F10) | ❌ (bloqué) | dépend de BepInEx |
| Phase 3 | Fenêtre ClubDirector externe au-dessus de FM26 | ✅ | `overlay/ClubDirector.Overlay` (WebView2, Ctrl+Alt+D, zone de notification) + page `/overlay` ; testée au-dessus de FM26 |
| Phase 4 | Identité du directeur sportif en poste (sauvegarde) | ✅ | code de fonction 10 hors départements ; vérifié sur 11 directeurs réels + confirmé par l'utilisateur (Francis Cagigao) |
| Phase 4 | Script de rôle complet (`ai/role_directeur_sportif.md`) | ✅ | rôle exact FM26, limites, méthode, style ; présentation + bienvenue testées |
| Phase 3 | Téléphone v2 : widgets (date du jeu, classement, dernier match), apps Messages, Contacts, Calendrier, Classement, Effectif (photos des joueurs), Réglages ; suggestions, sons, emojis, copie | ✅ | `web/phone.html` ; vérifié sur une copie de la vraie carrière |
| Phase 3 | Téléphone (iPhone) : accueil, Contacts, fiche, Messages | ✅ | `web/phone.html` sur `/overlay` ; fenêtre en forme de téléphone (coins arrondis, déplaçable, 3 tailles) ; testé sur la vraie carrière |
| Phase 3 | App Mercato : offres reçues / faites (joueur, club, montant, état, dates), budgets, plan de vente d'une offre reçue | ✅ | `/api/phone/mercato`, `/api/phone/sale/{uid}` (outils `get_transfer_offers`, `prepare_sale`) ; copie de la vraie carrière : 12 reçues, 9 faites, plan de Cioffi 686 k€ / 537 k€ |
| Phase 3 | Calendrier (vue du mois, fiche de match), Effectif : onze type sur terrain (9 systèmes, rotation) et notes par poste | ✅ | `/api/phone/lineup` (`propose_lineup`) ; copie : onze 4-2-3-1 identique à l'outil, notes de Dybala AMC 20 / STC 16 |
| Phase 3 | iMessage : réponses rapides, réactions (tapbacks) enregistrées, notifications groupées, écran verrouillé (prochain match + non lus) | ✅ | table `message_reactions` (migration 5) ; messages arrivés hors réponse (staff proactif) → bannière ; test de bout en bout `tests/test_phone.py` |
| Phase 3 | Réglages du téléphone : apparence, taille du texte et du téléphone, sons, bannières, aperçu, pastilles, verrouillage auto | ✅ / 🟡 taille | taille du téléphone : message `size:` à la fenêtre (OverlayForm.cs) compilé et testé en Debug ; à recompiler en Release pour l'avoir dans la fenêtre en cours |
| Données | Recherche par nom : index FTS5 trigramme (`player_names_fts`) reconstruit après chaque synchro | ✅ | copie (73 658 joueurs) : 200-2 300 ms → 2-7 ms, résultats identiques à LIKE ; reconstruction 2,2 s à la première recherche ; repli LIKE |
| Phase 4 | Trois contacts : directeur sportif, directeur technique, entraîneur adjoint | ✅ / 🟡 adjoint | DT = code 88 (Freund, Lange, Moncada, Maldini) ; adjoint = code 20 liste entraînement, équipe première, mieux payé (heuristique 5/6, corrigeable) |
| Phase 4 | Scripts de rôle DT et adjoint + format messages commun | ✅ | `role_directeur_technique.md`, `role_entraineur_adjoint.md`, `style_messagerie.md` |
| Phase 4 | Types de messages (politesse, discussion, question, demande, réponse) | ✅ | 19/19 exemples classés ; consigne adaptée à chaque type |
| Phase 4 | Réponses rapides | ✅ | réflexion coupée sauf analyse demandée, dossier après les outils (cache), préchauffage, affichage au fil de l'écriture : « ça va » 1,7 s, question 1,9 s, demande avec données 20 s |
| Phase 4 | Compositions calculées (`tools/lineup.py`, `propose_lineup`) | ✅ | affectation optimale sur les notes de poste FM26 (9 systèmes), calculée avant le modèle pour toute demande de onze ; effectif nominatif + notes dans le dossier ; plus de joueurs inventés (Rui Patrício) ni hors poste (Pellegrini ailier) |
| Phase 4 | Photos du staff | ✅ | pack de visages de l'utilisateur (`graphics/faces/<unique_id>.png`), lu en local |
| Phase 3 | Entrée dans le menu latéral natif | 🧪 | outil de relevé UI prêt (Maj+F10) |
| Phase 4 | Registre d'outils (50 disponibles / 60) | ✅ | dont `generate_scout_report`, `plan_transfer_window`, `analyze_player_performance`, `list_dossiers` (session staff vivant) |
| Phase 4 | Routage niveau 0 (sans IA) | ✅ | 13 formulations testées |
| Phase 4 | Connecteur OpenAI-compatible (llama.cpp, Ollama, OpenRouter) | ✅ | vrai modèle local (Gemma 4) |
| Phase 4 | Connecteur Anthropic (SDK officiel) | 🟡 | aucune clé dans l'environnement |
| Phase 4 | Mémoire (préférences, objectifs) | ✅ | |
| Phase 4 | Mémoire longue : décisions de l'entraîneur partagées par les trois contacts | ✅ | `memory/decisions.py` : « on ne vend pas X », « âge max 26 ans », plafonds, fin du mercato reconnus sans IA ; appliqués par les outils (vente, contre-offre, achat, cibles, plan) ; `tests/test_staff_live.py` |
| Phase 4 | Résumés de conversation | ✅ / 🟡 vrai modèle | `memory/summaries.py` : partie ancienne des fils résumée par le modèle local, placée dans le dossier du contact ; testé avec un modèle simulé |
| Phase 4 | Cache des requêtes | ⬜ | |
| Phase 5 | Recherche multicritère, score de compatibilité explicable, comparateur | ✅ | |
| Phase 5 | Brouillard de recrutement | ❌ actuellement | limitation affichée |
| Phase 6 | Dossiers suivis (achat, vente, contre-offre, contrat) | ✅ | `transfers/dossiers.py` : ouvert quand le directeur prépare l'opération, vérifié à chaque sauvegarde (offre faite / reçue / conclue / échouée, joueur parti, contrat prolongé, cible prolongée chez son club) et signalé une fois ; démontré sur la vraie carrière (voir TEST_REPORT) |
| Phase 6 | Moteur d'exécution transactionnel (table `operations`) | ⬜ | schéma prêt |
| Phase 6 | Actions dans FM26 | 🧪 | toutes marquées indisponibles |
| Phase 7 | Alertes proactives déterministes | ✅ | contrats, profondeur, forme, finances |
| Phase 7 | Messages proactifs du staff après chaque sauvegarde | ✅ | `proactive/staff_messages.py` : règles déterministes par contact (offres, contrats < 6 mois, arrivées/départs, blessures et retours, suspensions, prochain match + onze calculé, staff, finances, dossiers), un fait = un message une seule fois, rédigé par le modèle ; démontré sur la vraie carrière |
| Phase 7 | Personnalités | ✅ | 5 profils |
| Phase 8 | Installateur Windows (menu Démarrer, lancement à l'ouverture de session) + désinstallateur | ✅ | `scripts/install_windows.ps1`, `uninstall_windows.ps1` : création puis retrait vérifiés dans des dossiers temporaires ; installé sur le PC le 15/10/2026 à la demande de l'utilisateur (menu Démarrer + démarrage de Windows), environnement Python inchangé (`uv sync --inexact`) |
| Phase 8 | Intégration continue GitHub (tests, lint, .NET) | 🟡 | `.github/workflows/tests.yml` écrit, s'exécutera au premier envoi |
| Phase 8 | Profiling en jeu | ⬜ | |
