# Rapport de faisabilité technique — ClubDirector AI

_Dernière mise à jour : 15/10/2026 (session 1)._

## 0. Contexte de l'audit — à lire en premier

L'audit initial a été exécuté dans un **conteneur Linux cloud** (Ubuntu 24.04, 4 vCPU, 15 Go RAM,
sans GPU), **pas sur le PC Windows 11 de l'utilisateur**. Conséquences :

| Point demandé (§3.1) | Résultat |
|---|---|
| Version de Windows, installation FM26, plateforme (Steam/Epic), dossier du jeu | **Non vérifiable ici** — aucun FM26 présent. |
| Dossier des sauvegardes, fichiers `.fm` | **Aucune sauvegarde réelle disponible.** |
| Version Unity / IL2CPP / BepInEx installés | Non vérifiable localement ; sources publiques ci-dessous. |
| GPU (RX 9070 XT), llama.cpp, Ollama | Non vérifiable ici (pas de GPU dans le conteneur). |
| Python / Git / Node / .NET | Python 3.13.16, Git, Node 22.22, uv ; SDK .NET 8.0.426 installé dans le dossier temporaire de session. |

**Aucune fonctionnalité n'est donc « confirmée dans FM26 » à ce stade.** Les validations faites
utilisent des sauvegardes synthétiques au **vrai format conteneur `.fm`** (voir §3), et le protocole
plugin ↔ service a été testé de bout en bout hors du jeu. Le script `scripts/audit_windows.ps1`
réalise l'inventaire §3.1 sur le PC de l'utilisateur (lecture seule).

## 1. Projets existants étudiés

| Projet | Licence | Technique | Ce que nous réutilisons | Limites |
|---|---|---|---|---|
| **fmsave** 0.5.10 (rhiever) | MIT | Lecture du conteneur `.fm` (en-tête 26 octets + trames zstd + répertoire), 27 lecteurs, statut « vérifié / non confirmé » par champ | **Dépendance directe** (`fmsave==0.5.10`) pour le mode B ; constructeur de sauvegardes synthétiques pour les tests | Saison en cours seulement pour les stats ; scores partiels ; pas de dispo du jour, compositions, dette, prix demandés ; argent en unité interne ; noms de compétitions absents ; layouts 26.1.0 et 26.3.2 |
| **FMSuperScout** (mavarobli) | « MIT » déclaré dans `package.json` seulement (pas de fichier LICENSE) | BepInEx 6 BE #738 IL2CPP, `ReadProcessMemory` sur son propre processus, offsets codés en dur (26.3.x), dump JSON + serveur Node | Idées : travail hors thread principal, écriture atomique, garde de version. **Aucun code copié** (licence ambiguë) | Offsets cassés à chaque patch, date de jeu imprécise (±2 sem.), pas d'UI dans le jeu |
| **FM26Access** (GreenBeanGravy) | MIT | BepInEx 6 IL2CPP, UI Toolkit : document `PanelManager`, parcours des VisualElement, `TryCast`, activation de boutons (`SIButton`, `ClickEvent`, pointeur positionné, menu contextuel) | Techniques d'overlay (UIDocument + PanelSettings empruntés), relevé d'arbre UI borné, conversion de délégués. Code réécrit, pas copié | Pas d'injection dans les documents du jeu ; pas d'API de vérification des actions ; auto-updater sans signature |
| **The Director / ImmersiveFM** | Non trouvée (gratuit + Patreon) | Plugin BepInEx IL2CPP **+ panneau overlay (F7)**, lit le **fichier de sauvegarde** ~30 s après l'enregistrement, pas de lecture mémoire, brouillard de recrutement, IA : serveur hébergé / clé Anthropic / Claude Code local / API compatible OpenAI | **Confirme que l'architecture « overlay + lecture de sauvegarde » est viable et utilisée en production** | Code fermé |
| **FM26 AI Dialogue** (manicmillions) | Non trouvée, DLL fermée | BepInEx 6 IL2CPP, réécrit les dialogues (Groq, Gemini, OpenRouter, compatible OpenAI) | Rien (code fermé, cibles Harmony inconnues) | — |

