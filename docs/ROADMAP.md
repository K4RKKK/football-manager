# Feuille de route

## Terminé (session 1)
- Phase 0 : audit (cloud), étude des projets, dépôt, documentation, choix techniques.
- Phase 1 (partie hors jeu) : lecteur de sauvegarde, outil de diagnostic, plugin écrit (non validé).
- Phase 2 : adaptateur fmsave, SQLite, archivage, multi-carrières.
- Phase 4 (socle) : registre d'outils, niveau 0, connecteurs, budget, mémoire.
- Phase 5 (socle) : recherche, compatibilité explicable, comparateur.
- Phase 7 (socle) : alertes déterministes, personnalités.

## Terminé (session 2, PC de l'utilisateur)
- A-1 audit, R-1 vraie carrière (AS Roma 26.3.0), équipes du club, fork fmsave intégré,
  inventaire des sections, atelier de décodage, statuts des clubs et coups de pied arrêtés.

## Prochaines étapes (ordre)
0. **Lecture intégrale de la sauvegarde (priorité de l'utilisateur)** : importer les 16 lecteurs
   fmsave inutilisés ; décoder les sections non lues dans l'ordre de valeur (historiques
   `tc_*_history`, `player_stats_hist_dt`, `comp_history_dt`, `transfer_man`, `shortlist_man`,
   `hall_of_fame`, `person_db_changes`…) ; mesurer la couverture en octets jusqu'à 100 %.
   Refaire l'inventaire sur la sauvegarde plus récente de l'utilisateur (build actuel du jeu).
1. **Sur le PC de l'utilisateur** : R-3 (devise), L-1 (llama.cpp Vulkan), comparer 5 attributs à l'écran du jeu.
2. Compiler et charger le plugin (P-1 à P-4) ; corriger selon `LogOutput.log`.
3. Synchronisation automatique : surveillance du dossier `games` (fichier stable 30 s après écriture).
4. Entrée de menu native (P-5) à partir du relevé d'arbre UI.
5. Résumés de conversation, cache, FTS5, fusion de carrières dans l'UI.
6. Phase 6 : moteur transactionnel `operations` + préparation d'offres à règles ; exploration
   « Add To Shortlist » via menu contextuel avec vérification.
7. Phase 8 : installateur Windows (service + plugin), désinstallateur, profiling en jeu.
