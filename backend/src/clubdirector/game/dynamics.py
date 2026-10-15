"""Hiérarchie du vestiaire du club géré, telle que le jeu la calcule.

Source : miroir `fm_squad_influence` (fork fmsave, `Save.squad_influence()`). Le jeu garde, pour
chaque équipe du club géré seulement, des listes d'influence datées : la plus récente et des
anciennes. Vérifié dans FM26 (Dynamique de groupe > Hiérarchie, 28/10/2025) : sur la liste la plus
récente de l'équipe première de la Roma, les tranches d'influence donnent le groupe du jeu des 23
joueurs listés ; les 5 joueurs absents de la liste sont prêtés ailleurs (« autres » dans le jeu).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Engine, text

GROUP_OF_TIER = {"leader": "leaders", "highly_influential": "tres_influents", "influential": "influents",
                 "other": "autres"}
GROUP_ORDER = ("leaders", "tres_influents", "influents", "autres")
GROUP_FR = {"leaders": "leader", "tres_influents": "très influent", "influents": "influent", "autres": "autre"}
LIMITATIONS = (
    "Les joueurs prêtés à d'autres clubs ne sont pas dans la hiérarchie (le jeu les montre comme « autres »).",
    "Hiérarchie calculée par le jeu à la date indiquée (« date_calcul ») ; elle peut avoir bougé depuis.",
    "Les seuils des groupes (9 000, 7 500, 6 000) ont été vérifiés sur une seule sauvegarde (23 joueurs sur 23).",
    "Le jeu ne calcule cette hiérarchie que pour notre club, pas pour les autres.",
    "L'état d'esprit (moral) des joueurs n'est pas encore lu dans la sauvegarde.",
)


def _rows(engine: Engine, sql: str, **params) -> list[dict]:
    try:
        with engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), params)]
    except Exception:  # noqa: BLE001 — miroir absent avant la première synchronisation (ou ancienne révision)
        return []


def _day(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def squad_hierarchy(engine: Engine, career_id: int, club_uid: int, team_slot: int = 0) -> dict | None:
    """Groupes du vestiaire (leaders, très influents, influents, autres) d'une équipe du club, avec
    l'évolution depuis la liste précédente du jeu. None quand la sauvegarde n'a pas de liste pour elle."""
    rows = _rows(engine, """
        SELECT list_index, as_of, latest, rank, player_uid, player_name, influence, tier
        FROM fm_squad_influence WHERE career_id = :k AND club_uid = :c AND team_slot = :s
        ORDER BY list_index, rank""", k=career_id, c=club_uid, s=team_slot)
    current = [r for r in rows if r["latest"]]
    if not current:
        return None
    as_of = _day(current[0]["as_of"])
    groups: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    for r in current:
        groups[GROUP_OF_TIER.get(r["tier"], "autres")].append(
            {"joueur": r["player_name"], "player_uid": r["player_uid"], "influence": r["influence"]})
    listed = {r["player_uid"] for r in current}
    squad = _rows(engine, """
        SELECT uid, name FROM players_current WHERE career_id = :k AND club_uid = :c AND team_slot = :s
        ORDER BY name""", k=career_id, c=club_uid, s=team_slot)
    groups["autres"] += [{"joueur": p["name"], "player_uid": p["uid"], "influence": None, "hors_liste_du_jeu": True}
                         for p in squad if p["uid"] not in listed]
    out = {"date_calcul": as_of.isoformat() if as_of else None,
           **{g: groups[g] for g in GROUP_ORDER}}
    # Évolution : la liste la plus récente parmi celles calculées avant la liste courante.
    older = [r for r in rows if not r["latest"] and _day(r["as_of"]) and as_of and _day(r["as_of"]) < as_of]
    if older:
        previous_day = max(_day(r["as_of"]) for r in older)
        previous_list = min(r["list_index"] for r in older if _day(r["as_of"]) == previous_day)
        before = {r["player_uid"]: GROUP_OF_TIER.get(r["tier"], "autres")
                  for r in older if r["list_index"] == previous_list}
        moves = []
        for group in GROUP_ORDER:
            for p in groups[group]:
                was = before.get(p["player_uid"])
                if was is not None and was != group:
                    rise = GROUP_ORDER.index(group) < GROUP_ORDER.index(was)
                    moves.append({"joueur": p["joueur"], "avant": GROUP_FR[was], "maintenant": GROUP_FR[group],
                                  "sens": "monte" if rise else "descend"})
        out["evolution"] = {"depuis": previous_day.isoformat(), "changements": moves}
    return out
