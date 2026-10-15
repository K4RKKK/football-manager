"""Transfer offers and player rankings (ClubDirector addition)."""

import struct
from datetime import date

import pytest

from fmsave import PlayerRanking, TransferOffer
from fmsave._errors import ReaderCheckError
from fmsave.export import column_names
from fmsave.readers.transfers import (
    POSITIONS,
    SECTION_HEAD,
    read_player_rankings,
    read_transfer_offers,
)


def _day(d: date | None, high: int = 0) -> bytes:
    if d is None:
        return struct.pack("<HH", 1, 1900)
    return struct.pack("<HH", (d.timetuple().tm_yday & 0x1FF) | (high << 9), d.year)


def _offer(number, *, kind=2, person=41, bidder=877, seller=1191, amount=12_963_102, state=0x14,
           offered=date(2025, 7, 28), effective=date(2025, 7, 28), deadline=date(2025, 9, 1),
           updated=date(2025, 7, 31), tail=b"") -> bytes:
    head = struct.pack("<B2sIBIBIIII", kind, b"\x13\x00", person + 1, 0, bidder, 0, bidder, amount, number, 3000 + number)
    body = bytearray(head + bytes([state]) + b"\xff" * 4 + bytes(17))
    body += _day(None) + b"\x02" + _day(deadline) + _day(effective, high=68) + _day(None) + b"\x00"
    body += struct.pack("<I", seller) + b"\x01\xff" + _day(offered) + b"\x00" + _day(updated, high=23)
    body += bytes(40) + tail
    assert len(head) == 29 and body[69:73] == struct.pack("<I", seller)
    return bytes(body)


def _transfer_section(*records: bytes) -> bytes:
    return SECTION_HEAD + b"\x23\x00\x00" + struct.pack("<I", len(records)) + b"".join(records)


def test_offers_are_walked_record_by_record_with_their_fields() -> None:
    section = _transfer_section(
        _offer(0, tail=b"\x01\x02" + struct.pack("<II", 864_207, 10)),  # clauses: variable length
        _offer(1, kind=3, state=0x0F, person=7, seller=0xFFFFFFFF, amount=0),
        _offer(2, kind=2, state=0x13, effective=date(2026, 1, 2), updated=None),
    )
    first, loan, agreed = read_transfer_offers(section, "example.fm")
    assert (first.index, first.kind_code, first.status_code, first.person_index) == (0, 2, 0x14, 41)
    assert (first.bidding_team_id, first.selling_team_id, first.amount) == (877, 1191, 12_963_102)
    assert (first.offered_on, first.effective_on, first.deadline, first.updated_on) == (
        date(2025, 7, 28), date(2025, 7, 28), date(2025, 9, 1), date(2025, 7, 31))
    assert loan.kind_code == 3 and loan.selling_team_id is None and loan.person_index == 7
    assert agreed.effective_on == date(2026, 1, 2) and agreed.updated_on is None


def test_a_missing_record_raises() -> None:
    section = _transfer_section(_offer(0), _offer(5))
    section = section[:9] + struct.pack("<I", 2) + section[13:]
    with pytest.raises(ReaderCheckError):
        read_transfer_offers(section, "example.fm")


def test_another_head_raises() -> None:
    with pytest.raises(ReaderCheckError):
        read_transfer_offers(b"\x03\x01xxxx" + bytes(40), "example.fm")


def _rankings(tables: int = 30, broken: int | None = None) -> bytes:
    out = bytearray(SECTION_HEAD + b"\x32\x00")
    for t in range(tables):
        scores = [40_000 - 10 * i for i in range(3)]
        if t == broken:
            scores.reverse()
        out += struct.pack("<I", 3) + b"".join(struct.pack("<II", 100 * t + i + 1, s) for i, s in enumerate(scores))
    return bytes(out)


def test_rankings_come_best_first_for_each_position() -> None:
    rows = read_player_rankings(_rankings(), "example.fm")
    assert len(rows) == 90 and len(POSITIONS) == 15
    first = rows[0]
    assert (first.table, first.rank, first.person_index, first.score) == (0, 1, 0, 40_000)
    assert [r.rank for r in rows if r.table == 29] == [1, 2, 3]


def test_rankings_out_of_order_or_missing_raise() -> None:
    with pytest.raises(ReaderCheckError):
        read_player_rankings(_rankings(broken=4), "example.fm")
    with pytest.raises(ReaderCheckError):
        read_player_rankings(_rankings(tables=12), "example.fm")


def test_records_export_every_field() -> None:
    assert {"player_uid", "bidding_club_uid", "selling_club_uid", "status", "offered_on"} <= set(column_names(TransferOffer))
    assert {"position", "women", "rank", "player_uid", "score"} <= set(column_names(PlayerRanking))
