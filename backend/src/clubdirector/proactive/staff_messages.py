"""Messages proactifs du staff : après chaque nouvelle sauvegarde, chaque contact écrit de lui-même.

QUAND écrire est décidé par des règles déterministes (aucune IA), sur des faits réels de la
sauvegarde, chacun dans le domaine d'un contact :
- directeur sportif : offres reçues pour nos joueurs, transferts conclus ou échoués, contrats qui
  expirent dans moins de 6 mois, arrivées et départs de l'équipe première, fin de fenêtre des
  transferts (date donnée par l'entraîneur), suivi des dossiers qu'il a préparés ;
- directeur technique : contrats du staff qui expirent, arrivées et départs du staff, finances ;
- entraîneur adjoint : blessures récentes, suspensions, prochain match avec le onze calculé
  (`propose_lineup`), mauvaise série, joueurs intégrés à l'équipe première.

Un fait a une clé stable : il n'est signalé qu'une fois (table `staff_notices`). Chaque contact
écrit au plus un message par sauvegarde (les faits les plus importants d'abord, quatre au plus ;
les suivants attendent la sauvegarde d'après). Le modèle ne fait que RÉDIGER le message à partir
des faits fournis ; sans modèle, le message reprend les faits tels quels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from clubdirector.database import schema as s
from clubdirector.memory.decisions import CoachRules, coach_rules
from clubdirector.proactive.rules import finance_alerts, form_alerts
from clubdirector.transfers.dossiers import DossierStore, offer_key, pending_changes
from clubdirector.transfers.market import Market, valuation

log = logging.getLogger(__name__)
DS, DT, ADJ = "directeur_sportif", "directeur_technique", "entraineur_adjoint"
MAX_FACTS_PER_MESSAGE = 4
RECENT_DAYS = 10  # suspensions déjà en cours à la première lecture
OFFER_DAYS = 21  # offres reçues / évolutions d'offres
MATCH_DAYS = 7  # prochain match annoncé
WINDOW_DAYS = 7  # fin de fenêtre annoncée
CONTRACT_DAYS = 183  # « moins de 6 mois »
STATUS_OF_STATE = {"conclue": "conclu", "echouee": "refuse", "accord_a_venir": "accord"}


@dataclass
class Fact:
    role: str
    key: str
    kind: str
    priority: int  # 0 = le plus important
    text: str  # phrase factuelle en français : base du message (et repli sans modèle)
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _d(x: Any) -> date | None:
    if x is None or isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _fr(x: Any) -> str:
    d = _d(x)
    return d.strftime("%d/%m/%Y") if d else "?"


def _rows(engine: Engine, sql: str, **params) -> list[dict]:
    try:
        with engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), params)]
    except Exception:  # noqa: BLE001 — table miroir absente avant la synchronisation qui la remplit
        return []


# --------------------------------------------------------------------------- mémoire des faits
class NoticeStore:
    """Faits déjà signalés (et états mémorisés d'un relevé à l'autre) par carrière."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def known(self, career_id: int, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        n = s.staff_notices.c
        out: set[str] = set()
        with self.engine.connect() as c:
            for i in range(0, len(keys), 500):
                out |= set(c.execute(select(n.fact_key).where(n.career_id == career_id,
                                                              n.fact_key.in_(keys[i:i + 500]))).scalars())
        return out

    def record(self, career_id: int, facts: list[Fact], message_id: int | None, game_date: date | None) -> None:
        now = datetime.now(UTC)
        with self.engine.begin() as c:
            for f in facts:
                c.execute(sqlite_insert(s.staff_notices).values(
                    career_id=career_id, role=f.role, fact_key=f.key, kind=f.kind, data=f.data | {"texte": f.text},
                    game_date=game_date, created_at=now, message_id=message_id,
                ).on_conflict_do_nothing(index_elements=["career_id", "fact_key"]))

    def state(self, career_id: int, name: str) -> dict | None:
        n = s.staff_notices.c
        with self.engine.connect() as c:
            return c.execute(select(n.data).where(n.career_id == career_id, n.fact_key == f"etat|{name}")).scalar()

    def set_state(self, career_id: int, name: str, data: dict, game_date: date | None) -> None:
        stmt = sqlite_insert(s.staff_notices).values(
            career_id=career_id, role="service", fact_key=f"etat|{name}", kind="etat", data=data,
            game_date=game_date, created_at=datetime.now(UTC), message_id=None)
        with self.engine.begin() as c:
            c.execute(stmt.on_conflict_do_update(index_elements=["career_id", "fact_key"],
                                                 set_={"data": stmt.excluded.data, "game_date": stmt.excluded.game_date}))

    def recent(self, career_id: int, limit: int = 100) -> list[dict]:
        n = s.staff_notices.c
        with self.engine.connect() as c:
            rows = c.execute(select(s.staff_notices).where(n.career_id == career_id, n.kind != "etat")
                             .order_by(n.id.desc()).limit(limit))
            return [dict(r._mapping) for r in rows]


