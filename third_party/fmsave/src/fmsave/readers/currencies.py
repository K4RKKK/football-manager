"""Decode the currency table of `game_db` (ClubDirector addition).

Shape measured on the user's own save (FM26 26.3.0): 173 currencies in one contiguous run, each

    u32 length + UTF-8 name | u32 length + short name | u32 length + string (empty on every row)
    | u32 length + symbol (empty for many) | f32 rate | u32 count | count × (u8 1, u16 year, f32 rate)
    | u32 index | u32 | u32 | u8 (unidentified)

The trailing index runs 0, 1, 2… in stored order, which the reader checks. The run is found from the
base currency's name (the one whose rate is 1.0), then walked in both directions record by record: a
record before the first one is the one that ends exactly where it starts.
"""

from __future__ import annotations

import struct

from fmsave._errors import ReaderCheckError
from fmsave.models.currencies import CurrencyRate, CurrencyRow

GAME_DB_SECTION = "game_db"
BASE_NAME = "United Kingdom Pound"
MAX_RECORD_BYTES = 4_000
MAX_HISTORY = 300
# Rates measured from 0.3 (Kuwaiti dinar) to above 10^7 (Venezuelan bolívar).
MIN_RATE = 1e-6
MAX_RATE = 1e12
_U32 = struct.Struct("<I")
_F32 = struct.Struct("<f")
_HISTORY_ENTRY = struct.Struct("<BHf")
_TRAILER = struct.Struct("<IIIB")


def _string(buf: bytes, at: int, max_bytes: int) -> tuple[str, int] | None:
    if at < 0 or at + 4 > len(buf):
        return None
    (n,) = _U32.unpack_from(buf, at)
    end = at + 4 + n
    if n > max_bytes or end > len(buf):
        return None
    try:
        text = buf[at + 4 : end].decode("utf-8")
    except UnicodeDecodeError:
        return None
    if n and not text.isprintable():
        return None
    return text, end


def _record(buf: bytes, at: int) -> tuple[CurrencyRow, int] | None:
    name = _string(buf, at, 64)
    if name is None or len(name[0]) < 3:
        return None
    short = _string(buf, name[1], 32)
    if short is None:
        return None
    extra = _string(buf, short[1], 32)
    if extra is None:
        return None
    symbol = _string(buf, extra[1], 8)
    if symbol is None:
        return None
    at = symbol[1]
    if at + 8 > len(buf):
        return None
    (rate,) = _F32.unpack_from(buf, at)
    (count,) = _U32.unpack_from(buf, at + 4)
    if not (MIN_RATE < rate < MAX_RATE) or count > MAX_HISTORY:
        return None
    at += 8
    history = []
    for _ in range(count):
        if at + _HISTORY_ENTRY.size > len(buf):
            return None
        flag, year, value = _HISTORY_ENTRY.unpack_from(buf, at)
        # Year 0: an empty entry measured at the head of some histories (rate 0).
        if flag != 1 or not (year == 0 or 1900 <= year <= 2200):
            return None
        history.append(CurrencyRate(year, round(value, 6)))
        at += _HISTORY_ENTRY.size
    if at + _TRAILER.size > len(buf):
        return None
    trailer = _TRAILER.unpack_from(buf, at)
    row = CurrencyRow(name[0], short[0], symbol[0], round(rate, 6), tuple(history), extra[0], trailer[0], trailer[1:])
    return row, at + _TRAILER.size


def read_currencies(game_db: bytes, file_name: str) -> list[CurrencyRow]:
    """Every currency of the table, in stored order; the base currency has rate 1.0.

    Empty when `game_db` does not hold the base currency's name at all.

    Raises:
        ReaderCheckError: The base currency's record does not have the measured layout, or the
            indexes of the run are not 0, 1, 2… in order.
    """
    anchor = game_db.find(BASE_NAME.encode("utf-8"))
    if anchor < 0:
        return []
    base_at = anchor - 4
    base = _record(game_db, base_at)
    if base is None or abs(base[0].rate - 1.0) > 1e-6:
        raise ReaderCheckError(f"{file_name}: section '{GAME_DB_SECTION}' holds no currency table fmsave recognizes")
    first = base_at
    while True:
        previous = None
        for at in range(first - 30, max(-1, first - MAX_RECORD_BYTES), -1):
            rec = _record(game_db, at)
            if rec is not None and rec[1] == first:
                previous = at
                break
        if previous is None:
            break
        first = previous
    rows = []
    at = first
    while (rec := _record(game_db, at)) is not None:
        rows.append(rec[0])
        at = rec[1]
    if [row.index for row in rows] != list(range(len(rows))):
        raise ReaderCheckError(f"{file_name}: the currency indexes of '{GAME_DB_SECTION}' are not 0, 1, 2… in order")
    return rows
