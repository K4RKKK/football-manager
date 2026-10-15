"""Alertes proactives déterministes (aucun LLM).

Chaque règle produit des alertes uniques par (règle, sujet) : une alerte déjà émise n'est pas
dupliquée à la synchronisation suivante. Le LLM ne sert, éventuellement, qu'à reformuler.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from clubdirector.database import schema as s
from clubdirector.database.repositories import CareerContext, Repository

POSITION_GROUPS = {
    "GB": {"GK"},
    "DC": {"DC", "SW"},
    "Latéraux": {"DL", "DR", "WBL", "WBR"},
    "Milieux défensifs/centraux": {"DM", "MC"},
    "Ailiers/Milieux offensifs": {"ML", "MR", "AML", "AMR", "AMC"},
    "Attaquants": {"STC"},
}
MIN_DEPTH = {"GB": 2, "DC": 3, "Latéraux": 3, "Milieux défensifs/centraux": 3,
             "Ailiers/Milieux offensifs": 3, "Attaquants": 2}


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def contract_alerts(ctx: CareerContext, squad: list[dict]) -> list[dict]:
    out = []
    if ctx.game_date is None:
        return out
    for p in squad:
        end = p.get("contract_end")
        if end is None or end < ctx.game_date:
            continue
        months = _months_between(ctx.game_date, end)
        if months <= 18:
            sev = "haute" if months <= 6 else "moyenne"
            out.append(dict(
                rule="contrat_expirant",
                subject_key=f"{p['uid']}|{end.isoformat()}",
                severity=sev,
                message=(
                    f"Coach, il reste {months} mois de contrat à {p['name']} "
                    f"(fin le {end.strftime('%d/%m/%Y')}). Nous devrions examiner sa situation."
                ),
                data={"player_uid": p["uid"], "contract_end": end.isoformat(), "months_left": months},
            ))
    return out


def depth_alerts(ctx: CareerContext, squad: list[dict]) -> list[dict]:
    out = []
    for group, codes in POSITION_GROUPS.items():
        players = [
            p for p in squad
            if not p.get("on_loan") and codes & set(filter(None, (p.get("positions") or "").split(",")))
        ]
        need = MIN_DEPTH[group]
        if len(players) < need:
            out.append(dict(
                rule="profondeur_insuffisante",
                subject_key=f"{group}|{ctx.season_start_year}",
                severity="moyenne",
                message=(
                    f"Profondeur insuffisante au poste {group} : {len(players)} joueur(s) au poste "
                    f"naturel pour un minimum recommandé de {need}."
                ),
                data={"group": group, "count": len(players), "minimum": need,
                      "players": [p["name"] for p in players]},
            ))
    return out


def form_alerts(ctx: CareerContext, matches: list[dict]) -> list[dict]:
    scored = [m for m in matches if m["home_goals"] is not None and m["away_goals"] is not None]
    last = scored[:5]
    if len(last) < 3:
        return []
    losses = 0
    for m in last:
        home = m["home_club_uid"] == ctx.club_uid
        gf, ga = (m["home_goals"], m["away_goals"]) if home else (m["away_goals"], m["home_goals"])
        losses += gf < ga
    if losses >= 3:
        return [dict(
            rule="mauvaise_serie",
            subject_key=f"{last[0]['date'].isoformat()}",
            severity="haute",
            message=f"Mauvaise série : {losses} défaites sur nos {len(last)} derniers matchs au score connu.",
            data={"losses": losses, "matches": len(last)},
        )]
    return []


def finance_alerts(ctx: CareerContext, months: list[dict]) -> list[dict]:
    if not months:
        return []
    latest = months[0]
    out = []
    budget, payroll = latest.get("wage_budget_weekly"), latest.get("wage_payroll_weekly")
    if budget and payroll and payroll > budget:
        out.append(dict(
            rule="masse_salariale_depassee",
            subject_key=latest["month"].isoformat(),
            severity="haute",
            message="La masse salariale hebdomadaire dépasse le budget salarial accordé par le conseil.",
            data={"wage_budget_weekly": budget, "wage_payroll_weekly": payroll,
                  "unite": "unité stockée par la sauvegarde"},
        ))
    negatives = [m for m in months[:3] if m.get("net") is not None and m["net"] < 0]
    if len(negatives) >= 3:
        out.append(dict(
            rule="pertes_repetees",
            subject_key=latest["month"].isoformat(),
            severity="moyenne",
            message="Trois mois consécutifs de résultat net négatif.",
            data={"months": [m["month"].isoformat() for m in negatives]},
        ))
    return out


def run_rules(engine: Engine, career_id: int) -> int:
    repo = Repository(engine)
    ctx = repo.context(career_id)
    if ctx.club_uid is None:
        return 0
    squad = repo.squad(ctx)
    cutoff = ctx.game_date + timedelta(days=1) if ctx.game_date else None
    matches = repo.fixtures(ctx, date_to=cutoff, played=True, limit=10)
    candidates = (
        contract_alerts(ctx, squad)
        + depth_alerts(ctx, squad)
        + form_alerts(ctx, matches)
        + finance_alerts(ctx, repo.finances(ctx, months=3))
    )
    created = 0
    now = datetime.now(UTC)
    with engine.begin() as conn:
        for a in candidates:
            res = conn.execute(
                sqlite_insert(s.alerts)
                .values(career_id=career_id, game_date=ctx.game_date, created_at=now, dismissed=False, **a)
                .on_conflict_do_nothing(index_elements=["career_id", "rule", "subject_key"])
            )
            created += res.rowcount or 0
    return created
