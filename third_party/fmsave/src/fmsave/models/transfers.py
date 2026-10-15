"""Transfer offers and the game's player market rankings (ClubDirector addition)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class TransferOffer:
    """One offer the game's transfer manager keeps: a bid, a loan request or a squad move.

    Read from `transfer_man`. Offers stay in the section after they end, so a save carries the
    whole window's market: completed moves, failed bids, offers waiting for an answer and deals
    agreed for a later date. Staff appointments go through the same records; their
    `person_index` is not a player's and `player_uid` is then None.

    Money is in the save's stored unit (see `CurrencyRow`).

    Attributes:
        index: Position in the section, 0 for the first record (checked by the reader).
        deal_id: A number the game gives each offer, unique within a save (unconfirmed).
        kind_code: The record's type byte: 2 a transfer, 3 a loan, 10 a move between a club's
            own teams; 4, 7 and 9 are rare and not identified.
        kind: "transfer", "loan" or "squad_move" for the codes above, else None.
        status_code: The offer's state byte.
        status: "completed" (code 0x14) when the player joined the bidding club, "failed"
            (0x0F) when he never did; None for the other codes (offers still open or refused).
        person_index: The person the offer is about, None when the record names nobody.
        player_uid: That person's player uid, None for staff and unnamed records.
        player_name: That player's name.
        bidding_team_id: The team the offer is for (the buyer, or the borrower for a loan).
        bidding_club_uid: The club of that team.
        bidding_club_name: That club's name.
        selling_team_id: The team the player belonged to when the offer was made; None for a
            free agent.
        selling_club_uid: The club of that team.
        selling_club_name: That club's name.
        amount: The fee offered (for a loan, the loan fee), in the save's money unit.
        offered_on: The day the offer was made.
        effective_on: The day the move takes or took effect (later than the offer for deals
            agreed in advance).
        deadline: The day the offer lapses, when it has one (unconfirmed).
        updated_on: The day the offer last changed state.
        second_team_id: A second team id, equal to `bidding_team_id` on most records
            (unconfirmed).
    """

    index: int
    deal_id: int
    kind_code: int
    kind: str | None
    status_code: int
    status: str | None
    person_index: int | None
    player_uid: int | None
    player_name: str | None
    bidding_team_id: int | None
    bidding_club_uid: int | None
    bidding_club_name: str | None
    selling_team_id: int | None
    selling_club_uid: int | None
    selling_club_name: str | None
    amount: int
    offered_on: date | None
    effective_on: date | None
    deadline: date | None
    updated_on: date | None
    second_team_id: int | None


@dataclass(frozen=True, slots=True)
class PlayerRanking:
    """A player's place in one of the game's market rankings, read from `shortlist_man`.

    The game keeps one ranking per position (and one of young talents), best first, for men and
    for women. Clubs build their shortlists from them.

    Attributes:
        table: The ranking's position in the section, 0 to 29.
        position: "GK", "DR", "DL", "DC", "WBR", "WBL", "DM", "MR", "ML", "MC", "AMR", "AML",
            "AMC", "ST", or "young" for the young talents ranking.
        women: True for the women's rankings (tables 15 to 29).
        rank: 1 for the best player of the ranking.
        person_index: The player's person index.
        player_uid: The player's uid, None when the save holds no such player record.
        player_name: The player's name.
        score: The game's rating behind the order, higher is better (unconfirmed).
    """

    table: int
    position: str
    women: bool
    rank: int
    person_index: int
    player_uid: int | None
    player_name: str | None
    score: int


register_field_statuses(
    TransferOffer,
    verified=(
        "index", "kind_code", "kind", "status_code", "status", "person_index", "player_uid", "player_name",
        "bidding_team_id", "bidding_club_uid", "bidding_club_name", "selling_team_id", "selling_club_uid",
        "selling_club_name", "amount", "offered_on", "effective_on", "updated_on",
    ),
    unconfirmed=("deal_id", "deadline", "second_team_id"),
)
register_field_statuses(
    PlayerRanking,
    verified=("table", "position", "women", "rank", "person_index", "player_uid", "player_name"),
    unconfirmed=("score",),
)
