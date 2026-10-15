"""Decode the squad influence lists behind the game's squad hierarchy (ClubDirector addition).

Measured on the user's FM26 26.3.0 save: near the end of `game_db`, for each team of the managed
club, runs of 43-byte entries

    u8 1 | u32 influence | u32 person index + 1 | u32 15 | 15 × i16 components

each run followed by the day it was worked out (u16 day of year in its low nine bits, u16 year).
A team has several runs: the latest one and older ones, kept from earlier dates. The influence
is the game's own total of the components: their sum, scaled down for some young players
(0.8 × the sum) and held at 8 999 for every player but the team leaders. On the latest run of
Roma's first team, the four bands of the influence (9 000 and above, 7 500, 6 000, below) gave
the colours of the game's hierarchy screen for all 23 players listed (leaders, highly
influential, influential, others). The five Roma players the screen showed and the run left out were
loaned out to other clubs, and "others" in the game.

The runs are found by their shape, not by a pointer: a run is three or more consecutive
entries, all naming a person, followed by a valid day. The byte after the day is not read: it
is not the same kind of field after every run.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from datetime import date, timedelta

ENTRY_SIZE = 43
COMPONENT_COUNT = 15
_ENTRY = struct.Struct("<BIII15h")
_DATE = struct.Struct("<HH")
_ENTRY_PATTERN = rb"\x01.{8}\x0f\x00\x00\x00.{30}"
_RUN_START = re.compile(_ENTRY_PATTERN * 3, re.DOTALL)
_MIN_COMPONENT, _MAX_COMPONENT = -5_000, 20_000
_MAX_INFLUENCE = 50_000
_EARLIEST_YEAR, _LATEST_YEAR = 1990, 2300

# Bands of the influence, highest first, as the game's hierarchy screen showed them (unconfirmed:
# measured on one save).
LEADER_INFLUENCE = 9_000
HIGHLY_INFLUENTIAL_INFLUENCE = 7_500
INFLUENTIAL_INFLUENCE = 6_000


@dataclass(frozen=True, slots=True)
class RawInfluenceRun:
    """One run of influence entries, in stored order, before its people are resolved."""

    start: int
    as_of: date | None
    entries: tuple[tuple[int, int], ...]  # (person index, influence)


def influence_tier(influence: int) -> str:
    """The hierarchy band of an influence: "leader", "highly_influential", "influential" or "other"."""
    if influence >= LEADER_INFLUENCE:
        return "leader"
    if influence >= HIGHLY_INFLUENTIAL_INFLUENCE:
        return "highly_influential"
    if influence >= INFLUENTIAL_INFLUENCE:
        return "influential"
    return "other"


def _day(buf: bytes, at: int) -> date | None:
    if at + _DATE.size > len(buf):
        return None
    low, year = _DATE.unpack_from(buf, at)
    day = low & 0x1FF
    if not _EARLIEST_YEAR <= year <= _LATEST_YEAR or not 1 <= day <= 366:
        return None
    found = date(year, 1, 1) + timedelta(days=day - 1)
    return found if found.year == year else None


def _entry(buf: bytes, at: int, person_limit: int) -> tuple[int, int] | None:
    """(person index, influence) of the entry at `at`, or None when no entry is there."""
    if at + ENTRY_SIZE > len(buf):
        return None
    flag, influence, person, count, *components = _ENTRY.unpack_from(buf, at)
    if flag != 1 or count != COMPONENT_COUNT or not 1 <= person <= person_limit:
        return None
    if not 0 <= influence <= _MAX_INFLUENCE:
        return None
    if not all(_MIN_COMPONENT <= value <= _MAX_COMPONENT for value in components):
        return None
    return person - 1, influence


def read_influence_runs(game_db: bytes, person_limit: int) -> list[RawInfluenceRun]:
    """Every run of influence entries in `game_db`, in stored order.

    `person_limit` is the number of person indexes the save holds: an entry naming a person
    past it is not an entry. Runs that are not followed by a valid day are left out, and so are
    shapes that only look like entries (a component or an influence out of range).
    """
    runs: list[RawInfluenceRun] = []
    search_from = 0
    while True:
        match = _RUN_START.search(game_db, search_from)
        if match is None:
            return runs
        at = match.start()
        entries: list[tuple[int, int]] = []
        while (found := _entry(game_db, at, person_limit)) is not None:
            entries.append(found)
            at += ENTRY_SIZE
        if len(entries) >= 3:
            as_of = _day(game_db, at)
            if as_of is not None:
                runs.append(RawInfluenceRun(start=match.start(), as_of=as_of, entries=tuple(entries)))
            search_from = at
        else:
            search_from = match.start() + 1
