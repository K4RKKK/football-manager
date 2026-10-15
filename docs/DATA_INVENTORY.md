<!-- Généré par : uv run clubdirector inventory <sauvegarde>  (structure seulement, aucune donnée de carrière) -->
<!-- Sauvegarde de référence : carrière de l'utilisateur, build 26.3.0, 15/10/2026 -->

# Inventaire de la sauvegarde — build 26.3.0+2286575

Build connu de fmsave : non · 77 sections · 351.1 Mo décompressés.

| État | Volume (Mo) | Part |
|---|---:|---:|
| décodée avec échecs | 195.4 | 55.7 % |
| non décodée | 122.3 | 34.8 % |
| importée | 33.3 | 9.5 % |
| décodée, non importée | 0.0 | 0.0 % |

> Une section « décodée » peut ne l'être que partiellement (ex. `game_db`) : l'état indique
> qu'au moins un lecteur l'exploite, pas que chaque octet est compris.

## Lecteurs fmsave

| Lecteur | État | Lignes | Sections lues | ClubDirector | Contrôles en échec | s |
|---|---|---:|---|---|---|---:|
| clubs | failed | 29800 | game_db | clubs_current | status_normal=6.71e-05, status_confirmation=0, reputation_found=3.36e-05 | 3.97 |
| players | ok | 73658 | game_db | players_current + player_history | — | 6.47 |
| contracts | ok | 73343 | game_db | partiel : salaire, début, fin, statut (pas les clauses ni l'historique) | — | 0.0 |
| suspensions | ok | 193 | game_db | partiel : indicateur « suspendu » du joueur | — | 0.0 |
| managed_clubs | ok | 1 | game_db, humans, save_game_summary | careers (club géré, manager) | — | 0.41 |
| stages | ok | 4721 | game_db | **non importé** | — | 0.29 |
| competitions | ok | 2068 | game_db | **non importé** | — | 0.24 |
| fixtures | ok | 41220 | game_db, news, tc_record_man | fixtures | — | 2.72 |
| league_tables | ok | 890 | game_db, news, tc_record_man | league_tables | — | 0.73 |
| transfer_windows | ok | 54 | game_db | **non importé** | — | 0.31 |
| competition_rules | ok | 393 | game_db, news, tc_record_man | **non importé** | — | 0.01 |
| player_match_stats | ok | 5172 | game_db | **non importé** | — | 1.13 |
| player_season_stats | ok | 210376 | (trames non listées : statistiques de saison), game_db | season_stats | — | 2.3 |
| stadiums | ok | 29764 | game_db, news, tc_record_man | **non importé** | — | 0.79 |
| finances | ok | 1956 | game_db, humans, save_game_summary | finances | — | 0.44 |
| sponsorships | ok | 2731 | game_db, humans, save_game_summary | **non importé** | — | 0.0 |
| affiliates | ok | 158 | feeder_man, game_db | **non importé** | — | 0.0 |
| job_vacancies | ok | 270 | game_db, job_centre | **non importé** | — | 0.21 |
| staff | ok | 21926 | game_db, humans | **non importé** | — | 2.86 |
| staff_lists | ok | 3681 | game_db, humans | **non importé** | — | 0.0 |
| injury_types | ok | 93 | — | **non importé** | — | 0.0 |
| injuries | ok | 13803 | game_db, injury_manager | injuries | — | 0.28 |
| training | ok | 3 | game_db, humans, save_game_summary, training_man | **non importé** | — | 0.2 |
| mentoring | ok | 6 | game_db, humans, save_game_summary, training_man | **non importé** | — | 0.0 |
| tactics | failed | — | game_db, humans, save_game_summary, tactics_man | tactics (nom, mentalité, postes) | — | 0.19 |
| set_pieces | failed | — | — | **non importé** | — | 0.0 |
| facilities | ok | 489 | game_db, humans, save_game_summary | **non importé** | — | 0.21 |

## Sections

| Section | Schéma | Mo | Lecteurs | État |
|---|---:|---:|---|---|
| game_db.dat | 4000 | 193.88 | clubs, players, contracts, suspensions, managed_clubs, stages, competitions, fixtures, league_tables, transfer_windows, competition_rules, player_match_stats, player_season_stats, stadiums, finances, sponsorships, affiliates, job_vacancies, staff, staff_lists, injuries, training, mentoring, tactics, facilities | décodée avec échecs |
| person_db_changes.cmt | 3729 | 45.04 | — | non décodée |
| tc_record_man.dat | 24 | 21.76 | fixtures, league_tables, competition_rules, stadiums | importée |
| match_stats_cfg.dat | 6 | 19.92 | — | non décodée |
| news.dat | 2865 | 11.30 | fixtures, league_tables, competition_rules, stadiums | importée |
| person_record_history_dt.cmt | 2 | 10.29 | — | non décodée |
| transfer_man.dat | 35 | 6.05 | — | non décodée |
| used_player_data.dat | 35 | 5.22 | — | non décodée |
| hall_of_fame.dat | 10 | 4.97 | — | non décodée |
| tc_league_history_dt.cmt | 1 | 4.19 | — | non décodée |
| shortlist_man.dat | 50 | 3.99 | — | non décodée |
| comp_history_dt.cmt | 3 | 3.58 | — | non décodée |
| person_record_manager.dat | 30 | 2.77 | — | non décodée |
| starting_club_debt_db.cmt | 3729 | 2.75 | — | non décodée |
| press_conference_manager.dat | 10 | 2.50 | — | non décodée |
| manager_manager.dat | 35 | 2.25 | — | non décodée |
| tactics_man.dat | 26 | 1.52 | tactics | décodée avec échecs |
| player_stats_hist_dt.cmt | 6 | 1.43 | — | non décodée |
| person_record_history_ls.dat | 4 | 1.23 | — | non décodée |
| interaction_manager.dat | 47 | 1.23 | — | non décodée |
| injury_histories_dt.cmt | 2 | 1.06 | — | non décodée |
| tc_league_history_ls.dat | 4 | 0.74 | — | non décodée |
| regeneration_manager.dat | 46 | 0.71 | — | non décodée |
| award_year_hist_dt.cmt | 1 | 0.57 | — | non décodée |
| injury_histories_ls.dat | 4 | 0.38 | — | non décodée |
| media_man.dat | 18 | 0.33 | — | non décodée |
| weather_manager.dat | 3 | 0.29 | — | non décodée |
| injury_manager.dat | 8 | 0.29 | injuries | importée |
| tc_cup_history_dt.cmt | 1 | 0.16 | — | non décodée |
| sim_stats.dat | 1 | 0.14 | — | non décodée |
| edit_session_man.dat | 172 | 0.11 | — | non décodée |
| scout_man.dat | 31 | 0.08 | — | non décodée |
| tc_history_dt.cmt | 1 | 0.07 | — | non décodée |
| award_man.dat | 13 | 0.05 | — | non décodée |
| tc_cup_history_ls.dat | 4 | 0.04 | — | non décodée |
| award_year_hist_ls.dat | 4 | 0.03 | — | non décodée |
| official_manager.dat | 5 | 0.03 | — | non décodée |
| tc_history_ls.dat | 4 | 0.02 | — | non décodée |
| training_man.dat | 31 | 0.02 | training, mentoring | décodée, non importée |
| board_takeover_manager.dat | 5 | 0.01 | — | non décodée |
| memory_pools.dat | 0 | 0.01 | — | non décodée |
| backroom_advice_manager.dat | 18 | 0.01 | — | non décodée |
| humans.dat | 21 | 0.01 | managed_clubs, finances, sponsorships, staff, staff_lists, training, mentoring, tactics, facilities | décodée avec échecs |
| job_centre.dat | 1 | 0.01 | job_vacancies | décodée, non importée |
| game_info.dat | 46 | 0.01 | — | non décodée |
| finance_manager.dat | 17 | 0.01 | — | non décodée |
| contract_man.dat | 14 | 0.00 | — | non décodée |
| retirement_manager.dat | 2 | 0.00 | — | non décodée |
| team_talk_man.dat | 4 | 0.00 | — | non décodée |
| feeder_man.dat | 5 | 0.00 | affiliates | décodée, non importée |
| save_game_summary.dat | 29 | 0.00 | managed_clubs, finances, sponsorships, training, mentoring, tactics, facilities | décodée avec échecs |
| non_pl_hist_dt.cmt | 3 | 0.00 | — | non décodée |
| training_camp_man.dat | 1 | 0.00 | — | non décodée |
| tc_manager_history_dt.cmt | 2 | 0.00 | — | non décodée |
| agent_manager.dat | 2 | 0.00 | — | non décodée |
| non_pl_hist_ls.dat | 4 | 0.00 | — | non décodée |
| network_man.dat | 20 | 0.00 | — | non décodée |
| tc_manager_history_ls.dat | 4 | 0.00 | — | non décodée |
| fine_manager.dat | 1 | 0.00 | — | non décodée |
| matchday_manager.dat | 8 | 0.00 | — | non décodée |
| trade_man.dat | 11 | 0.00 | — | non décodée |
| morale_manager.dat | 4 | 0.00 | — | non décodée |
| pl_hist_ls.dat | 4 | 0.00 | — | non décodée |
| tc_best_eleven_history_ls.dat | 4 | 0.00 | — | non décodée |
| tc_extended_club_records_history_ls.dat | 4 | 0.00 | — | non décodée |
| tc_extended_nation_records_history_ls.dat | 4 | 0.00 | — | non décodée |
| award_club_hist_ls.dat | 4 | 0.00 | — | non décodée |
| database_analyser.dat | 2 | 0.00 | — | non décodée |
| captain_system.dat | 8 | 0.00 | — | non décodée |
| dynamics_pivotal_moments.dat | 3 | 0.00 | — | non décodée |
| play_fixture_manager.dat | 7 | 0.00 | — | non décodée |
| awol.dat | 1 | 0.00 | — | non décodée |
| fog_of_war.dat | 2 | 0.00 | — | non décodée |
| dispute.dat | 1 | 0.00 | — | non décodée |
| virtual_manager.dat | 1 | 0.00 | — | non décodée |
| financial_fair_play_manager.dat | 2 | 0.00 | — | non décodée |
| (trames non listées : statistiques de saison) | 0 | 0.00 | player_season_stats | importée |
