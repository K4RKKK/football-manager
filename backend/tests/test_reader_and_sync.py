"""Sections 5, 6, 19.1 — lecture, normalisation, archivage, fraîcheur, isolation des carrières."""

from datetime import date, timedelta

from sqlalchemy import func, select

from clubdirector.database import schema as s
from clubdirector.database.repositories import Repository
from clubdirector.game.fmsave_reader import FmsaveSaveReader
from clubdirector.game.snapshot import Snapshot

from .conftest import PLAIN, SCORED


def fake_snapshot(src, sha: str) -> Snapshot:
    from datetime import UTC, datetime

    return Snapshot(src, src, sha, 1, 0.0, datetime.now(UTC))


def test_reader_reads_real_container_format():
    e = FmsaveSaveReader().read(SCORED)
    assert e.meta.game == "FM26"
    assert e.meta.game_date == date(2031, 3, 1)
    assert [m.club_name for m in e.managed] == ["Northbridge FC"]
    assert len(e.players) == 4
    alex = next(p for p in e.players if p.name == "Alex Example")
    assert alex.attributes["heading"] == 20 and alex.attributes["crossing"] == 1
    assert alex.natural_positions == ["DC", "DL", "DM"]
    assert alex.contract_end == date(2030, 5, 31)
    assert e.field_status["player.transfer_value"] == "verified"
    assert e.field_status["player.wage"] == "unconfirmed"  # remonté tel quel depuis fmsave
    scored = [f for f in e.fixtures if f.home_goals is not None]
    assert {(f.date, f.home_goals, f.away_goals) for f in scored} == {(date(2031, 2, 20), 3, 1), (date(2031, 2, 27), 1, 2)}
    assert e.reader_warnings == []


def test_sync_counts_and_idempotence(sync, game_dir):
    r1 = sync.sync_save(game_dir / SCORED.name)
    assert r1.counts["players"] == 4 and r1.counts["fixtures"] == 6
    assert r1.season_start_year == 2030 and r1.season_source == "calendrier_club"
    r2 = sync.sync_save(game_dir / SCORED.name)
    assert r2.reused and r2.snapshot_id == r1.snapshot_id
    with sync.engine.connect() as c:
        assert c.execute(select(func.count()).select_from(s.snapshots)).scalar() == 1
        assert c.execute(select(func.count()).select_from(s.fixtures)).scalar() == 6


def test_multiple_careers_are_isolated(sync, engine, game_dir):
    a = sync.sync_save(game_dir / SCORED.name)
    b = sync.sync_save(game_dir / PLAIN.name)
    assert a.career_id != b.career_id
    repo = Repository(engine)
    assert len(repo.list_careers()) == 2
    ctx_b = repo.context(b.career_id)
    # La carrière B (sans scores décodés) ne voit pas les scores de la carrière A.
    rows = repo.fixtures(ctx_b, played=True, limit=10)
    assert rows and all(r["home_goals"] is None for r in rows)
    with engine.connect() as c:
        per_career = dict(c.execute(select(s.players_current.c.career_id, func.count()).group_by(s.players_current.c.career_id)).all())
    assert per_career == {a.career_id: 4, b.career_id: 4}


def test_known_score_never_overwritten_by_missing_score(sync, engine, game_dir):
    first = sync.sync_save(game_dir / SCORED.name)
    e = FmsaveSaveReader().read(SCORED)
    for f in e.fixtures:
        f.home_goals = f.away_goals = None  # la sauvegarde suivante a « oublié » les scores
    sync.import_extract(e, fake_snapshot(game_dir / SCORED.name, "b" * 64))
    repo = Repository(engine)
    ctx = repo.context(first.career_id)
    m = repo.match_near(ctx, date(2031, 2, 20), 0)[0]
    assert (m["home_goals"], m["away_goals"]) == (3, 1)
    assert m["score_snapshot"] == first.snapshot_id


def test_transfer_is_reflected_at_next_sync(sync, engine, game_dir):
    """Section 5.2 : un joueur transféré n'apparaît plus dans son ancien club."""
    first = sync.sync_save(game_dir / SCORED.name)
    repo = Repository(engine)
    ctx = repo.context(first.career_id)
    assert [p["name"] for p in repo.squad(ctx)] == ["Sam Sample"]
    e = FmsaveSaveReader().read(SCORED)
    e.meta.game_date = e.meta.game_date + timedelta(days=3)
    sam = next(p for p in e.players if p.name == "Sam Sample")
    sam.club_uid, sam.club_name = 5002, "Southport Example"
    sync.import_extract(e, fake_snapshot(game_dir / SCORED.name, "c" * 64))
    ctx = repo.context(first.career_id)
    assert repo.squad(ctx) == []
    assert repo.player(ctx, sam.uid)["club_name"] == "Southport Example"
    hist = repo.player_history(ctx, sam.uid)
    assert [h["change"] for h in hist][-1] == "club_uid"
    assert hist[-1]["game_date"] == date(2031, 3, 4)


def test_previous_season_stats_are_archived(sync, engine, game_dir):
    """Section 6.3 : FM ne garde que la saison en cours ; ClubDirector archive les précédentes."""
    first = sync.sync_save(game_dir / SCORED.name)
    e = FmsaveSaveReader().read(SCORED)
    e.meta.game_date = date(2031, 9, 1)
    for f in e.fixtures:
        f.season_start_year = 2031
        f.date = f.date.replace(year=2031, month=9)
    for st in e.season_stats:
        st.goals = 0
    sync.import_extract(e, fake_snapshot(game_dir / SCORED.name, "d" * 64))
    repo = Repository(engine)
    ctx = repo.context(first.career_id)
    assert ctx.season_start_year == 2031
    assert repo.archived_seasons(ctx) == [2030, 2031]
    prev = repo.season_stats(ctx, season_start_year=2030, player_uid=900001, kind="overall")
    assert prev[0]["goals"] == 4
    cur = repo.season_stats(ctx, season_start_year=2031, player_uid=900001, kind="overall")
    assert cur[0]["goals"] == 0
