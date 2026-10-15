"""Dossier du club injecté dans le rôle du directeur sportif à chaque conversation.

Construit automatiquement à partir de la carrière active (club géré détecté dans la sauvegarde),
avec les outils du registre — donc uniquement des données réelles. Une rubrique dont la donnée
est absente est omise, jamais estimée. Le dossier est un point de départ : pour toute décision,
le directeur reste tenu d'interroger les outils.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from clubdirector.positions import split_positions
from clubdirector.tools.registry import ToolContext, ToolRegistry, ToolResult

log = logging.getLogger(__name__)


def _call(registry: ToolRegistry, tctx: ToolContext, name: str, **args: Any) -> Any:
    """Exécute le gestionnaire d'un outil sans journal d'audit ; None si indisponible ou en échec."""
    spec = registry.get(name)
    if spec is None or not spec.available or spec.handler is None:
        return None
    try:
        out = spec.handler(tctx, spec.args_model.model_validate(args))
    except Exception as exc:  # noqa: BLE001 — une rubrique manquante ne bloque pas le dossier
        log.debug("dossier du club : %s indisponible (%s)", name, exc)
        return None
    return out.data if isinstance(out, ToolResult) else out


def _fr(d: str | None) -> str:
    if not d:
        return "?"
    y, m, j = d[:10].split("-")
    return f"{j}/{m}/{y}"


def _match(m: dict) -> str:
    comp = f" ({m['competition']})" if m.get("competition") else ""
    if m.get("score_disponible"):
        return f"{_fr(m['date'])} — {m['domicile']} {m['score']} {m['exterieur']}{comp}"
    return f"{_fr(m['date'])} — {m['domicile']} – {m['exterieur']}{comp}"


# Ligne d'un joueur d'après son premier poste (mêmes regroupements que l'app Effectif du téléphone).
LINES = (
    ("Gardiens", lambda p: p == "GK"),
    ("Défenseurs", lambda p: bool(re.fullmatch(r"D[CLR]?|WB[LR]?", p))),
    ("Milieux", lambda p: bool(re.fullmatch(r"DM|M[CLR]?|AMC", p))),
    ("Attaquants", lambda p: True),
)


def _roster(tctx: ToolContext) -> str | None:
    """Liste nominative de l'équipe première par ligne, avec le temps de jeu de la saison.

    Sans elle, le modèle complétait une composition avec sa mémoire du football réel (joueurs
    partis depuis, jamais présents dans la sauvegarde)."""
    try:
        rows = tctx.repo.squad(tctx.ctx)
        season = tctx.repo.season_lines(tctx.ctx, [r["uid"] for r in rows])
    except Exception as exc:  # noqa: BLE001
        log.debug("dossier du club : effectif indisponible (%s)", exc)
        return None
    if not rows:
        return None
    groups: dict[str, list[str]] = {title: [] for title, _ in LINES}
    for r in sorted(rows, key=lambda r: -((season.get(r["uid"]) or {}).get("minutes") or 0)):
        positions = split_positions(r.get("positions"))
        first = positions[0] if positions else ""
        title = next(t for t, test in LINES if test(first))
        s = season.get(r["uid"]) or {}
        bits = [f"{r['age']} ans" if r.get("age") else None, "/".join(positions) or None, f"{s.get('minutes') or 0} min"]
        if s.get("goals"):
            bits.append(f"{s['goals']} b")
        if s.get("assists"):
            bits.append(f"{s['assists']} pd")
        if r.get("on_loan"):
            bits.append("en prêt")
        groups[title].append(f"{r['name']} ({', '.join(b for b in bits if b)})")
    body = " ; ".join(f"{title} : {', '.join(names)}" for title, names in groups.items() if names)
    return ("Effectif COMPLET de l'équipe première (aucun autre joueur n'est à nous ; minutes = saison en cours) : "
            + body)


def build_club_dossier(registry: ToolRegistry, tctx: ToolContext) -> str:
    ctx = tctx.ctx
    if ctx.club_uid is None:
        return "Aucun club géré n'a été détecté dans la sauvegarde active."
    lines: list[str] = [f"Club : {ctx.club_name}", f"Entraîneur (ton interlocuteur) : {ctx.manager_name or 'inconnu'}"]

    club = _call(registry, tctx, "get_managed_club") or {}
    table = club.get("classement")
    if table:
        comp = table.get("competition_name") or f"compétition {table.get('competition_id')}"
        lines.append(
            f"Championnat : {comp} — {table['position']}e, {table['points']} pts en {table['played']} matchs "
            f"({table['won']} V, {table['drawn']} N, {table['lost']} D ; {table['goals_for']} buts pour, "
            f"{table['goals_against']} contre)"
        )
    if club.get("effectif"):
        per_team = club.get("joueurs_par_equipe") or {}
        extra = f" (toutes équipes : {sum(per_team.values())})" if per_team else ""
        lines.append(f"Équipe première : {club['effectif']} joueurs, âge moyen {club.get('age_moyen')} ans{extra}")
    roster = _roster(tctx)
    if roster:
        lines.append(roster)

    recent = _call(registry, tctx, "get_recent_matches", limit=3) or []
    if recent:
        lines.append("Derniers matchs : " + " ; ".join(_match(m) for m in recent))
    upcoming = _call(registry, tctx, "get_upcoming_matches", limit=3) or []
    if upcoming:
        lines.append("Prochains matchs : " + " ; ".join(_match(m) for m in upcoming))

    scorers = (_call(registry, tctx, "get_top_players_stat", stat="goals", scope="club", limit=3) or {}).get("classement") or []
    if scorers:
        lines.append("Meilleurs buteurs de la saison : " + ", ".join(f"{s['joueur']} ({s['valeur']})" for s in scorers))

    injured = [
        i for i in (_call(registry, tctx, "get_injured_players") or [])
        if i.get("nature") != "history" and ctx.game_date and i.get("date") and i["date"] >= ctx.game_date.isoformat()
    ]
    if injured:
        lines.append("Blessés (retour prévu) : " + ", ".join(f"{i['joueur']} ({_fr(i['date'])})" for i in injured[:8]))

    expiring = (_call(registry, tctx, "search_expiring_contracts", months=12, scope="club", limit=8) or {}).get("joueurs") or []
    first_team = [p for p in expiring if p.get("equipe_slot") in (0, None)]
    if first_team:
        lines.append("Contrats de l'équipe première expirant sous 12 mois : "
                     + ", ".join(f"{p['nom']} ({_fr(p['fin_contrat'])})" for p in first_team))

    transfer = _call(registry, tctx, "get_transfer_budget") or {}
    wages = _call(registry, tctx, "get_wage_budget") or {}
    if transfer.get("restant") or wages.get("marge_hebdo"):
        parts = []
        if transfer.get("restant"):
            parts.append(f"budget transferts restant {transfer['restant']['texte']}")
        if wages.get("marge_hebdo"):
            parts.append(f"marge salariale hebdomadaire {wages['marge_hebdo']['texte']}")
        lines.append("Finances (relevé du " + _fr(transfer.get("mois") or wages.get("mois")) + ") : " + " ; ".join(parts))

    history = (_call(registry, tctx, "get_club_league_history", since_year=(ctx.game_date.year - 4) if ctx.game_date else None) or {}).get("saisons") or []
    if history:
        lines.append("Historique récent en championnat : " + " ; ".join(
            f"{h['saison']} {h['position']}e{(' — ' + h['competition']) if h.get('competition') else ''} ({h['points']} pts)"
            for h in history[:4]))
    return "\n".join(f"- {line}" for line in lines)
