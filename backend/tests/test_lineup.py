"""Composition déterministe : chaque joueur à un poste où sa note FM26 le permet."""

from clubdirector.tools.lineup import SYSTEMS, best_lineup, familiarity, hungarian


def _p(uid, name, ratings, minutes=500, value=1_000_000, condition=9500):
    return {"uid": uid, "name": name, "position_ratings": ratings, "transfer_value": value, "condition": condition}, {
        uid: {"minutes": minutes, "starts": 5, "substitute_appearances": 0, "average_rating": 7.0}}


def _squad():
    rows, seasons = [], {}
    spec = [
        ("Gardien", {"gk": 20}), ("Gardien2", {"gk": 20}, 0),
        ("DD", {"dr": 20, "wbr": 19}), ("DC1", {"dc": 20}), ("DC2", {"dc": 20}), ("DG", {"dl": 20, "wbl": 20}),
        ("Sentinelle1", {"dm": 20, "mc": 20}), ("Sentinelle2", {"dm": 20, "mc": 20}),
        ("Pellegrini", {"mc": 20, "amc": 20, "dm": 15, "aml": 10}, 900),  # milieu : jamais ailier droit
        ("Meneur", {"amc": 20}, 400), ("AilierD", {"amr": 20}, 300), ("AilierG", {"aml": 18, "stc": 20}, 300),
        ("Buteur", {"stc": 20}, 600),
    ]
    for i, item in enumerate(spec):
        name, ratings, *rest = item
        row, season = _p(i + 1, name, ratings, minutes=rest[0] if rest else 500)
        rows.append(row)
        seasons.update(season)
    return rows, seasons


def test_hungarian_finds_the_cheapest_assignment():
    assert hungarian([[4, 1, 3], [2, 0, 5], [3, 2, 2]]) == [1, 0, 2]


def test_familiarity_forbids_positions_below_ten():
    assert familiarity(20) == 1.0 and familiarity(9) is None and familiarity(None) is None


def test_every_player_plays_where_his_rating_allows():
    rows, seasons = _squad()
    out = best_lineup(rows, seasons, "4-2-3-1")
    by_slot = [(x["poste"], x["joueur"], x["note_poste"]) for x in out["onze"]]
    assert all(rating >= 15 for _, _, rating in by_slot) and not out["alertes"]
    assert ("AMR", "AilierD", 20) in by_slot
    assert all(not (name == "Pellegrini" and slot in ("AMR", "AML", "STC")) for slot, name, _ in by_slot)
    assert len({name for _, name, _ in by_slot}) == 11


def test_missing_position_is_flagged_not_invented():
    rows, seasons = _squad()
    rows = [r for r in rows if r["name"] != "AilierD"]
    out = best_lineup(rows, seasons, "4-2-3-1")
    assert any("Ailier droit" in a or "dépanne" in a for a in out["alertes"])


def test_all_systems_have_eleven_positions():
    assert all(len(slots) == 11 and slots[0] == "GK" for slots in SYSTEMS.values())


def test_tool_excludes_players_named_by_the_coach(registry, tctx):
    r = registry.execute("propose_lineup", {"systeme": "4-4-2", "absents": ["Sam Sample"]}, tctx)
    if r.ok:  # sauvegarde synthétique : effectif parfois trop court pour onze joueurs
        assert all(x["joueur"] != "Sam Sample" for x in r.data["onze"])
    else:
        assert "joueurs disponibles" in r.error


def test_lineup_requests_are_detected_with_system_absents_and_rotation():
    from clubdirector.ai.orchestrator import lineup_request

    assert lineup_request("Quel onze tu alignerais jeudi contre Samsunspor ?") == {}
    assert lineup_request("Fais-moi la compo en 4-3-3 sans Dybala et Pellegrini") == {
        "systeme": "4-3-3", "absents": ["Dybala", "Pellegrini"]}
    assert lineup_request("On fait tourner dimanche, qui doit jouer ?") == {"rotation": True}
    assert lineup_request("Et en 4-3-3 sans Dybala ?") == {"systeme": "4-3-3", "absents": ["Dybala"]}
    assert lineup_request("Comment ça va ?") is None and lineup_request("Prolonge Dybala") is None


def test_a_lineup_question_gets_the_computed_eleven_before_the_model_answers(engine, registry, tctx):
    from clubdirector.ai.orchestrator import Orchestrator
    from clubdirector.ai.providers.base import StepResult

    from .test_ai import ScriptedProvider

    p = ScriptedProvider([StepResult("Voilà mon onze.")])
    a = Orchestrator(engine, registry, [p]).send(tctx, "entraineur_adjoint", "Quel onze tu alignerais samedi ?")
    assert a.tools[0]["tool"] == "propose_lineup"
    if a.tools[0]["ok"]:
        assert "Composition calculée par l'outil propose_lineup" in p.history[-1]["content"]


def test_injured_and_suspended_players_are_left_out(engine, registry, tctx):
    from sqlalchemy import text

    from clubdirector.database.mirror import MirrorTable, write_mirror

    squad = tctx.repo.squad(tctx.ctx)
    if len(squad) < 12:
        return  # sauvegarde synthétique trop courte pour onze joueurs
    hurt = squad[0]
    with engine.begin() as c:
        write_mirror(c, tctx.ctx.career_id, 1, [MirrorTable("injuries", ["player_uid", "kind", "type_name", "date"], [
            (hurt["uid"], "typed", "Entorse", "2099-01-01")])])
        c.execute(text("SELECT 1"))
    r = registry.execute("propose_lineup", {}, tctx)
    assert r.ok and all(x["joueur"] != hurt["name"] for x in r.data["onze"])
    assert any(x["joueur"] == hurt["name"] and "blessé" in x["raison"] for x in r.data["exclus"])


def test_lineup_follow_ups_are_recomputed():
    from clubdirector.ai.orchestrator import lineup_request

    shown = "Je partirais sur ce 4-2-3-1 :\n\nSvilar\nWesley, Mancini, Gadou, Angeliño"
    assert lineup_request("Et sans Dybala ?", shown) == {"absents": ["Dybala"]}
    assert lineup_request("Et sans Dybala ?") is None  # sans onze juste avant : pas une composition
    assert lineup_request("On fait tourner dimanche, qui joue ?") == {"rotation": True}
