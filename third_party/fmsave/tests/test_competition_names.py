"""Competition names found in the save's own sections (ClubDirector addition)."""

import struct

from fmsave.readers.competition_names import find_competition_names


def _named(database_id: int, long_name: str, short_name: str, nation_id: int = 7) -> bytes:
    def text(value: str) -> bytes:
        raw = value.encode("utf-8")
        return struct.pack("<I", len(raw)) + raw

    return (
        struct.pack("<III", database_id, nation_id, 0x308)
        + b"\x03"
        + struct.pack("<I", 0)
        + text(long_name)
        + text(short_name)
    )


def test_names_are_read_by_database_id() -> None:
    section = b"\xff" * 9 + _named(9001, "Example League", "Example Lg") + b"\x02" + bytes(16)
    other = _named(9002, "Example Cup Ñ", "Cup") + _named(9001, "Example League", "Example Lg")
    names = find_competition_names([section, other], [9001, 9002])
    assert names == {9001: ("Example League", "Example Lg"), 9002: ("Example Cup Ñ", "Cup")}


def test_unknown_ids_and_contradictions_are_dropped() -> None:
    section = (
        _named(9001, "Example League", "Example Lg")
        + _named(9001, "Another League", "Another")
        + _named(9003, "Unlisted League", "Unlisted")
    )
    assert find_competition_names([section], [9001, 9002]) == {}


def test_a_non_zero_word_before_the_names_is_not_a_competition() -> None:
    record = bytearray(_named(9001, "Example League", "Example Lg"))
    record[13:17] = struct.pack("<I", 5)
    assert find_competition_names([bytes(record)], [9001]) == {}
