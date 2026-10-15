"""Disponibilité du jour : blessés en cours (date de retour), retours récents, suspensions."""

from datetime import timedelta

from clubdirector.database.mirror import MirrorTable, write_mirror
from clubdirector.game.availability import club_availability, find_club, unavailable_player_uids

OUR, OTHER = 5001, 5002
SAM, ALEX = 900003, 900001


def _setup(engine, tctx):
    k, today = tctx.ctx.career_id, tctx.ctx.game_date
    with engine.begin() as c:
        write_mirror(c, k, 1, [
            MirrorTable("injuries", ["kind", "player_uid", "player_name", "date", "type_name"], [
                ("typed", SAM, "Sam Sample", (today + timedelta(days=17)).isoformat(), "entorse des ligaments croisés"),
                ("typed", ALEX, "Alex Example", (today - timedelta(days=6)).isoformat(), "douleur à la cuisse"),
                ("history", SAM, "Sam Sample", (today - timedelta(days=40)).isoformat(), None),
            ]),
            MirrorTable("suspensions", ["player_uid", "player_name", "club_uid", "scope", "competition_id", "issued_date"], [
                (ALEX, "Alex Example", OTHER, "competition", 664, (today - timedelta(days=3)).isoformat()),
            ]),
        ])
    return k, today


def test_injured_today_means_a_return_date_still_ahead(engine, tctx):
    k, today = _setup(engine, tctx)
    ours = club_availability(engine, k, OUR, today)
    assert [x["joueur"] for x in ours["blesses"]] == ["Sam Sample"]
    assert ours["blesses"][0]["jours_restants"] == 17 and ours["blesses"][0]["blessure"] == "entorse des ligaments croisés"
    other = club_availability(engine, k, OTHER, today)
    assert other["blesses"] == [] and other["retours_recents"][0]["revenu_depuis_jours"] == 6
    assert other["suspendus"][0]["competition_id"] == 664
    assert unavailable_player_uids(engine, k, OUR, today) == {SAM}
    assert unavailable_player_uids(engine, k, OTHER, today) == {ALEX}  # suspendu, pas blessé


def test_same_named_women_club_does_not_hide_the_men_club(engine, tctx):
    k, _ = _setup(engine, tctx)
    with engine.begin() as c:
        write_mirror(c, k, 1, [
            MirrorTable("clubs", ["uid", "name", "short_name", "reputation"], [
                (OUR, "Northbridge FC", "Northbridge", 5000), (77, "Northbridge FC", "Northbridge", 9000)]),
            MirrorTable("player_rankings", ["table", "position", "women", "rank", "player_uid", "player_name", "score"], [
                (3, "DC", False, 1, SAM, "Sam Sample", 100)]),
        ])
    assert find_club(engine, k, "Northbridge FC")["uid"] == OUR  # mieux réputée, la section 77 n'a aucun joueur classé
    assert find_club(engine, k, "north")["uid"] in (OUR, 77)


def test_the_tool_reports_today_and_an_opponent(engine, registry, tctx):
    _setup(engine, tctx)
    r = registry.execute("get_injured_players", {}, tctx)
    assert r.ok and r.data["blesses"][0]["joueur"] == "Sam Sample"
    assert "retour prévue" in " ".join(r.limitations)
