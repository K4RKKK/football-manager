"""Outils d'accès aux tables miroir fmsave (`fm_<lecteur>`) : toute la donnée décodée, en lecture.

Pas de SQL libre : la table vient d'une liste fermée, les colonnes et filtres sont validés contre
le schéma réel, les valeurs passent en paramètres liés, le nombre de lignes est plafonné et la
requête est toujours limitée à la carrière active. En mode de connaissance réaliste ou analyste,
les colonnes que le jeu ne montre pas à un club (capacités, personnalité, attributs cachés) sont
retirées des résultats et des filtres.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from clubdirector.database.mirror import ALL_TABLES, EXTRA_TABLES, table_name
from clubdirector.database.repositories import HIDDEN_ATTRIBUTES
from clubdirector.tools.presenters import advanced_allowed
from clubdirector.tools.registry import NoArgs, ToolArgs, ToolContext, ToolRegistry, ToolResult

GameTable = Literal[ALL_TABLES]  # type: ignore[valid-type]
MAX_ROWS = 50

_HIDDEN_RE = re.compile(
    r"(^|_)ability(_|$)|^personality_|^(raw_)?attributes_(" + "|".join(sorted(HIDDEN_ATTRIBUTES)) + r")$"
)

TABLE_HELP = {
    "players": "joueurs : identité, âge, nationalités, attributs, postes, contrat complet, prêt, traits, réputation",
    "contracts": "contrats : salaire, dates, statut, type, clauses, chaîne de clubs",
    "suspensions": "suspensions : portée, compétition, date",
    "clubs": "clubs : nom, nation, équipes, club parent, réputation, dernière position",
    "staff": "staff : identité, rôle, club, attributs d'entraîneur, préférences",
    "staff_lists": "listes du staff par club et département",
    "competitions": "compétitions : nom, identifiants, phases",
    "stages": "phases de compétition : tour, groupe, phase précédente",
    "fixtures": "matchs : date, heure, équipes, score, tour, stade",
    "league_tables": "classements (lignes en JSON)",
    "competition_rules": "règlements : matchs par club, promotions, relégations, primes, tours",
    "player_match_stats": "stats joueur match par match (récentes)",
    "player_season_stats": "stats de saison détaillées : xG, passes, centres, dribbles, distance, sprints…",
    "stadiums": "stades : capacité, propriétaire, clubs résidents, pelouse",
    "finances": "finances mensuelles par club",
    "sponsorships": "contrats de sponsoring : type, dates, montants",
    "affiliates": "groupes de clubs affiliés",
    "job_vacancies": "postes d'entraîneur vacants",
    "injury_types": "types de blessure",
    "injuries": "blessures : joueur, date, type, cause",
    "training": "programmes d'entraînement des équipes du club géré",
    "mentoring": "groupes de mentorat",
    "tactics": "tactiques du club géré",
    "set_pieces": "routines de coups de pied arrêtés",
    "facilities": "installations des clubs",
    "managed_clubs": "club(s) géré(s) par l'utilisateur",
    "transfer_windows": "fenêtres de transfert",
    **EXTRA_TABLES,
}


class TableQueryArgs(ToolArgs):
    table: GameTable = Field(description="Table fmsave à interroger (voir describe_game_tables).")
    columns: list[str] | None = Field(None, max_length=40, description="Colonnes à renvoyer (défaut : toutes les visibles).")
    filters: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=8, description="Égalités colonne = valeur (null = valeur absente)."
    )
    name_contains: str | None = Field(None, max_length=80, description="Texte contenu dans la colonne name (insensible à la casse).")
    order_by: str | None = Field(None, description="Colonne de tri.")
    descending: bool = Field(False, description="Tri décroissant.")
    limit: int = Field(20, ge=1, le=MAX_ROWS)
    offset: int = Field(0, ge=0)


class DescribeArgs(ToolArgs):
    table: GameTable | None = Field(None, description="Une table précise ; sinon la liste de toutes.")


def hidden_column(name: str) -> bool:
    return bool(_HIDDEN_RE.search(name))


def _columns(t: ToolContext, table: str) -> list[str]:
    with t.engine.connect() as c:
        cols = [r[1] for r in c.exec_driver_sql(f'PRAGMA table_info("{table_name(table)}")')]
    return [c for c in cols if c not in ("career_id", "snapshot_id")]


def _decode(value):
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def register_game_table_tools(reg: ToolRegistry) -> None:
    T = reg.tool

    @T("describe_game_tables", "Liste les tables complètes lues dans la sauvegarde (lignes, colonnes) — à utiliser avant query_game_table.", "lecture", DescribeArgs)
    def describe_game_tables(t: ToolContext, a: DescribeArgs):
        adv = advanced_allowed(t.prefs)
        out = []
        tables = [a.table] if a.table else list(ALL_TABLES)
        with t.engine.connect() as c:
            for name in tables:
                cols = _columns(t, name)
                if not cols:
                    continue
                n = c.execute(text(f'SELECT count(*) FROM "{table_name(name)}" WHERE career_id = :c'),
                              {"c": t.ctx.career_id}).scalar()
                visible = [col for col in cols if adv or not hidden_column(col)]
                item = {"table": name, "contenu": TABLE_HELP.get(name), "lignes": n, "nb_colonnes": len(visible)}
                if a.table:
                    item["colonnes"] = visible
                out.append(item)
        lim = [] if adv else ["Colonnes cachées (capacités, personnalité, attributs cachés) masquées en mode réaliste/analyste."]
        return ToolResult("", True, data=out, limitations=lim)

    @T("query_game_table", "Lit n'importe quelle table complète de la sauvegarde (filtres, tri, colonnes). Lecture seule, carrière active.", "lecture", TableQueryArgs)
    def query_game_table(t: ToolContext, a: TableQueryArgs):
        all_cols = _columns(t, a.table)
        if not all_cols:
            raise LookupError(f"Table {a.table} vide : resynchronisez la sauvegarde.")
        adv = advanced_allowed(t.prefs)
        visible = [c for c in all_cols if adv or not hidden_column(c)]
        wanted = a.columns or visible
        refused = [c for c in [*wanted, *a.filters, *([a.order_by] if a.order_by else [])] if c not in visible]
        if refused:
            hidden = [c for c in refused if c in all_cols]
            msg = f"Colonnes inconnues : {sorted(set(refused) - set(hidden))}" if set(refused) - set(hidden) else ""
            if hidden:
                msg += (" " if msg else "") + f"Colonnes masquées dans le mode de connaissance actuel : {sorted(set(hidden))}"
            raise ValueError(msg)
        conds, params = ["career_id = :career"], {"career": t.ctx.career_id}
        for i, (col, value) in enumerate(a.filters.items()):
            if value is None:
                conds.append(f'"{col}" IS NULL')
            else:
                conds.append(f'"{col}" = :f{i}')
                params[f"f{i}"] = int(value) if isinstance(value, bool) else value
        if a.name_contains:
            if "name" not in visible:
                raise ValueError(f"La table {a.table} n'a pas de colonne name.")
            conds.append("lower(name) LIKE :name")
            params["name"] = f"%{a.name_contains.lower()}%"
        where = " AND ".join(conds)
        order = f' ORDER BY "{a.order_by}" {"DESC" if a.descending else "ASC"}' if a.order_by else ""
        cols_sql = ", ".join(f'"{c}"' for c in wanted)
        tbl = table_name(a.table)
        with t.engine.connect() as c:
            total = c.execute(text(f'SELECT count(*) FROM "{tbl}" WHERE {where}'), params).scalar()
            rows = c.execute(text(f'SELECT {cols_sql} FROM "{tbl}" WHERE {where}{order} LIMIT :lim OFFSET :off'),
                             {**params, "lim": a.limit, "off": a.offset}).mappings().all()
        data = {"table": a.table, "total": total, "renvoyees": len(rows),
                "lignes": [{k: _decode(v) for k, v in r.items()} for r in rows]}
        lim = []
        if total > a.offset + len(rows):
            lim.append(f"{total - a.offset - len(rows)} autres lignes : utilisez offset ou des filtres.")
        if not adv and len(visible) < len(all_cols):
            lim.append("Colonnes cachées masquées (mode réaliste/analyste).")
        return ToolResult("", True, data=data, limitations=lim)


__all__ = ["NoArgs", "hidden_column", "register_game_table_tools"]
