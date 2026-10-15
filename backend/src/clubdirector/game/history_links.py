"""Rattacher les séries d'historique de championnat (fmsave `league_history`) à des clubs.

Ce que la sauvegarde établit (mesuré session 2, build 26.3.0) :
  * l'index `tc_league_history_ls` contient un groupe par club ayant un historique, **dans l'ordre
    croissant des uid de clubs** ; chaque groupe pointe vers le premier enregistrement de sa série
    (`LeagueHistoryRow.run` suit l'ordre de stockage des enregistrements, pas celui de l'index) ;
  * aucun identifiant de club n'est stocké : l'ordre est la seule clé.

Méthode, en trois étapes, toutes déterministes :
  1. Ancres : une série dont la dernière saison (la plus récente de la section) a la même
     compétition et la même position que le championnat actuel et la dernière position d'un club,
     sans ambiguïté dans les deux sens ; on ne garde que les ancres cohérentes avec l'ordre des uid
     (plus longue sous-suite croissante).
  2. Entre deux ancres, les groupes de l'index se répartissent sur les clubs d'uid intermédiaire,
     dans l'ordre. Une attribution n'est retenue que si elle est la SEULE compatible avec l'ordre
     et avec la nation (nation d'une compétition = nation majoritaire de ses clubs actuels).
  3. Tout le reste reste non rattaché ; les outils le disent.
Validation sur la vraie carrière : voir docs/TEST_REPORT.md (0 nation contradictoire).
"""

from __future__ import annotations

import bisect
import struct
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

METHOD_ANCHOR = "ancre : dernière saison (compétition, position) = nation et dernière position du club, recoupement unique"
METHOD_ORDER = "ordre de l'index (clubs triés par uid) entre deux ancres, attribution unique compatible avec la nation"
_U32 = struct.Struct("<I")
_RECORD_BYTES = 24
_TAIL_BYTES = 6


def index_groups(index_section: bytes) -> list[tuple[int, int]]:
    """(indice du premier enregistrement, nombre d'enregistrements) par groupe, dans l'ordre de l'index.

    Forme mesurée : en-tête de 8 octets, u32 0, u32 nombre de groupes, puis pour chaque groupe un
    u32 c suivi de c u32 dont le premier est l'offset (dans le corps de `_dt`) du premier
    enregistrement ; 6 octets de queue.
    """
    groups = []
    p = 16
    end = len(index_section) - _TAIL_BYTES
    while p + 4 <= end:
        (count,) = _U32.unpack_from(index_section, p)
        if p + 4 + 4 * count > end + _TAIL_BYTES:
            break
        first = _U32.unpack_from(index_section, p + 4)[0] // _RECORD_BYTES if count else -1
        groups.append((first, count))
        p += 4 + 4 * count
    return groups


