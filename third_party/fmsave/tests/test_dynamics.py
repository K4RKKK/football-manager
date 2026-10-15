"""Squad influence lists behind the game's squad hierarchy (ClubDirector addition)."""

import struct
from datetime import date

from fmsave import SquadInfluence
from fmsave.export import column_names
from fmsave.readers.dynamics import ENTRY_SIZE, influence_tier, read_influence_runs


def _entry(person: int, influence: int, components: tuple[int, ...] | None = None) -> bytes:
    parts = components if components is not None else (influence - 600,) + (600,) + (0,) * 13
    return struct.pack("<BIII15h", 1, influence, person + 1, 15, *parts)


def _day(d: date, high: int = 9) -> bytes:
    return struct.pack("<HH", d.timetuple().tm_yday | (high << 9), d.year)


def _run(day: date, *entries: tuple[int, int]) -> bytes:
    return b"".join(_entry(p, i) for p, i in entries) + _day(day) + b"\x01\x01"


def test_runs_are_found_by_their_shape_with_their_day() -> None:
    first = _run(date(2025, 10, 26), (10, 12_557), (11, 8_999), (12, 5_911), (13, 7_152))
    older = _run(date(2025, 10, 1), (10, 12_692), (11, 8_999), (12, 5_817))
    noise = b"\x01" + b"\x00" * 60  # a lone flag byte is no entry
    game_db = b"\xaa" * 100 + first + noise + struct.pack("<I", 3) + older + b"\xbb" * 50
    runs = read_influence_runs(game_db, person_limit=1_000)
    assert [r.start for r in runs] == [100, 100 + len(first) + len(noise) + 4]
    assert runs[0].as_of == date(2025, 10, 26) and runs[1].as_of == date(2025, 10, 1)
    assert runs[0].entries == ((10, 12_557), (11, 8_999), (12, 5_911), (13, 7_152))
    assert len(first) == 4 * ENTRY_SIZE + 6


def test_shapes_that_only_look_like_entries_are_left_out() -> None:
    no_day = b"".join(_entry(p, 7_000) for p in (1, 2, 3)) + b"\xff\xff\xff\xff"
    unknown_person = _run(date(2025, 10, 26), (1, 7_000), (5_000, 7_000), (3, 7_000))
    too_short = _run(date(2025, 10, 26), (1, 7_000), (2, 7_000))
    wild = b"".join(_entry(p, 7_000, (30_000,) + (0,) * 14) for p in (1, 2, 3)) + _day(date(2025, 10, 26))
    for game_db in (no_day, unknown_person, too_short, wild):
        assert read_influence_runs(b"\x00" * 8 + game_db, person_limit=1_000) == []


def test_influence_bands_follow_the_hierarchy_screen() -> None:
    assert [influence_tier(i) for i in (13_633, 9_000, 8_999, 7_500, 7_392, 6_000, 5_999, 0)] == [
        "leader", "leader", "highly_influential", "highly_influential", "influential", "influential", "other", "other",
    ]


def test_records_export_every_field() -> None:
    assert {"as_of", "latest", "club_uid", "team_slot", "rank", "player_uid", "influence", "tier"} <= set(
        column_names(SquadInfluence)
    )


def test_a_save_without_lists_reads_an_empty_table(career_save_path) -> None:
    import fmsave

    with fmsave.open(career_save_path) as save:
        assert list(save.squad_influence()) == []