# --------------------------------------------------------------------------- règles (aucune IA)
def director_facts(tctx, market: Market, rules: CoachRules) -> list[Fact]:
    ctx, fmt = tctx.ctx, tctx.prefs.currency.format
    today = ctx.game_date
    out: list[Fact] = []
    if today is None or ctx.club_uid is None:
        return out
    since = today - timedelta(days=OFFER_DAYS)
    for o in market.offers(club_uid=ctx.club_uid, side="recues", limit=150):
        offered, changed = _d(o.get("offered_on")), _d(o.get("updated_on")) or _d(o.get("offered_on"))
        amount = fmt(o["amount"]) if o.get("amount") else "montant non lu"
        kind = "prêt" if o.get("kind") == "loan" else "transfert"
        who = o.get("bidding_club_name") or "un club"
        name = o.get("player_name") or "un joueur"
        if o["etat"] in ("en_cours", "accord_a_venir") and offered and offered >= since:
            line = f"Offre reçue le {_fr(offered)} de {who} pour {name} : {kind}, {amount}"
            if o["etat"] == "accord_a_venir":
                line += f" (accord pour un départ le {_fr(o.get('effective_on'))})"
            p = market.player(o["player_uid"]) if o.get("player_uid") else None
            data = {"joueur": name, "club": who, "montant": amount, "type": kind, "date": _d(offered).isoformat()}
            if p and kind == "transfert":
                v = valuation(market, p)
                line += (f". Nos repères (estimations à règles) : prix demandé {fmt(v['prix_demande'])}, plancher "
                         f"{fmt(v['plancher'])}, valeur du jeu {fmt(v['valeur_jeu'])}")
                data |= {"prix_demande": fmt(v["prix_demande"]), "plancher": fmt(v["plancher"])}
            if o.get("player_uid") in rules.never_sell:
                line += ". L'entraîneur a décidé de NE PAS vendre ce joueur"
                data["ne_pas_vendre"] = True
            elif o.get("player_uid") in rules.to_sell:
                line += ". L'entraîneur a mis ce joueur en vente"
            out.append(Fact(DS, offer_key(o), "offre_recue", 1, line + ".", data))
        elif o["etat"] in ("conclue", "echouee") and changed and changed >= since:
            status = STATUS_OF_STATE[o["etat"]]
            verb = "Transfert conclu" if status == "conclu" else "Offre échouée"
            out.append(Fact(DS, offer_key(o) + f"|{status}", f"offre_{status}", 1,
                            f"{verb} : {name} — {kind} vers {who}, {amount} (dernière évolution le {_fr(changed)}).",
                            {"joueur": name, "club": who, "montant": amount, "etat": o["etat"]}))
    for o in market.offers(club_uid=ctx.club_uid, side="faites", limit=150):
        changed = _d(o.get("updated_on")) or _d(o.get("offered_on"))
        if o["etat"] in STATUS_OF_STATE and changed and changed >= since:
            status = STATUS_OF_STATE[o["etat"]]
            amount = fmt(o["amount"]) if o.get("amount") else "montant non lu"
            verb = {"conclu": "Notre offre a abouti", "refuse": "Notre offre a échoué",
                    "accord": f"Accord trouvé (effet le {_fr(o.get('effective_on'))})"}[status]
            out.append(Fact(DS, offer_key(o) + f"|{status}", f"notre_offre_{status}", 1,
                            f"{verb} : {o.get('player_name')} ({o.get('selling_club_name') or 'club vendeur'}), {amount}.",
                            {"joueur": o.get("player_name"), "club_vendeur": o.get("selling_club_name"), "montant": amount}))
    for p in tctx.repo.squad(ctx):
        end = _d(p.get("contract_end"))
        if end is None or end < today or (end - today).days > CONTRACT_DAYS:
            continue
        if p.get("on_loan") and p.get("loan_parent_club_uid") not in (None, ctx.club_uid):
            continue  # prêté chez nous : son contrat appartient à son club
        months = max(0, round((end - today).days / 30.44))
        line = (f"Contrat de {p['name']} : fin le {_fr(end)}, dans {months} mois "
                f"(salaire {fmt(p['wage']) if p.get('wage') else 'non lu'} par semaine, valeur {fmt(p.get('transfer_value'))})")
        if p["uid"] in rules.never_sell:
            line += " — joueur que l'entraîneur ne veut pas vendre"
        out.append(Fact(DS, f"contrat|{p['uid']}|{end.isoformat()}", "contrat_expirant", 2, line + ".",
                        {"joueur": p["name"], "fin": end.isoformat(), "mois": months}))
    if rules.window_end and 0 <= (rules.window_end - today).days <= WINDOW_DAYS:
        left = (rules.window_end - today).days
        out.append(Fact(DS, f"fenetre|{rules.window_end.isoformat()}", "fin_fenetre", 1,
                        f"La fenêtre des transferts ferme le {_fr(rules.window_end)} (date donnée par l'entraîneur) : "
                        f"plus que {left} jour(s).", {"fin": rules.window_end.isoformat(), "jours": left}))
    return out


