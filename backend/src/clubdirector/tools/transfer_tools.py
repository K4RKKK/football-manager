"""Outils du marché des transferts pour le directeur sportif (lecture et préparation, jamais d'action).

Ils lisent les offres réelles de la sauvegarde (transfer_man), les classements du marché du jeu
(shortlist_man) et les finances des clubs, et préparent ventes, achats, contre-offres et contrats
(moteur clubdirector/transfers/market.py). Montants affichés en devise étalonnée (euros).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import Field

from clubdirector.positions import LABEL_FR, normalize_position
from clubdirector.tools.registry import ToolArgs, ToolContext, ToolRegistry, ToolResult
from clubdirector.transfers.market import (
    POSITION_GROUP,
    RANKING_POSITION,
    Market,
    contract_proposal,
    counter_offer,
    find_buyers,
    purchase_plan,
    sale_plan,
    valuation,
)

KIND_FR = {"transfer": "transfert", "loan": "prêt"}
STATE_FR = {"conclue": "conclue", "echouee": "échouée", "en_cours": "en cours", "accord_a_venir": "accord pour plus tard",
            "sans_suite": "sans suite"}
NO_ACTION = ("Préparation uniquement : rien n'est envoyé dans FM26. L'entraîneur exécute dans le jeu, ou confie la "
             "négociation au directeur sportif du jeu (option de délégation de l'offre, ou écran des responsabilités du staff).")
ESTIMATE = "Prix, plafonds et salaires : estimations à règles explicites (voir « methode »), pas des prix du jeu."


class OffersArgs(ToolArgs):
    player_uid: int | None = Field(None, description="Un joueur précis (sinon : les offres de notre club).")
    name: str | None = Field(None, description="Nom du joueur si l'uid est inconnu.")
    direction: Literal["recues", "faites", "toutes"] = Field(
        "toutes", description="Pour notre club : offres reçues pour nos joueurs, faites par nous, ou toutes.")
    etat: Literal["toutes", "en_cours", "conclues", "echouees"] = "toutes"
    depuis_jours: int | None = Field(None, ge=1, le=3650, description="Seulement les offres des N derniers jours (date du jeu).")
    limit: int = Field(30, ge=1, le=200)


class PlayerArgs(ToolArgs):
    player_uid: int | None = Field(None, description="Identifiant du joueur (uid).")
    name: str | None = Field(None, description="Nom du joueur si l'uid est inconnu.")


class BuyersArgs(PlayerArgs):
    limit: int = Field(8, ge=1, le=25)


class CounterArgs(PlayerArgs):
    montant_recu: float | None = Field(None, description="Montant de l'offre reçue en devise affichée (sinon : la dernière offre en cours).")


class RankingArgs(ToolArgs):
    position: str | None = Field(None, description="Poste (code FM ou libellé : DC, ailier droit, attaquant…).")
    player_uid: int | None = Field(None, description="Un joueur : ses places dans les classements du marché.")
    name: str | None = None
    jeunes: bool = Field(False, description="Classement des jeunes talents.")
    limit: int = Field(15, ge=1, le=100)
    offset: int = Field(0, ge=0)


def _market(t: ToolContext) -> Market:
    return Market(t.engine, t.ctx.career_id, t.ctx.game_date, t.ctx.club_uid)


def _eur(t: ToolContext, raw: int | float | None) -> str | None:
    return None if raw is None else t.prefs.currency.format(int(raw))


def _player(t: ToolContext, uid: int | None, name: str | None) -> dict:
    """Le joueur demandé ; en cas d'homonymes, celui de notre club, sinon le mieux valorisé du nom exact."""
    from clubdirector.tools.catalog import PlayerRef, _resolve_player

    if uid is None and name:
        rows = t.repo.find_players_by_name(t.ctx, name, limit=10)
        exact = [r for r in rows if r["name"].casefold() == name.casefold()] or rows
        ours = [r for r in exact if r.get("club_uid") == t.ctx.club_uid]
        if len(ours) == 1:
            return ours[0]
        if len(exact) > 1 and len({r["name"].casefold() for r in exact}) == 1:
            return max(exact, key=lambda r: r.get("transfer_value") or 0)
    return _resolve_player(t, PlayerRef(player_uid=uid, name=name))


