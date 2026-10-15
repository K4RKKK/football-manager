"""Dossiers du directeur sportif : opérations préparées, puis suivies dans les sauvegardes suivantes.

Quand le directeur prépare un achat, une vente, une contre-offre ou un contrat (outils `prepare_*`),
l'opération devient un dossier ouvert, avec l'état réel du joueur à ce moment-là (club, contrat,
offres déjà connues). À chaque nouvelle sauvegarde, `review` compare avec les données réelles :
offre faite par notre club, offre reçue, transfert conclu, offre échouée, joueur parti ailleurs,
contrat prolongé… Chaque changement est un événement daté, signalé une seule fois à l'entraîneur
(messages proactifs). Rien n'est exécuté dans FM26 : c'est l'entraîneur qui agit dans le jeu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, insert, select, update

from clubdirector.database import schema as s
from clubdirector.transfers.market import Market, valuation

# Outil de préparation -> type de dossier (une contre-offre fait partie d'une vente).
DOSSIER_TOOLS = {"prepare_transfer_offer": "achat", "prepare_sale": "vente", "prepare_counter_offer": "vente",
                 "prepare_contract_proposal": "contrat"}
OPEN_STATUSES = ("ouvert", "offre_faite", "offre_recue", "accord")
STATUS_FR = {"ouvert": "ouvert (rien encore dans le jeu)", "offre_faite": "offre faite", "offre_recue": "offre reçue",
             "accord": "accord pour plus tard", "conclu": "conclu", "refuse": "offre échouée", "sans_suite": "sans suite",
             "parti": "joueur parti ailleurs", "clos": "clos"}
KIND_FR = {"achat": "achat", "vente": "vente", "contrat": "prolongation de contrat"}
STALE_DAYS = 90  # un dossier sans aucun mouvement depuis 90 jours de jeu est classé sans suite


def _d(x: Any) -> date | None:
    if x is None or isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def offer_key(o: dict) -> str:
    """Clé stable d'une offre d'une sauvegarde à l'autre (la position dans la section ne l'est pas)."""
    return f"offre|{o.get('player_uid')}|{o.get('bidding_club_uid')}|{o.get('kind')}|{str(o.get('offered_on') or '')[:10]}"


def seen_token(o: dict) -> str:
    """Une offre DANS un état : un changement d'état (en cours -> conclue) la fait réapparaître."""
    return f"{offer_key(o)}#{o.get('etat')}"


