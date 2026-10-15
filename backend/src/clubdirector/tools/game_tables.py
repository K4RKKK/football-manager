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
from clubdirector.tools.presenters import advanced_allowed, money
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
    "league_history": "historique des championnats : une série (run) par club, saisons passées (année de fin, compétition, position, V/N/D, buts, points)",
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


class ClubHistoryArgs(ToolArgs):
    club_uid: int | None = Field(None, description="Club ; par défaut le club géré.")
    since_year: int | None = Field(None, description="Première année de fin de saison à inclure (ex. 2015 pour 2014/15).")


class StaffArgs(ToolArgs):
    club_uid: int | None = Field(None, description="Club ; par défaut le club géré.")
    toutes_equipes: bool = Field(False, description="True : staff de toutes les équipes du club, pas seulement l'équipe première.")


class DescribeArgs(ToolArgs):
    table: GameTable | None = Field(None, description="Une table précise ; sinon la liste de toutes.")


def hidden_column(name: str) -> bool:
    return bool(_HIDDEN_RE.search(name))


def _columns(t: ToolContext, table: str) -> list[str]:
    with t.engine.connect() as c:
        cols = [r[1] for r in c.exec_driver_sql(f'PRAGMA table_info("{table_name(table)}")')]
    return [c for c in cols if c not in ("career_id", "snapshot_id")]


def _competition_names(conn, career_id: int) -> dict[int, str]:
    """Nom long par identifiant de compétition (noms stockés dans la sauvegarde)."""
    try:
        rows = conn.execute(text(
            "SELECT c.id, n.long_name FROM fm_competitions c JOIN fm_competition_names n "
            "ON n.career_id = c.career_id AND n.database_id = c.database_id WHERE c.career_id = :k"), {"k": career_id})
        return {r[0]: r[1] for r in rows}
    except Exception:  # noqa: BLE001 — tables absentes avant la première synchronisation
        return {}


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

    @T("get_club_league_history", "Historique des championnats d'un club, saison par saison (position, V/N/D, buts, points), lu dans la sauvegarde.", "lecture", ClubHistoryArgs)
    def get_club_league_history(t: ToolContext, a: ClubHistoryArgs):
        club = a.club_uid if a.club_uid is not None else t.ctx.club_uid
        if club is None:
            raise LookupError("Aucun club géré dans cette carrière.")
        if not _columns(t, "league_history_links"):
            raise LookupError("Historique non synchronisé : resynchronisez la sauvegarde.")
        with t.engine.connect() as c:
            link = c.execute(text("SELECT run, method FROM fm_league_history_links WHERE career_id = :k AND club_uid = :u"),
                             {"k": t.ctx.career_id, "u": club}).first()
            if link is None:
                return ToolResult("", True, data={"club_uid": club, "saisons": []}, limitations=[
                    "Historique de championnat non rattaché à ce club de façon certaine : la sauvegarde ne "
                    "stocke pas le club de chaque série, et le recoupement (championnat actuel + dernière "
                    "position) n'est pas unique pour lui. Aucune saison n'est attribuée par supposition."])
            names = _competition_names(c, t.ctx.career_id)
            rows = c.execute(text(
                "SELECT season_end_year, competition_id, position, team_count, played, won, drawn, lost, "
                "goals_for, goals_against, points FROM fm_league_history WHERE career_id = :k AND run = :r "
                "AND (:y IS NULL OR season_end_year >= :y) ORDER BY season_end_year DESC"),
                {"k": t.ctx.career_id, "r": link.run, "y": a.since_year}).mappings().all()
        seasons = [{**dict(r), "saison": f"{r['season_end_year'] - 1}/{str(r['season_end_year'])[-2:]}",
                    "competition": names.get(r["competition_id"])} for r in rows]
        lim = []
        if any(s["competition"] is None for s in seasons):
            lim.append("Certaines compétitions n'ont pas de nom stocké dans la sauvegarde (identifiant seulement).")
        if any(s["points"] is None or s["won"] is None for s in seasons):
            lim.append("Certaines saisons anciennes ont des valeurs inconnues dans la sauvegarde (laissées vides).")
        return ToolResult("", True, data={"club_uid": club, "rattachement": link.method, "saisons": seasons}, limitations=lim)

    @T("get_club_staff", "Staff du club (entraîneurs, encadrement) : nom, âge, nationalité, salaire, contrat, équipe.", "lecture", StaffArgs)
    def get_club_staff(t: ToolContext, a: StaffArgs):
        club = a.club_uid if a.club_uid is not None else t.ctx.club_uid
        if club is None:
            raise LookupError("Aucun club géré dans cette carrière.")
        if not _columns(t, "staff"):
            raise LookupError("Staff non synchronisé : resynchronisez la sauvegarde.")
        with t.engine.connect() as c:
            rows = c.execute(text(
                "SELECT name, age, nation_id, team_slot, is_human_manager, has_contract, wage, contract_start, contract_end "
                "FROM fm_staff WHERE career_id = :k AND club_uid = :u AND (:all OR team_slot = 0 OR team_slot IS NULL) "
                "ORDER BY is_human_manager DESC, wage DESC"), {"k": t.ctx.career_id, "u": club, "all": a.toutes_equipes}).mappings().all()
        staff = [{"nom": r["name"], "age": r["age"], "nation_id": r["nation_id"], "equipe_slot": r["team_slot"],
                  "entraineur_principal_humain": bool(r["is_human_manager"]),
                  "salaire": money(t.prefs, r["wage"]), "debut_contrat": r["contract_start"], "fin_contrat": r["contract_end"]}
                 for r in rows]
        return ToolResult("", True, data={"club_uid": club, "nombre": len(staff), "staff": staff}, limitations=[
            "Le rôle de chaque membre du staff (adjoint, préparateur, recruteur…) n'est pas encore décodé dans la "
            "sauvegarde : ne le déduis pas du nom ou du salaire."])

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