def _offer_view(t: ToolContext, o: dict) -> dict:
    out = {
        "date": o.get("offered_on"), "joueur": o.get("player_name"), "player_uid": o.get("player_uid"),
        "type": KIND_FR.get(o.get("kind"), o.get("kind")), "acheteur": o.get("bidding_club_name"),
        "vendeur": o.get("selling_club_name") or "libre", "montant": _eur(t, o.get("amount")),
        "etat": STATE_FR.get(o.get("etat"), o.get("etat")),
    }
    if o.get("effective_on") and o.get("effective_on") != o.get("offered_on"):
        out["effet"] = o["effective_on"]
    if o.get("updated_on") and o.get("updated_on") != o.get("offered_on"):
        out["derniere_evolution"] = o["updated_on"]
    return out


def _valuation_view(t: ToolContext, v: dict) -> dict:
    return {
        "valeur_du_jeu": _eur(t, v["valeur_jeu"]), "estimation": _eur(t, v["estimation"]),
        "prix_demande": _eur(t, v["prix_demande"]), "plancher": _eur(t, v["plancher"]),
        "achat": {k: _eur(t, x) for k, x in v["achat"].items()},
        "composantes": v["composantes"], "methode": v["methode"],
    }


def _contract_view(t: ToolContext, c: dict) -> dict:
    s = c.get("grille_equipe") or {}
    return {
        "type": c["type"], "duree_ans": c["duree_ans"], "fin_proposee": c["fin_proposee"],
        "salaire_actuel_hebdo": _eur(t, c["salaire_actuel_hebdo"]), "salaire_cible_hebdo": _eur(t, c["salaire_cible_hebdo"]),
        "salaire_plafond_hebdo": _eur(t, c["salaire_plafond_hebdo"]), "prime_signature": _eur(t, c["prime_signature"]),
        "primes": c["primes"], "clauses": c["clauses"],
        "grille_equipe_premiere": {k: (_eur(t, x) if k != "n" else x) for k, x in s.items()},
        "marge_salariale_hebdo": _eur(t, c["marge_salariale_hebdo"]), "impact_hebdo": _eur(t, c["impact_hebdo"]),
        "alertes": c["alertes"], "methode": c["methode"],
    }


