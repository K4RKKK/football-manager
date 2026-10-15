# fmsave — fork intégré à ClubDirector AI

- Origine : https://github.com/rhiever/fmsave (licence MIT, © 2026 Randal S. Olson — voir `LICENSE`).
- Base : commit `f732460719d80d74287a48b15abd22607952bee2` (0.5.10 + 1 commit de documentation), importé le 2026-10-15.
- Raison : prendre en charge les builds FM26 de l'utilisateur (26.3.0) et décoder davantage de
  sections, sans attendre les versions publiques.

## Règles conservées de l'amont
- Lecture seule ; pas de lecture mémoire, pas de réseau, pas de déchiffrement.
- Connaissance du format issue uniquement de l'observation de ses propres sauvegardes et de
  l'interface du jeu (pas de décompilation).
- Aucune donnée réelle (sauvegarde, extrait, nom, uid, valeur) dans le dépôt : tests sur
  fragments synthétiques ; analyses réelles dans `.local/` (ignoré par Git).

## Modifications locales
Chaque modification est listée ici et dans `CHANGELOG.md` (section « ClubDirector »), pour pouvoir
la reproposer à l'amont.

### 1. Ancre du parcours des statuts de clubs (`readers/clubs.py`)
Tant qu'aucun statut n'est accepté, la recherche couvre tout `game_db` : un doublon d'uid non
confirmé situé avant la vraie table pouvait être pris comme premier statut, et son ordinal élevé
faisait rejeter toute la table (build 26.3.0 : 2 statuts lus sur 29 800, puis 29 765 après
correction). L'ancre exige désormais la confirmation par l'index du club.
Test : `test_unconfirmed_decoy_before_the_table_does_not_anchor_the_status_walk`.

### 2. Octet de tête du nombre de tactiques (`readers/tactics.py`, `TacticsLayout`)
Sur une sauvegarde 26.3.0, le bloc de l'équipe première porte un octet de tête 1 suivi de deux
octets de plus (`01 05 00`) avant la valeur et le compte ; les autres blocs gardent `00`.
Nouveaux champs `tactic_count_flagged_lead_byte` / `tactic_count_flag_extra_bytes` (1 / 2 dans
le layout 26.3.2, valeur de repli). Tests : `test_a_flagged_tactic_count_skips_its_two_extra_bytes`,
`test_another_tactic_count_lead_byte_remains_an_error`.
**Reste ouvert (26.3.0)** : les enregistrements de tactique y ont une autre signature
(`22 42 00 1a 02 00 03 0x` au lieu de `22 42 00 1a 03 00 01 0x`) : 0 tactique extraite.

### 3. Noms de compétitions stockés dans la sauvegarde (`readers/competition_names.py`)
`find_competition_names` lit dans `news` et `edit_session_man` les paires (nom long, nom court)
précédées de l'identifiant d'éditeur (`database_id` 17 octets avant le nom, mot nul juste avant).
39 compétitions nommées sur 26.3.0, aucune contradiction. Tests : `tests/test_competition_names.py`.

### 4. Historique des championnats (`readers/league_history.py`, `Save.league_history()`)
`tc_league_history_dt` : en-tête de 8 octets puis enregistrements de 24 octets (année de fin de
saison, compétition, position 0-based, nombre d'équipes, matchs, V/N/D, buts pour/contre, points ;
valeurs tout-à-un = inconnu). Vérifié sur la réalité (AS Roma 2018/19 → 2024/25, AC Milan 2023/24
et 2024/25 : positions, V/N/D, buts, points identiques) et arithmétiquement sur toutes les lignes
connues. **Ouvert** : la section ne stocke pas le club d'une série et `tc_league_history_ls` n'est
qu'une pagination ; ClubDirector rattache une série à un club seulement par recoupement unique.
Tests : `tests/test_league_history.py`.

### 5. Table des devises (`readers/currencies.py`, `Save.currencies()`)
`game_db` contient 173 devises contiguës : nom, nom court, chaîne vide, symbole (souvent vide),
taux f32 par rapport à l'unité de stockage, historique annuel (u8 1, u16 année, f32 taux ; année 0 =
entrée vide), puis index 0, 1, 2… (vérifié) et 9 octets non identifiés. La livre sterling a le taux
1,0 : les montants de fmsave sont stockés en livres ; l'euro vaut 1,15713, le facteur mesuré auparavant
entre les montants stockés et les euros affichés à l'écran. Tests : `tests/test_currencies.py`.

### 6. Marché des transferts (`readers/transfers.py`, `Save.transfer_offers()`, `Save.player_rankings()`)
`transfer_man` : tête de 9 octets, nombre d'enregistrements (u32), puis enregistrements numérotés
0, 1, 2… de longueur variable (clauses en fin d'enregistrement). Champs établis : type (2 transfert,
3 prêt, 10 mouvement entre équipes du même club ; 4, 7, 9 rares et non identifiés), personne (index
de personne + 1 : joueur ou membre du staff), équipe acheteuse (+8), montant (+17, unité stockée),
état (+29 : 0x14 conclu, 0x0F échoué ; autres codes non identifiés), équipe du joueur au moment de
l'offre (+69), dates (+56 échéance, +60 effet, +75 offre, +80 dernier changement ; jour de l'année
sur les 9 bits bas). Vérifié sur la carrière de l'utilisateur (Batrakov Lokomotiv → Roma 12,96 M£
conclu le 31/07, Gadou Salzburg → Roma, offres reçues pour Hermoso, Rensch…), sur 1 855 des 1 857
transferts conclus (le joueur appartient au club acheteur) et 505 des 532 prêts conclus (club
prêteur = club du joueur à l'offre).
`shortlist_man` : tête de 8 octets puis 30 classements (u32 nombre, paires u32 personne + 1, u32
note), du meilleur au moins bon : 14 postes dans l'ordre du jeu et les jeunes talents, hommes puis
femmes. Vérifié par les postes des joueurs de chaque classement. La suite de la section (autre
structure, probablement le staff) n'est pas lue. Tests : `tests/test_transfers.py`.

### 7. Noms des joueurs d'une offre sans décoder tous les joueurs (`_save.py`, `Save._player_lookup`)
`transfer_offers()` lu à froid décodait les 73 658 joueurs d'une vraie carrière (≈ 8 s, dont 0,1 s
pour la section elle-même) pour les noms de quelques milliers. Quand la table des joueurs n'est pas
encore lue et que les joueurs demandés sont moins d'un quart du total, seuls leurs enregistrements
sont décodés, avec le décodeur du lecteur des joueurs : 4,4 s, table identique (vérifié sur la
carrière de l'utilisateur, 12 253 offres). Les contrôles du lecteur des joueurs s'appliquent quand
cette table est lue. Tests : `tests/test_transfers.py`.
