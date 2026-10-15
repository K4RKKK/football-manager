# Limitations vérifiées et problèmes ouverts

1. **Builds inconnus de fmsave** : les sauvegardes de l'utilisateur sont en 26.0.4, 26.1.2, 26.2.0 et
   26.3.0 ; fmsave ne connaît entièrement que 26.3.2. Sur 26.3.0 (session 2), seuls les
   enregistrements de tactique restent illisibles (autre signature). Le plugin n'est pas encore validé
   dans le jeu (BepInEx absent).
1b. **Couverture des données** : ≈ 35 % du volume décompressé de la sauvegarde n'est lu par aucun
   lecteur (`docs/DATA_INVENTORY.md`) et 16 lecteurs fmsave ne sont pas encore importés. Objectif :
   100 % (`docs/SECTION_MAP.md`).
1c. **Synchronisation lente** : ≈ 110 s sur une vraie carrière (73 658 joueurs).
2. **Statistiques des saisons passées** : FM26 ne conserve dans la sauvegarde que la saison en cours
   (fmsave). ClubDirector archive à chaque synchronisation ; une saison jamais synchronisée reste
   inconnue et l'assistant le dit.
3. **Scores partiels** : certains matchs joués n'ont pas de score décodable ; ils sont affichés
   « score non disponible ». Un score connu n'est jamais écrasé par une absence de score.
4. **Unité monétaire** : la sauvegarde stocke l'argent dans une unité interne. Sans étalonnage,
   aucune comparaison avec un montant en euros n'est faite (outils en erreur explicite).
5. **Brouillard de recrutement** non reproductible : les attributs visibles affichés pour les joueurs
   d'autres clubs sont les valeurs réelles. CA/PA, attributs cachés et personnalité restent masqués
   hors mode avancé confirmé.
6. **Champs non confirmés par fmsave** (`age`, `club_uid`, `wage`, `ability`) : leur statut est
   transmis à l'IA (`statut_champs`).
7. **Non lus** : disponibilité du jour, compositions de match, dette, prix demandés, noms de
   compétitions (pas de fichier de noms fourni), instructions tactiques détaillées, staff complet.
8. **Identité de carrière** : un « Enregistrer sous » crée une nouvelle carrière (choix prudent) ;
   la fusion manuelle n'est pas encore exposée dans l'UI.
9. **Recherche par nom** : balayage `LIKE` (≈ 250 ms sur 100 000 joueurs) ; FTS5 prévu.
10. **Synchronisation** : manuelle (UI/CLI) pour l'instant.
11. **Plugin** : non compilé ni chargé dans FM26 ; détection du chargement de carrière non implémentée ;
    entrée de menu native non réalisée.
12. **Actions** : aucune action dans le jeu n'est disponible (aucun mécanisme prouvé).
13. **Risque légal** : l'EULA SEGA générique restreint la rétro-ingénierie « sauf si la loi le
    permet ». Le projet est limité au solo local, en lecture seule, sans contournement de protection.

14. **Injection dans FM26 bloquée par la protection du jeu (constaté le 15/10/2026, build Steam 23583635)** :
    avec BepInEx 6 BE 738 (pack Thunderstore FM26), le jeu affiche « Le serveur n'est pas accessible »
    puis une demande d'activation hors ligne (protection anti-falsification Codefusion) et se ferme.
    Test d'isolement : BepInEx désactivé (`enabled = false`) → le message revient ; `winhttp.dll`
    (Doorstop) retiré → le jeu démarre normalement. Le chargeur suffit à déclencher la protection.
    Le projet ne contourne pas cette protection : plugin et overlay dans le jeu sont suspendus ;
    ClubDirector reste utilisable hors du processus du jeu (sauvegardes, IA, interface externe).
    État laissé : `winhttp.dll` mis de côté dans `C:\AI\downloads\fm26-desactive\`, dossier
    `BepInEx\` inerte (désinstallation complète : `scripts\uninstall_bepinex.ps1`).
