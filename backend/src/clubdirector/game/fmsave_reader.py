"""Adaptateur ISaveReader basé sur fmsave (MIT, https://github.com/rhiever/fmsave).

fmsave lit le conteneur .fm de FM26 en lecture seule. Il renvoie `None` pour toute valeur qu'il
ne sait pas lire : on conserve ce `None` tel quel. Le statut de vérification de chaque champ
(`fmsave.field_status`) est propagé pour que l'IA puisse qualifier ses réponses.
"""

from __future__ import annotations

import dataclasses
import logging
import warnings
from enum import Enum
from pathlib import Path
from typing import Any

import fmsave
from fmsave.readers.competition_names import NAME_SECTIONS, find_competition_names

from clubdirector.database.mirror import MIRRORED_READERS, MirrorTable, build_mirror_table
from clubdirector.domain.models import (
    ClubRecord,
    Confidence,
    FinanceMonth,
    FixtureRecord,
    InjuryRecord,
    LeagueTableRowRecord,
    ManagedClubInfo,
    PlayerRecord,
    SaveExtract,
    SaveMeta,
    SeasonStatLine,
    TacticRecord,
)
from clubdirector.game.history_links import link_runs_to_clubs

log = logging.getLogger(__name__)

# Champs dont le statut de vérification est remonté à l'IA (modèle fmsave, chemin pointé).
TRACKED_FIELDS: dict[str, tuple[str, str]] = {
    "player.age": ("Player", "age"),
    "player.club_uid": ("Player", "club_uid"),
    "player.current_ability": ("Player", "ability.current"),
    "player.potential_ability": ("Player", "ability.potential"),
    "player.transfer_value": ("Player", "transfer_value"),
    "player.wage": ("Player", "contract.wage"),
    "player.contract_end": ("Player", "contract.end"),
    "player.attributes": ("Player", "attributes.finishing"),
    "player.personality": ("Player", "personality.ambition"),
    "player.condition": ("Player", "raw_condition"),
    "fixture.score": ("Fixture", "home_goals"),
    "season_stats.goals": ("PlayerSeasonStats", "goals"),
    "season_stats.assists": ("PlayerSeasonStats", "assists"),
    "finance.transfer_budget_remaining": ("FinanceMonth", "transfer_budget_remaining"),
    "finance.wage_budget_weekly": ("FinanceMonth", "wage_budget_weekly"),
}

SEASON_STAT_CORE = {
    "player_uid", "player_name", "kind", "team_id", "club_uid", "club_name", "club_short_name",
    "team_slot", "starts", "substitute_appearances", "minutes", "goals", "assists",
    "average_rating", "expected_goals", "player_of_the_match", "yellow_cards", "red_cards",
}


def _label(value: Any) -> str | None:
    """Convertit un CodedValue / Enum fmsave en libellé stable (ou None)."""
    if value is None:
        return None
    label = getattr(value, "label", value)
    if isinstance(label, Enum):
        if label.name == "UNKNOWN":
            raw = getattr(value, "raw", None)
            return f"inconnu({raw})" if raw is not None else None
        return label.name.lower() if not isinstance(label.value, str) else label.value
    return str(label)


def _dc_to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}


def _status(model: str, field: str) -> Confidence:
    cls = getattr(fmsave, model, None)
    if cls is None:
        return "unknown"
    try:
        st = fmsave.field_status(cls, field)
    except Exception:  # champ absent dans cette version de fmsave
        return "unknown"
    text = getattr(st, "value", str(st)).lower()
    return "verified" if text == "verified" else "unconfirmed"


# À incrémenter quand l'adaptateur lit de nouveaux champs : une sauvegarde déjà importée par une
# révision antérieure est alors relue (sinon les nouveaux champs resteraient vides).
READER_REVISION = 6  # 3 : statuts des clubs ; 4 : miroir ; 5 : noms de compétitions ; 6 : historique


