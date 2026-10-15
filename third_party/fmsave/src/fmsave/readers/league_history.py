"""Decode `tc_league_history_dt` (ClubDirector addition).

Layout measured on the user's own saves (FM26 26.3.0): an 8-byte section head, then 24-byte
records. Checked against the game's real-world history for two clubs over two seasons (final
position, wins, draws, losses, goals and points all equal), and arithmetically on every record
whose values are known (won + drawn + lost = played).

    u16 season end year | u16 competition id | u8 position (0-based) | u8 team count
    | u16 unknown | i32 unknown | u16 played | u8 won | u8 drawn | u16 lost
    | u16 goals for | u16 goals against | u16 points

All-ones values (0xFF, 0xFFFF) mean "unknown" and come back as None.
"""

from __future__ import annotations

import struct

from fmsave._errors import ReaderCheckError
from fmsave.models.league_history import LeagueHistoryRow

LEAGUE_HISTORY_SECTION = "tc_league_history_dt"
SECTION_HEAD = b"\x03\x01tmc."
HEAD_BYTES = 8
RECORD = struct.Struct("<HHBBHiHBBHHHH")
FIRST_YEAR, LAST_YEAR = 1850, 2200


def _known(value: int, all_ones: int) -> int | None:
    return None if value == all_ones else value


def read_league_history(section: bytes, file_name: str) -> list[LeagueHistoryRow]:
    """Every record of the section, with its run index.

    Raises:
        ReaderCheckError: The section head is not the one measured, its body is not a whole
            number of records, or a season year falls outside the game's calendar.
    """
    if not section.startswith(SECTION_HEAD) or (len(section) - HEAD_BYTES) % RECORD.size:
        raise ReaderCheckError(
            f"{file_name}: section '{LEAGUE_HISTORY_SECTION}' does not have the measured layout"
        )
    rows: list[LeagueHistoryRow] = []
    run = -1
    previous_year = None
    for (
        year,
        competition_id,
        position,
        team_count,
        unknown_6,
        unknown_8,
        played,
        won,
        drawn,
        lost,
        goals_for,
        goals_against,
        points,
    ) in RECORD.iter_unpack(section[HEAD_BYTES:]):
        if not FIRST_YEAR <= year <= LAST_YEAR:
            raise ReaderCheckError(
                f"{file_name}: section '{LEAGUE_HISTORY_SECTION}' holds a season year outside "
                "the game's calendar"
            )
        if previous_year is None or year <= previous_year:
            run += 1
        previous_year = year
        rows.append(
            LeagueHistoryRow(
                run=run,
                season_end_year=year,
                competition_id=competition_id or None,
                position=None if position == 0xFF else position + 1,
                team_count=_known(team_count, 0xFF),
                played=_known(played, 0xFFFF),
                won=_known(won, 0xFF),
                drawn=_known(drawn, 0xFF),
                lost=_known(lost, 0xFFFF),
                goals_for=_known(goals_for, 0xFFFF),
                goals_against=_known(goals_against, 0xFFFF),
                points=_known(points, 0xFFFF),
                unknown_6=unknown_6,
                unknown_8=unknown_8,
            )
        )
    return rows
