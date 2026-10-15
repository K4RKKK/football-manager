"""Miroir intégral des tables fmsave : toutes les colonnes, sans perte, par carrière."""

import fmsave
from fmsave import export
from sqlalchemy import text

from clubdirector.database.mirror import MIRRORED_READERS, MirrorTable, build_mirror_table, table_name, write_mirror

from .conftest import PLAIN, SCORED


def _columns(engine, reader):
    with engine.connect() as c:
        return [r[1] for r in c.exec_driver_sql(f'PRAGMA table_info("{table_name(reader)}")')]


def _count(engine, reader, career_id=None):
    sql = f'SELECT count(*) FROM "{table_name(reader)}"' + (" WHERE career_id = :c" if career_id else "")
    with engine.connect() as c:
        return c.execute(text(sql), {"c": career_id}).scalar()


def test_every_fmsave_column_is_mirrored(sync, engine, game_dir):
    res = sync.sync_save(game_dir / SCORED.name)
    assert set(res.mirror_counts) >= set(MIRRORED_READERS)
    for reader, record_type in MIRRORED_READERS.items():
        cols = _columns(engine, reader)
        assert cols[:2] == ["career_id", "snapshot_id"]
        assert cols[2:] == list(export.column_names(record_type)), reader
    with fmsave.open(SCORED) as save:
        expected_players = len(save.players())
        expected_stats = len(save.player_season_stats())
    assert res.mirror_counts["players"] == expected_players == _count(engine, "players")
    assert res.mirror_counts["player_season_stats"] == expected_stats


def test_mirrored_values_match_fmsave(sync, engine, game_dir):
    sync.sync_save(game_dir / SCORED.name)
    with fmsave.open(SCORED) as save:
        alex = next(p for p in save.players() if p.name == "Alex Example")
    with engine.connect() as c:
        row = c.execute(text('SELECT * FROM fm_players WHERE name = :n'), {"n": "Alex Example"}).mappings().one()
    flat = export.flatten_dict(export.record_to_dict(alex, json_ready=True))
    for col, value in flat.items():
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            assert row[col] == value, col
    assert row["birth_date"] == (alex.birth_date.isoformat() if alex.birth_date else None)


def test_resync_replaces_and_careers_stay_isolated(sync, engine, game_dir):
    a = sync.sync_save(game_dir / SCORED.name)
    b = sync.sync_save(game_dir / PLAIN.name)
    assert a.career_id != b.career_id
    before = _count(engine, "players", a.career_id)
    # relecture forcée du même fichier : remplace, ne duplique pas
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE snapshots SET reader = 'ancien'")
    sync.sync_save(game_dir / SCORED.name)
    assert _count(engine, "players", a.career_id) == before
    assert _count(engine, "players", b.career_id) > 0


def test_new_fmsave_column_is_added_not_dropped(engine):
    with engine.begin() as c:
        write_mirror(c, 1, 1, [MirrorTable("stages", ["id", "name"], [(1, "Phase A")])])
        write_mirror(c, 1, 2, [MirrorTable("stages", ["id", "name", "nouvelle_colonne"], [(1, "Phase A", 7)])])
    assert _columns(engine, "stages") == ["career_id", "snapshot_id", "id", "name", "nouvelle_colonne"]
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT nouvelle_colonne FROM fm_stages").scalar() == 7


def run(registry, tctx, tool, **args):
    return registry.execute(tool, args, tctx)


def test_query_game_table_reads_any_table(registry, tctx):
    r = run(registry, tctx, "query_game_table", table="players", name_contains="alex",
            columns=["name", "attributes_heading", "contract_wage"])
    assert r.ok, r.error
    assert r.data["total"] == 1 and r.data["lignes"][0]["name"] == "Alex Example"
    assert r.data["lignes"][0]["attributes_heading"] == 20
    desc = run(registry, tctx, "describe_game_tables")
    assert {d["table"] for d in desc.data} >= {"players", "staff", "player_season_stats", "competitions"}


def test_hidden_columns_are_refused_in_realistic_mode(registry, tctx):
    r = run(registry, tctx, "query_game_table", table="players", columns=["name", "ability_potential"])
    assert not r.ok and "masquées" in r.error
    r = run(registry, tctx, "query_game_table", table="players", filters={"attributes_consistency": 10})
    assert not r.ok
    rows = run(registry, tctx, "query_game_table", table="players", limit=5).data["lignes"]
    assert rows and not any(k.startswith(("ability", "personality_")) or k == "attributes_dirtiness" for k in rows[0])


def test_query_game_table_rejects_injection_and_unknown_tables(registry, tctx):
    assert not run(registry, tctx, "query_game_table", table="careers").ok
    r = run(registry, tctx, "query_game_table", table="players", order_by='name; DROP TABLE careers')
    assert not r.ok and "inconnues" in r.error
    r = run(registry, tctx, "query_game_table", table="players", name_contains="' OR 1=1 --")
    assert r.ok and r.data["total"] == 0


def test_unsigned_64_bit_values_are_kept_as_text(engine):
    big = 2**64 - 1
    with engine.begin() as c:
        write_mirror(c, 1, 1, [build_mirror_table("injury_types", [])])
        from clubdirector.database.mirror import _sql_value
        assert _sql_value(big) == str(big) and _sql_value(5) == 5 and _sql_value(True) == 1


def test_club_staff_comes_from_the_save(registry, tctx):
    r = run(registry, tctx, "get_club_staff", toutes_equipes=True)
    assert r.ok, r.error
    assert r.data["nombre"] == len(r.data["staff"])
    assert any("rôle" in lim for lim in r.limitations)  # le rôle n'est pas inventé


def test_top_players_on_any_current_season_stat(registry, tctx, engine):
    r = run(registry, tctx, "get_top_players_stat", stat="expected_assists", scope="tous", limit=3)
    assert r.ok, r.error
    with engine.connect() as c:
        best = c.execute(text("SELECT player_name, expected_assists FROM fm_player_season_stats "
                              "WHERE kind = 'overall' AND expected_assists IS NOT NULL "
                              "ORDER BY expected_assists DESC LIMIT 1")).first()
    if best:
        assert (r.data["classement"][0]["joueur"], r.data["classement"][0]["valeur"]) == (best[0], best[1])
    bad = run(registry, tctx, "get_top_players_stat", stat="name; DROP TABLE careers")
    assert not bad.ok
