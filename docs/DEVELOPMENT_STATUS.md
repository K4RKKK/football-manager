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
| Données | Historique des coupes / stats d'historique | 🧪 | structure relevée, sens non confirmé (`docs/SECTION_MAP.md`) |
| Phase 4 | IA locale (llama.cpp b11658 Vulkan + Gemma 4 26B-A4B) | 🟡 | installation en cours (session 2) ; `scripts/start_llm.ps1`, `scripts/eval_ai.py` |
| Données | Sections non décodées (≈ 58) | ⬜ | coupes, stats joueurs passées, transferts, liste de recrutement, palmarès… (`docs/SECTION_MAP.md`) |
| Phase 1 | Plugin minimal BepInEx + détection du jeu | 🟡 | `plugin/src/ClubDirector.Plugin` |
| Phase 1 | Outil de diagnostic | ✅ | interface web + CLI `clubdirector tool …` |
| Phase 2 | Adaptateur fmsave, normalisation, SQLite, migrations | ✅ | |
| Phase 2 | Multi-carrières, saisons, archivage des résultats | ✅ | |
| Phase 2 | Synchronisation automatique à chaque sauvegarde | ⬜ | prochaine étape (surveillance du dossier) |
| Phase 3 | Overlay dans FM26 (F10) | 🟡 | |
| Phase 3 | Entrée dans le menu latéral natif | 🧪 | outil de relevé UI prêt (Maj+F10) |
| Phase 4 | Registre d'outils (33 disponibles / 51) | ✅ | |
| Phase 4 | Routage niveau 0 (sans IA) | ✅ | 13 formulations testées |
| Phase 4 | Connecteur OpenAI-compatible (llama.cpp, Ollama, OpenRouter) | ✅ protocole / 🟡 vrai modèle | |
| Phase 4 | Connecteur Anthropic (SDK officiel) | 🟡 | aucune clé dans l'environnement |
| Phase 4 | Mémoire (préférences, objectifs) | ✅ | |
| Phase 4 | Résumés de conversation, cache des requêtes | ⬜ | |
| Phase 5 | Recherche multicritère, score de compatibilité explicable, comparateur | ✅ | |
| Phase 5 | Brouillard de recrutement | ❌ actuellement | limitation affichée |
| Phase 6 | Moteur d'exécution transactionnel (table `operations`) | ⬜ | schéma prêt |
| Phase 6 | Actions dans FM26 | 🧪 | toutes marquées indisponibles |
| Phase 7 | Alertes proactives déterministes | ✅ | contrats, profondeur, forme, finances |
| Phase 7 | Personnalités | ✅ | 5 profils |
| Phase 8 | Installateur, profiling en jeu | ⬜ | |