Sources : README/sources clonés (fmsave, FMSuperScout, FM26Access), immersivefm.app,
fmscout.com, thunderstore.io (pack BepInEx FM26), github.com/LionelFW/fm26ultrawidefix.

## 2. Faits techniques FM26 (sources publiques)

- Moteur **Unity 6, IL2CPP** (FM26Access, articles communautaires) ; version exacte d'Unity non trouvée.
- UI **Unity UI Toolkit** (`UIDocument`, `PanelSettings`, `VisualElement`), pas uGUI (fm26ultrawidefix, FM26Access).
- **BepInEx 6 Bleeding Edge IL2CPP ≥ build 738** fonctionne (pack Thunderstore avec correctif Il2CppInterop).
  FM se relance lui-même : `ignore_disable_switch = true` requis dans `doorstop_config.ini`.
- Protection **Denuvo** ; aucune preuve d'anti-triche en solo. L'EULA SEGA générique interdit la
  rétro-ingénierie « sauf si la loi le permet » : **risque juridique à évaluer par l'utilisateur** ;
  le projet reste en lecture seule (sauvegarde) et sans contournement de protection.
- Sauvegardes : `Documents\Sports Interactive\Football Manager 26\games\*.fm` (habituel), zstd, non chiffrées.

## 3. Matrice des fonctionnalités

Légende : ✅ confirmée par test · 🟡 probable, non testée dans FM26 · 🧪 expérimentale · ❌ impossible avec les méthodes connues.
« Version testée » = build du layout fmsave des sauvegardes synthétiques (26.3.2+2329565) ; **aucune vraie carrière testée**.

