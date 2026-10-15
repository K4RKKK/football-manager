"""Currency table of game_db (ClubDirector addition)."""

import struct

import pytest

from fmsave import CurrencyRate, CurrencyRow
from fmsave._errors import ReaderCheckError
from fmsave.export import column_names
from fmsave.readers.currencies import read_currencies


def _string(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("<I", len(data)) + data


def _currency(index: int, name: str, short: str, symbol: str, rate: float, history=((2024, 1.2), (2025, 1.1))) -> bytes:
    body = _string(name) + _string(short) + _string("") + _string(symbol)
    body += struct.pack("<fI", rate, len(history))
    body += b"".join(struct.pack("<BHf", 1, year, value) for year, value in history)
    return body + struct.pack("<IIIB", index, index + 2, index + 2, 0)


def _table(*records: bytes) -> bytes:
    return bytes(64) + struct.pack("<I", len(records)) + bytes(2) + b"".join(records) + bytes(32)


def test_the_whole_run_is_read_from_the_base_currency_in_both_directions() -> None:
    db = _table(
        _currency(0, "Albanian Lek", "Lek", "Lek", 112.5),
        _currency(1, "European Euro", "Euro", "€", 1.15713, ((0, 0.0), (2025, 1.16))),
        _currency(2, "United Kingdom Pound", "Pound", "£", 1.0),
        _currency(3, "Venezuelan Bolívar", "Bolívar", "Bs", 2.5e7),
        _currency(4, "Swiss Franc", "Franc", "", 1.088),
    )
    rows = read_currencies(db, "example.fm")
    assert [row.name for row in rows] == [
        "Albanian Lek", "European Euro", "United Kingdom Pound", "Venezuelan Bolívar", "Swiss Franc",
    ]
    euro = rows[1]
    assert (euro.short_name, euro.symbol, euro.rate, euro.index) == ("Euro", "€", pytest.approx(1.15713), 1)
    assert euro.history[0] == CurrencyRate(0, 0.0)
    assert (euro.history[1].year, euro.history[1].rate) == (2025, pytest.approx(1.16))
    assert rows[2].trailer == (4, 4, 0)
    assert rows[4].symbol == ""
    assert rows[3].rate == pytest.approx(2.5e7)


def test_a_save_without_the_base_currency_has_no_currencies() -> None:
    assert read_currencies(_table(_currency(0, "European Euro", "Euro", "€", 1.15713)), "example.fm") == []


def test_a_base_currency_name_outside_a_record_raises() -> None:
    with pytest.raises(ReaderCheckError):
        read_currencies(bytes(16) + b"United Kingdom Pound" + bytes(16), "example.fm")


def test_indexes_out_of_order_raise() -> None:
    db = _table(
        _currency(0, "European Euro", "Euro", "€", 1.15713),
        _currency(5, "United Kingdom Pound", "Pound", "£", 1.0),
    )
    with pytest.raises(ReaderCheckError):
        read_currencies(db, "example.fm")


def test_rows_export_every_field() -> None:
    columns = column_names(CurrencyRow)
    assert columns[:4] == ("name", "short_name", "symbol", "rate")
    assert {"history", "extra", "index", "trailer"} <= set(columns)
