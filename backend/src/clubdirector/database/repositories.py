"""Dépôts de lecture. Toutes les requêtes sont filtrées par `career_id`.

Chaque méthode renvoie des dictionnaires simples + une `Provenance` construite depuis le
snapshot réellement utilisé. Aucune valeur n'est complétée par estimation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, column, desc, func, or_, select, table, text
from sqlalchemy.exc import DBAPIError

from clubdirector.database import schema as s
from clubdirector.domain.models import Provenance
from clubdirector.text import fold

# Attributs invisibles pour un club dans le jeu (ne jamais les exposer en mode réaliste).
HIDDEN_ATTRIBUTES = {
    "consistency", "dirtiness", "important_matches", "injury_proneness", "versatility",
    "adaptability", "ambition", "loyalty", "pressure", "professionalism", "sportsmanship",
    "temperament", "controversy",
}

GK_ONLY = {"handling", "aerial_reach", "command_of_area", "communication", "kicking", "throwing",
           "one_on_ones", "reflexes", "rushing_out", "punching", "eccentricity"}

ATTRIBUTE_FR = {
    "crossing": "Centres", "dribbling": "Dribble", "finishing": "Finition", "heading": "Jeu de tête",
    "long_shots": "Tirs de loin", "marking": "Marquage", "off_the_ball": "Appels de balle",
    "passing": "Passes", "penalty_taking": "Penalty", "tackling": "Tacle", "vision": "Vision",
    "first_touch": "Contrôle", "technique": "Technique", "flair": "Flair", "corners": "Corners",
    "long_throws": "Longues touches", "free_kick_taking": "Coups francs",
    "anticipation": "Anticipation", "decisions": "Décisions", "positioning": "Placement",
    "teamwork": "Collectif", "work_rate": "Activité", "leadership": "Leadership",
    "bravery": "Courage", "aggression": "Agressivité", "composure": "Sang-froid",
    "concentration": "Concentration", "determination": "Détermination",
    "acceleration": "Accélération", "pace": "Vitesse", "stamina": "Endurance",
    "strength": "Puissance", "jumping_reach": "Détente", "balance": "Équilibre",
    "agility": "Agilité", "natural_fitness": "Condition naturelle",
    "handling": "Prise de balle", "aerial_reach": "Jeu aérien (GB)", "command_of_area": "Autorité",
    "communication": "Communication", "kicking": "Dégagements", "throwing": "Relances à la main",
    "one_on_ones": "Face-à-face", "reflexes": "Réflexes", "rushing_out": "Sorties",
    "punching": "Tendance à boxer", "eccentricity": "Excentricité",
}


# Index FTS5 trigramme des noms (migration 5) : même résultat que LIKE '%…%' sur name_search, sans
# parcourir les ~75 000 joueurs de la carrière à chaque recherche.
NAME_FTS = table("player_names_fts", column("name_search"), column("career_id"), column("uid"))


class CareerNotFound(LookupError):
    pass


@dataclass
class CareerContext:
    career_id: int
    label: str
    club_uid: int | None
    club_name: str | None
    manager_name: str | None
    game_date: date | None
    season_start_year: int | None
    season_source: str | None
    snapshot_id: int | None
    snapshot_collected_at: datetime | None
    field_status: dict[str, str]

    def provenance(self, confidence: str = "unknown", note: str | None = None, source: str = "save") -> Provenance:
        return Provenance(
            source=source,  # type: ignore[arg-type]
            collected_at=self.snapshot_collected_at or datetime.min,
            game_date=self.game_date,
            snapshot_id=self.snapshot_id,
            confidence=confidence,  # type: ignore[arg-type]
            note=note,
        )

    def status(self, key: str) -> str:
        return self.field_status.get(key, "unknown")


def _row(r: Any) -> dict[str, Any]:
    return dict(r._mapping)


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # -- carrières -------------------------------------------------------------------------
    def list_careers(self) -> list[dict]:
        with self.engine.connect() as c:
            return [_row(r) for r in c.execute(select(s.careers).order_by(desc(s.careers.c.last_sync_at)))]

    def context(self, career_id: int | None = None) -> CareerContext:
        with self.engine.connect() as c:
            q = select(s.careers)
            q = q.where(s.careers.c.id == career_id) if career_id else q.order_by(desc(s.careers.c.last_sync_at))
            car = c.execute(q).first()
            if car is None:
                raise CareerNotFound("Aucune carrière synchronisée. Lancez une synchronisation de sauvegarde.")
            snap = c.execute(
                select(s.snapshots)
                .where(s.snapshots.c.career_id == car.id, s.snapshots.c.status == "ok")
                .order_by(desc(s.snapshots.c.game_date), desc(s.snapshots.c.id))
            ).first()
        return CareerContext(
            career_id=car.id,
            label=car.label,
            club_uid=car.club_uid,
            club_name=car.club_name,
            manager_name=car.manager_name,
            game_date=car.last_game_date,
            season_start_year=car.current_season_start_year,
            season_source=car.season_source,
            snapshot_id=snap.id if snap else None,
            snapshot_collected_at=snap.copied_at if snap else None,
            field_status=(snap.field_status or {}) if snap else {},
        )

    def snapshots(self, career_id: int) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(s.snapshots).where(s.snapshots.c.career_id == career_id).order_by(desc(s.snapshots.c.id))
            )
            return [_row(r) for r in rows]

    # -- joueurs ---------------------------------------------------------------------------
    def squad(self, ctx: CareerContext, club_uid: int | None = None, team_slot: int | None = 0) -> list[dict]:
        """Effectif d'un club. `team_slot=0` : équipe première (défaut) ; `None` : toutes les équipes.

        Un joueur dont l'équipe est inconnue (NULL) est conservé plutôt qu'écarté en silence.
        """
        club = club_uid if club_uid is not None else ctx.club_uid
        if club is None:
            return []
        p = s.players_current.c
        conds = [p.career_id == ctx.career_id, p.club_uid == club]
        if team_slot is not None:
            conds.append(or_(p.team_slot == team_slot, p.team_slot.is_(None)))
        with self.engine.connect() as c:
            rows = c.execute(select(s.players_current).where(*conds).order_by(p.name))
            return [_row(r) for r in rows]

    def mirror_season_stats(self, ctx: CareerContext, stat: str, *, kind: str = "overall", min_minutes: int = 0,
                            club_uid: int | None = None, limit: int = 5) -> list[dict]:
        """Classement sur une colonne de fm_player_season_stats (saison en cours, dernier relevé).
        `stat` doit venir d'une liste blanche (outil get_top_players_stat)."""
        sql = (f'SELECT player_uid, player_name, club_name, minutes, "{stat}" AS value FROM fm_player_season_stats '
               'WHERE career_id = :k AND kind = :kind AND "{stat}" IS NOT NULL AND coalesce(minutes, 0) >= :m '
               + ("AND club_uid = :club " if club_uid is not None else "")
               + 'ORDER BY value DESC LIMIT :lim').replace("{stat}", stat)
        with self.engine.connect() as c:
            try:
                rows = c.exec_driver_sql("SELECT 1 FROM fm_player_season_stats LIMIT 1")
            except Exception:  # noqa: BLE001 — miroir absent avant la première synchronisation
                return []
            rows = c.execute(text(sql), {"k": ctx.career_id, "kind": kind, "m": min_minutes, "club": club_uid, "lim": limit})
            return [dict(r._mapping) for r in rows]

    def team_counts(self, ctx: CareerContext, club_uid: int | None = None) -> dict[int | None, int]:
        club = club_uid if club_uid is not None else ctx.club_uid
        p = s.players_current.c
        with self.engine.connect() as c:
            rows = c.execute(
                select(p.team_slot, func.count())
                .where(p.career_id == ctx.career_id, p.club_uid == club)
                .group_by(p.team_slot)
            )
            return {r[0]: r[1] for r in rows}

    def season_lines(self, ctx: CareerContext, uids: list[int], kind: str = "overall") -> dict[int, dict]:
        """Ligne de saison (titularisations, minutes, buts, passes, note) par joueur, dernier relevé."""
        if not uids:
            return {}
        params = {f"u{i}": u for i, u in enumerate(uids)}
        sql = ("SELECT player_uid, starts, substitute_appearances, minutes, goals, assists, average_rating, "
               "clean_sheets FROM fm_player_season_stats WHERE career_id = :k AND kind = :kind AND player_uid IN "
               f"({', '.join(':' + k for k in params)})")
        try:
            with self.engine.connect() as c:
                return {r.player_uid: dict(r._mapping) for r in c.execute(text(sql), {"k": ctx.career_id, "kind": kind, **params})}
        except Exception:  # noqa: BLE001 — miroir absent
            return {}

    def club_short_name(self, ctx: CareerContext, club_uid: int | None) -> str | None:
        """Nom court du club (miroir `fm_clubs`), ex. « AS Roma »."""
        if club_uid is None:
            return None
        try:
            with self.engine.connect() as c:
                return c.execute(text("SELECT short_name FROM fm_clubs WHERE career_id = :k AND uid = :u LIMIT 1"),
                                 {"k": ctx.career_id, "u": club_uid}).scalar()
        except Exception:  # noqa: BLE001 — miroir absent
            return None

    def club_short_names(self, ctx: CareerContext, names: set[str]) -> dict[str, str]:
        """Noms courts des clubs (miroir `fm_clubs`) à partir de leurs noms complets."""
        if not names:
            return {}
        params = {f"n{i}": n for i, n in enumerate(sorted(names))}
        try:
            with self.engine.connect() as c:
                rows = c.execute(text(f"SELECT name, short_name FROM fm_clubs WHERE career_id = :k AND name IN "
                                      f"({', '.join(':' + k for k in params)})"), {"k": ctx.career_id, **params})
                return {r.name: r.short_name for r in rows if r.short_name}
        except Exception:  # noqa: BLE001 — miroir absent
            return {}

    def currency(self, ctx: CareerContext, name: str) -> dict | None:
        """Devise de la table du jeu (miroir `fm_currencies`) : nom, symbole, taux par unité stockée."""
        try:
            with self.engine.connect() as c:
                r = c.execute(
                    text("SELECT name, short_name, symbol, rate FROM fm_currencies WHERE career_id = :k "
                         "AND (name = :n OR short_name = :n) ORDER BY (name = :n) DESC LIMIT 1"),
                    {"k": ctx.career_id, "n": name},
                ).mappings().first()
        except Exception:  # noqa: BLE001 — table absente avant la première synchronisation r8
            return None
        return dict(r) if r else None

    def player(self, ctx: CareerContext, uid: int) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(
                select(s.players_current).where(
                    s.players_current.c.career_id == ctx.career_id, s.players_current.c.uid == uid
                )
            ).first()
            return _row(r) if r else None

    def find_players_by_name(self, ctx: CareerContext, name: str, limit: int = 10) -> list[dict]:
        if not fold(name):
            return []
        cond, indexed = self.name_condition(ctx, name)
        value = s.players_current.c.transfer_value
        with self.engine.connect() as c:
            rows = c.execute(
                select(s.players_current)
                .where(s.players_current.c.career_id == ctx.career_id, cond)
                .order_by(desc(value + 0 if indexed else value))
                .limit(limit)
            )
            return [_row(r) for r in rows]

    def name_condition(self, ctx: CareerContext, name: str) -> tuple[Any, bool]:
        """Condition « le nom contient `name` » (casse et accents ignorés) et vrai si elle passe par l'index.

        Avec l'index, l'appelant neutralise les index de tri (`colonne + 0`) : sinon SQLite parcourt la table
        dans l'ordre du tri et teste chaque joueur. Sous 3 lettres, le trigramme ne sert pas : LIKE direct."""
        needle = fold(name)
        if len(needle) >= 3 and self.ensure_name_index(ctx):
            return s.players_current.c.uid.in_(
                select(NAME_FTS.c.uid).where(NAME_FTS.c.career_id == ctx.career_id,
                                             NAME_FTS.c.name_search.like(f"%{needle}%"))), True
        return s.players_current.c.name_search.like(f"%{needle}%"), False

    def _name_signature(self, conn, career_id: int) -> str:
        last = conn.execute(select(s.careers.c.last_sync_at).where(s.careers.c.id == career_id)).scalar()
        n = conn.execute(select(func.count()).select_from(s.players_current)
                         .where(s.players_current.c.career_id == career_id)).scalar_one()
        return f"{last}|{n}"

    def ensure_name_index(self, ctx: CareerContext) -> bool:
        """Remplit l'index des noms après chaque synchronisation de la carrière (≈ 1 s pour 75 000 joueurs).

        Faux si l'index est indisponible (base sans FTS5, verrou d'une synchronisation en cours) : la
        recherche passe alors par LIKE, plus lente mais identique."""
        k = ctx.career_id
        st = s.name_index_state
        try:
            with self.engine.connect() as c:
                if c.execute(select(st.c.signature).where(st.c.career_id == k)).scalar() == self._name_signature(c, k):
                    return True
            with self.engine.begin() as c:
                c.execute(text("DELETE FROM player_names_fts WHERE career_id = :k"), {"k": k})
                sig = self._name_signature(c, k)  # relu sous le verrou d'écriture
                c.execute(text("INSERT INTO player_names_fts (name_search, career_id, uid) "
                               "SELECT name_search, career_id, uid FROM players_current WHERE career_id = :k"), {"k": k})
                c.execute(st.delete().where(st.c.career_id == k))
                c.execute(st.insert().values(career_id=k, signature=sig))
            return True
        except DBAPIError:
            return False

    def search_players(
        self,
        ctx: CareerContext,
        *,
        position: str | None = None,
        min_age: int | None = None,
        max_age: int | None = None,
        max_value: int | None = None,
        max_wage: int | None = None,
        exclude_club_uid: int | None = None,
        club_uid: int | None = None,
        nation_id: int | None = None,
        contract_expires_before: date | None = None,
        name: str | None = None,
        attribute_min: dict[str, int] | None = None,
        order_by: str = "transfer_value",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        p = s.players_current.c
        conds = [p.career_id == ctx.career_id]
        if position:
            from clubdirector.positions import normalize_position

            pos = normalize_position(position)
            if pos is None:
                raise ValueError(f"Poste inconnu : {position}")
            conds.append(or_(p.positions.like(f"%,{pos},%"), p.accomplished_positions.like(f"%,{pos},%")))
        if min_age is not None:
            conds.append(p.age >= min_age)
        if max_age is not None:
            conds.append(p.age <= max_age)
        if max_value is not None:
            conds.append(and_(p.transfer_value.is_not(None), p.transfer_value <= max_value))
        if max_wage is not None:
            conds.append(and_(p.wage.is_not(None), p.wage <= max_wage))
        if exclude_club_uid is not None:
            conds.append(or_(p.club_uid.is_(None), p.club_uid != exclude_club_uid))
        if club_uid is not None:
            conds.append(p.club_uid == club_uid)
        if nation_id is not None:
            conds.append(p.nation_id == nation_id)
        if contract_expires_before is not None:
            conds.append(and_(p.contract_end.is_not(None), p.contract_end <= contract_expires_before))
        indexed = False
        if name:
            cond, indexed = self.name_condition(ctx, name)
            conds.append(cond)
        for attr, minimum in (attribute_min or {}).items():
            if attr not in ATTRIBUTE_FR:
                raise ValueError(f"Attribut inconnu : {attr}")
            conds.append(func.json_extract(p.attributes, f"$.{attr}") >= minimum)
        def col(c):  # par l'index des noms : ne pas laisser un index de tri piloter la requête
            return c + 0 if indexed else c

        sort_col = {
            "transfer_value": desc(col(p.transfer_value)),
            "age": col(p.age),
            "wage": col(p.wage),
            "name": p.name,
        }.get(order_by, desc(col(p.transfer_value)))
        with self.engine.connect() as c:
            total = c.execute(select(func.count()).select_from(s.players_current).where(*conds)).scalar_one()
            rows = c.execute(
                select(s.players_current).where(*conds).order_by(sort_col).limit(limit).offset(offset)
            )
            return total, [_row(r) for r in rows]

    def player_history(self, ctx: CareerContext, uid: int) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(s.player_history)
                .where(s.player_history.c.career_id == ctx.career_id, s.player_history.c.uid == uid)
                .order_by(s.player_history.c.game_date)
            )
            return [_row(r) for r in rows]

    # -- statistiques ----------------------------------------------------------------------
    def season_stats(
        self,
        ctx: CareerContext,
        *,
        season_start_year: int | None = None,
        player_uid: int | None = None,
        club_uid: int | None = None,
        kind: str | None = None,
    ) -> list[dict]:
        st = s.season_stats.c
        conds = [st.career_id == ctx.career_id]
        if season_start_year is not None:
            conds.append(st.season_start_year == season_start_year)
        if player_uid is not None:
            conds.append(st.player_uid == player_uid)
        if club_uid is not None:
            conds.append(st.club_uid == club_uid)
        if kind is not None:
            conds.append(st.kind == kind)
        with self.engine.connect() as c:
            return [_row(r) for r in c.execute(select(s.season_stats).where(*conds).order_by(st.season_start_year))]

    def archived_seasons(self, ctx: CareerContext) -> list[int]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(s.season_stats.c.season_start_year)
                .where(s.season_stats.c.career_id == ctx.career_id)
                .distinct()
                .order_by(s.season_stats.c.season_start_year)
            )
            return [r[0] for r in rows if r[0] is not None]

    # -- matchs ----------------------------------------------------------------------------
    def fixtures(
        self,
        ctx: CareerContext,
        *,
        club_uid: int | None = None,
        team_slot: int | None = 0,
        date_from: date | None = None,
        date_to: date | None = None,
        played: bool | None = None,
        limit: int = 20,
        newest_first: bool = True,
    ) -> list[dict]:
        f = s.fixtures.c
        club = club_uid if club_uid is not None else ctx.club_uid
        conds = [f.career_id == ctx.career_id]
        if club is not None:
            side = [and_(f.home_club_uid == club), and_(f.away_club_uid == club)]
            if team_slot is not None:
                side = [
                    and_(f.home_club_uid == club, f.home_team_slot == team_slot),
                    and_(f.away_club_uid == club, f.away_team_slot == team_slot),
                ]
            conds.append(or_(*side))
        if date_from is not None:
            conds.append(f.date >= date_from)
        if date_to is not None:
            conds.append(f.date <= date_to)
        if played is not None:
            conds.append(f.played == played)
        order = desc(f.date) if newest_first else f.date
        with self.engine.connect() as c:
            return [_row(r) for r in c.execute(select(s.fixtures).where(*conds).order_by(order).limit(limit))]

    def match_near(self, ctx: CareerContext, target: date, window_days: int = 4) -> list[dict]:
        """Matchs du club joués dans ±window_days autour d'une date de jeu, les plus proches d'abord."""
        rows = self.fixtures(
            ctx,
            date_from=target - timedelta(days=window_days),
            date_to=target + timedelta(days=window_days),
            limit=10,
        )
        rows = [r for r in rows if ctx.game_date is None or r["date"] <= ctx.game_date]
        return sorted(rows, key=lambda r: abs((r["date"] - target).days))

    def league_table(self, ctx: CareerContext, competition_id: int | None = None) -> list[dict]:
        t = s.league_tables.c
        with self.engine.connect() as c:
            snap = c.execute(
                select(func.max(t.snapshot_id)).where(t.career_id == ctx.career_id)
            ).scalar()
            if snap is None:
                return []
            conds = [t.career_id == ctx.career_id, t.snapshot_id == snap]
            if competition_id is None and ctx.club_uid is not None:
                comp = c.execute(
                    select(t.competition_id).where(*conds, t.club_uid == ctx.club_uid).limit(1)
                ).scalar()
                if comp is not None:
                    competition_id = comp
            if competition_id is not None:
                conds.append(t.competition_id == competition_id)
            rows = [_row(r) for r in c.execute(select(s.league_tables).where(*conds).order_by(t.competition_id, t.position))]
        # Une même équipe peut apparaître deux fois dans un classement relu (ligne d'une phase antérieure,
        # ex. Bologne « 1er après 2 matchs ») : on garde, par compétition, la ligne la plus avancée.
        best: dict[tuple, dict] = {}
        for r in rows:
            key = (r.get("competition_id"), r.get("club_uid") or r.get("club_name"), r.get("team_slot"))
            if key not in best or (r.get("played") or 0) > (best[key].get("played") or 0):
                best[key] = r
        return sorted(best.values(), key=lambda r: (r.get("competition_id") or 0, r.get("position") or 0))

    # -- finances --------------------------------------------------------------------------
    def finances(self, ctx: CareerContext, club_uid: int | None = None, months: int = 12) -> list[dict]:
        club = club_uid if club_uid is not None else ctx.club_uid
        if club is None:
            return []
        f = s.finances.c
        with self.engine.connect() as c:
            rows = c.execute(
                select(s.finances)
                .where(f.career_id == ctx.career_id, f.club_uid == club)
                .order_by(desc(f.month))
                .limit(months)
            )
            return [_row(r) for r in rows]

    def tactics(self, ctx: CareerContext) -> list[dict]:
        t = s.tactics.c
        with self.engine.connect() as c:
            snap = c.execute(select(func.max(t.snapshot_id)).where(t.career_id == ctx.career_id)).scalar()
            if snap is None:
                return []
            return [_row(r) for r in c.execute(select(s.tactics).where(t.career_id == ctx.career_id, t.snapshot_id == snap))]

    def injuries(self, ctx: CareerContext, club_uid: int | None = None) -> list[dict]:
        i = s.injuries.c
        conds = [i.career_id == ctx.career_id]
        if club_uid is not None:
            conds.append(i.club_uid == club_uid)
        with self.engine.connect() as c:
            return [_row(r) for r in c.execute(select(s.injuries).where(*conds).order_by(desc(i.date)))]

    def alerts(self, ctx: CareerContext, include_dismissed: bool = False) -> list[dict]:
        a = s.alerts.c
        conds = [a.career_id == ctx.career_id]
        if not include_dismissed:
            conds.append(a.dismissed.is_(False))
        with self.engine.connect() as c:
            return [_row(r) for r in c.execute(select(s.alerts).where(*conds).order_by(desc(a.created_at)))]
