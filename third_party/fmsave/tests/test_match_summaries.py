from __future__ import annotations

import dataclasses
import struct
from datetime import date

import pytest

from fmsave._layouts import MatchSummaryLayout
from fmsave.readers.match_summaries import find_match_summary_layout, locate_match_summary_scores

LAYOUT = find_match_summary_layout(4000, "26.3.2+2329565")
DAY = date(2026, 4, 12)
KEY = (DAY, 812, 901, 902)


def packed_day(day: date) -> bytes:
    return struct.pack("<HH", day.timetuple().tm_yday, day.year)


def summary_bytes(
    scores: tuple[tuple[int, int], ...] = ((2, 1),),
    *,
    layout: MatchSummaryLayout = LAYOUT,
    tail_date: bytes | None = None,
    fixture_key: tuple[date, int, int, int] = KEY,
) -> bytes:
    """A fictional complete object, including both trailing reference collections."""
    header = bytearray(layout.header_bytes)
    struct.pack_into("<I", header, 0, 123)
    for offset in (layout.uid_offset, layout.uid_copy_offset):
        struct.pack_into("<I", header, offset, 1_234_567)
    header[layout.kind_offset] = layout.kind_value
    for offset in layout.ability_offsets:
        struct.pack_into("<H", header, offset, 140)
    header[layout.attributes_offset : layout.attributes_offset + layout.attributes_count] = (
        bytes([12]) * layout.attributes_count
    )
    header[layout.count_offset] = len(scores)
    body = bytearray()
    for home_score, away_score in scores:
        row = bytearray(layout.record_bytes)
        row[layout.lead_byte_offset] = layout.lead_byte_value
        row[layout.date_offset : layout.date_offset + 4] = packed_day(fixture_key[0])
        struct.pack_into("<I", row, layout.competition_id_offset, fixture_key[1])
        struct.pack_into("<I", row, layout.home_team_id_offset, fixture_key[2])
        struct.pack_into("<I", row, layout.away_team_id_offset, fixture_key[3])
        row[layout.home_goals_offset] = home_score
        row[layout.away_goals_offset] = away_score
        body.extend(row)
    tail = struct.pack("<III", 2, 111, 222) + struct.pack("<II", 1, 333)
    return (
        bytes(header + body) + tail + (layout.null_date_bytes if tail_date is None else tail_date)
    )


@pytest.mark.parametrize("count", [0, 1, 4, 10, 255])
def test_complete_counts_include_empty_and_the_full_byte_range(count: int) -> None:
    result = locate_match_summary_scores(summary_bytes(((2, 1),) * count), LAYOUT)
    assert (result.lists_found, result.lists_decoded, result.record_count) == (1, 1, count)
    assert result.scores == ({KEY: (2, 1)} if count else {})


def test_tail_accepts_a_real_date_as_well_as_the_registered_null() -> None:
    result = locate_match_summary_scores(
        summary_bytes(tail_date=packed_day(date(2025, 12, 22))), LAYOUT
    )
    assert result.scores == {KEY: (2, 1)}


def test_every_truncated_header_row_collection_and_date_is_rejected() -> None:
    complete = summary_bytes()
    for end in range(len(complete)):
        result = locate_match_summary_scores(complete[:end], LAYOUT)
        assert result.lists_decoded == 0
        assert not result.scores


@pytest.mark.parametrize("offset,value", [(8, 99), (17, 1), (21, 201), (27, 0), (34, 3)])
def test_header_identity_sentinel_and_declared_fields_must_agree(offset: int, value: int) -> None:
    db = bytearray(summary_bytes())
    db[offset] = value
    assert not locate_match_summary_scores(bytes(db), LAYOUT).scores


@pytest.mark.parametrize("field", ["lead_byte_offset", "date_offset"])
def test_a_broken_declared_row_rejects_the_entire_collection(field: str) -> None:
    db = bytearray(summary_bytes(((2, 1), (2, 1))))
    at = LAYOUT.header_bytes + LAYOUT.record_bytes + getattr(LAYOUT, field)
    db[at : at + (1 if field == "lead_byte_offset" else 4)] = b"\x00" * (
        1 if field == "lead_byte_offset" else 4
    )
    result = locate_match_summary_scores(bytes(db), LAYOUT)
    assert (result.lists_found, result.lists_decoded, result.record_count) == (1, 0, 0)
    assert not result.scores


