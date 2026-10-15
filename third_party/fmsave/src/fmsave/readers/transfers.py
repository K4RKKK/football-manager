"""Decode `transfer_man` and `shortlist_man` (ClubDirector addition).

`transfer_man` (measured on the user's FM26 26.3.0 save): an 9-byte head, a u32 record count,
then that many variable-length records, numbered 0, 1, 2… Each record starts with

    u8 kind | 13 00 | u32 person index + 1 | u8 0/1 | u32 team | u8 0/1 | u32 team | u32 amount
    | u32 record number | u32 deal id | u8 state | …

and keeps, at fixed offsets from its start, the offer's dates (u16 day of year in its low nine
bits, u16 year; year 1900 = no date) and the team the player belonged to (+69). The fields were
checked against the user's career: Roma's signings (players, clubs, fees and joining days), its
loans out (the owning club equals the loan's parent club on 505 of 532 completed loans), and on
every completed transfer the player now belongs to the bidding club (1 855 of 1 857). The length
of a record is not stored: the next record is the next start whose number follows.

`shortlist_man`: an 8-byte head, then 30 rankings, each a u32 count and that many
(u32 person index + 1, u32 score) pairs, best first: the 14 positions in the game's order and
the young talents, for men then for women. Checked by the positions of each ranking's players
(the goalkeepers' ranking holds only goalkeepers, and so on) and its order.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import date, timedelta

from fmsave._errors import ReaderCheckError

TRANSFER_SECTION = "transfer_man"
SHORTLIST_SECTION = "shortlist_man"
SECTION_HEAD = b"\x03\x01tad."
TRANSFER_COUNT_AT = 9
SHORTLIST_TABLES_AT = 8
RECORD_MARK = b"\x13\x00"
MAX_RECORD_BYTES = 4_000
NONE32 = 0xFFFFFFFF
NO_DATE_YEAR = 1900
KINDS = {2: "transfer", 3: "loan", 10: "squad_move"}
STATUSES = {0x14: "completed", 0x0F: "failed"}
POSITIONS = ("GK", "DR", "DL", "DC", "WBR", "WBL", "DM", "MR", "ML", "MC", "AMR", "AML", "AMC", "ST", "young")
RANKING_TABLES = 2 * len(POSITIONS)
_U32 = struct.Struct("<I")
_DATE = struct.Struct("<HH")
_PAIR = struct.Struct("<II")
_MIN_RECORD = 84


@dataclass(frozen=True, slots=True)
class RawTransferOffer:
    """A `transfer_man` record before its people and teams are resolved."""

    index: int
    deal_id: int
    kind_code: int
    status_code: int
    person_index: int | None
    bidding_team_id: int | None
    second_team_id: int | None
    selling_team_id: int | None
    amount: int
    offered_on: date | None
    effective_on: date | None
    deadline: date | None
    updated_on: date | None


@dataclass(frozen=True, slots=True)
class RawPlayerRanking:
    table: int
    rank: int
    person_index: int
    score: int


def _date(buf: bytes, at: int) -> date | None:
    day, year = _DATE.unpack_from(buf, at)
    day &= 0x1FF
    if year == NO_DATE_YEAR or not 1 <= day <= 366 or not 1900 < year < 2300:
        return None
    return date(year, 1, 1) + timedelta(days=day - 1)


def _id(value: int) -> int | None:
    return None if value == NONE32 else value


def _record_start(section: bytes, start: int, number: int) -> int | None:
    limit = min(len(section) - _MIN_RECORD, start + MAX_RECORD_BYTES)
    at = start
    while at <= limit:
        mark = section.find(RECORD_MARK, at + 1, limit + 3)
        if mark < 0:
            return None
        begin = mark - 1
        if (
            _U32.unpack_from(section, begin + 21)[0] == number
            and section[begin + 7] in (0, 1)
            and section[begin + 12] in (0, 1)
        ):
            return begin
        at = mark
    return None


def read_transfer_offers(section: bytes, file_name: str) -> list[RawTransferOffer]:
    """Every record of `transfer_man`, in stored order.

    Raises:
        ReaderCheckError: The head is not the one measured, or a record numbered below the
            stored count cannot be found where the previous one ends.
    """
    if not section.startswith(SECTION_HEAD) or len(section) < TRANSFER_COUNT_AT + 4:
        raise ReaderCheckError(f"{file_name}: section '{TRANSFER_SECTION}' does not have the measured layout")
    (count,) = _U32.unpack_from(section, TRANSFER_COUNT_AT)
    rows: list[RawTransferOffer] = []
    at = TRANSFER_COUNT_AT + 4 - 1
    for number in range(count):
        begin = _record_start(section, at, number)
        if begin is None:
            raise ReaderCheckError(
                f"{file_name}: record {number} of {count} of section '{TRANSFER_SECTION}' was not found"
            )
        person = _id(_U32.unpack_from(section, begin + 3)[0])
        rows.append(RawTransferOffer(
            index=number,
            deal_id=_U32.unpack_from(section, begin + 25)[0],
            kind_code=section[begin],
            status_code=section[begin + 29],
            person_index=None if person is None else person - 1,
            bidding_team_id=_id(_U32.unpack_from(section, begin + 8)[0]),
            second_team_id=_id(_U32.unpack_from(section, begin + 13)[0]),
            selling_team_id=_id(_U32.unpack_from(section, begin + 69)[0]),
            amount=_U32.unpack_from(section, begin + 17)[0],
            offered_on=_date(section, begin + 75),
            effective_on=_date(section, begin + 60),
            deadline=_date(section, begin + 56),
            updated_on=_date(section, begin + 80),
        ))
        at = begin + 29
    return rows


def read_player_rankings(section: bytes, file_name: str) -> list[RawPlayerRanking]:
    """Every entry of the 30 rankings of `shortlist_man`, best first within each ranking.

    Raises:
        ReaderCheckError: The head is not the one measured, a ranking runs past the section, or
            its scores are not in descending order.
    """
    if not section.startswith(SECTION_HEAD):
        raise ReaderCheckError(f"{file_name}: section '{SHORTLIST_SECTION}' does not have the measured layout")
    rows: list[RawPlayerRanking] = []
    at = SHORTLIST_TABLES_AT
    for table in range(RANKING_TABLES):
        if at + 4 > len(section):
            raise ReaderCheckError(f"{file_name}: ranking {table} of section '{SHORTLIST_SECTION}' is missing")
        (count,) = _U32.unpack_from(section, at)
        end = at + 4 + count * _PAIR.size
        if count == 0 or end > len(section):
            raise ReaderCheckError(f"{file_name}: ranking {table} of section '{SHORTLIST_SECTION}' runs past the section")
        previous = None
        for rank, (person, score) in enumerate(_PAIR.iter_unpack(section[at + 4:end]), start=1):
            if previous is not None and score > previous:
                raise ReaderCheckError(
                    f"{file_name}: ranking {table} of section '{SHORTLIST_SECTION}' is not in descending order"
                )
            previous = score
            rows.append(RawPlayerRanking(table, rank, person - 1, score))
        at = end
    return rows
