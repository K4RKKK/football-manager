# Limitations vérifiées et problèmes ouverts

1. **Builds inconnus de fmsave** : les sauvegardes de l'utilisateur sont en 26.0.4, 26.1.2, 26.2.0 et
   26.3.0 ; fmsave ne connaît entièrement que 26.3.2. Sur 26.3.0 (session 2), seuls les
   enregistrements de tactique restent illisibles (autre signature). Le plugin n'est pas encore validé
   dans le jeu (BepInEx absent).
1b. **Couverture des données** : ≈ 35 % du volume décompressé de la sauvegarde n'est lu par aucun
   lecteur (`docs/DATA_INVENTORY.md`) et 16 lecteurs fmsave ne sont pas encore importés. Objectif :
   100 % (`docs/SECTION_MAP.md`).
1c. **Durée de synchronisation** : ≈ 1 min sur une vraie carrière (73 658 joueurs ; 168 s avant le
   15/10/2026). Il reste ≈ 37 s de décodage fmsave (joueurs 8 s, conversions du miroir 13 s) ; une
   lecture en parallèle dans un second processus a été mesurée puis écartée (les sections indépendantes
   reconstruisent les index partagés : 21 s de travail pour 9 s gagnés, +1 Go de RAM et un 2e cœur pris
   pendant que FM26 tourne). Pendant la lecture, le service répond sur l'état précédent ; pendant
   l'écriture (17-23 s), ses propres écritures (messages) attendent la validation au lieu d'échouer.
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
7. **Non lus** : compositions de match, dette, prix demandés, noms de
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
    (≈ 1 min de lecture sur une grosse base). Régler la sauvegarde automatique de FM26 sur une
    fréquence élevée pour suivre la partie au plus près.
16. **Fonction du staff** : établies et vérifiées sur des personnes réelles : directeur sportif (10, hors
    départements), directeur technique (88), entraîneur principal (16), entraîneur adjoint (20), entraîneur
    (2), préparateur physique (26), entraîneur des gardiens (34), scientifique du sport (40), kinésithérapeute
    (50) ; départements : 0 médical et performance, 1 entraînement, 2 recrutement. Les autres fonctions
    restent « non précisée » (le département est connu). L'adjoint principal reste une heuristique
    (correction depuis la fiche du contact). Chaque contact n'a que les outils de son métier (le directeur
    technique : le staff ; l'adjoint : le terrain ; le directeur sportif : tout).
17. **Fenêtre externe** : visible au-dessus de FM26 en mode « fenêtré sans bordure » ; un plein écran
    exclusif passe devant toute fenêtre.
18. **Photos** : elles viennent du pack de visages installé par l'utilisateur
    (`Documents\Sports Interactive\Football Manager 26\graphics\faces`, fichiers `<unique_id>.png`).
    Sans pack, le téléphone affiche les initiales.
