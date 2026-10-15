# Carte des sections non décodées

<!-- Généré par tools/decode/workbench.py (structure seulement, aucune valeur de carrière). -->
Sauvegarde de référence : build 26.3.0. « Liens » : identifiants d'entités connues trouvés dans la
section (lift = réfs / témoin décalé ; *pas* = écart dominant entre deux références, souvent la
taille d'un enregistrement). Les identifiants à plage dense (équipes, phases, index de club, pindex)
sont marqués *(dense)* : leur signal doit être confirmé par la structure.

| Section | Octets | Étiquettes du flux balisé | Chaînes | Liens principaux |
|---|---:|---|---:|---|
| person_db_changes | 45,040,575 | `hgty`, `nati`, `dtty`, `duni`, `prty`, `vers`, `nwvl`, `nwvl` … | 346516 | stade.uid ×538791 (lift 63.6, pas 99)<br>club.unique_id (stocké -1) ×457956 (lift 35.6, pas 99)<br>club.uid (stocké -1) ×457956 (lift 35.6, pas 99) |
| match_stats_cfg | 19,920,264 | `i91a`, `vqt0` | 4 | competition.id (stocké -1) ×1105 (lift 4.3, pas 12)<br>club.index *(dense)* ×7105 (lift 4.1, pas 4)<br>equipe.id *(dense)* ×7549 (lift 3.6, pas 4) |
| person_record_history_dt | 10,290,596 | — | 1 | stade.uid ×99563 (lift 29.8, pas 42)<br>club.unique_id ×133541 (lift 19.2, pas 42)<br>club.uid ×133541 (lift 19.2, pas 42) |
| transfer_man | 6,045,586 | `deti` | 56 | stade.uid (+1) ×30460 (lift 7.4, pas 69)<br>club.unique_id (stocké -1) ×39866 (lift 5.4, pas 69)<br>club.uid (stocké -1) ×39866 (lift 5.4, pas 69) |
| used_player_data | 5,218,197 | — | 0 | stade.uid ×8345 (lift 8.4, pas 37)<br>club.unique_id (stocké -1) ×10337 (lift 5.3, pas 37)<br>club.uid (stocké -1) ×10337 (lift 5.3, pas 37) |
| hall_of_fame | 4,974,727 | `aloi`, `emem`, `siwe`, `sotn`, `lw6l`, `hsin`, `ynna`, `ijmi` … | 92339 | club.unique_id (stocké -1) ×99693 (lift 46.4, pas 28)<br>club.uid (stocké -1) ×99693 (lift 46.4, pas 28)<br>competition.database_id ×66642 (lift 44.2, pas 28) |
| tc_league_history_dt | 4,188,608 | — | 0 | competition.id ×37022 (lift 156.9, pas 24)<br>staff.uid ×5794 (lift 11.5, pas 24)<br>joueur.unique_id ×99 (lift 11.0, pas 24) |
| shortlist_man | 3,986,056 | `w8bx` | 0 | stade.uid (+1) ×63262 (lift 6.9, pas 8)<br>club.unique_id (stocké -1) ×97545 (lift 6.1, pas 4)<br>club.uid (stocké -1) ×97545 (lift 6.1, pas 4) |
| comp_history_dt | 3,580,728 | — | 0 | stade.uid ×37888 (lift 20.7, pas 55)<br>club.unique_id ×72951 (lift 15.5, pas 55)<br>club.uid ×72951 (lift 15.5, pas 55) |
| person_record_manager | 2,771,497 | `dddd`, `dddd`, `dddd`, `dddd` | 35 | stade.uid ×7283 (lift 18.1, pas 4)<br>club.unique_id (stocké -1) ×10308 (lift 14.9, pas 4)<br>club.uid (stocké -1) ×10308 (lift 14.9, pas 4) |
| starting_club_debt_db | 2,753,014 | — | 0 | phase.id *(dense)* ×57362 (lift 3.8, pas 79) |
| press_conference_manager | 2,502,926 | `dref`, `p1pm`, `quno`, `qcmp`, `qexr`, `fofl`, `qres`, `qjb2` … | 5188 | stade.uid (+1) ×34375 (lift 29.6, pas 11)<br>club.unique_id (stocké -1) ×42026 (lift 28.0, pas 11)<br>club.uid (stocké -1) ×42026 (lift 28.0, pas 11) |
| manager_manager | 2,248,209 | — | 13 | staff.unique_id (stocké -1) ×3131 (lift 4.0, pas 87)<br>staff.uid (stocké -1) ×3146 (lift 3.9, pas 87)<br>stade.uid (+1) ×3851 (lift 3.0, pas 32) |
| player_stats_hist_dt | 1,426,224 | — | 0 | stade.uid ×9615 (lift 63.3, pas 152)<br>club.unique_id (stocké -1) ×4054 (lift 21.3, pas 152)<br>club.uid (stocké -1) ×4054 (lift 21.3, pas 152) |
| person_record_history_ls | 1,230,182 | — | 1104 | stade.uid (+1) ×17423 (lift 30.8, pas 20)<br>club.unique_id (stocké -1) ×19066 (lift 28.7, pas 20)<br>club.uid (stocké -1) ×19066 (lift 28.7, pas 20) |
| interaction_manager | 1,227,504 | — | 0 | club.unique_id (stocké -1) ×10504 (lift 15.2, pas 59)<br>club.uid (stocké -1) ×10504 (lift 15.2, pas 59)<br>competition.id (stocké -1) ×6820 (lift 15.0, pas 59) |
| injury_histories_dt | 1,062,696 | — | 0 | staff.uid ×3207 (lift 178.2, pas 16)<br>staff.unique_id (stocké -1) ×3017 (lift 167.6, pas 16)<br>competition.id ×7619 (lift 25.6, pas 16) |
| tc_league_history_ls | 744,126 | — | 71 | stade.uid (+1) ×3821 (lift 23.9, pas 8)<br>club.unique_id (stocké -1) ×4985 (lift 21.3, pas 8)<br>club.uid (stocké -1) ×4985 (lift 21.3, pas 8) |
| regeneration_manager | 711,116 | `w612` | 0 | stade.uid (+1) ×3728 (lift 21.1, pas 4)<br>staff.uid ×669 (lift 15.6, pas 14)<br>staff.unique_id ×1092 (lift 9.8, pas 14) |
| award_year_hist_dt | 569,990 | — | 0 | club.unique_id (stocké -1) ×8036 (lift 14.3, pas 26)<br>club.uid (stocké -1) ×8036 (lift 14.3, pas 26)<br>competition.id (stocké -1) ×4400 (lift 13.1, pas 26) |
| injury_histories_ls | 383,986 | — | 148 | club.unique_id (stocké -1) ×4091 (lift 8.3, pas 20)<br>club.uid (stocké -1) ×4091 (lift 8.3, pas 20)<br>stade.uid (+1) ×3091 (lift 7.7, pas 20) |
| media_man | 334,262 | — | 8 | stade.uid (+1) ×3620 (lift 14.7, pas 40)<br>staff.uid ×1935 (lift 10.8, pas 40)<br>club.unique_id (stocké -1) ×4209 (lift 10.8, pas 40) |
| weather_manager | 291,757 | — | 0 | stade.uid (stocké -1) ×1292 (lift 646.0, pas 40)<br>club.unique_id (+1) ×209 (lift 209.0, pas 20)<br>club.uid (+1) ×209 (lift 209.0, pas 20) |
| tc_cup_history_dt | 164,150 | — | 0 | staff.uid ×487 (lift 243.5, pas 18)<br>staff.unique_id ×674 (lift 74.9, pas 18)<br>club.unique_id (stocké -1) ×5099 (lift 58.6, pas 18) |
| sim_stats | 136,680 | — | 0 | joueur.uid (stocké -1) ×6 (lift 3.0, pas 1287) |
| edit_session_man | 113,496 | `dref`, `sqot`, `sqop`, `sqcp`, `pcqi`, `p1pm`, `qot2`, `quno` … | 47 | staff.uid (+1) ×224 (lift 24.9, pas 214)<br>stade.uid (stocké -1) ×375 (lift 22.1, pas 5)<br>club.unique_id (+1) ×469 (lift 20.4, pas 5) |
| scout_man | 80,579 | `flvl`, `pifr`, `mgen`, `darr`, `flvl`, `fmnv`, `fmxv`, `flvl` … | 53 | stade.uid ×575 (lift 12.0, pas 29)<br>club.unique_id (stocké -1) ×799 (lift 9.2, pas 29)<br>club.uid (stocké -1) ×799 (lift 9.2, pas 29) |
| tc_history_dt | 66,767 | — | 0 | — |
| award_man | 46,575 | — | 1 | club.unique_id (stocké -1) ×672 (lift 20.4, pas 35)<br>club.uid (stocké -1) ×672 (lift 20.4, pas 35)<br>stade.uid (+1) ×364 (lift 17.3, pas 35) |
| tc_cup_history_ls | 38,974 | — | 3 | competition.id (stocké -1) ×403 (lift 7.6, pas 8) |
| award_year_hist_ls | 29,346 | — | 1 | — |
| official_manager | 25,172 | — | 0 | stade.uid ×22 (lift 3.1, pas 10) |
| tc_history_ls | 21,558 | — | 36 | competition.id (stocké -1) ×980 (lift 20.4, pas 12) |
| board_takeover_manager | 14,660 | — | 170 | staff.uid ×98 (lift 98.0, pas 119)<br>stade.uid (+1) ×251 (lift 41.8, pas 38)<br>club.unique_id (stocké -1) ×260 (lift 37.1, pas 38) |
| memory_pools | 13,879 | — | 513 | competition.id (stocké -1) ×99 (lift 12.4, pas 26)<br>staff.unique_id ×40 (lift 10.0, pas 40)<br>club.unique_id (stocké -1) ×85 (lift 9.4, pas 3) |
| backroom_advice_manager | 12,099 | — | 0 | staff.uid (stocké -1) ×8 (lift 8.0, pas 63)<br>stade.uid ×58 (lift 7.2, pas 18)<br>club.unique_id (+1) ×92 (lift 3.4, pas 45) |
| finance_manager | 6,347 | — | 0 | staff.unique_id ×28 (lift 28.0, pas 52)<br>staff.uid ×17 (lift 17.0, pas 52)<br>competition.id (stocké -1) ×53 (lift 6.6, pas 52) |
| contract_man | 2,599 | — | 0 | — |
| retirement_manager | 2,569 | — | 0 | club.unique_id ×103 (lift 25.8, pas 24)<br>club.uid ×103 (lift 25.8, pas 24)<br>competition.id ×12 (lift 12.0, pas 24) |
| team_talk_man | 2,457 | — | 0 | stade.uid (+1) ×32 (lift 32.0, pas 8)<br>club.unique_id (stocké -1) ×23 (lift 23.0, pas 5)<br>club.uid (stocké -1) ×23 (lift 23.0, pas 5) |
| non_pl_hist_dt | 1,228 | — | 0 | club.unique_id ×34 (lift 34.0, pas 20)<br>club.uid ×34 (lift 34.0, pas 20)<br>phase.id *(dense)* ×34 (lift 34.0, pas 20) |
| training_camp_man | 1,122 | — | 0 | stade.uid (+1) ×49 (lift 49.0, pas 8)<br>competition.id ×22 (lift 11.0, pas 4)<br>club.unique_id ×54 (lift 7.7, pas 29) |
| tc_manager_history_dt | 814 | — | 0 | club.unique_id (+1) ×10 (lift 10.0, pas 93)<br>club.uid (+1) ×10 (lift 10.0, pas 93)<br>phase.id *(dense)* ×17 (lift 8.5, pas 6) |
| agent_manager | 360 | — | 0 | — |
| non_pl_hist_ls | 290 | — | 0 | club.unique_id ×7 (lift 7.0, pas 8)<br>club.uid ×7 (lift 7.0, pas 8)<br>staff.unique_id ×7 (lift 7.0, pas 3) |
| network_man | 254 | — | 0 | club.index *(dense)* ×7 (lift 7.0, pas 27)<br>phase.id *(dense)* ×6 (lift 6.0, pas 27) |
| tc_manager_history_ls | 210 | — | 0 | — |
| fine_manager | 176 | — | 0 | — |
| matchday_manager | 88 | — | 0 | — |
| trade_man | 46 | — | 0 | — |
| morale_manager | 33 | — | 0 | — |
| pl_hist_ls | 26 | — | 0 | — |
| tc_best_eleven_history_ls | 26 | — | 0 | — |
| tc_extended_club_records_history_ls | 26 | — | 0 | — |
| tc_extended_nation_records_history_ls | 26 | — | 0 | — |
| award_club_hist_ls | 26 | — | 0 | — |
| database_analyser | 25 | — | 0 | — |
| captain_system | 25 | — | 0 | — |
| dynamics_pivotal_moments | 24 | — | 0 | — |
| play_fixture_manager | 17 | — | 0 | — |
| awol | 14 | — | 0 | — |
| fog_of_war | 13 | — | 0 | — |
| dispute | 12 | — | 0 | — |
| virtual_manager | 12 | — | 0 | — |
| financial_fair_play_manager | 10 | — | 0 | — |

## Notes de décodage (session 2) — établi / ouvert

| Section | Établi (vérifié) | Ouvert |
|---|---|---|
| `tc_league_history_dt` + `_ls` | Enregistrements de 24 o (année de fin de saison, compétition, position, V/N/D, buts, points) — vérifié sur la réalité ; l'index liste les clubs ayant un historique **triés par uid** (0 nation contradictoire / 514). Lecteur `league_history` + rattachement (894 clubs). | Clubs sans historique non identifiables directement : ~10 600 séries non rattachées. |
| `tc_cup_history_dt` + `_ls` | En-tête 8 o puis enregistrements de 18 o : u32 clé de compétition historique (plage dense 3–4712, aucun espace d'id connu), u16 année début, u16 année fin, u8 drapeau, u8 code (tour atteint ?), 2 × u32. L'index a la même forme que celui des championnats : 618 groupes = séries (tailles identiques). | Sens du code et des 2 u32 ; table de la clé de compétition ; ordre des groupes (clubs ou sélections ?). |
| `player_stats_hist_dt` | 9 383 enregistrements de 152 o (en-tête 8 o) : u8 0, u32 équipe (79 %), u16 compétition (ex. 22 = Serie A), u32 X (0 / −1 dans 87 %), u16 année (2025 partout), puis compteurs (92 % de zéros). 30 enregistrements pour l'équipe première de la Roma en Serie A. | Les compteurs ne recoupent pas les stats de saison connues des joueurs : sens non établi (stats d'équipe par match ? par joueur sans clé ?). |
| `edit_session_man` | Séance du prochain match : compétition (noms long/court + `database_id`), stade, arbitre, couleurs des maillots. | Format complet. |
| `news` / `edit_session_man` | Noms des compétitions citées (39). | — |
