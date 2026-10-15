"""League history records (ClubDirector addition)."""

import struct

import pytest

from fmsave import LeagueHistoryRow
from fmsave._errors import ReaderCheckError
from fmsave.export import column_names
from fmsave.readers.league_history import HEAD_BYTES, SECTION_HEAD, read_league_history


def _record(
    year,
    competition_id=7,
    position=0,
    teams=20,
    played=38,
    won=20,
    drawn=9,
    lost=9,
    gf=56,
    ga=35,
    pts=69,
):
    return struct.pack(
        "<HHBBHiHBBHHHH",
        year,
        competition_id,
        position,
        teams,
        0,
        -1,
        played,
        won,
        drawn,
        lost,
        gf,
        ga,
        pts,
    )


def _section(*records: bytes) -> bytes:
    head = SECTION_HEAD + b"\x01\x00"
    assert len(head) == HEAD_BYTES
    return head + b"".join(records)


def test_records_decode_and_runs_split_where_the_year_stops_rising() -> None:
    rows = read_league_history(
        _section(
            _record(2023), _record(2024, position=4), _record(1999), _record(2000, competition_id=0)
        ),
        "example.fm",
    )
    assert [(r.run, r.season_end_year) for r in rows] == [
        (0, 2023),
        (0, 2024),
        (1, 1999),
        (1, 2000),
    ]
    assert (
        rows[1].position == 5
        and rows[1].points == 69
        and rows[1].won + rows[1].drawn + rows[1].lost == 38
    )
    assert rows[3].competition_id is None


def test_all_ones_values_are_unknown_not_numbers() -> None:
    (row,) = read_league_history(
        _section(
            _record(
                1899,
                position=0xFF,
                won=0xFF,
                drawn=0xFF,
                lost=0xFFFF,
                gf=0xFFFF,
                ga=0xFFFF,
                pts=0xFFFF,
            )
        ),
        "example.fm",
    )
    assert row.position is None and row.won is None and row.points is None and row.played == 38


@pytest.mark.parametrize(
    "section",
    [
        b"\x03\x01tad.\x01\x00" + _record(2024),
        _section(_record(2024))[:-1],
        _section(_record(1700)),
    ],
)
def test_an_unmeasured_layout_raises(section: bytes) -> None:
    with pytest.raises(ReaderCheckError):
        read_league_history(section, "example.fm")


def test_rows_export_to_flat_columns() -> None:
    assert column_names(LeagueHistoryRow)[:3] == ("run", "season_end_year", "competition_id")