def roster_facts(tctx, notices: NoticeStore) -> list[Fact]:
    """Arrivées et départs de l'équipe première (DS), joueurs intégrés à l'équipe première (adjoint)."""
    ctx = tctx.ctx
    current = {p["uid"]: {"nom": p["name"], "slot": p.get("team_slot")} for p in tctx.repo.squad(ctx, team_slot=None)}
    previous = notices.state(ctx.career_id, "effectif")
    notices.set_state(ctx.career_id, "effectif", {str(k): v for k, v in current.items()}, ctx.game_date)
    if previous is None:
        return []  # premier relevé : la base de départ, rien à annoncer
    prev = {int(k): v for k, v in previous.items()}
    out: list[Fact] = []
    stamp = ctx.game_date.isoformat() if ctx.game_date else "?"
    for uid, p in current.items():
        first = p["slot"] in (0, None)
        if uid not in prev and first:
            out.append(Fact(DS, f"arrivee|{uid}|{stamp}", "arrivee", 2, f"{p['nom']} est arrivé dans l'effectif de l'équipe première.",
                            {"joueur": p["nom"]}))
        elif uid in prev and first and prev[uid].get("slot") not in (0, None):
            out.append(Fact(ADJ, f"promotion|{uid}|{stamp}", "promotion", 3, f"{p['nom']} a été intégré à l'équipe première.",
                            {"joueur": p["nom"]}))
    for uid, p in prev.items():
        if uid in current or p.get("slot") not in (0, None):
            continue
        row = tctx.repo.player(ctx, uid)
        where = (row or {}).get("club_name")
        out.append(Fact(DS, f"depart|{uid}|{stamp}", "depart", 2,
                        f"{p['nom']} a quitté le club" + (f" : il joue désormais à {where}." if where else "."),
                        {"joueur": p["nom"], "nouveau_club": where}))
    return out