@pytest.mark.parametrize("tail_array", [0, 1])
def test_an_inflated_trailing_array_count_cannot_escape_the_buffer(tail_array: int) -> None:
    db = bytearray(summary_bytes())
    start = LAYOUT.header_bytes + LAYOUT.record_bytes + (0 if tail_array == 0 else 12)
    struct.pack_into("<I", db, start, 0xFFFFFFFF)
    assert not locate_match_summary_scores(bytes(db), LAYOUT).scores


def test_a_different_invalid_date_is_not_treated_as_the_null_sentinel() -> None:
    result = locate_match_summary_scores(summary_bytes(tail_date=b"\x00" * 4), LAYOUT)
    assert result.lists_decoded == 0


@pytest.mark.parametrize(
    "scores", [((2, 1), (3, 1), (2, 1)), ((41, 1), (2, 1)), ((2, 1), (255, 1), (2, 1))]
)
def test_a_conflict_or_invalid_score_permanently_blocks_the_exact_key(
    scores: tuple[tuple[int, int], ...],
) -> None:
    result = locate_match_summary_scores(summary_bytes(scores), LAYOUT)
    assert result.scores == {KEY: None}
    assert result.record_count == len(scores)
    assert result.lists_decoded == 1
    assert result.invalid_score_records == sum(max(pair) > 40 for pair in scores)


def test_an_incomplete_object_cannot_poison_a_later_complete_one() -> None:
    broken = bytearray(summary_bytes(((3, 1),)))
    broken[LAYOUT.count_offset] = 2
    result = locate_match_summary_scores(bytes(broken) + summary_bytes(), LAYOUT)
    assert result.scores == {KEY: (2, 1)}
    assert (result.lists_found, result.lists_decoded, result.record_count) == (2, 1, 1)


def test_unidentified_header_word_does_not_inherit_reputation_bounds() -> None:
    db = bytearray(summary_bytes())
    struct.pack_into("<H", db, 25, 65_535)
    assert locate_match_summary_scores(bytes(db), LAYOUT).scores == {KEY: (2, 1)}


def test_zero_ability_like_words_still_frame_the_collection() -> None:
    db = bytearray(summary_bytes())
    for offset in LAYOUT.ability_offsets:
        struct.pack_into("<H", db, offset, 0)
    assert locate_match_summary_scores(bytes(db), LAYOUT).scores == {KEY: (2, 1)}


@pytest.mark.parametrize(
    "field", ["competition_id_offset", "home_team_id_offset", "away_team_id_offset"]
)
def test_nonjoining_references_do_not_discard_valid_sibling_rows(field: str) -> None:
    db = bytearray(summary_bytes(((2, 1), (3, 1))))
    struct.pack_into(
        "<I", db, LAYOUT.header_bytes + LAYOUT.record_bytes + getattr(LAYOUT, field), 0xFFFFFFFF
    )
    result = locate_match_summary_scores(bytes(db), LAYOUT)
    assert result.record_count == 2
    assert result.lists_decoded == 1
    assert result.scores[KEY] == (2, 1)


def test_record_and_header_offsets_come_from_the_registered_layout() -> None:
    shifted = dataclasses.replace(
        LAYOUT,
        header_bytes=LAYOUT.header_bytes + 5,
        **{
            name: getattr(LAYOUT, name) + 5
            for name in (
                "uid_offset",
                "uid_copy_offset",
                "kind_offset",
                "header_word_offset",
                "attributes_offset",
                "count_offset",
            )
        },
        ability_offsets=tuple(x + 5 for x in LAYOUT.ability_offsets),
        flag_offsets=tuple(x + 5 for x in LAYOUT.flag_offsets),
        record_bytes=LAYOUT.record_bytes + 3,
        **{
            name: getattr(LAYOUT, name) + 3
            for name in (
                "lead_byte_offset",
                "date_offset",
                "competition_id_offset",
                "home_goals_offset",
                "away_goals_offset",
                "home_team_id_offset",
                "away_team_id_offset",
            )
        },
        kind_value=7,
        lead_byte_value=3,
    )
    assert locate_match_summary_scores(summary_bytes(layout=shifted), shifted).scores == {
        KEY: (2, 1)
    }
