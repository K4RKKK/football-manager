"""Détermination de la saison en cours, avec la source de la déduction."""

from __future__ import annotations

from datetime import date

from clubdirector.domain.models import FixtureRecord


def resolve_season(
    game_date: date, fixtures: list[FixtureRecord], club_uid: int | None
) -> tuple[int, str]:
    """Renvoie (année de début de saison, source).

    1. Match du club géré le plus proche de la date de jeu (calendrier FM : fiable).
    2. Tout match le plus proche de la date de jeu.
    3. Heuristique calendaire (juillet = début de saison) — signalée comme telle.
    """
    def nearest(candidates: list[FixtureRecord]) -> FixtureRecord | None:
        dated = [f for f in candidates if f.season_start_year is not None]
        if not dated:
            return None
        return min(dated, key=lambda f: abs((f.date - game_date).days))

    if club_uid is not None:
        own = [f for f in fixtures if club_uid in (f.home_club_uid, f.away_club_uid)]
        f = nearest(own)
        if f:
            return f.season_start_year, "calendrier_club"  # type: ignore[return-value]
    f = nearest(fixtures)
    if f:
        return f.season_start_year, "calendrier_global"  # type: ignore[return-value]
    return (game_date.year if game_date.month >= 7 else game_date.year - 1), "heuristique_date"


def season_label(start_year: int | None) -> str:
    if start_year is None:
        return "saison inconnue"
    return f"{start_year}/{(start_year + 1) % 100:02d}"
