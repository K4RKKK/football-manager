"""The squad hierarchy the game works out for the managed club (ClubDirector addition)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class SquadInfluence:
    """A player's influence in his team's dressing room, from one of the game's influence lists.

    Read from `game_db`, where the game keeps, for each team of the club the user manages, the
    list it ranks the squad hierarchy from: the latest one and older ones. Other clubs have no
    such list. Players the club has loaned out are not in it (the game's screen shows them, as
    "others").

    Attributes:
        list_index: Position of the list among the save's lists, 0 for the first one.
        as_of: The day the game worked the list out (unconfirmed).
        latest: True for the list with the latest `as_of` of its club's team, the first one
            stored when several share that day. The game's hierarchy screen matched the latest
            list on the one save measured (unconfirmed).
        club_uid: The club of the list: the one most of its players belong to.
        club_name: That club's name.
        team_id: The team of the list: the one most of its players are registered with.
        team_slot: That team's slot in the club's team list, 0 for the first team.
        rank: 1 for the most influential player of the list (the list itself is not stored in
            that order).
        person_index: The player's person index.
        player_uid: The player's uid, None when the save holds no such player record.
        player_name: That player's name.
        influence: The game's total of the player's influence, higher is more influential.
            Held at 8 999 for every player but the team leaders.
        tier: The hierarchy band of the influence: "leader" (9 000 and above),
            "highly_influential" (7 500 and above), "influential" (6 000 and above) or "other".
            The bands gave the game's own for all 23 players of one list (unconfirmed).
    """

    list_index: int
    as_of: date | None
    latest: bool
    club_uid: int | None
    club_name: str | None
    team_id: int | None
    team_slot: int | None
    rank: int
    person_index: int
    player_uid: int | None
    player_name: str | None
    influence: int
    tier: str


register_field_statuses(
    SquadInfluence,
    verified=(
        "list_index", "club_uid", "club_name", "team_id", "team_slot", "rank", "person_index", "player_uid",
        "player_name", "influence",
    ),
    unconfirmed=("as_of", "latest", "tier"),
)