def technical_facts(tctx, notices: NoticeStore) -> list[Fact]:
    """Staff (contrats, arrivées, départs) et finances, pour le directeur technique."""
    from clubdirector.ai.director_identity import staff_function

    ctx, fmt = tctx.ctx, tctx.prefs.currency.format
    out: list[Fact] = []
    if ctx.club_uid is None:
        return out
    staff = _rows(tctx.engine, "SELECT uid, name, is_human_manager, has_contract, wage, contract_end, unknown_r4 AS code, "
                               "list_indexes FROM fm_staff WHERE career_id = :k AND club_uid = :c", k=ctx.career_id, c=ctx.club_uid)
    today = ctx.game_date
    for r in staff:
        end = _d(r.get("contract_end"))
        if r.get("is_human_manager") or not r.get("has_contract") or end is None or today is None:
            continue
        if today <= end and (end - today).days <= CONTRACT_DAYS:
            job = staff_function(r.get("code"), r.get("list_indexes")) or "membre du staff"
            months = max(0, round((end - today).days / 30.44))
            out.append(Fact(DT, f"contrat_staff|{r['uid']}|{end.isoformat()}", "contrat_staff", 2,
                            f"Contrat de {r['name']} ({job.lower()}) : fin le {_fr(end)}, dans {months} mois "
                            f"(salaire {fmt(r['wage']) if r.get('wage') else 'non lu'} par semaine).",
                            {"nom": r["name"], "fonction": job, "fin": end.isoformat()}))
    current = {r["uid"]: r["name"] for r in staff if not r.get("is_human_manager")}
    previous = notices.state(ctx.career_id, "staff")
    notices.set_state(ctx.career_id, "staff", {str(k): v for k, v in current.items()}, ctx.game_date)
    if previous is not None and current:
        prev = {int(k): v for k, v in previous.items()}
        stamp = today.isoformat() if today else "?"
        for uid, name in current.items():
            if uid not in prev:
                out.append(Fact(DT, f"staff_arrivee|{uid}|{stamp}", "staff_arrivee", 2, f"{name} a rejoint le staff du club.",
                                {"nom": name}))
        for uid, name in prev.items():
            if uid not in current:
                out.append(Fact(DT, f"staff_depart|{uid}|{stamp}", "staff_depart", 2, f"{name} a quitté le staff du club.",
                                {"nom": name}))
    for a in finance_alerts(ctx, tctx.repo.finances(ctx, months=3)):
        out.append(Fact(DT, f"finance|{a['rule']}|{a['subject_key']}", a["rule"], 3, a["message"], a.get("data") or {}))
    return out


