"""Miroir intégral des tables fmsave dans SQLite : aucune donnée décodée n'est perdue.

Chaque lecteur fmsave (`players`, `staff`, `player_season_stats`…) a sa table `fm_<lecteur>`,
dont les colonnes sont exactement les colonnes « à plat » de fmsave (`fmsave.export.column_names`),
préfixées de `career_id` et `snapshot_id`. Les tables typées de ClubDirector (`players_current`,
`season_stats`…) restent la base des outils rapides ; le miroir garantit que TOUT ce que fmsave
sait lire est conservé et interrogeable (outil `query_game_table`).

Le schéma suit fmsave : une colonne apparue dans une nouvelle version est ajoutée (ALTER TABLE),
jamais supprimée. Les listes et sous-structures sont stockées en JSON, les dates en ISO 8601.
Seul le dernier relevé de chaque carrière est conservé (les tables typées gardent l'historique).
"""

from __future__ import annotations

import enum
import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import fmsave
from fmsave import export
from sqlalchemy import Connection, text

log = logging.getLogger(__name__)

# Lecteur fmsave -> type d'enregistrement. Ordre de `fmsave.validate_save`.
MIRRORED_READERS: dict[str, type] = {
    "clubs": fmsave.Club,
    "players": fmsave.Player,
    "contracts": fmsave.Contract,
    "suspensions": fmsave.Suspension,
    "managed_clubs": fmsave.ManagedClub,
    "stages": fmsave.Stage,
    "competitions": fmsave.Competition,
    "fixtures": fmsave.Fixture,
    "league_tables": fmsave.LeagueTable,
    "transfer_windows": fmsave.TransferWindow,
    "competition_rules": fmsave.CompetitionRules,
    "player_match_stats": fmsave.PlayerMatchStats,
    "player_season_stats": fmsave.PlayerSeasonStats,
    "stadiums": fmsave.Stadium,
    "finances": fmsave.FinanceMonth,
    "sponsorships": fmsave.Sponsorship,
    "affiliates": fmsave.AffiliateGroup,
    "job_vacancies": fmsave.JobVacancy,
    "staff": fmsave.Staff,
    "staff_lists": fmsave.StaffList,
    "injury_types": fmsave.InjuryType,
    "injuries": fmsave.InjuryRecord,
    "training": fmsave.TeamTraining,
    "mentoring": fmsave.MentoringGroup,
    "tactics": fmsave.Tactic,
    "set_pieces": fmsave.SetPieceRoutine,
    "facilities": fmsave.ClubFacilities,
    "league_history": fmsave.LeagueHistoryRow,  # fork ClubDirector
    "currencies": fmsave.CurrencyRow,  # fork ClubDirector
    "transfer_offers": fmsave.TransferOffer,  # fork ClubDirector : marché des transferts (offres, prêts)
    "player_rankings": fmsave.PlayerRanking,  # fork ClubDirector : classements du marché par poste
}
# Tables produites par ClubDirector à partir de la sauvegarde, hors lecteurs fmsave d'origine.
EXTRA_TABLES: dict[str, str] = {
    "competition_names": "noms (long, court) des compétitions stockés dans la sauvegarde (actualités, séance de match)",
    "league_history_links": "séries d'historique de championnat rattachées à un club (preuve par recoupement unique)",
}
ALL_TABLES: tuple[str, ...] = (*MIRRORED_READERS, *EXTRA_TABLES)
# Colonnes indexées quand elles existent (recherches courantes des outils).
INDEXED_COLUMNS = ("uid", "id", "database_id", "run", "player_uid", "club_uid", "competition_id", "team_id", "date",
                   "bidding_club_uid", "selling_club_uid")


@dataclass
class MirrorTable:
    """Une table fmsave déjà convertie en valeurs SQLite."""

    reader: str
    columns: list[str]
    rows: list[tuple]


def table_name(reader: str) -> str:
    return f"fm_{reader}"


_INT64 = (-(2**63), 2**63 - 1)


def _sql_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        # Champs de bits sur 64 bits non signés (ex. traits) : hors des entiers SQLite -> texte.
        return value if _INT64[0] <= value <= _INT64[1] else str(value)
    if value is None or isinstance(value, (float, str, bytes)):
        return value
    if isinstance(value, enum.Enum):
        return value.value if isinstance(value.value, (int, str)) else value.name
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return json.dumps({str(k): _jsonable(v) for k, v in value.items()}, ensure_ascii=False)
    if isinstance(value, (list, tuple, set, frozenset)):
        return json.dumps([_jsonable(v) for v in value], ensure_ascii=False)
    return json.dumps(_jsonable(value), ensure_ascii=False)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, enum.Enum):
        return value.value if isinstance(value.value, (int, str)) else value.name
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    try:  # enregistrement fmsave imbriqué (ex. lignes d'un classement)
        return _jsonable(export.record_to_dict(value, json_ready=True))
    except TypeError:
        return str(value)


def build_mirror_table(reader: str, records: Iterable[object]) -> MirrorTable:
    record_type = MIRRORED_READERS[reader]
    records = list(records)
    columns = list(export.column_names(record_type))
    if not records:
        return MirrorTable(reader, columns, [])
    cols = export.to_columns(records, record_type)
    converted = [[_sql_value(v) for v in cols[c]] for c in columns]
    return MirrorTable(reader, columns, list(zip(*converted, strict=True)))


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _ensure_table(conn: Connection, table: MirrorTable) -> None:
    name = table_name(table.reader)
    existing = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({_quote(name)})")}
    if not existing:
        cols = ", ".join(_quote(c) for c in table.columns)
        conn.exec_driver_sql(
            f"CREATE TABLE {_quote(name)} (career_id INTEGER NOT NULL, snapshot_id INTEGER NOT NULL, {cols})"
        )
        conn.exec_driver_sql(f"CREATE INDEX {_quote('ix_' + name + '_career')} ON {_quote(name)} (career_id)")
        for col in INDEXED_COLUMNS:
            if col in table.columns:
                conn.exec_driver_sql(
                    f"CREATE INDEX {_quote('ix_' + name + '_' + col)} ON {_quote(name)} (career_id, {_quote(col)})"
                )
        return
    for col in table.columns:
        if col not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {_quote(name)} ADD COLUMN {_quote(col)}")


def write_mirror(conn: Connection, career_id: int, snapshot_id: int, tables: Iterable[MirrorTable]) -> dict[str, int]:
    """Remplace, pour cette carrière, le contenu de chaque table miroir fournie."""
    counts = {}
    for table in tables:
        _ensure_table(conn, table)
        name = _quote(table_name(table.reader))
        conn.exec_driver_sql(f"DELETE FROM {name} WHERE career_id = ?", (career_id,))
        if table.rows:
            cols = ", ".join(["career_id", "snapshot_id", *(_quote(c) for c in table.columns)])
            marks = ", ".join("?" * (len(table.columns) + 2))
            conn.exec_driver_sql(
                f"INSERT INTO {name} ({cols}) VALUES ({marks})",
                [(career_id, snapshot_id, *row) for row in table.rows],
            )
        counts[table.reader] = len(table.rows)
    return counts


def mirror_tables(conn: Connection) -> list[str]:
    rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fm\\_%' ESCAPE '\\'"))
    return sorted(r[0] for r in rows)
