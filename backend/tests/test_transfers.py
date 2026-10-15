"""Marché des transferts : offres réelles, valeur, acheteurs, plans de vente et d'achat, contrats."""

from sqlalchemy import text

from clubdirector.database.mirror import MirrorTable, write_mirror
from clubdirector.transfers.market import (
    Market,
    contract_proposal,
    counter_offer,
    find_buyers,
    purchase_plan,
    valuation,
)

OUR, SOUTHPORT, ATHLETIC, RICH, POOR = 5001, 5002, 5004, 5100, 5101
SAM, ALEX = 900003, 900001  # Sam Sample (notre défenseur), Alex Example (Southport)

OFFER_COLS = ["index", "kind", "status", "player_uid", "player_name", "bidding_club_uid", "bidding_club_name",
              "selling_club_uid", "selling_club_name", "amount", "offered_on", "effective_on", "deadline", "updated_on"]


def _market(engine, tctx):
    k = tctx.ctx.career_id
    with engine.begin() as c:
        c.execute(text("UPDATE players_current SET transfer_value = 2000000, contract_end = '2034-06-30' "
                       "WHERE career_id = :k AND uid = :u"), {"k": k, "u": SAM})
        write_mirror(c, k, 1, [
            MirrorTable("transfer_offers", OFFER_COLS, [
                # offre reçue, en cours : Example Athletic veut Sam Sample
                (0, "transfer", None, SAM, "Sam Sample", ATHLETIC, "Example Athletic", OUR, "Northbridge FC",
                 1_500_000, "2031-02-20", "2031-02-20", "2031-03-20", None),
                # transfert conclu ailleurs (marché observé)
                (1, "transfer", "completed", ALEX, "Alex Example", RICH, "Rich United", SOUTHPORT, "Southport Example",
                 2_250_000, "2030-08-01", "2030-08-01", "2030-09-01", "2030-08-03"),
                # notre offre pour Alex, accord pour plus tard ; une offre concurrente en cours
                (2, "transfer", 0x13, ALEX, "Alex Example", OUR, "Northbridge FC", SOUTHPORT, "Southport Example",
                 3_000_000, "2031-02-25", "2031-07-01", "2031-03-25", "2031-02-25"),
                (3, "loan", None, ALEX, "Alex Example", ATHLETIC, "Example Athletic", SOUTHPORT, "Southport Example",
                 100_000, "2031-02-26", "2031-02-26", "2031-03-26", None),
            ]),
            MirrorTable("player_rankings", ["table", "position", "women", "rank", "player_uid", "player_name", "score"], [
                (3, "DC", False, 5, SAM, "Sam Sample", 30000), (3, "DC", False, 40, ALEX, "Alex Example", 20000),
                (3, "DC", False, 41, 1, "Autre", 100),
            ]),
            MirrorTable("finances", ["club_uid", "club_name", "month", "transfer_budget_allocated", "transfer_budget_remaining",
                                     "wage_budget_weekly", "wage_payroll_weekly", "balance"], [
                (OUR, "Northbridge FC", "2031-02-01", 1_000_000, 500_000, 50_000, 40_000, 100_000),
                (RICH, "Rich United", "2031-02-01", 50_000_000, 40_000_000, 400_000, 300_000, 9_000_000),
                (POOR, "Poor Town", "2031-02-01", 10_000, 0, 5_000, 6_000, -50_000),
                (ATHLETIC, "Example Athletic", "2031-02-01", 1_000_000, 900_000, 20_000, 19_000, 0),
            ]),
        ])
        c.execute(text("UPDATE fm_clubs SET reputation = 5000 WHERE career_id = :k AND uid = :u"), {"k": k, "u": OUR})
    return Market(engine, k, tctx.ctx.game_date, OUR)


