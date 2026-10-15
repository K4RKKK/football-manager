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


def _index(groups):
    """Index synthétique au format mesuré : (premier enregistrement, nombre)."""
    import struct
    body = b"\x03\x01tad.\x04\x00" + struct.pack("<II", 0, len(groups))
    for first, count in groups:
        vals = [first * 24, 24] * count
        body += struct.pack(f"<I{count}I", count, *vals[:count])
    return body + b"\x18\x00\x00\x00\x01\x00"


def test_index_order_fills_a_gap_only_when_unique():
    # Trois séries stockées ; l'index les range par uid de club : 10 (ancre), 20, 30 (ancre).
    history = [row(0, 2025, 1, 3), row(1, 2025, 9, 7), row(2, 2025, 1, 4)]
    clubs = [NS(uid=10, last_league_position=3, nation_id=5), NS(uid=20, last_league_position=None, nation_id=5),
             NS(uid=30, last_league_position=4, nation_id=5)]
    tables = [NS(competition_id=1, rows=[NS(club_uid=10, team_slot=0), NS(club_uid=30, team_slot=0)])]
    links = link_runs_to_clubs(history, clubs, tables, _index([(0, 1), (1, 1), (2, 1)]))
    assert [(r, u) for r, u, _ in links] == [(0, 10), (1, 20), (2, 30)]
    # Deux clubs possibles pour une seule série entre les ancres : rien n'est attribué au milieu.
    clubs.insert(2, NS(uid=25, last_league_position=None, nation_id=5))
    links = link_runs_to_clubs(history, clubs, tables, _index([(0, 1), (1, 1), (2, 1)]))
    assert [(r, u) for r, u, _ in links] == [(0, 10), (2, 30)]
