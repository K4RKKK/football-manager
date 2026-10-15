"""Équipes d'un club (première / réserve / jeunes) et remontée des échecs de lecteurs.

Constatés sur une vraie carrière FM26 (session 2) : l'effectif de l'AS Roma mélangeait équipe
première, Primavera et U18 (74 joueurs), et l'échec du lecteur de tactiques était masqué.
"""

import fmsave
from sqlalchemy import insert, select, update

from clubdirector.database import schema as s
from clubdirector.database.db import CURRENT_VERSION, migrate
from clubdirector.game.fmsave_reader import FmsaveSaveReader

from .conftest import SCORED


def run(registry, tctx, tool, **args):
    return registry.execute(tool, args, tctx)


def _add_youth_player(engine, career_id: int, club_uid: int, uid: int, slot: int | None) -> None:
    with engine.begin() as c:
        snap = c.execute(select(s.snapshots.c.id).where(s.snapshots.c.career_id == career_id)).scalar()
        c.execute(insert(s.players_current).values(
            career_id=career_id, snapshot_id=snap, uid=uid, name=f"Jeune {uid}", name_search=f"jeune {uid}", age=17,
            club_uid=club_uid, club_name="Northbridge FC", team_slot=slot, positions=",DC,",
            accomplished_positions=",,",
        ))


def test_reader_keeps_team_slot():
    e = FmsaveSaveReader().read(SCORED)
    managed = e.managed[0].club_uid
    assert [(p.name, p.team_slot) for p in e.players if p.club_uid == managed] == [("Sam Sample", 0)]


def test_squad_defaults_to_first_team(registry, tctx, engine):
    _add_youth_player(engine, tctx.ctx.career_id, tctx.ctx.club_uid, 777000001, slot=1)
    first = run(registry, tctx, "get_club_squad")
    everyone = run(registry, tctx, "get_club_squad", toutes_equipes=True)
    reserve = run(registry, tctx, "get_club_squad", team_slot=1)
    assert [p["nom"] for p in first.data] == ["Sam Sample"]
    assert {p["nom"] for p in everyone.data} == {"Sam Sample", "Jeune 777000001"}
    assert [p["nom"] for p in reserve.data] == ["Jeune 777000001"]
    club = run(registry, tctx, "get_managed_club").data
    assert club["effectif"] == 1 and club["joueurs_par_equipe"] == {"slot 0": 1, "slot 1": 1}


def test_unknown_team_is_kept_not_hidden(registry, tctx, engine):
    _add_youth_player(engine, tctx.ctx.career_id, tctx.ctx.club_uid, 777000002, slot=None)
    assert "Jeune 777000002" in {p["nom"] for p in run(registry, tctx, "get_club_squad").data}


def test_youth_prospects_cover_all_teams(registry, tctx, engine):
    _add_youth_player(engine, tctx.ctx.career_id, tctx.ctx.club_uid, 777000003, slot=2)
    assert "Jeune 777000003" in {p["nom"] for p in run(registry, tctx, "evaluate_youth_prospects").data}


def test_migration_adds_team_slot_to_v1_database(engine):
    with engine.begin() as c:
        c.exec_driver_sql("ALTER TABLE players_current DROP COLUMN team_slot")
        c.execute(update(s.schema_version).values(version=1))
    assert migrate(engine) == CURRENT_VERSION
    with engine.connect() as c:
        cols = {r[1] for r in c.exec_driver_sql("PRAGMA table_info(players_current)")}
        assert "team_slot" in cols
        assert c.execute(select(s.schema_version.c.version)).scalar() == CURRENT_VERSION


def test_failed_reader_is_reported_not_silent(monkeypatch):
    def broken(self):
        raise fmsave.ReaderCheckError("section 'tactics_man': layout inattendu")

    monkeypatch.setattr(fmsave.Save, "tactics", broken)
    e = FmsaveSaveReader().read(SCORED)
    assert e.tactics == []
    assert any(w.startswith("tactics: ReaderCheckError") for w in e.reader_warnings)


def test_newer_reader_reimports_same_file(sync, game_dir, engine, monkeypatch):
    first = sync.sync_save(game_dir / SCORED.name)
    with engine.begin() as c:  # simule un import fait par une révision antérieure du lecteur
        c.execute(update(s.players_current).values(team_slot=None))
        c.execute(update(s.snapshots).values(reader="fmsave 0.5.10"))
    again = sync.sync_save(game_dir / SCORED.name)
    assert not again.reused and again.snapshot_id == first.snapshot_id
    with engine.connect() as c:
        slots = c.execute(select(s.players_current.c.team_slot).where(s.players_current.c.name == "Sam Sample")).scalars().all()
        assert slots == [0]
        assert c.execute(select(s.snapshots.c.reader)).scalar() == sync.reader.name
    assert sync.sync_save(game_dir / SCORED.name).reused
