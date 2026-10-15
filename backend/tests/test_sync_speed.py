"""Synchronisation rapide sans changer son résultat, et service disponible pendant une relecture.

Mesures sur la vraie carrière (docs/TEST_REPORT.md) ; ici : les raccourcis donnent exactement les
valeurs des chemins d'origine, une table inchangée n'est pas réécrite, et pendant l'écriture d'une
synchronisation le service lit l'état précédent et ses propres écritures attendent sans échouer.
"""

from __future__ import annotations

import datetime as dt
import enum
import gc
import random
import threading
from dataclasses import replace

import pytest

from clubdirector.database.mirror import MirrorTable, _sql_value, _sql_values, write_mirror
from clubdirector.database.repositories import Repository
from clubdirector.game.fmsave_reader import FmsaveSaveReader
from clubdirector.game.history_links import _unique_assignment
from clubdirector.memory.store import ConversationStore
from clubdirector.sync import service as service_mod

from .conftest import SCORED


def _reference_assignment(groups, clubs, nation, last_position):
    """Version d'origine (programmation dynamique, k × n) gardée comme référence."""
    k, n = len(groups), len(clubs)
    if k == 0:
        return []
    if k > n:
        return None

    def ok(i, j):
        nations, position = groups[i]
        if nations and nation.get(clubs[j]) not in nations:
            return False
        return position is None or last_position.get(clubs[j]) == position

    ways = [[0] * (n + 1) for _ in range(k + 1)]
    for j in range(n + 1):
        ways[k][j] = 1
    for i in range(k - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            w = ways[i][j + 1]
            if ok(i, j):
                w += ways[i + 1][j + 1]
            ways[i][j] = min(w, 2)
    if ways[0][0] != 1:
        return None
    out, j = [], 0
    for i in range(k):
        while not (ok(i, j) and ways[i + 1][j + 1] == 1):
            j += 1
        out.append(clubs[j])
        j += 1
    return out


def test_linear_history_assignment_matches_the_exhaustive_count():
    rng = random.Random(26)
    unique = 0
    for _ in range(4000):
        n = rng.randint(0, 9)
        clubs = list(range(100, 100 + n))
        nation = {c: rng.choice([1, 2, 3, None]) for c in clubs}
        last_position = {c: rng.choice([1, 2, None]) for c in clubs}
        groups = [({*rng.sample([1, 2, 3], rng.randint(0, 2))}, rng.choice([None, None, 1, 2]))
                  for _ in range(rng.randint(0, 6))]
        expected = _reference_assignment(groups, clubs, nation, last_position)
        assert _unique_assignment(groups, clubs, nation, last_position) == expected, (groups, clubs, nation)
        unique += expected not in (None, [])
    assert unique > 100  # le tirage couvre bien des cas à solution unique


class Couleur(enum.Enum):
    ROUGE = (1, 2)


class Note(enum.IntEnum):
    BONNE = 3


def test_column_conversion_gives_the_value_by_value_result():
    columns = [
        [1, None, 2**63 - 1, -(2**63)],
        [1, 2**64 - 5, None],  # hors des entiers SQLite : texte
        [True, False, None],
        ["a", None, "é"],
        [1.5, None],
        [dt.date(2025, 7, 1), None],
        [Note.BONNE, Couleur.ROUGE, None],
        [(1, 2), [Note.BONNE, dt.date(2025, 1, 2)], None, (), ("é", None, 1.5, {"x": 1})],
        [frozenset({1}), {2: "a"}, None],
        [[{Couleur.ROUGE: 1}], None],  # clé refusée par json : conversion valeur par valeur
    ]
    for col in columns:
        assert _sql_values(list(col)) == [_sql_value(v) for v in col], col


def _table(rows):
    return MirrorTable("currencies", ["id", "name"], rows)


def _mirror_rows(engine):
    with engine.connect() as c:
        return c.exec_driver_sql("SELECT career_id, snapshot_id, id, name FROM fm_currencies ORDER BY id").all()


def test_unchanged_mirror_table_is_not_rewritten(engine):
    skipped: list[str] = []
    with engine.begin() as c:
        write_mirror(c, 1, 10, [_table([(1, "euro"), (2, "livre")])], skipped)
    with engine.begin() as c:
        counts = write_mirror(c, 1, 11, [_table([(1, "euro"), (2, "livre")])], skipped)
    assert skipped == ["currencies"] and counts == {"currencies": 2}
    assert {r.snapshot_id for r in _mirror_rows(engine)} == {10}  # relevé de la dernière écriture
    with engine.begin() as c:  # contenu changé : réécrit
        write_mirror(c, 1, 12, [_table([(1, "euro"), (2, "livre sterling")])], skipped)
    assert [tuple(r) for r in _mirror_rows(engine)] == [(1, 12, 1, "euro"), (1, 12, 2, "livre sterling")]
    with engine.begin() as c:  # table modifiée hors synchronisation : le compte ne colle plus, réécrite
        c.exec_driver_sql("DELETE FROM fm_currencies WHERE id = 2")
    with engine.begin() as c:
        write_mirror(c, 1, 13, [_table([(1, "euro"), (2, "livre sterling")])], skipped)
    assert len(_mirror_rows(engine)) == 2 and skipped == ["currencies"]


def test_sync_pauses_the_cyclic_gc_and_restores_it(sync, game_dir, monkeypatch):
    seen = []
    real_read = sync.reader.read

    def read(path):
        seen.append(gc.isenabled())
        return real_read(path)

    monkeypatch.setattr(sync.reader, "read", read)
    assert gc.isenabled()
    sync.sync_save(game_dir / SCORED.name)
    assert seen == [False] and gc.isenabled()


def test_service_answers_on_previous_state_while_a_sync_writes(sync, engine, game_dir, monkeypatch):
    first = sync.sync_save(game_dir / SCORED.name)
    repo = Repository(engine)
    before = repo.context(first.career_id).game_date
    extract = FmsaveSaveReader().read(SCORED)
    extract.meta.game_date = extract.meta.game_date + dt.timedelta(days=3)
    snap = replace(sync_snapshot(sync, game_dir), sha256="d" * 64)

    in_write, release = threading.Event(), threading.Event()
    real_write = service_mod.write_mirror

    def slow_write(*args, **kwargs):
        in_write.set()
        assert release.wait(30)
        return real_write(*args, **kwargs)

    monkeypatch.setattr(service_mod, "write_mirror", slow_write)
    result: dict = {}
    syncing = threading.Thread(target=lambda: result.setdefault("sync", sync.import_extract(extract, snap)))
    syncing.start()
    assert in_write.wait(30)
    # Lecture pendant la transaction : l'état précédent, sans attendre.
    assert repo.context(first.career_id).game_date == before
    # Écriture du service pendant la transaction : elle attend la validation, puis réussit.
    wrote: dict = {}
    writer = threading.Thread(target=lambda: wrote.setdefault(
        "conv", ConversationStore(engine).create(first.career_id, "pendant la synchronisation")))
    writer.start()
    writer.join(0.5)
    assert writer.is_alive()  # bloquée par l'écriture de la synchronisation, pas en échec
    release.set()
    syncing.join(60)
    writer.join(60)
    assert "sync" in result and wrote.get("conv")
    assert repo.context(first.career_id).game_date == before + dt.timedelta(days=3)


def sync_snapshot(sync, game_dir):
    from clubdirector.game.snapshot import take_snapshot

    return take_snapshot(game_dir / SCORED.name, sync.snapshot_dir)


@pytest.fixture(autouse=True)
def _gc_enabled():
    gc.enable()
    yield
    gc.enable()

