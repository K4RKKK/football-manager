"""Hiérarchie du vestiaire calculée par le jeu (miroir fm_squad_influence)."""

from datetime import timedelta

from sqlalchemy import text

from clubdirector.database.mirror import MirrorTable, write_mirror
from clubdirector.game.dynamics import squad_hierarchy

SAM, ALEX, KIM = 900003, 900001, 900077
COLUMNS = ["list_index", "as_of", "latest", "club_uid", "club_name", "team_id", "team_slot", "rank", "person_index",
           "player_uid", "player_name", "influence", "tier"]


def _setup(engine, tctx):
    k, today, club = tctx.ctx.career_id, tctx.ctx.game_date, tctx.ctx.club_uid
    with engine.connect() as c:
        slot = c.execute(text("SELECT team_slot FROM players_current WHERE career_id = :k AND uid = :u"),
                         {"k": k, "u": SAM}).scalar()
    now, before = (today - timedelta(days=2)).isoformat(), (today - timedelta(days=25)).isoformat()
    rows = [
        (0, now, True, club, "Notre club", 1, slot, 1, 1, ALEX, "Alex Example", 9_500, "leader"),
        (0, now, True, club, "Notre club", 1, slot, 2, 2, KIM, "Kim Placeholder", 6_100, "influential"),
        (1, before, False, club, "Notre club", 1, slot, 1, 1, ALEX, "Alex Example", 8_999, "highly_influential"),
        (1, before, False, club, "Notre club", 1, slot, 2, 2, KIM, "Kim Placeholder", 5_000, "other"),
    ]
    with engine.begin() as c:
        write_mirror(c, k, 1, [MirrorTable("squad_influence", COLUMNS, rows)])
    return k, club, slot


def test_groups_come_from_the_latest_list_and_the_rest_of_the_squad_is_other(engine, tctx):
    k, club, slot = _setup(engine, tctx)
    h = squad_hierarchy(engine, k, club, slot)
    assert [p["joueur"] for p in h["leaders"]] == ["Alex Example"] and h["leaders"][0]["influence"] == 9_500
    assert [p["joueur"] for p in h["influents"]] == ["Kim Placeholder"] and h["tres_influents"] == []
    assert h["autres"] == [{"joueur": "Sam Sample", "player_uid": SAM, "influence": None, "hors_liste_du_jeu": True}]
    assert h["date_calcul"] == (tctx.ctx.game_date - timedelta(days=2)).isoformat()


def test_moves_since_the_previous_list(engine, tctx):
    k, club, slot = _setup(engine, tctx)
    moves = squad_hierarchy(engine, k, club, slot)["evolution"]["changements"]
    assert {(m["joueur"], m["avant"], m["maintenant"], m["sens"]) for m in moves} == {
        ("Alex Example", "très influent", "leader", "monte"), ("Kim Placeholder", "autre", "influent", "monte")}


def test_the_tool_reads_our_club_and_says_when_there_is_no_list(engine, registry, tctx):
    r = registry.execute("get_squad_hierarchy", {}, tctx)
    assert not r.ok  # pas encore de liste : le jeu ne l'a pas calculée ou pas de synchronisation
    _, _, slot = _setup(engine, tctx)
    r = registry.execute("get_squad_hierarchy", {"equipe_slot": slot}, tctx)
    assert r.ok and r.data["leaders"][0]["joueur"] == "Alex Example"
    assert any("seule sauvegarde" in x for x in r.limitations)
