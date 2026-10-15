"""Historique des championnats : rattachement prouvé, jamais deviné."""

from types import SimpleNamespace as NS

from clubdirector.game.history_links import link_runs_to_clubs


def row(run, year, comp, pos):
    return NS(run=run, season_end_year=year, competition_id=comp, position=pos)


def table(comp, *club_uids):
    return NS(competition_id=comp, rows=[NS(club_uid=u, team_slot=0) for u in club_uids])


def club(uid, last):
    return NS(uid=uid, last_league_position=last)


def test_unique_match_links_run_to_club():
    history = [row(0, 2024, 22, 6), row(0, 2025, 22, 5), row(1, 2025, 22, 8)]
    links = link_runs_to_clubs(history, [club(1100, 5), club(1200, 8)], [table(22, 1100, 1200)])
    assert [(r, u) for r, u, _ in links] == [(0, 1100), (1, 1200)]


def test_ambiguous_or_outdated_runs_are_not_linked():
    history = [row(0, 2025, 22, 5), row(1, 2025, 22, 5), row(2, 2019, 22, 3)]
    clubs = [club(1100, 5), club(1300, 3)]
    assert link_runs_to_clubs(history, clubs, [table(22, 1100, 1300)]) == []


def test_club_in_another_league_is_not_linked():
    history = [row(0, 2025, 22, 5)]
    assert link_runs_to_clubs(history, [club(1100, 5)], [table(23, 1100)]) == []


def test_tool_says_when_history_is_not_linked(registry, tctx):
    r = registry.execute("get_club_league_history", {}, tctx)
    assert r.ok and r.data["saisons"] == [] and "supposition" in r.limitations[0]