@dataclass
class DossierChange:
    """Changement constaté dans la sauvegarde pour un dossier."""

    dossier_id: int
    kind: str
    player_uid: int
    player_name: str
    status: str
    detail: str
    fact_key: str
    data: dict

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class DossierStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ------------------------------------------------------------------ ouverture
    def open_from_tool(self, tctx, tool: str, args: dict, data: dict | None, *, role: str | None = None,
                       conversation_id: int | None = None) -> int | None:
        """Ouvre (ou met à jour) le dossier d'une préparation réussie. None si l'outil n'ouvre pas de dossier."""
        kind = DOSSIER_TOOLS.get(tool)
        if kind is None or tctx.ctx.club_uid is None:
            return None
        from clubdirector.tools.transfer_tools import _player

        try:
            p = _player(tctx, (args or {}).get("player_uid"), (args or {}).get("name"))
        except (LookupError, ValueError):
            return None
        ours = p.get("club_uid") == tctx.ctx.club_uid
        if kind == "contrat" and not ours:
            kind = "achat"  # contrat d'une recrue : le dossier suit son arrivée
        if kind == "achat" and ours:
            return None
        if kind == "vente" and not ours:
            return None
        market = Market(tctx.engine, tctx.ctx.career_id, tctx.ctx.game_date, tctx.ctx.club_uid)
        offers = market.offers(player_uid=p["uid"], limit=200)
        baseline = {"club_uid": p.get("club_uid"), "club_name": p.get("club_name"),
                    "contract_end": str(p.get("contract_end") or "")[:10] or None, "wage": p.get("wage"),
                    "transfer_value": p.get("transfer_value"), "seen_offers": sorted({seen_token(o) for o in offers})}
        plan = _plan_summary(tool, data or {})
        now = datetime.now(UTC)
        d = s.dossiers.c
        with self.engine.begin() as c:
            existing = c.execute(select(d.id, d.plan).where(
                d.career_id == tctx.ctx.career_id, d.kind == kind, d.player_uid == p["uid"],
                d.status.in_(OPEN_STATUSES))).first()
            if existing is not None:
                merged = dict(existing.plan or {}) | plan
                c.execute(update(s.dossiers).where(d.id == existing.id).values(plan=merged, updated_at=now))
                return existing.id
            return c.execute(insert(s.dossiers).values(
                career_id=tctx.ctx.career_id, kind=kind, player_uid=p["uid"], player_name=p["name"],
                club_uid=None if ours else p.get("club_uid"), club_name=None if ours else p.get("club_name"),
                status="ouvert", detail="préparé par le directeur sportif ; rien n'est encore fait dans le jeu",
                plan=plan, baseline=baseline,
                events=[{"date": _iso(tctx.ctx.game_date), "statut": "ouvert", "detail": f"dossier ouvert ({tool})"}],
                role=role, conversation_id=conversation_id, opened_game_date=tctx.ctx.game_date,
                created_at=now, updated_at=now)).inserted_primary_key[0]

    # ------------------------------------------------------------------ lecture
    def list(self, career_id: int, *, open_only: bool = False) -> list[dict]:
        d = s.dossiers.c
        q = select(s.dossiers).where(d.career_id == career_id)
        if open_only:
            q = q.where(d.status.in_(OPEN_STATUSES))
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(q.order_by(d.id.desc()))]

    # ------------------------------------------------------------------ suivi
    def review(self, tctx) -> list[DossierChange]:
        """Compare chaque dossier ouvert avec la sauvegarde active ; enregistre et renvoie les changements."""
        ctx = tctx.ctx
        if ctx.club_uid is None:
            return []
        market = Market(tctx.engine, ctx.career_id, ctx.game_date, ctx.club_uid)
        changes: list[DossierChange] = []
        for row in self.list(ctx.career_id, open_only=True):
            found, tokens, current = self._check(tctx, market, row)
            base = row.get("baseline") or {}
            if found or tokens or any(base.get(k) != v for k, v in current.items()):
                self._apply(row, found, tokens, current, ctx.game_date)
                changes.extend(found)
        return changes

    def _check(self, tctx, market: Market, row: dict) -> tuple[list[DossierChange], set[str], dict]:
        """Changements, offres vues et nouvel état de référence d'un joueur visé à l'achat (club, contrat)."""
        ctx, fmt = tctx.ctx, tctx.prefs.currency.format
        base = row.get("baseline") or {}
        seen = set(base.get("seen_offers") or [])
        p = market.player(row["player_uid"])
        name = (p or {}).get("name") or row["player_name"]
        out: list[DossierChange] = []

        def change(status: str, detail: str, key: str, **data) -> None:
            out.append(DossierChange(row["id"], row["kind"], row["player_uid"], name, status, detail, key,
                                     {"dossier": row["id"], "type": KIND_FR[row["kind"]], "statut": STATUS_FR[status],
                                      "joueur": name, **data}))

        if p is None:
            change("clos", f"{name} n'apparaît plus dans la sauvegarde (retraite ou base modifiée)",
                   f"dossier|{row['id']}|clos")
            return out, set(), {}
        offers = [o for o in market.offers(player_uid=p["uid"], limit=200) if seen_token(o) not in seen]
        offers.sort(key=lambda o: (str(o.get("offered_on") or ""), str(o.get("updated_on") or "")))
        ours_now = p.get("club_uid") == ctx.club_uid

        def offer_text(o: dict) -> str:
            amount = fmt(o["amount"]) if o.get("amount") else "montant non lu"
            kind = "prêt" if o.get("kind") == "loan" else "transfert"
            return f"{kind}, {amount}, le {_fr(o.get('offered_on'))}"

        if row["kind"] == "achat":
            mine = [o for o in offers if o.get("bidding_club_uid") == ctx.club_uid]
            last = mine[-1] if mine else None
            if ours_now:
                done = next((o for o in reversed(mine) if o["etat"] == "conclue"), last)
                change("conclu", f"{name} a rejoint le club" + (f" ({offer_text(done)})" if done else ""),
                       f"dossier|{row['id']}|conclu", offre=_offer_data(done, fmt))
            elif last is not None:
                status = {"conclue": "conclu", "echouee": "refuse", "accord_a_venir": "accord",
                          "sans_suite": "sans_suite"}.get(last["etat"], "offre_faite")
                detail = {"offre_faite": "notre offre est enregistrée dans le jeu, en attente de réponse",
                          "conclu": "notre offre a abouti", "refuse": "notre offre a échoué",
                          "accord": f"accord trouvé, effet le {_fr(last.get('effective_on'))}",
                          "sans_suite": "notre offre est restée sans suite (échéance passée)"}[status]
                change(status, f"{detail} ({offer_text(last)}, club vendeur : {last.get('selling_club_name') or 'inconnu'})",
                       offer_key(last) + f"|{status}", offre=_offer_data(last, fmt))
            elif p.get("club_uid") != base.get("club_uid"):
                change("parti", f"{name} a signé ailleurs : {p.get('club_name') or 'club inconnu'}",
                       f"dossier|{row['id']}|parti", nouveau_club=p.get("club_name"))
            elif (now_end := _d(p.get("contract_end"))) and (before := _d(base.get("contract_end"))) and now_end > before:
                # Le joueur visé a prolongé chez son club : le dossier reste ouvert, mais son prix change.
                target = valuation(market, p)["achat"]["cible"]
                change(row["status"], f"{name} a prolongé à {p.get('club_name') or 'son club'} jusqu'au {_fr(now_end)} "
                       f"(avant : {_fr(before)}) ; prix cible réestimé à {fmt(target)}",
                       f"dossier|{row['id']}|prolonge|{now_end.isoformat()}", fin_contrat=now_end.isoformat(),
                       prix_cible=fmt(target))
        elif row["kind"] == "vente":
            received = [o for o in offers if o.get("selling_club_uid") == ctx.club_uid]
            if not ours_now:
                done = next((o for o in reversed(received) if o["etat"] == "conclue"
                             and o.get("bidding_club_uid") == p.get("club_uid")), None)
                change("conclu", f"{name} a quitté le club pour {p.get('club_name') or 'un autre club'}"
                       + (f" ({offer_text(done)})" if done else ""), f"dossier|{row['id']}|conclu",
                       nouveau_club=p.get("club_name"), offre=_offer_data(done, fmt))
            else:
                for o in received:
                    status = {"conclue": "conclu", "echouee": "refuse", "accord_a_venir": "accord"}.get(o["etat"], "offre_recue")
                    detail = {"offre_recue": "offre reçue", "conclu": "offre acceptée", "refuse": "offre échouée",
                              "accord": f"accord pour un départ le {_fr(o.get('effective_on'))}"}[status]
                    change(status, f"{detail} de {o.get('bidding_club_name') or 'un club'} ({offer_text(o)})",
                           offer_key(o) + ("" if status == "offre_recue" else f"|{status}"),
                           offre=_offer_data(o, fmt), club=o.get("bidding_club_name"))
        else:  # contrat (prolongation d'un de nos joueurs)
            before, now_end = _d(base.get("contract_end")), _d(p.get("contract_end"))
            if not ours_now:
                change("parti", f"{name} a quitté le club ({p.get('club_name') or 'sans club'}) avant toute prolongation",
                       f"dossier|{row['id']}|parti", nouveau_club=p.get("club_name"))
            elif now_end and (before is None or now_end > before):
                wage = f", salaire {fmt(p['wage'])} par semaine" if p.get("wage") else ""
                was = f" (avant : {fmt(base['wage'])})" if base.get("wage") and base.get("wage") != p.get("wage") else ""
                change("conclu", f"{name} a prolongé jusqu'au {_fr(now_end)}{wage}{was}",
                       f"dossier|{row['id']}|conclu", fin_contrat=now_end.isoformat(), ancienne_fin=_iso(before))
            elif now_end and ctx.game_date and now_end < ctx.game_date:
                change("sans_suite", f"le contrat de {name} est arrivé à échéance le {_fr(now_end)} sans prolongation",
                       f"dossier|{row['id']}|sans_suite")
        opened = _d(row.get("opened_game_date"))
        if not out and row["status"] == "ouvert" and opened and ctx.game_date and ctx.game_date - opened > timedelta(days=STALE_DAYS):
            change("sans_suite", f"rien n'a bougé dans le jeu depuis l'ouverture du dossier le {_fr(opened)}",
                   f"dossier|{row['id']}|sans_suite")
        current = {} if row["kind"] != "achat" else {
            "club_uid": p.get("club_uid"), "club_name": p.get("club_name"),
            "contract_end": str(p.get("contract_end") or "")[:10] or None}
        return out, {seen_token(o) for o in offers}, current

    def _apply(self, row: dict, found: list[DossierChange], tokens: set[str], current: dict,
               game_date: date | None) -> None:
        base = dict(row.get("baseline") or {}) | current
        base["seen_offers"] = sorted(set(base.get("seen_offers") or []) | tokens)
        values: dict = {"baseline": base, "updated_at": datetime.now(UTC)}
        if found:
            last = found[-1]
            values |= {"status": last.status, "detail": last.detail,
                       "events": list(row.get("events") or []) + [{"date": _iso(game_date), "statut": ch.status,
                                                                    "detail": ch.detail, "cle": ch.fact_key,
                                                                    "donnees": ch.data} for ch in found],
                       "closed_game_date": game_date if last.status not in OPEN_STATUSES else None}
        with self.engine.begin() as c:
            c.execute(update(s.dossiers).where(s.dossiers.c.id == row["id"]).values(**values))


