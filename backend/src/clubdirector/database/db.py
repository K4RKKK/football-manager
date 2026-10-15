"""Moteur SQLite + migrations versionnées (liste ordonnée, idempotente)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, select

from clubdirector.database import schema

Migration = Callable[[Engine], None]


def _m1_initial(engine: Engine) -> None:
    schema.metadata.create_all(engine)


def _m2_player_team_slot(engine: Engine) -> None:
    """Équipe de chaque joueur (première / réserve / jeunes) — ajoutée en session 2."""
    with engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(players_current)")}
        if "team_slot" not in cols:
            conn.exec_driver_sql("ALTER TABLE players_current ADD COLUMN team_slot INTEGER")


def _m3_dedupe_snapshot_rows(engine: Engine) -> None:
    """Supprime les doublons laissés par les relectures d'un même relevé (session 2, avant
    correctif) : une seule ligne par clé naturelle et par relevé."""
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "DELETE FROM league_tables WHERE id NOT IN (SELECT max(id) FROM league_tables "
            "GROUP BY career_id, snapshot_id, competition_id, club_uid, team_slot, position)"
        )
        conn.exec_driver_sql(
            "DELETE FROM tactics WHERE id NOT IN (SELECT max(id) FROM tactics "
            "GROUP BY career_id, snapshot_id, club_uid, team_slot, idx)"
        )


def _m4_contact_threads(engine: Engine) -> None:
    """Fils de messages par contact du téléphone (session 3)."""
    with engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(conversations)")}
        for name, sql_type in (("contact_role", "VARCHAR(40)"), ("staff_uid", "INTEGER"), ("last_read_id", "INTEGER")):
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE conversations ADD COLUMN {name} {sql_type}")


MIGRATIONS: list[Migration] = [_m1_initial, _m2_player_team_slot, _m3_dedupe_snapshot_rows, _m4_contact_threads]
CURRENT_VERSION = len(MIGRATIONS)


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def open_database(path: Path | str) -> Engine:
    url = "sqlite:///:memory:" if str(path) == ":memory:" else f"sqlite:///{Path(path)}"
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Une écriture du service (message, mémoire) qui tombe pendant l'écriture d'une synchronisation
    # attend sa validation (≈ 10-15 s sur une vraie carrière) au lieu d'échouer après 5 s.
    engine = create_engine(url, future=True, connect_args={"timeout": 60})
    event.listen(engine, "connect", _sqlite_pragmas)
    migrate(engine)
    return engine


def migrate(engine: Engine) -> int:
    schema.schema_version.create(engine, checkfirst=True)
    with engine.begin() as conn:
        row = conn.execute(select(schema.schema_version.c.version)).first()
        current = row[0] if row else 0
    for version in range(current + 1, CURRENT_VERSION + 1):
        MIGRATIONS[version - 1](engine)
        with engine.begin() as conn:
            conn.execute(schema.schema_version.delete())
            conn.execute(schema.schema_version.insert().values(version=version))
    return CURRENT_VERSION