class FmsaveSaveReader:
    name = f"fmsave {getattr(fmsave, '__version__', '?')} r{READER_REVISION}"

    def __init__(self, competition_names: dict[int, str] | None = None) -> None:
        self.competition_names = competition_names

    def read(self, snapshot_path: Path) -> SaveExtract:
        caught: list[str] = []
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            save_names = self._save_competition_names(snapshot_path)
            # Noms fournis par l'utilisateur prioritaires ; sinon ceux que la sauvegarde stocke.
            names = {db: long for db, (long, _short) in save_names.items()} | (self.competition_names or {})
            with fmsave.open(snapshot_path, competition_names=names or None) as save:
                extract = self._read_open(save)
                extract.mirror.append(MirrorTable(
                    "competition_names", ["database_id", "long_name", "short_name"],
                    sorted((db, long, short) for db, (long, short) in save_names.items()),
                ))
            caught = [f"{x.category.__name__}: {x.message}" for x in w]
        # Les échecs de lecteurs (ajoutés par _read_open) ne doivent pas être écrasés : sans eux,
        # une section illisible (ex. tactiques du build 26.3.0) passait pour une section vide.
        extract.reader_warnings = caught + extract.reader_warnings
        for msg in caught:
            log.warning("fmsave: %s", msg)
        return extract

    @staticmethod
    def _save_competition_names(snapshot_path: Path) -> dict[int, tuple[str, str]]:
        """Noms (long, court) des compétitions que la sauvegarde stocke elle-même (fork fmsave)."""
        try:
            with fmsave.open(snapshot_path) as save:
                ids = [c.database_id for c in save.competitions() if c.database_id is not None]
                listed = {s.name for s in save.info.sections}
                buffers = [save._read_section(n) for n in NAME_SECTIONS if n in listed]
            return find_competition_names(buffers, ids)
        except Exception as exc:  # noqa: BLE001 — sans noms, la lecture continue
            log.warning("noms de compétitions illisibles : %s", exc)
            return {}

    def _safe(self, label: str, fn, errors: list[str]):
        """Un lecteur en échec ne doit pas faire tomber toute la synchronisation."""
        try:
            return list(fn())
        except Exception as exc:  # noqa: BLE001 — on journalise et on continue
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            return []

    def _read_open(self, save: Any) -> SaveExtract:
        info = save.info
        errors: list[str] = []
        meta = SaveMeta(
            game=info.game,
            build=info.build,
            db_version=info.db_version,
            game_date=info.game_date,
            known_build=bool(info.known_build),
        )
        managed = [
            ManagedClubInfo(
                club_uid=m.club_uid,
                club_name=m.club_name,
                club_short_name=m.club_short_name,
                manager_name=m.manager_name,
                manager_staff_uid=m.manager_staff_uid,
            )
            for m in self._safe("managed_clubs", save.managed_clubs, errors)
        ]
        players = [self._player(p) for p in self._safe("players", save.players, errors)]
        clubs = [
            ClubRecord(
                uid=c.uid,
                name=c.name,
                short_name=c.short_name,
                nation_id=c.nation_id,
                reputation=c.reputation,
                last_league_position=c.last_league_position,
            )
            for c in self._safe("clubs", save.clubs, errors)
        ]
        fixtures = [
            FixtureRecord(
                stage_id=f.stage_id,
                competition_id=f.competition_id,
                competition_name=f.competition_name,
                round_label=_label(f.round),
                date=f.date,
                season_start_year=f.season_start_year,
                home_club_uid=f.home_club_uid,
                home_club_name=f.home_club_name,
                home_team_slot=f.home_team_slot,
                away_club_uid=f.away_club_uid,
                away_club_name=f.away_club_name,
                away_team_slot=f.away_team_slot,
                home_goals=f.home_goals,
                away_goals=f.away_goals,
                played=f.played,
            )
            for f in self._safe("fixtures", save.fixtures, errors)
            if f.date is not None
        ]
        season_stats = []
        for s in self._safe("player_season_stats", save.player_season_stats, errors):
            d = _dc_to_dict(s)
            extra = {
                k: v
                for k, v in d.items()
                if k not in SEASON_STAT_CORE and isinstance(v, (int, float)) and not isinstance(v, bool)
            }
            season_stats.append(
                SeasonStatLine(
                    player_uid=s.player_uid,
                    player_name=s.player_name,
                    kind=_label(s.kind) or "inconnu",
                    club_uid=s.club_uid,
                    club_name=s.club_name,
                    team_slot=s.team_slot,
                    starts=s.starts,
                    substitute_appearances=s.substitute_appearances,
                    minutes=s.minutes,
                    goals=s.goals,
                    assists=s.assists,
                    average_rating=s.average_rating,
                    expected_goals=s.expected_goals,
                    player_of_the_match=s.player_of_the_match,
                    yellow_cards=d.get("yellow_cards"),
                    red_cards=d.get("red_cards"),
                    extra=extra,
                )
            )
        finances = [
            FinanceMonth(
                club_uid=f.club_uid,
                month=f.month,
                balance=f.balance,
                transfer_budget_allocated=f.transfer_budget_allocated,
                transfer_budget_remaining=f.transfer_budget_remaining,
                wage_budget_weekly=f.wage_budget_weekly,
                wage_payroll_weekly=f.wage_payroll_weekly,
                total_income=f.total_income,
                total_expenditure=f.total_expenditure,
                net=f.net,
            )
            for f in self._safe("finances", save.finances, errors)
        ]
        tables = []
        for t in self._safe("league_tables", save.league_tables, errors):
            for r in t.rows:
                tables.append(
                    LeagueTableRowRecord(
                        competition_id=t.competition_id,
                        competition_name=t.competition_name,
                        position=r.position,
                        club_uid=r.club_uid,
                        club_name=r.club_name,
                        team_slot=r.team_slot,
                        played=r.played,
                        won=r.won,
                        drawn=r.drawn,
                        lost=r.lost,
                        goals_for=r.goals_for,
                        goals_against=r.goals_against,
                        points=r.points,
                    )
                )
        tactics = [
            TacticRecord(
                club_uid=t.club_uid,
                team_slot=t.team_slot,
                index=t.index,
                name=t.name,
                style_name=t.style_name,
                mentality=_label(t.mentality),
                slots=[
                    {
                        "number": sl.number,
                        "in_possession_positions": [_label(x) for x in sl.in_possession_positions],
                        "out_of_possession_positions": [
                            _label(x) for x in sl.out_of_possession_positions
                        ],
                    }
                    for sl in t.slots
                ],
            )
            for t in self._safe("tactics", save.tactics, errors)
        ]
        injuries = [
            InjuryRecord(
                kind=_label(i.kind) or "inconnu",
                player_uid=i.player_uid,
                player_name=i.player_name,
                date=i.date,
                club_uid=i.club_uid,
                type_name=i.type_name,
            )
            for i in self._safe("injuries", save.injuries, errors)
        ]
        field_status = {k: _status(m, f) for k, (m, f) in TRACKED_FIELDS.items()}
        mirror = self._mirror(save, errors)
        extract = SaveExtract(
            meta=meta,
            managed=managed,
            players=players,
            clubs=clubs,
            fixtures=fixtures,
            season_stats=season_stats,
            finances=finances,
            league_tables=tables,
            tactics=tactics,
            injuries=injuries,
            field_status=field_status,
            mirror=mirror,
        )
        extract.reader_warnings.extend(errors)
        return extract

    def _mirror(self, save: Any, errors: list[str]) -> list[MirrorTable]:
        """Toutes les tables fmsave, colonnes complètes (fmsave met ses décodages en cache :
        les lecteurs déjà appelés plus haut ne relisent rien)."""
        already_reported = {e.split(":", 1)[0] for e in errors}
        tables = []
        for name in MIRRORED_READERS:
            try:
                tables.append(build_mirror_table(name, getattr(save, name)()))
            except Exception as exc:  # noqa: BLE001 — un lecteur en échec n'arrête pas le miroir
                if name not in already_reported:
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
        try:
            links = link_runs_to_clubs(save.league_history(), save.clubs(), save.league_tables())
            tables.append(MirrorTable("league_history_links", ["run", "club_uid", "method"], links))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"league_history_links: {type(exc).__name__}: {exc}")
        return tables

    @staticmethod
    def _player(p: Any) -> PlayerRecord:
        c = p.contract
        ability = p.ability
        return PlayerRecord(
            uid=p.uid,
            unique_id=p.unique_id,
            name=p.name,
            birth_date=p.birth_date,
            age=p.age,
            nation_id=p.nation_id,
            height_cm=p.height_cm,
            club_uid=p.club_uid,
            club_name=p.club_name,
            team_slot=p.team_slot,
            natural_positions=list(p.natural_positions or ()),
            accomplished_positions=list(p.accomplished_positions or ()),
            position_ratings=_dc_to_dict(p.positions),
            left_foot=p.left_foot,
            right_foot=p.right_foot,
            current_ability=ability.current if ability else None,
            potential_ability=ability.potential if ability else None,
            transfer_value=p.transfer_value,
            transfer_value_state=_label(p.transfer_value_state),
            wage=c.wage if c else None,
            contract_start=c.start if c else None,
            contract_end=c.end if c else None,
            squad_status=_label(c.squad_status) if c else None,
            on_loan=bool(p.on_loan),
            loan_parent_club_uid=p.loan_parent_club_uid,
            condition=p.raw_condition,
            attributes=_dc_to_dict(p.attributes),
            personality=_dc_to_dict(p.personality),
            traits=[t for t in (_label(x) for x in (p.traits or ())) if t],
            banned=bool(p.suspensions),
        )