def _lis(pairs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Plus longue sous-suite strictement croissante sur le 2e élément (paires triées sur le 1er)."""
    tails: list[int] = []
    tail_idx: list[int] = []
    prev = [-1] * len(pairs)
    for i, (_, v) in enumerate(pairs):
        j = bisect.bisect_left(tails, v)
        if j == len(tails):
            tails.append(v)
            tail_idx.append(i)
        else:
            tails[j] = v
            tail_idx[j] = i
        prev[i] = tail_idx[j - 1] if j > 0 else -1
    out = []
    k = tail_idx[-1] if tail_idx else -1
    while k != -1:
        out.append(pairs[k])
        k = prev[k]
    return out[::-1]


def _unique_assignment(
    groups: list[tuple[set[int], int | None]], clubs: list[int], nation: dict[int, int | None],
    last_position: dict[int, int | None],
) -> list[int] | None:
    """Seule application croissante groupes -> clubs compatible (nation, dernière position), ou None.

    Placement glouton au plus tôt (chaque groupe sur le premier club compatible après le précédent)
    et au plus tard (en partant de la fin) : toute application compatible place chaque groupe entre
    ces deux bornes, donc elle est unique si et seulement si les deux placements coïncident. Temps
    linéaire (l'ancien décompte par programmation dynamique, k × n, coûtait 8 s par synchronisation)."""
    k, n = len(groups), len(clubs)
    if k == 0:
        return []
    if k > n:
        return None
    club_nation = [nation.get(c) for c in clubs]
    club_position = [last_position.get(c) for c in clubs]

    def ok(i: int, j: int) -> bool:
        nations, position = groups[i]
        if nations and club_nation[j] not in nations:
            return False
        return position is None or club_position[j] == position

    earliest, j = [], 0
    for i in range(k):
        while j < n and not ok(i, j):
            j += 1
        if j == n:
            return None
        earliest.append(j)
        j += 1
    latest, j = [], n - 1
    for i in range(k - 1, -1, -1):
        while not ok(i, j):  # un placement existe (au plus tôt) : la borne est atteinte avant -1
            j -= 1
        latest.append(j)
        j -= 1
    latest.reverse()
    return [clubs[j] for j in earliest] if earliest == latest else None


def link_runs_to_clubs(
    history: Iterable[Any], clubs: Iterable[Any], league_tables: Iterable[Any], index_section: bytes | None = None,
) -> list[tuple[int, int, str]]:
    """[(run, club_uid, méthode)] pour chaque rattachement établi."""
    history = list(history)
    if not history:
        return []
    clubs = list(clubs)
    latest = max(r.season_end_year for r in history)
    rows_by_record = history  # une ligne par enregistrement, dans l'ordre de stockage
    run_of_record = [r.run for r in rows_by_record]

    current: dict[int, int] = {}
    nation_votes: dict[int, Counter] = defaultdict(Counter)
    nation_of_club = {c.uid: getattr(c, "nation_id", None) for c in clubs}
    for table in league_tables:
        for row in table.rows:
            if row.club_uid and table.competition_id:
                if getattr(row, "team_slot", 0) == 0:
                    current.setdefault(row.club_uid, table.competition_id)
                if nation_of_club.get(row.club_uid) is not None:
                    nation_votes[table.competition_id][nation_of_club[row.club_uid]] += 1
    comp_nation = {comp: votes.most_common(1)[0][0] for comp, votes in nation_votes.items()}

    # Séries : par l'index (exact) quand il est fourni, sinon par les ruptures d'année.
    if index_section:
        groups = index_groups(index_section)
        spans = [(f, c) for f, c in groups if c and 0 <= f and f + c <= len(rows_by_record)]
        order_known = True
    else:
        spans, start = [], 0
        for i in range(1, len(rows_by_record) + 1):
            if i == len(rows_by_record) or run_of_record[i] != run_of_record[i - 1]:
                spans.append((start, i - start))
                start = i
        order_known = False

    def last_row(span):
        f, c = span
        return rows_by_record[f + c - 1]

    span_keys: dict[tuple[int, int], list[int]] = defaultdict(list)
    for g, span in enumerate(spans):
        r = last_row(span)
        if r.season_end_year == latest and r.competition_id and r.position:
            span_keys[(r.competition_id, r.position)].append(g)
    club_keys: dict[tuple[int, int], list[int]] = defaultdict(list)
    last_position = {c.uid: getattr(c, "last_league_position", None) for c in clubs}
    clubs_by_nation_position: dict[tuple[int, int], list[int]] = defaultdict(list)
    for c in clubs:
        if last_position[c.uid]:
            clubs_by_nation_position[(nation_of_club[c.uid], last_position[c.uid])].append(c.uid)
    for c in clubs:
        comp = current.get(c.uid)
        if comp and last_position[c.uid]:
            club_keys[(comp, last_position[c.uid])].append(c.uid)
    for comp, position in span_keys:
        # Promus / relégués : le club qui a fini `position` de `comp` la saison dernière est de la
        # nation de `comp` et porte cette dernière position ; retenu seulement s'il est le seul.
        if len(club_keys.get((comp, position), [])) != 1 and comp in comp_nation:
            same = clubs_by_nation_position.get((comp_nation[comp], position), [])
            if len(same) == 1:
                club_keys[(comp, position)] = same
    anchors = sorted(
        (gs[0], club_keys[key][0]) for key, gs in span_keys.items() if len(gs) == 1 and len(club_keys.get(key, [])) == 1
    )
    assigned: dict[int, tuple[int, str]] = {}
    if order_known:
        anchors = _lis(anchors)
    for g, uid in anchors:
        assigned[g] = (uid, METHOD_ANCHOR)

    if order_known and anchors:
        all_uids = sorted(nation_of_club)

        def constraint(span) -> tuple[set[int], int | None]:
            f, c = span
            nations = {comp_nation[r.competition_id] for r in rows_by_record[f:f + c] if r.competition_id in comp_nation}
            # La dernière position n'est pas utilisée ici : elle diffère de la fiche club dans ~2 %
            # des cas mesurés (barrages, championnats scindés), elle exclurait de bonnes attributions.
            return nations, None

        for (g1, u1), (g2, u2) in zip(anchors, anchors[1:], strict=False):
            between = all_uids[bisect.bisect_right(all_uids, u1):bisect.bisect_left(all_uids, u2)]
            gap = [constraint(spans[g]) for g in range(g1 + 1, g2)]
            result = _unique_assignment(gap, between, nation_of_club, last_position)
            if result is not None:
                for k, uid in enumerate(result):
                    assigned[g1 + 1 + k] = (uid, METHOD_ORDER)

    links = []
    for g, (uid, method) in assigned.items():
        f, _c = spans[g]
        links.append((run_of_record[f], uid, method))
    # Une série revendiquée par deux groupes (groupes d'index qui se chevauchent) est ambiguë : retirée.
    claimed = Counter(run for run, _uid, _m in links)
    return sorted(link for link in links if claimed[link[0]] == 1)
