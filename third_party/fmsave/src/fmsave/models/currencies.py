"""Currencies and exchange rates the save's database holds (ClubDirector addition)."""

from __future__ import annotations

from dataclasses import dataclass

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class CurrencyRate:
    """One yearly rate a currency's history keeps.

    Attributes:
        year: The year; 0 marks an empty entry (rate 0) measured at the head of some histories.
        rate: Units of the currency per unit of the save's money that year.
    """

    year: int
    rate: float


@dataclass(frozen=True, slots=True)
class CurrencyRow:
    """One currency of the save's database, with its rate against the save's money unit.

    The money fields fmsave returns (wages, values, budgets, balances) are stored in the unit whose
    `rate` is 1.0 — the United Kingdom pound on every save measured. A value displayed in another
    currency is the stored value times that currency's `rate`: the euro's rate (1.15713 on the
    user's 26.3.0 save) is the single factor an earlier measurement found between a save's stored
    money and the euros its screens displayed.

    Attributes:
        name: Full name, as the database stores it (English), e.g. "European Euro".
        short_name: Short name, e.g. "Euro".
        symbol: Display symbol, e.g. "€"; empty for many currencies.
        rate: Units of this currency per unit of the save's money.
        history: Yearly rates the database keeps, oldest first.
        extra: A third string stored between the short name and the symbol, empty on every row
            measured (unconfirmed).
        index: Position in the table, 0 for the first currency (checked by the reader).
        trailer: The two u32 and one u8 stored after the index (unconfirmed).
    """

    name: str
    short_name: str
    symbol: str
    rate: float
    history: tuple[CurrencyRate, ...]
    extra: str
    index: int
    trailer: tuple[int, ...]


register_field_statuses(CurrencyRate, verified=("year", "rate"))
register_field_statuses(
    CurrencyRow,
    verified=("name", "short_name", "symbol", "rate", "history", "index"),
    unconfirmed=("extra", "trailer"),
)
