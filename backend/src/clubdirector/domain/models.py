"""Modèles normalisés, indépendants de la source (sauvegarde, plugin, saisie utilisateur).

Chaque donnée qui sort vers l'IA ou l'UI est accompagnée d'une `Provenance`.
Une valeur inconnue reste `None` : on ne la remplace jamais par une estimation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["save", "live_plugin", "user", "computed"]
Confidence = Literal["verified", "unconfirmed", "unknown"]


class Provenance(BaseModel):
    source: Source
    collected_at: datetime
    game_date: date | None
    snapshot_id: int | None = None
    confidence: Confidence = "unknown"
    note: str | None = None


class SaveMeta(BaseModel):
    game: str
    build: str
    db_version: str | None
    game_date: date
    known_build: bool


class ManagedClubInfo(BaseModel):
    club_uid: int
    club_name: str
    club_short_name: str | None
    manager_name: str | None
    manager_staff_uid: int | None


class PlayerRecord(BaseModel):
    uid: int
    unique_id: int | None
    name: str
    birth_date: date | None
    age: int | None
    nation_id: int | None
    height_cm: int | None
    club_uid: int | None
    club_name: str | None
    natural_positions: list[str] = Field(default_factory=list)
    accomplished_positions: list[str] = Field(default_factory=list)
    position_ratings: dict[str, int | None] = Field(default_factory=dict)
    left_foot: int | None = None
    right_foot: int | None = None
    current_ability: int | None = None
    potential_ability: int | None = None
    transfer_value: int | None = None
    transfer_value_state: str | None = None
    wage: int | None = None
    contract_start: date | None = None
    contract_end: date | None = None
    squad_status: str | None = None
    on_loan: bool = False
    loan_parent_club_uid: int | None = None
    condition: int | None = None
    attributes: dict[str, int | None] = Field(default_factory=dict)
    personality: dict[str, int | None] = Field(default_factory=dict)
    traits: list[str] = Field(default_factory=list)
    banned: bool = False


class ClubRecord(BaseModel):
    uid: int
    name: str
    short_name: str | None
    nation_id: int | None
    reputation: int | None
    last_league_position: int | None


class FixtureRecord(BaseModel):
    stage_id: int | None
    competition_id: int | None
    competition_name: str | None
    round_label: str | None
    date: date
    season_start_year: int | None
    home_club_uid: int | None
    home_club_name: str | None
    home_team_slot: int | None
    away_club_uid: int | None
    away_club_name: str | None
    away_team_slot: int | None
    home_goals: int | None
    away_goals: int | None
    played: bool | None


class SeasonStatLine(BaseModel):
    player_uid: int
    player_name: str
    kind: str  # league / cup / continental / overall... (libellés fmsave)
    club_uid: int | None
    club_name: str | None
    team_slot: int | None
    starts: int | None
    substitute_appearances: int | None
    minutes: int | None
    goals: int | None
    assists: int | None
    average_rating: float | None
    expected_goals: float | None
    player_of_the_match: int | None
    yellow_cards: int | None = None
    red_cards: int | None = None
    extra: dict[str, float | int | None] = Field(default_factory=dict)


class FinanceMonth(BaseModel):
    club_uid: int
    month: date
    balance: int | None
    transfer_budget_allocated: int | None
    transfer_budget_remaining: int | None
    wage_budget_weekly: int | None
    wage_payroll_weekly: int | None
    total_income: int | None
    total_expenditure: int | None
    net: int | None


class LeagueTableRowRecord(BaseModel):
    competition_id: int | None
    competition_name: str | None
    position: int
    club_uid: int | None
    club_name: str | None
    team_slot: int | None
    played: int | None
    won: int | None
    drawn: int | None
    lost: int | None
    goals_for: int | None
    goals_against: int | None
    points: int | None


class TacticRecord(BaseModel):
    club_uid: int
    team_slot: int | None
    index: int | None
    name: str | None
    style_name: str | None
    mentality: str | None
    slots: list[dict] = Field(default_factory=list)


class InjuryRecord(BaseModel):
    kind: str
    player_uid: int | None
    player_name: str | None
    date: date | None
    club_uid: int | None
    type_name: str | None


class SaveExtract(BaseModel):
    """Résultat complet d'une lecture de sauvegarde, prêt à être archivé."""

    meta: SaveMeta
    managed: list[ManagedClubInfo]
    players: list[PlayerRecord]
    clubs: list[ClubRecord]
    fixtures: list[FixtureRecord]
    season_stats: list[SeasonStatLine]
    finances: list[FinanceMonth]
    league_tables: list[LeagueTableRowRecord]
    tactics: list[TacticRecord]
    injuries: list[InjuryRecord]
    field_status: dict[str, Confidence] = Field(default_factory=dict)
    reader_warnings: list[str] = Field(default_factory=list)
