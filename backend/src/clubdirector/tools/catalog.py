"""Catalogue des outils du directeur sportif.

Les noms suivent le cahier des charges (section 9). Ce sont des interfaces de ClubDirector,
pas des fonctions natives de FM26.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Literal

from pydantic import Field

from clubdirector.database.repositories import ATTRIBUTE_FR
from clubdirector.money import UncalibratedCurrency
from clubdirector.positions import LABEL_FR, normalize_position, split_positions
from clubdirector.proactive.rules import POSITION_GROUPS, contract_alerts, depth_alerts
from clubdirector.recruitment.roles import ROLES
from clubdirector.recruitment.scoring import METHOD, role_with_adjustments, score_player
from clubdirector.sync.season import season_label
from clubdirector.tools.game_tables import register_game_table_tools
from clubdirector.tools.presenters import (
    FOG_LIMITATION,
    advanced_allowed,
    money,
    player_full,
    player_summary,
)
from clubdirector.tools.registry import (
    NoArgs,
    ToolArgs,
    ToolContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
)

NOT_PROVEN = (
    "Exécution dans FM26 non prouvée : aucun mécanisme d'action n'a encore été validé dans le jeu. "
    "Je peux préparer l'opération, mais pas l'exécuter."
)


# --------------------------------------------------------------------------- arguments ---
class PlayerRef(ToolArgs):
    player_uid: int | None = Field(None, description="Identifiant du joueur dans la sauvegarde (uid).")
    name: str | None = Field(None, description="Nom (ou partie du nom) si l'uid est inconnu.")


class SquadArgs(ToolArgs):
    club_uid: int | None = Field(None, description="Club ; par défaut le club géré.")
    team_slot: int = Field(0, ge=0, description="Équipe : 0 = équipe première (défaut), 1, 2… = réserve / jeunes.")
    toutes_equipes: bool = Field(False, description="True : toutes les équipes du club (première, réserve, jeunes).")


class StatsArgs(PlayerRef):
    season_start_year: int | None = Field(None, description="Année de début de saison (ex. 2030 pour 2030/31).")
    relative_season: int | None = Field(None, description="0 = saison en cours, -1 = saison précédente.")


class MatchesArgs(ToolArgs):
    limit: int = Field(5, ge=1, le=50)
    competition_id: int | None = None


class MatchOnDateArgs(ToolArgs):
    days_ago: int | None = Field(None, ge=0, le=3650, description="Il y a N jours (date du JEU).")
    game_date: date | None = Field(None, description="Date précise dans le jeu (AAAA-MM-JJ).")
    window_days: int = Field(4, ge=0, le=14)


class TopStatArgs(ToolArgs):
    stat: Literal["goals", "assists", "average_rating", "minutes", "player_of_the_match", "expected_goals"] = "goals"
    scope: Literal["club", "tous"] = "club"
    season_start_year: int | None = None
    relative_season: int | None = Field(None, description="0 = saison en cours, -1 = précédente.")
    limit: int = Field(5, ge=1, le=50)


class SearchArgs(ToolArgs):
    position: str | None = Field(None, description="Code FM (DC, AMR, STC...) ou libellé français (ailier droit).")
    min_age: int | None = Field(None, ge=14, le=45)
    max_age: int | None = Field(None, ge=14, le=45)
    max_value: float | None = Field(None, description="Valeur maximale EN DEVISE AFFICHÉE (ex. 20000000 pour 20 M€).")
    max_wage: float | None = Field(None, description="Salaire maximal en devise affichée.")
    include_own_club: bool = False
    contract_expires_within_months: int | None = Field(None, ge=0, le=60)
    name: str | None = None
    attribute_min: dict[str, int] = Field(default_factory=dict, description="Ex. {\"crossing\": 14}.")
    order_by: Literal["transfer_value", "age", "wage", "name"] = "transfer_value"
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class CompareArgs(ToolArgs):
    player_uids: list[int] = Field(..., min_length=2, max_length=5)
    role: str | None = Field(None, description=f"Rôle de référence : {', '.join(ROLES)}")


class TargetsArgs(ToolArgs):
    role: str = Field(..., description=f"Rôle recherché : {', '.join(ROLES)}")
    min_age: int | None = Field(None, ge=14, le=45)
    max_age: int | None = Field(None, ge=14, le=45)
    max_value: float | None = Field(None, description="Valeur max en devise affichée.")
    max_wage: float | None = None
    extra_weights: dict[str, float] = Field(default_factory=dict, description="Ajustements de poids (0-10) par attribut.")
    limit: int = Field(5, ge=1, le=30)
    candidate_pool: int = Field(400, ge=10, le=5000, description="Nombre max de candidats évalués.")


class FitArgs(ToolArgs):
    player_uid: int
    role: str


class ExpiringArgs(ToolArgs):
    months: int = Field(12, ge=0, le=60)
    scope: Literal["club", "tous"] = "club"
    limit: int = Field(30, ge=1, le=200)


class AffordArgs(ToolArgs):
    fee: float | None = Field(None, description="Indemnité envisagée en devise affichée.")
    weekly_wage: float | None = Field(None, description="Salaire hebdomadaire envisagé en devise affichée.")


class MemoryArgs(ToolArgs):
    kind: Literal["preference", "objectif", "joueur_refuse", "cible", "promesse", "decision", "a_vendre", "strategie"]
    text: str = Field(..., min_length=3, max_length=500)
    key: str | None = Field(None, description="Clé structurée, ex. 'age_max_recrue'.")
    value: int | float | str | bool | None = None
    player_uid: int | None = None


class ForgetArgs(ToolArgs):
    memory_id: int


class ActionArgs(ToolArgs):
    player_uid: int | None = None
    amount: float | None = None
    details: str | None = None


# ------------------------------------------------------------------------------ helpers ---
def _resolve_player(t: ToolContext, ref: PlayerRef) -> dict:
    if ref.player_uid is not None:
        row = t.repo.player(t.ctx, ref.player_uid)
        if row is None:
            raise LookupError(f"Aucun joueur avec l'uid {ref.player_uid} dans la sauvegarde active.")
        return row
    if ref.name:
        rows = t.repo.find_players_by_name(t.ctx, ref.name, limit=6)
        if not rows:
            raise LookupError(f"Aucun joueur nommé « {ref.name} » dans la sauvegarde active.")
        if len(rows) > 1:
            exact = [r for r in rows if r["name"].casefold() == ref.name.casefold()]
            if len(exact) == 1:
                return exact[0]
            names = "; ".join(f"{r['name']} ({r.get('club_name') or 'sans club'}, uid {r['uid']})" for r in rows)
            raise LookupError(f"Plusieurs joueurs correspondent à « {ref.name} » : {names}. Précisez l'uid.")
        return rows[0]
    raise ValueError("Indiquez player_uid ou name.")


def _season(t: ToolContext, explicit: int | None, relative: int | None) -> int | None:
    if explicit is not None:
        return explicit
    if t.ctx.season_start_year is None:
        return None
    return t.ctx.season_start_year + (relative or 0)


def _to_raw(t: ToolContext, amount: float | None) -> int | None:
    if amount is None:
        return None
    return t.prefs.currency.to_raw(amount)


def _stat_view(r: dict) -> dict:
    return {
        "saison": season_label(r["season_start_year"]),
        "saison_debut": r["season_start_year"],
        "type": r["kind"],
        "club": r["club_name"],
        "equipe_slot": r["team_slot"],
        "titularisations": r["starts"],
        "entrees": r["substitute_appearances"],
        "minutes": r["minutes"],
        "buts": r["goals"],
        "passes_decisives": r["assists"],
        "note_moyenne": r["average_rating"],
        "xg": r["expected_goals"],
        "homme_du_match": r["player_of_the_match"],
        "cartons_jaunes": r["yellow_cards"],
        "cartons_rouges": r["red_cards"],
        "releve_le": r["game_date"].isoformat() if r["game_date"] else None,
    }


def _match_view(m: dict, club_uid: int | None) -> dict:
    has = m["home_goals"] is not None and m["away_goals"] is not None
    res = None
    if has and club_uid is not None:
        home = m["home_club_uid"] == club_uid
        gf, ga = (m["home_goals"], m["away_goals"]) if home else (m["away_goals"], m["home_goals"])
        res = "victoire" if gf > ga else "défaite" if gf < ga else "nul"
    return {
        "date": m["date"].isoformat(),
        "domicile": m["home_club_name"],
        "exterieur": m["away_club_name"],
        "score": f"{m['home_goals']}-{m['away_goals']}" if has else None,
        "score_disponible": has,
        "resultat": res,
        "joue": m["played"],
        "competition_id": m["competition_id"],
        "competition": m["competition_name"],
        "tour": m["round_label"],
    }


def _require_club(t: ToolContext) -> int:
    if t.ctx.club_uid is None:
        raise LookupError("Le manager n'a pas de club dans la sauvegarde active.")
    return t.ctx.club_uid


# ------------------------------------------------------------------------------ registry ---
def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    T = reg.tool

    # ---------------------------------------------------------------- lecture
    @T("get_current_save", "Carrière active : club, manager, date de JEU, saison, dernière synchronisation.", "lecture")
    def get_current_save(t: ToolContext, a: NoArgs):
        snaps = t.repo.snapshots(t.ctx.career_id)
        last = snaps[0] if snaps else None
        return {
            "carriere": t.ctx.label,
            "club": t.ctx.club_name,
            "club_uid": t.ctx.club_uid,
            "manager": t.ctx.manager_name,
            "date_jeu": t.ctx.game_date.isoformat() if t.ctx.game_date else None,
            "saison": season_label(t.ctx.season_start_year),
            "saison_source": t.ctx.season_source,
            "derniere_synchro": last["copied_at"].isoformat() if last else None,
            "build_jeu": last["build"] if last else None,
            "statut_champs": t.ctx.field_status,
            "avertissements_lecteur": (last or {}).get("warnings") or [],
        }

    @T("get_managed_club", "Informations du club géré (réputation, dernière position, effectif).", "lecture")
    def get_managed_club(t: ToolContext, a: NoArgs):
        club = _require_club(t)
        squad = t.repo.squad(t.ctx)
        table = [r for r in t.repo.league_table(t.ctx) if r["club_uid"] == club]
        counts = t.repo.team_counts(t.ctx)
        return {
            "club": t.ctx.club_name,
            "club_uid": club,
            "effectif": len(squad),
            "perimetre": "équipe première (slot 0)",
            "joueurs_par_equipe": {("inconnue" if k is None else f"slot {k}"): v for k, v in sorted(counts.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))},
            "age_moyen": round(sum(p["age"] for p in squad if p["age"]) / max(1, sum(1 for p in squad if p["age"])), 1),
            "classement": table[0] if table else None,
        }

    @T("get_club_squad", "Liste de l'effectif (club géré par défaut).", "lecture", SquadArgs)
    def get_club_squad(t: ToolContext, a: SquadArgs):
        rows = t.repo.squad(t.ctx, a.club_uid, None if a.toutes_equipes else a.team_slot)
        return ToolResult("", True, data=[player_summary(r, t.prefs) for r in rows])

    @T("get_player_profile", "Fiche complète d'un joueur (attributs visibles, contrat, postes).", "lecture", PlayerRef)
    def get_player_profile(t: ToolContext, a: PlayerRef):
        row = _resolve_player(t, a)
        lim = [] if row.get("club_uid") == t.ctx.club_uid else [FOG_LIMITATION]
        return ToolResult("", True, data=player_full(row, t.prefs), limitations=lim)

    @T("get_player_contract", "Contrat d'un joueur (salaire, début, fin, statut).", "lecture", PlayerRef)
    def get_player_contract(t: ToolContext, a: PlayerRef):
        row = _resolve_player(t, a)
        return {
            "joueur": row["name"],
            "club": row["club_name"],
            "salaire": money(t.prefs, row["wage"]),
            "debut": row["contract_start"].isoformat() if row["contract_start"] else None,
            "fin": row["contract_end"].isoformat() if row["contract_end"] else None,
            "statut": row["squad_status"],
            "pret": bool(row["on_loan"]),
            "fiabilite_salaire": t.ctx.status("player.wage"),
        }

    @T("get_player_attributes", "Attributs visibles d'un joueur (selon le mode de connaissance).", "lecture", PlayerRef)
    def get_player_attributes(t: ToolContext, a: PlayerRef):
        row = _resolve_player(t, a)
        full = player_full(row, t.prefs)
        return {"joueur": row["name"], "attributs": {ATTRIBUTE_FR.get(k, k): v for k, v in full["attributs"].items()}}

    @T("get_player_statistics", "Statistiques d'un joueur pour une saison ARCHIVÉE (par défaut la saison en cours).", "lecture", StatsArgs)
    def get_player_statistics(t: ToolContext, a: StatsArgs):
        row = _resolve_player(t, a)
        season = _season(t, a.season_start_year, a.relative_season)
        rows = t.repo.season_stats(t.ctx, player_uid=row["uid"], season_start_year=season)
        archived = t.repo.archived_seasons(t.ctx)
        lim = []
        if not rows:
            lim.append(
                f"Aucune statistique archivée pour {row['name']} en {season_label(season)}. "
                f"Saisons archivées pour cette carrière : {', '.join(season_label(x) for x in archived) or 'aucune'}. "
                "FM26 ne conserve dans la sauvegarde que la saison en cours ; les saisons passées ne sont "
                "connues que si ClubDirector les a synchronisées à l'époque."
            )
        return ToolResult("", True, data={"joueur": row["name"], "uid": row["uid"], "saison": season_label(season),
                                          "lignes": [_stat_view(r) for r in rows]}, limitations=lim)

    @T("get_player_season_history", "Toutes les saisons archivées d'un joueur + historique club/salaire/valeur.", "lecture", PlayerRef)
    def get_player_season_history(t: ToolContext, a: PlayerRef):
        row = _resolve_player(t, a)
        stats = t.repo.season_stats(t.ctx, player_uid=row["uid"])
        hist = t.repo.player_history(t.ctx, row["uid"])
        return {
            "joueur": row["name"],
            "saisons": [_stat_view(r) for r in stats],
            "historique": [
                {"date_jeu": h["game_date"].isoformat() if h["game_date"] else None, "club": h["club_name"],
                 "salaire": money(t.prefs, h["wage"]), "valeur": money(t.prefs, h["transfer_value"]),
                 "fin_contrat": h["contract_end"].isoformat() if h["contract_end"] else None, "changement": h["change"]}
                for h in hist
            ],
        }

    @T("get_recent_matches", "Derniers matchs joués par le club géré (équipe première), du plus récent au plus ancien.", "lecture", MatchesArgs)
    def get_recent_matches(t: ToolContext, a: MatchesArgs):
        club = _require_club(t)
        rows = t.repo.fixtures(t.ctx, date_to=t.ctx.game_date, played=True, limit=a.limit)
        if a.competition_id is not None:
            rows = [r for r in rows if r["competition_id"] == a.competition_id]
        lim = []
        if any(r["home_goals"] is None for r in rows):
            lim.append("Certains scores ne sont pas conservés ou pas décodables dans la sauvegarde : ils sont indiqués comme indisponibles.")
        return ToolResult("", True, data=[_match_view(r, club) for r in rows], limitations=lim)

    @T("get_match_details", "Match du club autour d'une date de JEU (ex. « il y a une semaine »).", "lecture", MatchOnDateArgs)
    def get_match_details(t: ToolContext, a: MatchOnDateArgs):
        club = _require_club(t)
        if t.ctx.game_date is None:
            raise LookupError("Date de jeu inconnue.")
        target = a.game_date or (t.ctx.game_date - timedelta(days=a.days_ago or 0))
        rows = t.repo.match_near(t.ctx, target, a.window_days)
        data = {"date_cible": target.isoformat(), "date_jeu": t.ctx.game_date.isoformat(),
                "matchs": [_match_view(r, club) for r in rows]}
        lim = []
        if not rows:
            lim.append(f"Aucun match du club trouvé entre le {(target - timedelta(days=a.window_days)).isoformat()} et le {(target + timedelta(days=a.window_days)).isoformat()} (date du jeu).")
            # Les matchs réels les plus proches, pour répondre utilement (ex. trêve internationale).
            before = t.repo.fixtures(t.ctx, date_to=target, limit=1)
            after = t.repo.fixtures(t.ctx, date_from=target, date_to=t.ctx.game_date, limit=1, newest_first=False)
            data["match_precedent"] = _match_view(before[0], club) if before else None
            data["match_suivant"] = _match_view(after[0], club) if after else None
        return ToolResult("", True, data=data, limitations=lim)

    @T("get_upcoming_matches", "Prochains matchs du club géré.", "lecture", MatchesArgs)
    def get_upcoming_matches(t: ToolContext, a: MatchesArgs):
        club = _require_club(t)
        start = t.ctx.game_date + timedelta(days=1) if t.ctx.game_date else None
        rows = t.repo.fixtures(t.ctx, date_from=start, limit=a.limit, newest_first=False)
        return [_match_view(r, club) for r in rows]

    @T("get_league_table", "Classement actuel du championnat du club géré.", "lecture")
    def get_league_table(t: ToolContext, a: NoArgs):
        rows = t.repo.league_table(t.ctx)
        return [
            {k: r[k] for k in ("position", "club_name", "played", "won", "drawn", "lost", "goals_for", "goals_against", "points")}
            | {"est_notre_club": r["club_uid"] == t.ctx.club_uid}
            for r in rows
        ]

    @T("get_club_finances", "Finances mensuelles du club géré (12 derniers mois archivés).", "lecture")
    def get_club_finances(t: ToolContext, a: NoArgs):
        rows = t.repo.finances(t.ctx)
        return [
            {"mois": r["month"].isoformat(), "solde": money(t.prefs, r["balance"]),
             "revenus": money(t.prefs, r["total_income"]), "depenses": money(t.prefs, r["total_expenditure"]),
             "resultat_net": money(t.prefs, r["net"])}
            for r in rows
        ]

    @T("get_transfer_budget", "Budget transferts alloué et restant (dernier mois connu).", "lecture")
    def get_transfer_budget(t: ToolContext, a: NoArgs):
        rows = t.repo.finances(t.ctx, months=1)
        if not rows:
            raise LookupError("Aucune donnée financière dans la sauvegarde pour le club géré.")
        r = rows[0]
        return {"mois": r["month"].isoformat(), "alloue": money(t.prefs, r["transfer_budget_allocated"]),
                "restant": money(t.prefs, r["transfer_budget_remaining"]),
                "fiabilite": t.ctx.status("finance.transfer_budget_remaining")}

    @T("get_wage_budget", "Budget salarial hebdomadaire et masse salariale actuelle.", "lecture")
    def get_wage_budget(t: ToolContext, a: NoArgs):
        rows = t.repo.finances(t.ctx, months=1)
        if not rows:
            raise LookupError("Aucune donnée financière dans la sauvegarde pour le club géré.")
        r = rows[0]
        marge = None
        if r["wage_budget_weekly"] is not None and r["wage_payroll_weekly"] is not None:
            marge = r["wage_budget_weekly"] - r["wage_payroll_weekly"]
        return {"mois": r["month"].isoformat(), "budget_hebdo": money(t.prefs, r["wage_budget_weekly"]),
                "masse_hebdo": money(t.prefs, r["wage_payroll_weekly"]), "marge_hebdo": money(t.prefs, marge)}

    @T("get_active_tactics", "Tactiques enregistrées du club (nom, style, mentalité, postes). Instructions détaillées non décodées.", "lecture")
    def get_active_tactics(t: ToolContext, a: NoArgs):
        rows = [r for r in t.repo.tactics(t.ctx) if r["club_uid"] == t.ctx.club_uid]
        return ToolResult("", True, data=[
            {"nom": r["name"], "style": r["style_name"], "mentalite": r["mentality"], "equipe_slot": r["team_slot"],
             "index": r["idx"], "postes": [ (sl.get("in_possession_positions") or [None])[0] for sl in (r["slots"] or []) ]}
            for r in rows
        ], limitations=["Les instructions collectives/individuelles et les rôles sont stockés sous forme codée non confirmée : non interprétés."])

    @T("get_injured_players", "Historique des blessures connues du club (pas l'état médical du jour).", "lecture")
    def get_injured_players(t: ToolContext, a: NoArgs):
        rows = t.repo.injuries(t.ctx, club_uid=t.ctx.club_uid)
        return ToolResult("", True, data=[
            {"joueur": r["player_name"], "date": r["date"].isoformat() if r["date"] else None, "type": r["type_name"], "nature": r["kind"]}
            for r in rows[:30]
        ], limitations=["La sauvegarde n'expose pas la disponibilité du jour : ceci est l'historique des blessures conservé, pas la liste des blessés actuels."])

    @T("get_transfer_history", "Changements de club observés entre synchronisations (transferts détectés).", "lecture", PlayerRef)
    def get_transfer_history(t: ToolContext, a: PlayerRef):
        row = _resolve_player(t, a)
        hist = t.repo.player_history(t.ctx, row["uid"])
        moves = [h for h in hist if h["change"] and "club_uid" in h["change"]]
        return ToolResult("", True, data={"joueur": row["name"], "club_actuel": row["club_name"],
            "mouvements": [{"date_jeu": h["game_date"].isoformat() if h["game_date"] else None, "nouveau_club": h["club_name"]} for h in moves]},
            limitations=["Seuls les changements observés entre deux synchronisations sont connus ; les montants des transferts ne sont pas lus."])

    @T("search_players", "Recherche multicritère dans TOUTE la base de la sauvegarde (poste, âge, valeur, salaire, contrat, attributs).", "lecture", SearchArgs)
    def search_players(t: ToolContext, a: SearchArgs):
        try:
            max_value = _to_raw(t, a.max_value)
            max_wage = _to_raw(t, a.max_wage)
        except UncalibratedCurrency as exc:
            raise ValueError(str(exc)) from exc
        expires = None
        if a.contract_expires_within_months is not None and t.ctx.game_date:
            expires = t.ctx.game_date + timedelta(days=round(a.contract_expires_within_months * 30.44))
        total, rows = t.repo.search_players(
            t.ctx, position=a.position, min_age=a.min_age, max_age=a.max_age, max_value=max_value, max_wage=max_wage,
            exclude_club_uid=None if a.include_own_club else t.ctx.club_uid, contract_expires_before=expires,
            name=a.name, attribute_min=a.attribute_min, order_by=a.order_by, limit=a.limit, offset=a.offset,
        )
        return ToolResult("", True, data={"total": total, "resultats": [player_summary(r, t.prefs) for r in rows]},
                          limitations=[FOG_LIMITATION])

    @T("compare_players", "Compare 2 à 5 joueurs (attributs visibles, âge, valeur, salaire, contrat, stats de la saison, compatibilité).", "lecture", CompareArgs)
    def compare_players(t: ToolContext, a: CompareArgs):
        out = []
        role = role_with_adjustments(a.role, None) if a.role else None
        for uid in a.player_uids:
            row = t.repo.player(t.ctx, uid)
            if row is None:
                raise LookupError(f"Joueur uid {uid} introuvable dans la sauvegarde active.")
            full = player_full(row, t.prefs)
            stats = [r for r in t.repo.season_stats(t.ctx, player_uid=uid, season_start_year=t.ctx.season_start_year) if r["kind"] == "overall"]
            full["stats_saison"] = [_stat_view(r) for r in stats]
            if role:
                full["compatibilite"] = score_player(row, role).as_dict()
            out.append(full)
        return ToolResult("", True, data=out, limitations=[FOG_LIMITATION])

    @T("search_expiring_contracts", "Joueurs dont le contrat se termine dans N mois (date du jeu).", "lecture", ExpiringArgs)
    def search_expiring_contracts(t: ToolContext, a: ExpiringArgs):
        if t.ctx.game_date is None:
            raise LookupError("Date de jeu inconnue.")
        until = t.ctx.game_date + timedelta(days=round(a.months * 30.44))
        _total, rows = t.repo.search_players(
            t.ctx, club_uid=t.ctx.club_uid if a.scope == "club" else None, contract_expires_before=until,
            order_by="transfer_value", limit=a.limit,
        )
        rows = [r for r in rows if r["contract_end"] and r["contract_end"] >= t.ctx.game_date]
        return {"jusqu_au": until.isoformat(), "total": len(rows), "joueurs": [player_summary(r, t.prefs) for r in rows]}

    @T("get_top_players_stat", "Classement des joueurs sur une statistique de saison archivée (buteurs, passeurs, notes...).", "lecture", TopStatArgs)
    def get_top_players_stat(t: ToolContext, a: TopStatArgs):
        season = _season(t, a.season_start_year, a.relative_season)
        rows = t.repo.season_stats(t.ctx, season_start_year=season, kind="overall",
                                   club_uid=t.ctx.club_uid if a.scope == "club" else None)
        rows = [r for r in rows if r[a.stat] is not None]
        rows.sort(key=lambda r: r[a.stat], reverse=True)
        lim = []
        if not rows:
            archived = t.repo.archived_seasons(t.ctx)
            lim.append(f"Aucune statistique archivée pour {season_label(season)} ({'club géré' if a.scope == 'club' else 'tous joueurs'}). "
                       f"Saisons archivées : {', '.join(season_label(x) for x in archived) or 'aucune'}.")
        return ToolResult("", True, data={"saison": season_label(season), "statistique": a.stat, "portee": a.scope,
                                          "classement": [{"joueur": r["player_name"], "uid": r["player_uid"], "club": r["club_name"], "valeur": r[a.stat],
                                                          "minutes": r["minutes"]} for r in rows[: a.limit]]}, limitations=lim)

    @T("get_alerts", "Alertes proactives actives (contrats, profondeur, forme, finances).", "lecture")
    def get_alerts(t: ToolContext, a: NoArgs):
        return [{"regle": r["rule"], "gravite": r["severity"], "message": r["message"], "donnees": r["data"]} for r in t.repo.alerts(t.ctx)]

    reg.register(ToolSpec("get_tactical_instructions", "Instructions tactiques détaillées.", "lecture", NoArgs, None, False,
                          "Les réglages tactiques sont stockés dans un format codé non confirmé (fmsave : valeurs brutes)."))
    reg.register(ToolSpec("get_club_staff", "Personnel du club.", "lecture", NoArgs, None, False,
                          "Non encore implémenté : fmsave ne lit qu'une partie des attributs du staff."))

    # ---------------------------------------------------------------- analyse
    @T("analyze_squad", "Bilan d'effectif déterministe : profondeur par poste, âges, contrats, valeurs.", "analyse")
    def analyze_squad(t: ToolContext, a: NoArgs):
        _require_club(t)
        squad = t.repo.squad(t.ctx)
        groups = {}
        for g, codes in POSITION_GROUPS.items():
            members = [p for p in squad if codes & set(split_positions(p["positions"]))]
            ages = [p["age"] for p in members if p["age"]]
            groups[g] = {"nombre": len(members), "joueurs": [p["name"] for p in members],
                         "age_moyen": round(sum(ages) / len(ages), 1) if ages else None}
        ages = [p["age"] for p in squad if p["age"]]
        buckets = Counter("≤21" if x <= 21 else "22-25" if x <= 25 else "26-29" if x <= 29 else "30+" for x in ages)
        return {
            "effectif": len(squad),
            "age_moyen": round(sum(ages) / len(ages), 1) if ages else None,
            "repartition_ages": dict(buckets),
            "postes": groups,
            "contrats_a_surveiller": [a_["message"] for a_ in contract_alerts(t.ctx, squad)],
            "manques_profondeur": [a_["message"] for a_ in depth_alerts(t.ctx, squad)],
            "valeur_totale": money(t.prefs, sum(p["transfer_value"] or 0 for p in squad) if squad else None),
            "methode": "Postes naturels (note ≥ 18) ; seuils de profondeur : clubdirector/proactive/rules.py",
        }

    @T("identify_weak_positions", "Postes sous-dotés (règles de profondeur déterministes).", "analyse")
    def identify_weak_positions(t: ToolContext, a: NoArgs):
        _require_club(t)
        return [x["data"] | {"message": x["message"]} for x in depth_alerts(t.ctx, t.repo.squad(t.ctx))]

    @T("analyze_tactical_fit", "Compatibilité explicable (0-100) d'un joueur avec un rôle.", "analyse", FitArgs)
    def analyze_tactical_fit(t: ToolContext, a: FitArgs):
        row = t.repo.player(t.ctx, a.player_uid)
        if row is None:
            raise LookupError(f"Joueur uid {a.player_uid} introuvable.")
        return {"joueur": row["name"], **score_player(row, role_with_adjustments(a.role, None)).as_dict()}

    @T("find_recruitment_targets", "Cibles de recrutement classées par compatibilité avec un rôle, filtrées par âge/valeur/salaire. Joueurs réels de la sauvegarde.", "analyse", TargetsArgs)
    def find_recruitment_targets(t: ToolContext, a: TargetsArgs):
        role = role_with_adjustments(a.role, a.extra_weights)
        try:
            max_value, max_wage = _to_raw(t, a.max_value), _to_raw(t, a.max_wage)
        except UncalibratedCurrency as exc:
            raise ValueError(str(exc)) from exc
        pool: dict[int, dict] = {}
        for pos in role.positions:
            _, rows = t.repo.search_players(
                t.ctx, position=pos, min_age=a.min_age, max_age=a.max_age, max_value=max_value, max_wage=max_wage,
                exclude_club_uid=t.ctx.club_uid, order_by="transfer_value", limit=a.candidate_pool,
            )
            pool.update({r["uid"]: r for r in rows})
        scored = []
        for r in pool.values():
            fit = score_player(r, role)
            if fit.score is not None:
                scored.append((fit, r))
        scored.sort(key=lambda x: x[0].score, reverse=True)
        return ToolResult("", True, data={
            "role": role.label, "candidats_evalues": len(pool), "methode": METHOD,
            "cibles": [player_summary(r, t.prefs) | {"compatibilite": f.score, "points_forts": f.strengths,
                        "points_faibles": f.weaknesses, "meilleur_poste": f.best_position} for f, r in scored[: a.limit]],
        }, limitations=[FOG_LIMITATION, "Le pool de candidats est limité aux joueurs les plus valorisés respectant les filtres (paramètre candidate_pool)."])

    @T("estimate_wage_affordability", "Vérifie si une indemnité et un salaire tiennent dans les budgets actuels.", "analyse", AffordArgs)
    def estimate_wage_affordability(t: ToolContext, a: AffordArgs):
        rows = t.repo.finances(t.ctx, months=1)
        if not rows:
            raise LookupError("Aucune donnée financière pour le club géré.")
        r = rows[0]
        if not t.prefs.currency.calibrated:
            raise ValueError(str(UncalibratedCurrency()))
        out = {"mois_reference": r["month"].isoformat()}
        if a.fee is not None:
            remaining = t.prefs.currency.to_display(r["transfer_budget_remaining"])
            out["indemnite"] = {"demandee": a.fee, "budget_restant": remaining,
                                "faisable": remaining is not None and a.fee <= remaining,
                                "ecart": None if remaining is None else remaining - a.fee}
        if a.weekly_wage is not None:
            budget = t.prefs.currency.to_display(r["wage_budget_weekly"])
            payroll = t.prefs.currency.to_display(r["wage_payroll_weekly"])
            margin = None if budget is None or payroll is None else budget - payroll
            out["salaire"] = {"demande_hebdo": a.weekly_wage, "marge_hebdo": margin,
                              "faisable": margin is not None and a.weekly_wage <= margin}
        lim = t.prefs.limits
        out["limites_utilisateur"] = {
            "indemnite_max": lim.max_fee, "salaire_max": lim.max_wage,
            "respecte_indemnite_max": None if lim.max_fee is None or a.fee is None else a.fee <= lim.max_fee,
            "respecte_salaire_max": None if lim.max_wage is None or a.weekly_wage is None else a.weekly_wage <= lim.max_wage,
        }
        return out

    @T("analyze_contract_risks", "Contrats du club expirant dans les 18 mois, classés par urgence.", "analyse")
    def analyze_contract_risks(t: ToolContext, a: NoArgs):
        _require_club(t)
        items = contract_alerts(t.ctx, t.repo.squad(t.ctx))
        return sorted((x["data"] | {"message": x["message"], "gravite": x["severity"]} for x in items), key=lambda d: d["months_left"])

    @T("evaluate_youth_prospects", "Jeunes du club (≤ 21 ans) avec temps de jeu de la saison.", "analyse")
    def evaluate_youth_prospects(t: ToolContext, a: NoArgs):
        _require_club(t)
        young = [p for p in t.repo.squad(t.ctx, team_slot=None) if p["age"] is not None and p["age"] <= 21]
        out = []
        for p in young:
            st = [r for r in t.repo.season_stats(t.ctx, player_uid=p["uid"], season_start_year=t.ctx.season_start_year) if r["kind"] == "overall"]
            item = player_summary(p, t.prefs) | {"minutes_saison": sum(r["minutes"] or 0 for r in st) if st else None}
            out.append(item)
        lim = [] if advanced_allowed(t.prefs) else ["Potentiel (PA) masqué en mode réaliste/analyste."]
        return ToolResult("", True, data=out, limitations=lim)

    for name, desc in [("evaluate_transfer_value", "Évaluation d'un prix de transfert."),
                       ("generate_scout_report", "Rapport de recrutement rédigé."),
                       ("plan_transfer_window", "Plan de mercato complet."),
                       ("analyze_player_performance", "Analyse fine des performances (par 90 min)."),
                       ("build_transfer_shortlist", "Shortlist interne persistante.")]:
        reg.register(ToolSpec(name, desc, "analyse", NoArgs, None, False, "Non encore implémenté (prévu phases 5-7)."))

    # ---------------------------------------------------------------- mémoire
    @T("remember", "Mémorise une préférence, un objectif, une décision ou une cible de l'utilisateur.", "memoire", MemoryArgs)
    def remember(t: ToolContext, a: MemoryArgs):
        from clubdirector.memory.store import MemoryStore

        mid = MemoryStore(t.engine).add(t.ctx.career_id, a.kind, a.text, key=a.key,
                                        value={"value": a.value, "player_uid": a.player_uid}, game_date=t.ctx.game_date)
        return {"memoire_id": mid, "enregistre": a.text}

    @T("list_memories", "Préférences, objectifs et décisions mémorisés pour cette carrière.", "memoire")
    def list_memories(t: ToolContext, a: NoArgs):
        from clubdirector.memory.store import MemoryStore

        return MemoryStore(t.engine).list(t.ctx.career_id)

    @T("forget", "Désactive un souvenir (sur demande explicite de l'utilisateur).", "memoire", ForgetArgs)
    def forget(t: ToolContext, a: ForgetArgs):
        from clubdirector.memory.store import MemoryStore

        return {"desactive": MemoryStore(t.engine).deactivate(t.ctx.career_id, a.memory_id)}

    # ---------------------------------------------------------------- actions (non prouvées)
    for name, desc in [
        ("add_player_to_shortlist", "Ajouter un joueur à la liste de recrutement FM26."),
        ("remove_player_from_shortlist", "Retirer un joueur de la liste de recrutement FM26."),
        ("assign_scout", "Assigner un recruteur."),
        ("submit_transfer_offer", "Envoyer une offre de transfert dans FM26."),
        ("read_transfer_response", "Lire la réponse du club vendeur dans FM26."),
        ("submit_counter_offer", "Envoyer une contre-proposition."),
        ("submit_contract_proposal", "Envoyer une proposition de contrat."),
        ("withdraw_offer", "Retirer une offre."),
    ]:
        reg.register(ToolSpec(name, desc, "action", ActionArgs, None, False, NOT_PROVEN, requires_approval=True))
    for name, desc in [("prepare_transfer_offer", "Préparer une offre (sans l'envoyer)."),
                       ("prepare_counter_offer", "Préparer une contre-proposition."),
                       ("prepare_contract_proposal", "Préparer une proposition de contrat.")]:
        reg.register(ToolSpec(name, desc, "action", ActionArgs, None, False,
                              "Moteur de négociation à règles prévu en phase 6 ; non encore implémenté."))
    register_game_table_tools(reg)
    return reg


def position_labels() -> dict[str, str]:
    return dict(LABEL_FR)


__all__ = ["build_registry", "normalize_position", "position_labels"]
