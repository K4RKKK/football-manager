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
