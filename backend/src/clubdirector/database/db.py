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


MIGRATIONS: list[Migration] = [_m1_initial, _m2_player_team_slot]
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
    engine = create_engine(url, future=True)
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
