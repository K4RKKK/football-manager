"""Rattacher les séries d'historique de championnat (fmsave `league_history`) à des clubs.

La section ne dit pas à quel club appartient une série. Un rattachement n'est produit que s'il
est prouvé par les données de la sauvegarde elle-même, sans ambiguïté dans les deux sens :
la dernière saison de la série (saison la plus récente de toute la section) doit avoir la même
compétition que le championnat actuel du club (équipe première) et la même position finale que
sa « dernière position » (fiche du club). Une série ou un club qui correspond à plusieurs
candidats n'est pas rattaché : l'outil le dira plutôt que de deviner.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

METHOD = "recoupement unique : championnat actuel + dernière position finale (saison la plus récente)"


def link_runs_to_clubs(history: Iterable[Any], clubs: Iterable[Any], league_tables: Iterable[Any]) -> list[tuple[int, int, str]]:
    """[(run, club_uid, méthode)] pour chaque rattachement prouvé."""
    history = list(history)
    if not history:
        return []
    latest = max(r.season_end_year for r in history)
    last_by_run: dict[int, Any] = {}
    for r in history:
        last_by_run[r.run] = r  # lignes rangées par série puis par année croissante
    runs_by_key: dict[tuple[int, int], list[int]] = defaultdict(list)
    for run, r in last_by_run.items():
        if r.season_end_year == latest and r.competition_id and r.position:
            runs_by_key[(r.competition_id, r.position)].append(run)

    current: dict[int, int] = {}
    for table in league_tables:
        for row in table.rows:
            if getattr(row, "team_slot", 0) == 0 and row.club_uid and table.competition_id:
                current.setdefault(row.club_uid, table.competition_id)
    clubs_by_key: dict[tuple[int, int], list[int]] = defaultdict(list)
    for club in clubs:
        comp = current.get(club.uid)
        if comp and club.last_league_position:
            clubs_by_key[(comp, club.last_league_position)].append(club.uid)

    links = []
    for key, runs in runs_by_key.items():
        candidates = clubs_by_key.get(key, [])
        if len(runs) == 1 and len(candidates) == 1:
            links.append((runs[0], candidates[0], METHOD))
    return sorted(links)
