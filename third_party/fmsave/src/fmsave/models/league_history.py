"""League history records (ClubDirector addition)."""

from __future__ import annotations

from dataclasses import dataclass

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class LeagueHistoryRow:
    """One club's final league record for one season, from `tc_league_history_dt`.

    The section holds one run of seasons per club, oldest first; a new run starts where the
    season year stops rising. **The run is not linked to a club inside this section** (the
    companion `tc_league_history_ls` only pages the records), so `run` is a position, not a
    club id. ClubDirector links a run to a club only when the run's latest season matches that
    club's competition and last league position without ambiguity.

    Attributes:
        run: Index of the run (one club's history) in stored order.
        season_end_year: The calendar year the season ends in (2025 is 2024/25), as stored.
        competition_id: Competition id (`Competition.id`); None when stored as 0.
        position: Final league position, 1-based; None when unknown.
        team_count: Number of teams in that league season; None when unknown.
        played: Matches played; None where the save stores the all-ones "unknown" value.
        won: Matches won; None when unknown (mostly very old seasons).
        drawn: Matches drawn; None when unknown.
        lost: Matches lost; None when unknown.
        goals_for: Goals scored; None when unknown.
        goals_against: Goals conceded; None when unknown.
        points: Points, under the rules of that season (two points a win in old seasons);
            None when unknown.
        unknown_6: Unidentified u16, 0 on almost every row (unconfirmed).
        unknown_8: Unidentified i32, -1 on almost every row (unconfirmed).
    """

    run: int
    season_end_year: int
    competition_id: int | None
    position: int | None
    team_count: int | None
    played: int | None
    won: int | None
    drawn: int | None
    lost: int | None
    goals_for: int | None
    goals_against: int | None
    points: int | None
    unknown_6: int
    unknown_8: int


register_field_statuses(
    LeagueHistoryRow,
    verified=(
        "run",
        "season_end_year",
        "competition_id",
        "position",
        "team_count",
        "played",
        "won",
        "drawn",
        "lost",
        "goals_for",
        "goals_against",
        "points",
    ),
    unconfirmed=("unknown_6", "unknown_8"),
)