def test_real_offers_and_their_states(engine, tctx):
    m = _market(engine, tctx)
    received = m.offers(club_uid=OUR, side="recues")
    assert [o["player_name"] for o in received] == ["Sam Sample"] and received[0]["etat"] == "en_cours"
    made = m.offers(club_uid=OUR, side="faites")
    assert made[0]["etat"] == "accord_a_venir"  # effet le 01/07/2031, après la date du jeu
    assert {o["etat"] for o in m.offers(player_uid=ALEX)} == {"conclue", "accord_a_venir", "en_cours"}


def test_valuation_combines_value_contract_age_rank_and_market(engine, tctx):
    m = _market(engine, tctx)
    v = valuation(m, m.player(SAM))
    comp = v["composantes"]
    assert comp["meilleur_classement"] == {"poste": "DC", "rang": 5, "sur": 41} and comp["facteur_rang"] == 1.2
    assert comp["facteur_contrat"] == 1.1 and comp["facteur_age"] == 1.0
    assert v["estimation"] == int(2_000_000 * 1.1 * 1.0 * 1.2 * comp["facteur_marche"])
    assert v["plancher"] < v["estimation"] < v["prix_demande"]
    assert v["achat"]["premiere_offre"] < v["achat"]["cible"] < v["achat"]["plafond"]


def test_buyers_put_real_interest_first_and_drop_clubs_without_money(engine, tctx):
    m = _market(engine, tctx)
    res = find_buyers(m, m.player(SAM))
    clubs = [b["club_uid"] for b in res["acheteurs"]]
    assert clubs[0] == ATHLETIC  # a fait une offre réelle
    assert any("proposé le 2031-02-20" in r for r in res["acheteurs"][0]["raisons"])
    assert RICH in clubs and POOR not in clubs and OUR not in clubs


def test_counter_offer_and_contracts(engine, tctx):
    m = _market(engine, tctx)
    sam = m.player(SAM)
    v = valuation(m, sam)
    low = counter_offer(m, sam, None)  # dernière offre en cours : 1,5 M
    assert low["offre_recue"] == 1_500_000 and low["decision"] == "contre-proposer"
    assert low["contre_offre"] == int(v["prix_demande"] * 0.95)
    assert counter_offer(m, sam, v["prix_demande"] + 1)["decision"] == "accepter"
    renewal = contract_proposal(m, sam, OUR, renewal=True)
    assert renewal["duree_ans"] == 4 and renewal["salaire_cible_hebdo"] == int(2000 * 1.15)


def test_purchase_plan_shows_our_deal_the_competition_and_the_budget(engine, tctx):
    m = _market(engine, tctx)
    plan = purchase_plan(m, m.player(ALEX), OUR)
    assert [o["bidding_club_uid"] for o in plan["nos_offres"]] == [OUR]
    assert [o["bidding_club_uid"] for o in plan["concurrence"]] == [ATHLETIC]
    assert any("accord déjà trouvé" in n for n in plan["alertes"])
    assert plan["offre"]["structure"]["comptant_pct"] == 40  # cible au-dessus du budget restant (500 k)


def test_market_tools_are_offered_to_the_director(engine, registry, tctx):
    _market(engine, tctx)
    names = {t.name for t in registry.for_llm()}
    assert {"get_transfer_offers", "get_market_ranking", "evaluate_transfer_value", "find_buyers", "prepare_sale",
            "prepare_transfer_offer", "prepare_counter_offer", "prepare_contract_proposal"} <= names
    r = registry.execute("get_transfer_offers", {"direction": "recues"}, tctx)
    assert r.ok and r.data["offres"][0]["acheteur"] == "Example Athletic" and r.data["offres"][0]["etat"] == "en cours"
    r = registry.execute("find_buyers", {"player_uid": SAM}, tctx)
    assert r.ok and r.data["acheteurs"][0]["club_uid"] == ATHLETIC
    r = registry.execute("prepare_transfer_offer", {"player_uid": SAM}, tctx)
    assert not r.ok and "déjà au club" in r.error
