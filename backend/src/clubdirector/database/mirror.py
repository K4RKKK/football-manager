"""Miroir intégral des tables fmsave dans SQLite : aucune donnée décodée n'est perdue.

Chaque lecteur fmsave (`players`, `staff`, `player_season_stats`…) a sa table `fm_<lecteur>`,
dont les colonnes sont exactement les colonnes « à plat » de fmsave (`fmsave.export.column_names`),
préfixées de `career_id` et `snapshot_id`. Les tables typées de ClubDirector (`players_current`,
`season_stats`…) restent la base des outils rapides ; le miroir garantit que TOUT ce que fmsave
sait lire est conservé et interrogeable (outil `query_game_table`).

Le schéma suit fmsave : une colonne apparue dans une nouvelle version est ajoutée (ALTER TABLE),
jamais supprimée. Les listes et sous-structures sont stockées en JSON, les dates en ISO 8601.
Seul le dernier relevé de chaque carrière est conservé (les tables typées gardent l'historique).
Une table dont le contenu n'a pas changé depuis la synchronisation précédente n'est pas réécrite
(empreinte dans `mirror_state`) : sa colonne `snapshot_id` est alors celui du relevé qui l'a
écrite en dernier.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import pickle
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
    "squad_influence": fmsave.SquadInfluence,  # fork ClubDirector : hiérarchie du vestiaire (club géré)
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


def _json_default(value: Any) -> Any:
    """Ce que `json` ne sait pas écrire seul, converti comme `_jsonable` le ferait."""
    if isinstance(value, (set, frozenset)):
        return list(value)
    return _jsonable(value)


def _sql_values(values: list) -> list:
    """`_sql_value` sur une colonne entière, sans conversion quand elle n'en a pas besoin : la
    plupart des colonnes ne contiennent que des entiers, textes, réels ou None (51 millions de
    conversions par synchronisation sur une vraie carrière, sinon)."""
    types = set(map(type, values))
    if types <= _PLAIN:
        if int not in types:
            return values
        ints = [v for v in values if type(v) is int]
        if _INT64[0] <= min(ints) and max(ints) <= _INT64[1]:
            return values
    if types <= _SEQUENCES | {type(None)}:
        # Listes et tuples : json les écrit directement (même texte que _jsonable), sauf clé de
        # dictionnaire qu'il refuse (Enum simple…) : conversion valeur par valeur.
        dumps = json.dumps
        try:
            return [None if v is None else dumps(v, ensure_ascii=False, default=_json_default) for v in values]
        except (TypeError, ValueError):
            pass
    return [_sql_value(v) for v in values]


_PLAIN = {type(None), int, float, str, bytes, bool}
_SEQUENCES = {list, tuple}


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
    converted = [_sql_values(cols[c]) for c in columns]
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


def table_digest(table: MirrorTable) -> str:
    """Empreinte du contenu (colonnes + lignes). Deux contenus différents ont deux empreintes
    différentes ; un contenu identique peut, rarement, en avoir deux (simple réécriture)."""
    return hashlib.blake2b(pickle.dumps((table.columns, table.rows), protocol=5), digest_size=20).hexdigest()


def _ensure_state(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS mirror_state (career_id INTEGER NOT NULL, reader TEXT NOT NULL, "
        "digest TEXT NOT NULL, row_count INTEGER NOT NULL, snapshot_id INTEGER NOT NULL, "
        "PRIMARY KEY (career_id, reader))"
    )


def write_mirror(conn: Connection, career_id: int, snapshot_id: int, tables: Iterable[MirrorTable],
                 skipped: list[str] | None = None) -> dict[str, int]:
    """Remplace, pour cette carrière, le contenu de chaque table miroir fournie ; une table
    identique à celle déjà écrite n'est pas réécrite (son nom est ajouté à `skipped`)."""
    counts = {}
    _ensure_state(conn)
    known = {r[0]: (r[1], r[2]) for r in conn.exec_driver_sql(
        "SELECT reader, digest, row_count FROM mirror_state WHERE career_id = ?", (career_id,))}
    for table in tables:
        _ensure_table(conn, table)
        name = _quote(table_name(table.reader))
        counts[table.reader] = len(table.rows)
        digest = table_digest(table)
        if known.get(table.reader) == (digest, len(table.rows)):
            stored = conn.exec_driver_sql(f"SELECT count(*) FROM {name} WHERE career_id = ?", (career_id,)).scalar()
            if stored == len(table.rows):
                if skipped is not None:
                    skipped.append(table.reader)
                continue
        conn.exec_driver_sql(f"DELETE FROM {name} WHERE career_id = ?", (career_id,))
        if table.rows:
            cols = ", ".join(["career_id", "snapshot_id", *(_quote(c) for c in table.columns)])
            marks = ", ".join("?" * (len(table.columns) + 2))
            conn.exec_driver_sql(
                f"INSERT INTO {name} ({cols}) VALUES ({marks})",
                [(career_id, snapshot_id, *row) for row in table.rows],
            )
        conn.exec_driver_sql(
            "INSERT OR REPLACE INTO mirror_state (career_id, reader, digest, row_count, snapshot_id) "
            "VALUES (?, ?, ?, ?, ?)", (career_id, table.reader, digest, len(table.rows), snapshot_id))
    return counts


def mirror_tables(conn: Connection) -> list[str]:
    rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fm\\_%' ESCAPE '\\'"))
    return sorted(r[0] for r in rows)