19. **IA locale à un seul fil** : llama-server traite une demande à la fois ; un message attend la
    réponse précédente (ou le préchauffage d'un contact, 10-15 s après une nouvelle sauvegarde).
    Le 15/10/2026, le serveur s'est bloqué une fois (aucune activité, requêtes sans réponse, `/health`
    pourtant « ok ») ; cause inconnue. Depuis, la surveillance du service (`ai/llm_watchdog.py`) détecte
    un serveur figé (requête de test `/slots` sans réponse, ou demande sans aucun jeton lu ni généré
    pendant 60 s) ou arrêté, le relance avec les mêmes paramètres (`scripts/start_llm.ps1`, mode jeu
    compris) et refait la demande : l'entraîneur voit un message d'état, ou une erreur claire si la relance
    échoue. Détection en ≈ 70 s ; au plus 3 relances par heure. Journal du serveur :
    `%LOCALAPPDATA%\ClubDirectorAI\llm.log` (le précédent est archivé en `llm-<date>.log`, il garde la
    trace d'un blocage) ; décisions de la surveillance : `llm-watchdog.log`. Un serveur jamais vu depuis
    le démarrage du service n'est pas lancé d'office. La surveillance n'est active qu'après un
    redémarrage du service ; elle n'a pas encore été éprouvée sur un vrai blocage.
20. **Messages** : appels, vidéo et e-mail du téléphone sont décoratifs. Entre deux messages, le staff
    ne travaille qu'à chaque nouvelle sauvegarde lue (messages proactifs, suivi des dossiers, voir 27) ;
    il n'agit jamais dans le jeu (voir 12 et 14).
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
26. **Disponibilité du jour** : lue. Blessé aujourd'hui = ligne de blessure « typée » dont la date
    de retour prévue est postérieure à la date du jeu (vérifié dans FM26 sur Gabriel Jesus et
    Barcola) ; le jeu affiche une fourchette (« 6 jours - 2 semaines »), la sauvegarde une seule date.
    Suspensions : la sauvegarde garde aussi des sanctions que le jeu n'affiche plus, et le nombre de
    matchs restants n'est pas lu. Les sections féminines portant le nom d'un club masculin sont
    écartées par les classements du marché (joueurs classés chez les hommes).
27. **Staff vivant (messages proactifs, dossiers, mémoire)** : un contact écrit de lui-même seulement
    quand une sauvegarde est lue (pas d'horloge propre), au plus un message par sauvegarde et quatre faits
    par message (les suivants attendent la sauvegarde d'après). La première lecture d'une carrière sert de
    base : arrivées, départs et changements de staff ne sont signalés qu'à partir de la deuxième.
    **Fin de fenêtre des transferts** : la sauvegarde contient 22 fenêtres sans pays ni compétition
    (fmsave) ; le directeur ne l'annonce que si l'entraîneur a donné la date (« le mercato ferme le
    2 février »), jamais par supposition. **Dossiers** : un dossier suit ce qui est visible dans la
    sauvegarde (offre enregistrée, état conclue / échouée / accord, club et contrat du joueur) ; une
    offre refusée par le club vendeur peut rester « en cours » (voir 21) ; un dossier sans aucun
    mouvement pendant 90 jours de jeu est classé sans suite. **Décisions** : reconnues sans IA pour
    des formulations courantes (« on ne vend pas X », « X n'est pas à vendre », « âge max 26 ans »,
    « pas plus de 30 M€ par transfert », « salaire max … par semaine », « retiens que … ») ; une
    formulation inhabituelle dépend du modèle (outil `remember`). Un joueur n'est retenu que s'il est
    de notre club et reconnu sans ambiguïté. **Résumés** : faits par le modèle local (quand au moins
    8 messages sortent de la fenêtre de 12) ; sans modèle, pas de résumé. Le texte proactif est rédigé
    par le modèle à partir des seuls faits fournis ; sans modèle, les faits sont envoyés tels quels.
28. **Téléphone : réactions, réponses rapides, notifications** : une réaction (tapback) est enregistrée
    avec le message et relue par le téléphone, mais n'est pas transmise au modèle (le contact ne « voit »
    pas un ❤️). Les réponses rapides apparaissent quand le dernier message du contact finit par « ? » ;
    une question sans point d'interrogation n'en propose pas. Les messages arrivés hors d'une réponse sont
    vus au rafraîchissement du téléphone (toutes les 15 s, ou à l'affichage de la fenêtre). L'heure de
    l'écran verrouillé est celle de Windows (la sauvegarde ne contient que la date du jeu). Mercato : les
    offres affichées sont celles de la dernière sauvegarde, avec les états de la section transfer_man (voir 21) ;
    une offre refusée par le club vendeur peut rester « en cours ». La taille du téléphone choisie dans
    Réglages demande la fenêtre recompilée (`dotnet build overlay\ClubDirector.Overlay -c Release`, fenêtre
    fermée) ; sinon, clic droit sur l'icône de la zone de notification.