def field_facts(tctx, registry, notices: NoticeStore) -> list[Fact]:
    """Terrain, pour l'entraîneur adjoint : blessures, retours, suspensions, prochain match (onze calculé), série.

    Blessés du jour : lignes « typed » de `fm_injuries` (blessure en cours, date de retour prévue ; vérifié dans
    FM26, voir game/availability.py). Une blessure, un retour ou une suspension est un fait la première fois
    qu'il apparaît d'une sauvegarde à l'autre (état mémorisé)."""
    ctx = tctx.ctx
    out: list[Fact] = []
    today = ctx.game_date
    if today is None or ctx.club_uid is None:
        return out
    stamp = today.isoformat()
    first_team = {p["uid"] for p in tctx.repo.squad(ctx)}
    hurt = {r["player_uid"]: r for r in _rows(tctx.engine, """
        SELECT i.player_uid, p.name, i.type_name, i.date AS retour FROM fm_injuries i
        JOIN players_current p ON p.career_id = i.career_id AND p.uid = i.player_uid
        WHERE i.career_id = :k AND i.kind = 'typed' AND p.club_uid = :c AND i.date >= :today""",
        k=ctx.career_id, c=ctx.club_uid, today=stamp) if r["player_uid"] in first_team}
    bans = {r["player_uid"]: r for r in _rows(tctx.engine, """
        SELECT s.player_uid, p.name, s.issued_date, s.competition_id,
               (SELECT st.competition_name FROM fm_stages st WHERE st.career_id = s.career_id AND st.id = s.competition_id
                LIMIT 1) AS competition
        FROM fm_suspensions s JOIN players_current p ON p.career_id = s.career_id AND p.uid = s.player_uid
        WHERE s.career_id = :k AND p.club_uid = :c""", k=ctx.career_id, c=ctx.club_uid) if r["player_uid"] in first_team}
    previous = notices.state(ctx.career_id, "infirmerie")
    notices.set_state(ctx.career_id, "infirmerie", {
        "blesses": {str(u): {"nom": r["name"], "type": r["type_name"]} for u, r in hurt.items()},
        "suspendus": {str(u): {"nom": r["name"], "depuis": str(r["issued_date"])[:10]} for u, r in bans.items()}}, today)
    was_hurt = {int(k): v for k, v in ((previous or {}).get("blesses") or {}).items()}
    was_banned = {int(k): v for k, v in ((previous or {}).get("suspendus") or {}).items()}
    for uid, r in hurt.items():
        if uid in was_hurt and was_hurt[uid].get("type") == r["type_name"]:
            continue  # déjà signalé
        back = _d(r["retour"])
        days = (back - today).days if back else None
        out.append(Fact(ADJ, f"blessure|{uid}|{r['type_name'] or '?'}|{stamp}", "blessure", 1,
                        f"{r['name']} est blessé : {r['type_name'] or 'blessure de type non lu'}, retour prévu le {_fr(back)}"
                        + (f" (dans {days} jours ; le jeu affiche une fourchette autour de cette date)" if days is not None else "")
                        + ".", {"joueur": r["name"], "blessure": r["type_name"], "retour_prevu": _d(back).isoformat() if back else None}))
    if previous is not None:
        for uid, v in was_hurt.items():
            if uid not in hurt and uid in first_team:
                out.append(Fact(ADJ, f"retour|{uid}|{stamp}", "retour_blessure", 2,
                                f"{v.get('nom')} n'est plus à l'infirmerie ({v.get('type') or 'blessure'} terminée).",
                                {"joueur": v.get("nom")}))
    for uid, r in bans.items():
        since = str(r["issued_date"])[:10] if r.get("issued_date") else "?"
        if previous is None and _d(since) and (today - _d(since)).days > RECENT_DAYS:
            continue  # première lecture : seules les sanctions récentes sont des nouvelles
        if uid in was_banned and was_banned[uid].get("depuis") == since:
            continue
        comp = f" ({r['competition']})" if r.get("competition") else ""
        out.append(Fact(ADJ, f"suspension|{uid}|{since}", "suspension", 1,
                        f"{r['name']} est suspendu{comp}, sanction du {_fr(since)} (nombre de matchs non lu dans la "
                        "sauvegarde).", {"joueur": r["name"]}))
    injured = [r["name"] for r in hurt.values()] + [r["name"] for r in bans.values()]
    nxt = tctx.repo.fixtures(ctx, date_from=today + timedelta(days=1), date_to=today + timedelta(days=MATCH_DAYS),
                             limit=1, newest_first=False)
    if nxt:
        m = nxt[0]
        home = m["home_club_uid"] == ctx.club_uid
        opp = m["away_club_name"] if home else m["home_club_name"]
        line = (f"Prochain match le {_fr(m['date'])} : {'à domicile' if home else 'à l’extérieur'} contre {opp}"
                + (f" ({m['competition_name']})" if m.get("competition_name") else ""))
        data = {"date": m["date"].isoformat() if hasattr(m["date"], "isoformat") else str(m["date"]), "adversaire": opp,
                "domicile": home, "competition": m.get("competition_name")}
        args = {"absents": list(dict.fromkeys(injured))} if injured else {}
        r = registry.execute("propose_lineup", args, tctx) if registry is not None and registry.get("propose_lineup") else None
        if r is not None and r.ok:
            onze = " ; ".join(f"{x['poste']} {x['joueur']} ({x['note_poste']}/20)" for x in r.data["onze"])
            line += f". Onze calculé ({r.data['systeme']}, notes de poste FM26) : {onze}"
            data["onze"] = [x["joueur"] for x in r.data["onze"]]
        if injured:
            line += f". Indisponibles (blessés ou suspendus) : {', '.join(dict.fromkeys(injured))}"
        out.append(Fact(ADJ, f"match|{m['match_key']}", "prochain_match", 2, line + ".", data))
    played = tctx.repo.fixtures(ctx, date_to=today + timedelta(days=1), played=True, limit=10)
    for a in form_alerts(ctx, played):
        out.append(Fact(ADJ, f"serie|{a['subject_key']}", "mauvaise_serie", 3, a["message"], a.get("data") or {}))
    return out


def dossier_facts(changes) -> list[Fact]:
    return [Fact(DS, ch.fact_key, f"dossier_{ch.status}", 0,
                 f"Dossier « {ch.data['type']} de {ch.player_name} » (préparé par toi) : {ch.detail}.", ch.data)
            for ch in changes]