def pending_changes(rows: list[dict]) -> list[DossierChange]:
    """Changements enregistrés dans l'historique des dossiers (à signaler s'ils ne l'ont pas encore été)."""
    out = []
    for row in rows:
        for ev in row.get("events") or []:
            if ev.get("cle"):
                out.append(DossierChange(row["id"], row["kind"], row["player_uid"], (ev.get("donnees") or {}).get("joueur")
                                         or row["player_name"], ev["statut"], ev["detail"], ev["cle"], ev.get("donnees") or {}))
    return out


def dossier_view(row: dict) -> dict:
    """Présentation d'un dossier (outil list_dossiers, API)."""
    return {"id": row["id"], "type": KIND_FR.get(row["kind"], row["kind"]), "joueur": row["player_name"],
            "club_en_face": row.get("club_name"), "statut": STATUS_FR.get(row["status"], row["status"]),
            "ouvert": row["status"] in OPEN_STATUSES, "detail": row.get("detail"), "plan": row.get("plan") or {},
            "ouvert_le": _iso(row.get("opened_game_date")), "clos_le": _iso(row.get("closed_game_date")),
            "historique": row.get("events") or []}


def _plan_summary(tool: str, data: dict) -> dict:
    """Les chiffres clés de la préparation (déjà en devise affichée)."""
    if tool == "prepare_transfer_offer":
        offer = data.get("offre") or {}
        contract = data.get("contrat") or {}
        return {"offre": {k: offer.get(k) for k in ("premiere", "cible", "plafond") if offer.get(k)},
                "salaire_cible_hebdo": contract.get("salaire_cible_hebdo"), "club_vendeur": data.get("club_vendeur")}
    if tool == "prepare_sale":
        st = data.get("strategie") or {}
        return {"prix_affiche": st.get("prix_affiche"), "plancher": st.get("plancher")}
    if tool == "prepare_counter_offer":
        return {"offre_recue": data.get("offre_recue"), "decision": data.get("decision"),
                "contre_offre": data.get("contre_offre"), "plancher": data.get("plancher")}
    if tool == "prepare_contract_proposal":
        return {"duree_ans": data.get("duree_ans"), "fin_proposee": data.get("fin_proposee"),
                "salaire_cible_hebdo": data.get("salaire_cible_hebdo"), "salaire_plafond_hebdo": data.get("salaire_plafond_hebdo")}
    return {}


def _offer_data(o: dict | None, fmt) -> dict | None:
    if not o:
        return None
    return {"club_acheteur": o.get("bidding_club_name"), "club_vendeur": o.get("selling_club_name"),
            "montant": fmt(o["amount"]) if o.get("amount") else None, "type": "prêt" if o.get("kind") == "loan" else "transfert",
            "date": str(o.get("offered_on") or "")[:10] or None}


def _iso(d: Any) -> str | None:
    d = _d(d)
    return d.isoformat() if d else None


def _fr(d: Any) -> str:
    d = _d(d)
    return d.strftime("%d/%m/%Y") if d else "?"


__all__ = ["DOSSIER_TOOLS", "DossierChange", "DossierStore", "OPEN_STATUSES", "dossier_view", "offer_key",
           "pending_changes", "seen_token"]
