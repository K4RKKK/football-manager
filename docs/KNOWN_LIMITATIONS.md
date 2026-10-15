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
4. **Unité monétaire** : réglé. La sauvegarde stocke l'argent en livres (taux 1,0 de sa propre
   table des devises, 173 devises lues par `Save.currencies()`). Les montants sont convertis avec le
   taux de l'euro lu dans la même sauvegarde (1,15713 sur la carrière AS Roma), à chaque
   synchronisation. Un étalonnage manuel reste prioritaire. Reste à confronter quelques valeurs à
   l'écran du jeu (l'ancien relevé à l'écran donnait déjà ≈ 1,157).
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

15. **Temps réel = à chaque sauvegarde** : sans plugin dans le jeu, le directeur voit l'état de la
    dernière sauvegarde. La synchronisation automatique la relit 20 s après chaque enregistrement
    (≈ 2 à 3 min de lecture sur une grosse base). Régler la sauvegarde automatique de FM26 sur une
    fréquence élevée pour suivre la partie au plus près.
16. **Fonction du staff** : établies : directeur sportif (10, hors départements), directeur technique
    (88), entraîneur principal (16) ; entraîneur adjoint = code 20 de la liste « entraînement », celui de
    l'équipe première le mieux payé (heuristique : 5 clubs sur 6 vérifiés, un ex aequo au Bayern).
    Les autres fonctions (chef recruteur, kinés…) restent non décodées. Correction depuis la fiche du
    contact dans le téléphone (« Ce n'est pas la bonne personne ? »).
17. **Fenêtre externe** : visible au-dessus de FM26 en mode « fenêtré sans bordure » ; un plein écran
    exclusif passe devant toute fenêtre.
18. **Photos** : elles viennent du pack de visages installé par l'utilisateur
    (`Documents\Sports Interactive\Football Manager 26\graphics\faces`, fichiers `<unique_id>.png`).
    Sans pack, le téléphone affiche les initiales.
19. **IA locale à un seul fil** : llama-server traite une demande à la fois ; un message attend la
    réponse précédente (ou le préchauffage d'un contact, 10-15 s après une nouvelle sauvegarde).
    Le 15/10/2026, le serveur s'est bloqué une fois (aucune activité, requêtes sans réponse) ; il a été
    relancé avec un journal (`%LOCALAPPDATA%\ClubDirectorAI\llm.log`) pour en trouver la cause.
20. **Messages** : appels, vidéo et e-mail du téléphone sont décoratifs ; le directeur ne travaille pas
    entre deux messages (pas de tâche de fond) et n'agit pas dans le jeu (voir 12 et 14).
21. **Marché des transferts** : les offres de la sauvegarde sont lues (club acheteur, vendeur,
    montant, dates). Seuls les états « conclue » (0x14) et « échouée » (0x0F) sont établis ; les autres
    codes sont affichés « en cours », « sans suite » (échéance passée) ou « accord pour plus tard »
    (date d'effet future) : une offre refusée par le club vendeur peut apparaître « en cours ». Les
    clauses (bonus, pourcentages) en fin d'enregistrement ne sont pas décodées. Les membres du staff
    recrutés passent par les mêmes enregistrements sans être identifiés.
22. **Prix, plafonds, salaires proposés** : estimations à règles explicites (valeur du jeu, contrat,
    âge, rang au marché, prix réellement payés pour des joueurs comparables) ; ce ne sont pas les prix
    que l'IA du jeu accepterait. Les budgets des clubs sont ceux du dernier mois de finances lu.
23. **Listes de recrutement des clubs** : `shortlist_man` contient les classements du marché tenus
    par le jeu, pas les listes de chaque club ; la fin de la section (probablement le staff) n'est
    pas lue. L'intérêt « prouvé » d'un club = une offre enregistrée.
24. **Délégation à Cagigao dans FM26** : le directeur explique quoi déléguer (responsabilités du
    staff, négociation d'une offre, liste des transferts) ; il ne voit pas ces réglages dans la
    sauvegarde et les intitulés exacts des écrans sont à vérifier dans le jeu.
25. **Compositions** : calculées sur les notes de poste (familiarité 1-20), le temps de jeu, la note moyenne, la
    valeur et la condition, jamais sur les attributs cachés. L'infirmerie du jour n'est pas lue dans la sauvegarde :
    l'adjoint demande les absents (« sans Dybala » est compris). La tactique active (26.3.0) n'est pas lue : système
    4-2-3-1 par défaut, ou celui demandé.