def detect_facts(tctx, registry=None, notices: NoticeStore | None = None) -> list[Fact]:
    """Tous les faits du moment, sans filtrer ceux déjà signalés (le suivi des dossiers est mis à jour)."""
    ctx = tctx.ctx
    notices = notices or NoticeStore(tctx.engine)
    rules = coach_rules(tctx.engine, ctx.career_id, tctx.prefs)
    market = Market(tctx.engine, ctx.career_id, ctx.game_date, ctx.club_uid)
    dossiers = DossierStore(tctx.engine)
    dossiers.review(tctx)  # les changements vont dans l'historique des dossiers, signalés tant qu'ils ne l'ont pas été
    facts = dossier_facts(pending_changes(dossiers.list(ctx.career_id)))
    for fn in (lambda: director_facts(tctx, market, rules), lambda: roster_facts(tctx, notices),
               lambda: technical_facts(tctx, notices), lambda: field_facts(tctx, registry, notices)):
        try:
            facts.extend(fn())
        except Exception:  # noqa: BLE001 — une règle en échec ne bloque pas les autres
            log.exception("Règle proactive en échec")
    unique: dict[str, Fact] = {}
    for f in facts:  # même fait vu par deux règles (dossier + offre) : le plus important l'emporte
        if f.key not in unique or f.priority < unique[f.key].priority:
            unique[f.key] = f
    return list(unique.values())


# --------------------------------------------------------------------------- rédaction
def instruction(role: str, facts: list[Fact], game_date: date | None) -> str:
    lines = "\n".join(f"- {f.text}" for f in facts)
    proposal = {DS: "« Je vous prépare une contre-offre ? », « On lance la prolongation ? »",
                DT: "« Je vous propose une liste de remplaçants ? »",
                ADJ: "« Je te prépare une variante ? », « On ménage quelqu'un ? »"}[role]
    return (
        f"[Message automatique — tu écris DE TOI-MÊME à l'entraîneur, sans qu'il t'ait rien demandé : des faits nouveaux "
        f"de ton domaine sont apparus (date du jeu : {_fr(game_date)}). Faits établis, exacts, à annoncer :\n{lines}\n\n"
        "Écris UN message naturel de ton métier : 1 à 3 bulles courtes séparées par une ligne vide, l'essentiel d'abord, "
        "avec les noms et chiffres exacts ci-dessus (n'en ajoute aucun de mémoire ; consulte les données seulement si "
        "c'est indispensable). Donne ton avis en une phrase et termine, si c'est utile, par une proposition concrète "
        f"sous forme de question ({proposal}). Ne parle jamais de sauvegarde lue, de synchronisation, de message "
        "automatique, d'outil ni de données consultées : écris comme un collègue qui vient de voir passer l'info.]"
    )


def fallback_text(facts: list[Fact]) -> str:
    """Message sans modèle (IA indisponible) : les faits, un par bulle."""
    return "\n\n".join(f.text for f in facts)


@dataclass
class ProactiveReport:
    facts: int = 0
    new: int = 0
    messages: list[dict] = field(default_factory=list)
    deferred: int = 0
    skipped_roles: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def run_proactive(tctx, orchestrator, registry=None, *, roles: tuple[str, ...] = (DS, DT, ADJ)) -> ProactiveReport:
    """Détecte les faits nouveaux, fait écrire chaque contact concerné (un message au plus) et retient les faits."""
    notices = NoticeStore(tctx.engine)
    facts = detect_facts(tctx, registry or orchestrator.registry, notices)
    report = ProactiveReport(facts=len(facts))
    known = notices.known(tctx.ctx.career_id, [f.key for f in facts])
    fresh = [f for f in facts if f.key not in known]
    report.new = len(fresh)
    for role in roles:
        mine = sorted((f for f in fresh if f.role == role), key=lambda f: (f.priority, f.key))
        if not mine:
            continue
        chosen, report.deferred = mine[:MAX_FACTS_PER_MESSAGE], report.deferred + max(0, len(mine) - MAX_FACTS_PER_MESSAGE)
        answer = orchestrator.notify(tctx, role, instruction(role, chosen, tctx.ctx.game_date), fallback_text(chosen))
        if answer is None:  # poste vacant : personne pour écrire
            report.skipped_roles.append(role)
            continue
        notices.record(tctx.ctx.career_id, chosen, answer.message_id, tctx.ctx.game_date)
        report.messages.append({"role": role, "message_id": answer.message_id, "route": answer.route,
                                "faits": [f.key for f in chosen], "texte": answer.text})
    return report


__all__ = ["Fact", "NoticeStore", "ProactiveReport", "detect_facts", "fallback_text", "instruction", "run_proactive"]
