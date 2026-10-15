"""Competition names the save itself stores (ClubDirector addition).

The save holds no table of competition names, but every competition the news feed or the
current match session refers to is written with its editor database id, its nation and both of
its names. The shape below was measured on the user's own saves (FM26 26.3.0) and confirmed on
every competition found: 39 of 39 names, with no id ever given two different names.

    u32 database_id | u32 nation_id | u32 (unidentified) | u8 (unidentified) | u32 zero
    | u32 length + UTF-8 long name | u32 length + UTF-8 short name

Only the ids a competition table already lists are accepted, and an id seen with two different
name pairs is dropped rather than guessed, so a name returned here is one the save stores for
that competition.
"""

from __future__ import annotations

import re
import struct
from collections import Counter, defaultdict
from collections.abc import Iterable

NAME_SECTIONS = ("news", "edit_session_man")
_DATABASE_ID_BACK = 17
_ZERO_BACK = 4
_LENGTH = struct.Struct("<I")
_LENGTH_CANDIDATE = re.compile(rb"[\x01-\x78]\x00\x00\x00")
MAX_LONG_NAME_BYTES = 120
MAX_SHORT_NAME_BYTES = 60


def _string_at(buffer: bytes, offset: int, max_bytes: int) -> str | None:
    if offset + _LENGTH.size > len(buffer):
        return None
    (length,) = _LENGTH.unpack_from(buffer, offset)
    end = offset + _LENGTH.size + length
    if not 1 <= length <= max_bytes or end > len(buffer):
        return None
    try:
        text = buffer[offset + _LENGTH.size : end].decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text.isprintable() or not any(character.isalpha() for character in text):
        return None
    return text


def find_competition_names(
    sections: Iterable[bytes], database_ids: Iterable[int]
) -> dict[int, tuple[str, str]]:
    """(long name, short name) by competition database id, from the given section bytes."""
    known = set(database_ids)
    seen: dict[int, Counter[tuple[str, str]]] = defaultdict(Counter)
    for buffer in sections:
        for match in _LENGTH_CANDIDATE.finditer(buffer):
            offset = match.start()
            if offset < _DATABASE_ID_BACK:
                continue
            if _LENGTH.unpack_from(buffer, offset - _ZERO_BACK)[0] != 0:
                continue
            (database_id,) = _LENGTH.unpack_from(buffer, offset - _DATABASE_ID_BACK)
            if database_id not in known:
                continue
            long_name = _string_at(buffer, offset, MAX_LONG_NAME_BYTES)
            if long_name is None:
                continue
            short_at = offset + _LENGTH.size + len(long_name.encode("utf-8"))
            short_name = _string_at(buffer, short_at, MAX_SHORT_NAME_BYTES)
            if short_name is None:
                continue
            seen[database_id][(long_name, short_name)] += 1
    return {
        database_id: next(iter(pairs)) for database_id, pairs in seen.items() if len(pairs) == 1
    }
