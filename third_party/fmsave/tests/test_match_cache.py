"""Independent byte fixtures for the owned nullable cache field walk."""

from __future__ import annotations

import dataclasses
import struct
from datetime import date

import pytest

from fmsave.readers.match_cache import CacheDeclarations, MatchCacheWalker
from fmsave.readers.matches import (
    LocatedMatchRecords,
    build_player_match_stats,
    find_match_record_layout,
    locate_match_records,
)
from tests.fixtures.game_db import match_list_bytes, match_record_bytes
from tests.test_player_match_stats import (
    EXAMPLE_CLUB_INDEX,
    EXAMPLE_STAGE_INDEX,
    NO_PLAYERS,
    synthetic_player_records,
)

ABILITY = 30
NULL_DATE = b"\x01\x00\x6c\x07"
VALID_DATE = struct.pack("<HH", 100, 2026)
LAYOUT = find_match_record_layout(4000, "")
assert LAYOUT.cache_layout is not None
WALKER = MatchCacheWalker(LAYOUT.cache_layout)


def prefix(
    *, text: str = "", tagged: bytes = b"\x00", fixed: bytes = b"\x00", attributes: bool = True
) -> bytes:
    encoded = text.encode("utf-8")
    return (
        bytes(159)
        + struct.pack("<I", 3)
        + b"\x0b\x07\x04"
        + b"\x93\x42\x17\x08\x09\x07"
        + bytes(9)
        + fixed
        + tagged
        + struct.pack("<IHH", 2, 42, 65535)
        + b"\x00\x00\x00"
        + b"\x02"
        + b"\x7b" * 31
        + NULL_DATE
        + b"\x00"
        + VALID_DATE
        + NULL_DATE
        + struct.pack("<I", len(encoded))
        + encoded
        + b"\x19" * 12
        + (b"\x01" + b"\x81" * 30 if attributes else b"\x00")
    )


def predecessor(
    *,
    children: bytes = b"",
    child_count: int = 0,
    medical: bytes = b"\x00",
    suffix: bytes = bytes(5),
) -> bytes:
    return b"\x01" + medical + bytes([child_count]) + children + suffix


def tagged(kind: int, payload: bytes) -> bytes:
    return (
        b"\x01\x01" + struct.pack("<I", 1) + b"\x05\x9c" + VALID_DATE + bytes([1, kind]) + payload
    )


def child(kind: int, width: int, *, attached: bool = False) -> bytes:
    core = bytearray(b"\xff" * width)
    core[9:13] = VALID_DATE
    core[13:15] = bytes([5, kind])
    if not attached:
        return bytes(core) + b"\xff\x00"
    tail = bytearray(b"\x73" * 28)
    tail[:3] = b"\x03\x01\x01"
    tail[3:7] = VALID_DATE
    tail[11] = 3  # This raw byte is not constrained to the earlier default value.
    tail[12] = tail[17] = 0
    return bytes(core + tail)


def medical_row(optional: bool) -> bytes:
    core = bytearray(b"\x78" * (34 + 26 * optional))
    core[0] = 2
    core[3] = int(optional)
    if optional:
        core[4] = 1
        core[5:9] = VALID_DATE
    core[4 + 26 * optional : 8 + 26 * optional] = VALID_DATE
    return bytes(core)


@pytest.mark.parametrize(
    "declaration,state",
    [
        (b"\x00", "containing_null"),
        (predecessor() + b"\x00", "null"),
        (predecessor() + b"\x01\x00", "empty"),
        (predecessor() + b"\x01\x03", "nonempty"),
    ],
)
@pytest.mark.parametrize("attributes", [False, True])
def test_owned_nullable_declarations(declaration: bytes, state: str, attributes: bool) -> None:
    data = prefix(text="Mandić", attributes=attributes) + declaration
    result = WALKER.locate(data, ABILITY, len(data))
    assert result.state == state
    assert result.offset == (
        None
        if state == "containing_null"
        else len(data) - (2 if state in ("empty", "nonempty") else 1)
    )


@pytest.mark.parametrize(
    "kind,payload",
    [
        (0, b""),
        (17, b"\x7b"),
        (24, b"\x93" * 8),
        (11, struct.pack("<I", 2) + b"\x01\x02\x39\x31\x00\x00" * 2),
        (10, bytes.fromhex("01000000746a626f010a01000000666572640101") + b"\x87\x65\x43\x21"),
    ],
)
def test_counted_typed_value_branches(kind: int, payload: bytes) -> None:
    row = bytearray(24)
    row[:2] = b"\x04\x05"
    row[4:8] = VALID_DATE
    row[20:24] = NULL_DATE
    data = (
        prefix(tagged=tagged(kind, payload), fixed=b"\x01\x02\x02" + bytes(row) * 2)
        + predecessor()
        + b"\x00"
    )
    assert WALKER.locate(data, ABILITY, len(data)).state == "null"


@pytest.mark.parametrize("kind,width", [(1, 18), (15, 17), (20, 20), (34, 21), (40, 21)])
@pytest.mark.parametrize("attached", [False, True])
def test_complete_variable_counted_children(kind: int, width: int, attached: bool) -> None:
    data = (
        prefix()
        + predecessor(children=child(kind, width, attached=attached) + child(15, 17), child_count=2)
        + b"\x00"
    )
    assert WALKER.locate(data, ABILITY, len(data)).state == "null"