def register_transfer_tools(reg: ToolRegistry) -> None:
    T = reg.tool

    @T("get_transfer_offers", "Offres de transfert et de prêt RÉELLES de la sauvegarde : reçues pour nos joueurs, faites par "
       "notre club, ou toutes celles d'un joueur (club acheteur, vendeur, montant, état, dates).", "lecture", OffersArgs)
    def get_transfer_offers(t: ToolContext, a: OffersArgs):
        m = _market(t)
        since = t.ctx.game_date - timedelta(days=a.depuis_jours) if a.depuis_jours and t.ctx.game_date else None
        if a.player_uid is not None or a.name:
            p = _player(t, a.player_uid, a.name)
            rows = m.offers(player_uid=p["uid"], state=a.etat, since=since, limit=a.limit)
            head = {"joueur": p["name"], "club": p.get("club_name")}
        else:
            if t.ctx.club_uid is None:
                raise LookupError("Club géré inconnu.")
            rows = m.offers(club_uid=t.ctx.club_uid, side=a.direction, state=a.etat, since=since, limit=a.limit)
            head = {"club": t.ctx.club_name, "direction": a.direction}
        return ToolResult("", True, data=head | {"nombre": len(rows), "offres": [_offer_view(t, o) for o in rows]},
                          limitations=["Offres enregistrées par le jeu (section transfer_man) ; « en cours » = ni conclue ni "
                                       "échouée (une offre refusée garde aussi cet état). Montants en devise affichée."])

    @T("get_market_ranking", "Classement du marché tenu par le jeu pour un poste (meilleurs joueurs du monde au poste), ou les "
       "places d'un joueur dans ces classements.", "lecture", RankingArgs)
    def get_market_ranking(t: ToolContext, a: RankingArgs):
        m = _market(t)
        if a.player_uid is not None or a.name:
            p = _player(t, a.player_uid, a.name)
            return {"joueur": p["name"], "classements": [
                {"poste": r["position"], "rang": r["rank"], "sur": r["total"]} for r in m.rankings(p["uid"])]}
        if a.jeunes:
            pos = "young"
        else:
            code = normalize_position(a.position)
            if code is None or code not in RANKING_POSITION:
                raise ValueError("Indiquez un poste (GK, DR, DL, DC, WBR, WBL, DM, MR, ML, MC, AMR, AML, AMC, STC) ou jeunes=true.")
            pos = RANKING_POSITION[code]
        rows = m.ranking_table(pos, limit=a.limit, offset=a.offset)
        return {"classement": "jeunes talents" if pos == "young" else LABEL_FR.get(normalize_position(a.position) or "", pos),
                "joueurs": [{"rang": r["rank"], "joueur": r["player_name"], "uid": r["player_uid"], "age": r["age"],
                             "club": r["club_name"], "valeur": _eur(t, r["transfer_value"]),
                             "fin_contrat": str(r["contract_end"])[:10] if r["contract_end"] else None} for r in rows]}

    @T("evaluate_transfer_value", "Estimation chiffrée du prix d'un joueur : valeur du jeu, contrat, âge, rang au marché, prix "
       "réellement payés pour des joueurs comparables ; prix demandé, plancher, offre d'achat et plafond.", "analyse", PlayerArgs)
    def evaluate_transfer_value(t: ToolContext, a: PlayerArgs):
        p = _player(t, a.player_uid, a.name)
        return ToolResult("", True, data={"joueur": p["name"], "club": p.get("club_name"),
                                          **_valuation_view(t, valuation(_market(t), p))}, limitations=[ESTIMATE])

    @T("find_buyers", "Clubs acheteurs pour un de nos joueurs : offres réelles déjà faites, clubs qui ont visé ce profil, budget "
       "transferts restant, besoin au poste, standing ; classés avec leurs raisons.", "analyse", BuyersArgs)
    def find_buyers_tool(t: ToolContext, a: BuyersArgs):
        p = _player(t, a.player_uid, a.name)
        res = find_buyers(_market(t), p, exclude=set(t.prefs.limits.excluded_clubs), limit=a.limit)
        return ToolResult("", True, data={
            "joueur": p["name"], "poste": LABEL_FR.get(res["poste"] or "", res["poste"]),
            "valeur": _valuation_view(t, res["valeur"]),
            "acheteurs": [b | {"budget_transferts_restant": _eur(t, b["budget_transferts_restant"]),
                               "marge_salariale_hebdo": _eur(t, b["marge_salariale_hebdo"]),
                               "offres_reelles": [o | {"montant": _eur(t, o["montant"]), "etat": STATE_FR.get(o["etat"], o["etat"]),
                                                       "type": KIND_FR.get(o["type"], o["type"])}
                                                  for o in b["offres_reelles"]]}
                          for b in res["acheteurs"]],
            "clubs_examines": res["clubs_examines"], "methode": res["methode"],
        }, limitations=[ESTIMATE, "Budgets : dernier mois de finances lu (489 clubs suivis par la sauvegarde).", NO_ACTION])

    @T("prepare_sale", "Plan de vente complet d'un de nos joueurs : prix affiché, plancher, acheteurs, offres déjà reçues, "
       "pourcentage à la revente, échéancier, alternative.", "analyse", PlayerArgs)
    def prepare_sale(t: ToolContext, a: PlayerArgs):
        p = _player(t, a.player_uid, a.name)
        plan = sale_plan(_market(t), p, exclude=set(t.prefs.limits.excluded_clubs))
        if p["uid"] in t.prefs.limits.never_sell:
            plan["strategie"]["alerte"] = "joueur marqué « jamais vendre » par l'entraîneur"
        st = plan["strategie"]
        return ToolResult("", True, data={
            "joueur": plan["joueur"], "valeur": _valuation_view(t, plan["valeur"]),
            "strategie": st | {"prix_affiche": _eur(t, st["prix_affiche"]), "plancher": _eur(t, st["plancher"])},
            "acheteurs": [{"club": b["club"], "score": b["score"], "raisons": b["raisons"],
                           "budget": _eur(t, b["budget_transferts_restant"])} for b in plan["acheteurs"]],
            "offres_recues": [_offer_view(t, o) for o in plan["offres_recues"]],
        }, limitations=[ESTIMATE, NO_ACTION])

    @T("prepare_transfer_offer", "Plan d'achat d'un joueur : première offre, cible, plafond, structure (comptant, versements, "
       "bonus, % à la revente), concurrence réelle, budget, contrat à proposer, tactique de négociation.", "analyse", PlayerArgs)
    def prepare_transfer_offer(t: ToolContext, a: PlayerArgs):
        if t.ctx.club_uid is None:
            raise LookupError("Club géré inconnu.")
        p = _player(t, a.player_uid, a.name)
        if p.get("club_uid") == t.ctx.club_uid:
            raise ValueError(f"{p['name']} est déjà au club : utilisez prepare_contract_proposal pour le prolonger.")
        plan = purchase_plan(_market(t), p, t.ctx.club_uid)
        lim = t.prefs.limits
        warnings = list(plan["alertes"])
        if lim.max_fee is not None and t.prefs.currency.to_display(plan["offre"]["plafond"]) and \
                t.prefs.currency.to_display(plan["offre"]["plafond"]) > lim.max_fee:
            warnings.append("plafond au-dessus de l'indemnité maximale fixée par l'entraîneur")
        return ToolResult("", True, data={
            "joueur": plan["joueur"], "club_vendeur": plan["club_vendeur"], "valeur": _valuation_view(t, plan["valeur"]),
            "offre": {k: (_eur(t, v) if k != "structure" else v) for k, v in plan["offre"].items()},
            "budget_transferts_restant": _eur(t, plan["budget_transferts_restant"]),
            "concurrence": [_offer_view(t, o) for o in plan["concurrence"]],
            "nos_offres": [_offer_view(t, o) for o in plan["nos_offres"]],
            "contrat": _contract_view(t, plan["contrat"]), "alertes": warnings, "negociation": plan["negociation"],
        }, limitations=[ESTIMATE, NO_ACTION])

    @T("prepare_counter_offer", "Réponse à une offre reçue pour un de nos joueurs : accepter ou contre-proposer, et à quel "
       "montant (par rapport au prix demandé et au plancher).", "analyse", CounterArgs)
    def prepare_counter_offer(t: ToolContext, a: CounterArgs):
        p = _player(t, a.player_uid, a.name)
        raw = t.prefs.currency.to_raw(a.montant_recu) if a.montant_recu is not None else None
        r = counter_offer(_market(t), p, raw)
        return ToolResult("", True, data={
            "joueur": r["joueur"], "offre_recue": _eur(t, r["offre_recue"]), "decision": r["decision"],
            "contre_offre": _eur(t, r["contre_offre"]), "plancher": _eur(t, r["plancher"]),
            "prix_demande": _eur(t, r["prix_demande"]),
        }, limitations=[ESTIMATE, NO_ACTION])

    @T("prepare_contract_proposal", "Proposition de contrat chiffrée (prolongation d'un de nos joueurs ou contrat d'une recrue) : "
       "durée, salaire cible et plafond, primes, clauses, impact sur la masse salariale.", "analyse", PlayerArgs)
    def prepare_contract_proposal(t: ToolContext, a: PlayerArgs):
        if t.ctx.club_uid is None:
            raise LookupError("Club géré inconnu.")
        p = _player(t, a.player_uid, a.name)
        renewal = p.get("club_uid") == t.ctx.club_uid
        c = contract_proposal(_market(t), p, t.ctx.club_uid, renewal=renewal)
        return ToolResult("", True, data={"joueur": p["name"], "fin_contrat_actuel": str(p.get("contract_end") or "")[:10] or None,
                                          **_contract_view(t, c)}, limitations=[ESTIMATE, NO_ACTION])


__all__ = ["register_transfer_tools", "POSITION_GROUP"]