| Fonctionnalité | Statut | Source / méthode | Version testée | Difficulté | Risques | Plan alternatif |
|---|---|---|---|---|---|---|
| Copie sûre de la sauvegarde (original intact, détection d'écriture en cours) | ✅ | `game/snapshot.py`, tests `test_save_safety.py` | synthétique | Faible | Sauvegarde OneDrive/Steam Cloud verrouillée | Réessai, message clair |
| Lecture conteneur `.fm` → club géré, date de jeu, joueurs, attributs, contrats, matchs, stats de saison, finances, classements, tactiques (nom/mentalité), blessures historiques | ✅ (format) / 🟡 (vraie carrière) | fmsave 0.5.10 | 26.3.2 synthétique | Faible | Patch FM26 → nouveau layout fmsave | Épingler la version, mettre à jour fmsave ; signaler `known_build=False` |
| Normalisation + SQLite + isolation multi-carrières | ✅ | `sync/service.py`, `test_reader_and_sync.py` | synthétique | Moyenne | Fusion erronée de carrières | Empreinte prudente (manager + DB + nom de fichier) ; fusion manuelle seulement |
| Archivage historique (saisons passées, scores, transferts observés) | ✅ | upserts, `player_history` | synthétique | Moyenne | Trous si l'utilisateur ne synchronise pas | Synchronisation automatique à chaque sauvegarde (à faire, phase 2b) |
| Fraîcheur : un transfert est reflété à la synchro suivante | ✅ | `test_transfer_is_reflected_at_next_sync` | synthétique | Faible | Données entre deux sauvegardes | Mode A (plugin) futur |
| Scores manquants signalés, jamais inventés | ✅ | `None` conservé, coalesce à l'archivage | synthétique | Faible | — | — |
| Statistiques détaillées des saisons non archivées | ❌ | FM26 n'en garde que la saison en cours (fmsave) | — | — | — | L'assistant le dit explicitement |
| Disponibilité du jour, compositions, dette, prix demandés | ❌ (via sauvegarde) | non lus par fmsave | — | — | — | Lecture UI via plugin (🧪) |
| Instructions tactiques détaillées / rôles | ❌ (actuellement) | codage non confirmé dans fmsave | — | Élevée | Mauvaise interprétation | Outil marqué indisponible |
| Montants en devise affichée | 🟡 | Étalonnage utilisateur (valeur affichée ÷ brute) | synthétique | Faible | Facteur non linéaire ou par devise | Refus de comparer tant que non étalonné |
| Brouillard de recrutement (mode réaliste strict) | ❌ (actuellement) | connaissance des recruteurs non lue | — | Élevée | Fuite d'information | Attributs cachés/CA/PA masqués ; limitation affichée à chaque résultat |
| Service local 127.0.0.1, jeton, garde Host | ✅ | `api/app.py`, `test_api.py` | — | Faible | — | — |
| Interface diagnostique hors jeu | ✅ | `web/index.html`, captures Chromium bureau + mobile | — | Faible | — | — |
| Chat niveau 0 (sans IA) sur questions factuelles | ✅ | `ai/router.py`, `test_ai.py` | synthétique | Faible | Couverture des formulations | Repli vers l'IA |
| Boucle d'outils LLM (format OpenAI : llama.cpp/Ollama/OpenRouter) | ✅ (protocole simulé) / 🟡 (vrai modèle) | `openai_compat.py`, transport simulé | — | Moyenne | Qualité du tool calling des petits modèles locaux | Niveau 2 API économique |
| Connecteur Anthropic (SDK officiel, Haiku 5.5 / Opus 5.5) | 🟡 | `anthropic_provider.py` (non appelé : aucune clé ici) | — | Faible | Coût | Budget mensuel bloquant |
| Budget mensuel et routage économique | ✅ | `test_monthly_budget_blocks_paid_provider` | — | Faible | — | — |
| Client C# plugin ↔ service (battement, chat, jeton) | ✅ (hors jeu) | `ClubDirector.Core` + `scripts/e2e_plugin_backend.sh` | — | Faible | — | — |
| Chargement du plugin BepInEx dans FM26 | ❌ (constaté) | BepInEx 738 se charge, mais le chargeur `winhttp.dll` déclenche la protection anti-falsification | Steam 23583635 | — | Réactivation exigée, fermeture du jeu | Interface externe au-dessus du jeu (hors processus) |
| Panneau overlay UI Toolkit dans le jeu (raccourci F10) | ❌ (bloqué, dépend de BepInEx) | UIDocument + PanelSettings empruntés (technique FM26Access) | — | Moyenne | PanelSettings, focus clavier, raccourcis du jeu | Interface externe de secours |
| Entrée « Directeur sportif IA » dans le menu latéral natif | 🧪 | Relevé d'arbre UI (Maj+F10) puis insertion dans le slot du menu | — | Élevée | Reconstruction des écrans par FM | Overlay + raccourci |
| Détection « carrière chargée » en direct | 🧪 | Non implémenté (pistes : écran courant, événements de chargement) | — | Moyenne | — | Date/sauvegarde via mode B |
| Lecture mémoire directe (mode A données) | 🧪 / non retenu | FMSuperScout montre la faisabilité par offsets | — | Élevée | Casse à chaque patch, licence ambiguë | Mode B + lecture UI |
| Ajouter à la liste de recrutement | 🧪 | Menu contextuel (clic droit positionné) → « Add To Shortlist » (FM26Access) | — | Élevée | État UI inconnu, langue de l'UI | Préparation seulement |
| Offre de transfert / contre-offre / contrat | 🧪 | Automatisation UI vérifiée étape par étape | — | Très élevée | Action irréversible, vérification de résultat | Workflow supervisé de préparation (actuel) |
| Modification mémoire / sauvegarde présentée comme négociation | ❌ (refusé par principe) | — | — | — | — | — |

## 4. Recommandation d'architecture (validée par les preuves)

1. **Données : mode B (sauvegarde) d'abord**, via fmsave — format confirmé, read-only, le même choix
   que The Director. Mode C (hybride) quand le plugin saura signaler les sauvegardes/écrans.
2. **UI : overlay UI Toolkit natif** dans FM26 (pas de navigateur embarqué), puis tentative
   d'entrée dans le menu latéral après relevé de l'arbre UI sur le PC de l'utilisateur.
3. **Actions : aucune exécution** tant qu'un mécanisme n'est pas prouvé ; ordre d'exploration :
   shortlist (réversible) → lecture des réponses → offres.

## 5. Conditions pour valider ce qui reste 🟡 / 🧪

Voir `docs/TEST_PLAN.md` (tests R-1 à R-4, P-1 à P-6). Indispensable : exécuter sur le PC Windows
de l'utilisateur, avec FM26 26.3.x, BepInEx 6 BE ≥ 738 et une vraie sauvegarde (copie).