def test_counted_schema02_multiple_variable_rows_and_full_nullable_suffix() -> None:
    suffix = bytearray(b"\x01\x03" + b"\x9a" * 42)
    suffix[39:43] = VALID_DATE
    suffix[43] = 0
    suffix += b"\x01\x05" + b"\x23" * 58
    third = bytearray(b"\x01\x04" + b"\x67" * 68)
    third[26:30] = VALID_DATE
    third[30:34] = NULL_DATE
    suffix += third + b"\x01\x01" + b"\x44" * 8 + VALID_DATE
    suffix += b"\x01\x01" + b"\x84" * 12 + VALID_DATE
    medical = b"\x02" + medical_row(True) + medical_row(False)
    data = prefix() + predecessor(medical=medical, suffix=bytes(suffix)) + b"\x01\x00"
    assert WALKER.locate(data, ABILITY, len(data)).state == "empty"
    medical_at = len(prefix()) + 1
    second_at = medical_at + 1 + 60
    for changed in (
        data[:second_at] + b"\x03" + data[second_at + 1 :],
        data[:medical_at] + b"\x03" + data[medical_at + 1 :],
        data[: second_at + 5],
    ):
        assert WALKER.locate(changed, ABILITY, len(changed)).state == "unknown"


def test_malformed_prefix_and_owner_bounds_remain_unknown() -> None:
    data = prefix(text="Enzo") + predecessor() + b"\x00"
    for end in range(ABILITY, len(data)):
        assert WALKER.locate(data, ABILITY, end).state == "unknown"
    for changed in (
        data[:159] + b"\xff" * 4 + data[163:],
        data[:170] + b"\x08" + data[171:],
        prefix(tagged=tagged(255, b"")) + b"\x00",
        prefix(tagged=tagged(10, b"\x00" * 24)) + b"\x00",
        prefix(tagged=tagged(17, b"")),
    ):
        assert WALKER.locate(changed, ABILITY, len(changed)).state == "unknown"
    bad = bytearray(data)
    text_at = data.index(b"Enzo")
    bad[text_at] = 255
    assert WALKER.locate(bytes(bad), ABILITY, len(bad)).state == "unknown"
    assert WALKER.locate(data, -1, len(data)).state == "unknown"
    assert WALKER.locate(data, ABILITY, len(data) + 1).state == "unknown"


def test_corrupt_counted_children_and_unknown_type_do_not_declare_empty() -> None:
    first = child(20, 20)
    second = child(1, 18)
    for bad in (
        second[:13] + b"\x00" + second[14:],
        second[:9] + bytes(4) + second[13:],
        child(255, 20),
        second[:-1],
    ):
        data = prefix() + predecessor(children=first + bad, child_count=2) + b"\x00"
        assert WALKER.locate(data, ABILITY, len(data)).state == "unknown"


def test_empty_parent_rejects_a_complete_undeclared_child_only() -> None:
    header = prefix() + predecessor() + b"\x01\x00"
    record = match_record_bytes(
        day_of_year=100, year=2026, opponent_team_id=100, competition_id=12, played=False
    )
    extra = match_list_bytes(record, team_id=100)[2:]
    for tail, expected in (
        (extra, "unknown"),
        (extra[:-1], "empty"),
        (b"\x14\x01", "empty"),
        (b"", "empty"),
    ):
        data = header + tail
        located = locate_match_records(
            data, synthetic_player_records((ABILITY,)), LAYOUT, date(2026, 5, 1)
        )
        declarations = located.history_declarations
        assert declarations is not None
        assert getattr(declarations, expected) == 1


def test_unsupported_layout_does_not_supply_absence_metadata() -> None:
    data = prefix() + b"\x00"
    located = locate_match_records(
        data,
        synthetic_player_records((ABILITY,)),
        dataclasses.replace(LAYOUT, cache_layout=None),
        date(2026, 5, 1),
    )
    assert located.history_declarations is None


def test_population_mismatch_cannot_forward_absence_metadata() -> None:
    players = synthetic_player_records((ABILITY,))
    located = LocatedMatchRecords(
        {}, lists_found=0, lists_decoded=0, history_declarations=CacheDeclarations(2, 2, 0, 0, 0, 0)
    )
    rows, stats = build_player_match_stats(
        located, players, NO_PLAYERS, EXAMPLE_CLUB_INDEX, EXAMPLE_STAGE_INDEX, LAYOUT
    )
    assert rows == ()
    assert stats.history_slots is None
    assert stats.history_containing_null is None
    assert stats.history_unknown is None


def test_actual_positive_declaration_survives_filtered_zero_output() -> None:
    record = match_record_bytes(
        day_of_year=100, year=2026, opponent_team_id=100, competition_id=12, played=False
    )
    data = prefix() + predecessor() + match_list_bytes(record, team_id=100)
    players = synthetic_player_records((ABILITY,))
    located = locate_match_records(data, players, LAYOUT, date(2040, 1, 1))
    rows, stats = build_player_match_stats(
        located, players, NO_PLAYERS, EXAMPLE_CLUB_INDEX, EXAMPLE_STAGE_INDEX, LAYOUT
    )
    assert rows == ()
    assert stats.records == 0
    assert stats.lists_found == stats.lists_decoded == 1
    assert stats.history_slots == stats.history_nonempty == 1
    assert stats.history_null == stats.history_empty == stats.history_unknown == 0
