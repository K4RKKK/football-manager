"""Disponibilité du jour d'un club : blessés en cours, suspensions, retours récents.

Sources (miroirs fmsave) :
- `fm_injuries`, lignes TYPED : une blessure en cours de suivi, avec son type et la date de retour
  prévue que le jeu enregistre. Vérifié dans FM26 (15/10/2026) : Gabriel Jesus, « entorse des
  ligaments croisés », date au 07/11 = retour prévu affiché « dans 6 jours - 2 semaines » ; Barcola,
  date passée (15/10), n'est plus blessé ; aucune ligne pour la Roma, qui n'a aucun blessé. Règle :
  blessé aujourd'hui ⇔ date de retour ≥ date du jeu ; date passée de moins de 14 jours = retour récent.
- `fm_suspensions` : suspensions non purgées (la sauvegarde garde aussi des sanctions que le jeu
  n'affiche plus ; le nombre de matchs restants n'est pas lu).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Engine, text

RECENT_RETURN_DAYS = 14


def _rows(engine: Engine, sql: str, **params) -> list[dict]:
    try:
        with engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), params)]
    except Exception:  # noqa: BLE001 — miroir absent avant la première synchronisation
        return []


def _day(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def club_availability(engine: Engine, career_id: int, club_uid: int, today: date | None) -> dict:
    """Blessés en cours (retour prévu), retours récents et suspensions des joueurs d'un club."""
    injuries = _rows(engine, """
        SELECT i.player_uid, p.name, p.team_slot, p.positions, i.type_name, i.date AS retour
        FROM fm_injuries i JOIN players_current p ON p.career_id = i.career_id AND p.uid = i.player_uid
        WHERE i.career_id = :k AND i.kind = 'typed' AND p.club_uid = :c
        ORDER BY i.date""", k=career_id, c=club_uid)
    injured, recent = [], []
    for r in injuries:
        back = _day(r["retour"])
        item = {"player_uid": r["player_uid"], "joueur": r["name"], "equipe": r["team_slot"],
                "postes": [x for x in (r["positions"] or "").split(",") if x], "blessure": r["type_name"],
                "retour_prevu": back.isoformat() if back else None}
        if back is None or today is None or back >= today:
            if back and today:
                item["jours_restants"] = (back - today).days
            injured.append(item)
        elif today - back <= timedelta(days=RECENT_RETURN_DAYS):
            item["revenu_depuis_jours"] = (today - back).days
            recent.append(item)
    bans = _rows(engine, """
        SELECT s.player_uid, p.name, p.team_slot, s.scope, s.competition_id, s.nation_id, s.issued_date,
               (SELECT st.competition_name FROM fm_stages st WHERE st.career_id = s.career_id AND st.id = s.competition_id LIMIT 1)
                 AS competition
        FROM fm_suspensions s JOIN players_current p ON p.career_id = s.career_id AND p.uid = s.player_uid
        WHERE s.career_id = :k AND p.club_uid = :c ORDER BY s.issued_date DESC""", k=career_id, c=club_uid)
    suspended = [{"player_uid": b["player_uid"], "joueur": b["name"], "equipe": b["team_slot"],
                  "portee": "competition" if b["scope"] == "competition" else "nation" if b["scope"] == "nation" else b["scope"],
                  "competition": b["competition"], "competition_id": b["competition_id"],
                  "depuis": str(b["issued_date"])[:10] if b["issued_date"] else None} for b in bans]
    return {"blesses": injured, "retours_recents": recent, "suspendus": suspended}


def unavailable_player_uids(engine: Engine, career_id: int, club_uid: int, today: date | None) -> set[int]:
    """Joueurs à écarter d'une composition : blessés en cours et suspendus (toutes compétitions).

    Une suspension limitée à une compétition n'empêche pas de jouer les autres : l'appelant qui
    connaît la compétition du match peut affiner avec `club_availability`."""
    a = club_availability(engine, career_id, club_uid, today)
    return {x["player_uid"] for x in a["blesses"]} | {x["player_uid"] for x in a["suspendus"]}


def find_club(engine: Engine, career_id: int, name: str) -> dict | None:
    """Club par son nom (complet ou court, sans tenir compte de la casse).

    Les sections féminines portent souvent le même nom que le club masculin (« Arsenal ») : à nom
    égal, le club dont les joueurs figurent dans les classements masculins du marché passe devant,
    puis le mieux réputé."""
    exact = _rows(engine, """
        SELECT uid, name, short_name, reputation FROM fm_clubs WHERE career_id = :k
          AND (lower(name) = lower(:n) OR lower(short_name) = lower(:n))""", k=career_id, n=name)
    candidates = exact or _rows(engine, """
        SELECT uid, name, short_name, reputation FROM fm_clubs WHERE career_id = :k
          AND (lower(name) LIKE lower(:like) OR lower(short_name) LIKE lower(:like))
        ORDER BY coalesce(reputation, 0) DESC LIMIT 10""", k=career_id, like=f"%{name}%")
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    def men(uid: int) -> bool:
        return bool(_rows(engine, """
            SELECT 1 FROM players_current p WHERE p.career_id = :k AND p.club_uid = :c AND EXISTS (
              SELECT 1 FROM fm_player_rankings r WHERE r.career_id = p.career_id AND r.player_uid = p.uid
                AND r.women = 0) LIMIT 1""", k=career_id, c=uid))

    return max(candidates, key=lambda c: (men(c["uid"]), c.get("reputation") or 0))


LIMITATIONS = [
    "Blessures en cours : date de retour prévue enregistrée par le jeu (le jeu affiche une fourchette, "
    "ex. « 6 jours - 2 semaines »). État au jour de la dernière sauvegarde.",
    "Suspensions : la sauvegarde garde aussi des sanctions que le jeu n'affiche plus ; le nombre de matchs "
    "restants n'est pas lu.",
]
