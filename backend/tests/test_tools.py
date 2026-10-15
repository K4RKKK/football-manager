"""Sections 9, 12.2, 19.2, 19.3 — outils, modes de connaissance, refus des actions."""

from datetime import date

from sqlalchemy import select

from clubdirector.database import schema as s
from clubdirector.money import calibrate
from clubdirector.preferences import Preferences


def run(registry, tctx, tool, **args):
    return registry.execute(tool, args, tctx)


def test_match_a_week_ago_uses_game_date_not_system_date(registry, tctx):
    r = run(registry, tctx, "get_match_details", days_ago=7)
    assert r.ok
    assert r.data["date_jeu"] == "2031-03-01"
    m = r.data["matchs"][0]
    assert m["date"] == "2031-02-20" and m["score"] == "3-1" and m["resultat"] == "victoire"
    assert r.provenance["game_date"] == "2031-03-01" and r.provenance["source"] == "save"


def test_unknown_scores_are_reported_not_invented(registry, tctx):
    r = run(registry, tctx, "get_recent_matches", limit=10)
    unknown = [m for m in r.data if not m["score_disponible"]]
    assert unknown and all(m["score"] is None and m["resultat"] is None for m in unknown)
    assert any("scores" in lim for lim in r.limitations)


def test_top_scorer_matches_database(registry, tctx, engine):
    r = run(registry, tctx, "get_top_players_stat", stat="goals", scope="tous")
    with engine.connect() as c:
        best = c.execute(select(s.season_stats.c.player_name, s.season_stats.c.goals)
                         .where(s.season_stats.c.kind == "overall").order_by(s.season_stats.c.goals.desc())).first()
    assert (r.data["classement"][0]["joueur"], r.data["classement"][0]["valeur"]) == (best.player_name, best.goals)


def test_previous_season_without_archive_says_so(registry, tctx):
    r = run(registry, tctx, "get_player_statistics", name="Alex Example", relative_season=-1)
    assert r.ok and r.data["lignes"] == []
    assert "2029/30" in r.limitations[0] and "2030/31" in r.limitations[0]


def test_unknown_player_is_refused(registry, tctx):
    r = run(registry, tctx, "get_player_statistics", name="Mbappé")
    assert not r.ok and "Aucun joueur" in r.error


def test_search_requires_currency_calibration_for_money_filters(registry, tctx):
    r = run(registry, tctx, "search_players", position="DC", max_value=10_000_000)
    assert not r.ok and "non étalonnée" in r.error


def test_search_results_are_verified_against_criteria(registry, tctx):
    """19.2 : « trois défenseurs centraux de moins de 23 ans à moins de 10 M » — vérif automatique."""
    tctx.prefs = Preferences(currency=calibrate(4_500_000, 9_000_000, "€", "test"))  # facteur 2
    for max_age, max_value in [(23, 10_000_000), (30, 10_000_000), (30, 8_000_000)]:
        r = run(registry, tctx, "search_players", position="défenseur central", max_age=max_age,
                max_value=max_value, limit=3, include_own_club=True)
        assert r.ok
        for p in r.data["resultats"]:
            assert "DC" in p["postes"]
            assert p["age"] <= max_age
            assert p["valeur"]["affiche"] <= max_value
            assert tctx.repo.player(tctx.ctx, p["uid"]) is not None  # le joueur existe dans la sauvegarde
    young = run(registry, tctx, "search_players", position="DC", max_age=23, max_value=10_000_000)
    assert young.data["total"] == 0  # aucun DC de moins de 23 ans dans la sauvegarde synthétique


def test_realistic_mode_hides_hidden_data(registry, tctx):
    r = run(registry, tctx, "get_player_profile", player_uid=900001)
    assert "ca" not in r.data and "pa" not in r.data and "personnalite" not in r.data
    assert "consistency" not in r.data["attributs"] and "injury_proneness" not in r.data["attributs"]
    assert "finishing" in r.data["attributs"]
    assert any("Brouillard" in lim for lim in r.limitations)


def test_advanced_mode_requires_explicit_confirmation(registry, tctx):
    tctx.prefs = Preferences(knowledge_mode="avance", advanced_mode_confirmed=False)
    assert "ca" not in run(registry, tctx, "get_player_profile", player_uid=900001).data
    tctx.prefs = Preferences(knowledge_mode="avance", advanced_mode_confirmed=True)
    d = run(registry, tctx, "get_player_profile", player_uid=900001).data
    assert d["ca"] == 140 and d["pa"] == 165 and "consistency" in d["attributs"]


def test_action_tools_are_unavailable_and_hidden_from_llm(registry, tctx, engine):
    names = {t.name for t in registry.for_llm()}
    for action in ("submit_transfer_offer", "add_player_to_shortlist", "submit_contract_proposal", "withdraw_offer"):
        assert action not in names
        r = run(registry, tctx, action, player_uid=900001, amount=1)
        assert not r.ok and "non prouvée" in r.error and r.data is None
    with engine.connect() as c:
        audited = c.execute(select(s.tool_audit.c.tool, s.tool_audit.c.ok).where(s.tool_audit.c.category == "action")).all()
    assert audited and all(ok is False for _, ok in audited)


def test_unknown_tool_and_bad_arguments_are_refused(registry, tctx):
    assert not registry.execute("os_system", {"cmd": "rm -rf /"}, tctx).ok
    r = registry.execute("get_recent_matches", {"limit": 5, "inject": "x"}, tctx)
    assert not r.ok and "Arguments invalides" in r.error
    r = registry.execute("get_recent_matches", {"limit": 10_000}, tctx)
    assert not r.ok


def test_affordability_compares_with_budget(registry, tctx):
    tctx.prefs = Preferences(currency=calibrate(1, 1.0, "€", "test"))
    r = run(registry, tctx, "estimate_wage_affordability", fee=40_000_000, weekly_wage=1000)
    assert r.ok
    assert r.data["indemnite"]["faisable"] is False and r.data["indemnite"]["budget_restant"] == 300_000
    assert r.data["salaire"]["marge_hebdo"] == 4000 and r.data["salaire"]["faisable"] is True


def test_recruitment_targets_are_real_players_and_explained(registry, tctx):
    r = run(registry, tctx, "find_recruitment_targets", role="dc_stoppeur", limit=5)
    assert r.ok and r.data["cibles"]
    for c in r.data["cibles"]:
        row = tctx.repo.player(tctx.ctx, c["uid"])
        assert row is not None and row["club_uid"] != tctx.ctx.club_uid
        assert 0 <= c["compatibilite"] <= 100
    assert "85 %" in r.data["methode"]


def test_memory_preference_is_persisted_and_replaced(registry, tctx):
    run(registry, tctx, "remember", kind="preference", text="Pas de recrue de plus de 28 ans", key="age_max", value=28)
    run(registry, tctx, "remember", kind="preference", text="Pas de recrue de plus de 26 ans", key="age_max", value=26)
    mems = run(registry, tctx, "list_memories").data
    assert [m["texte"] for m in mems] == ["Pas de recrue de plus de 26 ans"]


def test_alerts_are_deterministic_and_not_duplicated(sync, game_dir, engine, tctx):
    from clubdirector.proactive.rules import run_rules

    before = len(tctx.repo.alerts(tctx.ctx))
    assert before > 0
    assert run_rules(engine, tctx.ctx.career_id) == 0
    assert len(tctx.repo.alerts(tctx.ctx)) == before


def test_contract_alert_wording_and_threshold():
    from clubdirector.database.repositories import CareerContext
    from clubdirector.proactive.rules import contract_alerts

    ctx = CareerContext(1, "x", 1, "Club", None, date(2031, 1, 1), 2030, "t", 1, None, {})
    squad = [
        {"uid": 1, "name": "Titulaire DC", "contract_end": date(2032, 7, 1)},  # 18 mois
        {"uid": 2, "name": "Long contrat", "contract_end": date(2034, 6, 30)},
        {"uid": 3, "name": "Fin proche", "contract_end": date(2031, 6, 30)},
    ]
    alerts = contract_alerts(ctx, squad)
    assert [a["data"]["player_uid"] for a in alerts] == [1, 3]
    assert "dix-huit" not in alerts[0]["message"] and "18 mois" in alerts[0]["message"]
    assert alerts[1]["severity"] == "haute"
