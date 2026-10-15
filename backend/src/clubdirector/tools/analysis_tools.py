"""Outils d'analyse rédigés : performance par 90 minutes, rapport de recrutement, plan de mercato, dossiers.

Tout vient de la sauvegarde (statistiques de la saison en cours, attributs visibles, contrats, offres
réelles, finances) et des décisions de l'entraîneur (mémoire) ; les prix sont les estimations à règles
du moteur du marché. Aucune valeur inventée : une donnée absente est dite absente.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from sqlalchemy import text

from clubdirector.memory.decisions import CoachRules, coach_rules
from clubdirector.positions import LABEL_FR, split_positions
from clubdirector.proactive.rules import depth_alerts
from clubdirector.recruitment.roles import ROLES
from clubdirector.recruitment.scoring import score_player
from clubdirector.tools.presenters import FOG_LIMITATION, player_full, player_summary
from clubdirector.tools.registry import ToolArgs, ToolContext, ToolRegistry, ToolResult
from clubdirector.transfers.dossiers import DossierStore, dossier_view
from clubdirector.transfers.market import POSITION_GROUP, Market, main_position, valuation

# Statistiques par 90 minutes retenues pour chaque groupe de postes ; False = plus bas est meilleur.
METRICS: dict[str, list[tuple[str, str, bool]]] = {
    "GK": [("save_percent", "arrêts (%)", True), ("expected_goals_prevented_per_90", "buts évités (xG) /90", True),
           ("goals_allowed_per_90", "buts encaissés /90", False), ("pass_completion_percent", "passes réussies (%)", True)],
    "DC": [("interceptions_per_90", "interceptions /90", True), ("tackles_completed_per_90", "tacles réussis /90", True),
           ("headers_won_per_90", "duels aériens gagnés /90", True), ("headers_won_percent", "duels aériens (%)", True),
           ("clearances_per_90", "dégagements /90", True), ("progressive_passes_per_90", "passes progressives /90", True),
           ("pass_completion_percent", "passes réussies (%)", True), ("possession_lost_per_90", "ballons perdus /90", False)],
    "LAT": [("tackles_completed_per_90", "tacles réussis /90", True), ("interceptions_per_90", "interceptions /90", True),
            ("crosses_completed_per_90", "centres réussis /90", True), ("key_passes_per_90", "passes clés /90", True),
            ("progressive_passes_per_90", "passes progressives /90", True), ("dribbles_per_90", "dribbles /90", True),
            ("high_intensity_sprints_per_90", "sprints /90", True), ("distance_km_per_90", "distance (km) /90", True)],
    "MIL": [("progressive_passes_per_90", "passes progressives /90", True), ("key_passes_per_90", "passes clés /90", True),
            ("passes_completed_per_90", "passes réussies /90", True), ("pass_completion_percent", "passes réussies (%)", True),
            ("possession_won_per_90", "ballons récupérés /90", True), ("interceptions_per_90", "interceptions /90", True),
            ("tackles_completed_per_90", "tacles réussis /90", True), ("pressures_completed_per_90", "pressings réussis /90", True),
            ("distance_km_per_90", "distance (km) /90", True)],
    "OFF": [("goals_per_90", "buts /90", True), ("assists_per_90", "passes décisives /90", True),
            ("expected_goals_per_90", "xG /90", True), ("expected_assists_per_90", "xA /90", True),
            ("key_passes_per_90", "passes clés /90", True), ("clear_cut_chances_created_per_90", "occasions franches créées /90", True),
            ("dribbles_per_90", "dribbles /90", True), ("crosses_completed_per_90", "centres réussis /90", True)],
    "ATT": [("goals_per_90", "buts /90", True), ("non_penalty_expected_goals_per_90", "xG hors penalty /90", True),
            ("shots_per_90", "tirs /90", True), ("shots_on_target_per_90", "tirs cadrés /90", True),
            ("conversion_percent", "réussite devant le but (%)", True), ("assists_per_90", "passes décisives /90", True),
            ("expected_assists_per_90", "xA /90", True), ("headers_won_per_90", "duels aériens gagnés /90", True)],
}
GROUP_CODES = {"GK": ("GK",), "DC": ("DC", "SW"), "LAT": ("DL", "DR", "WBL", "WBR"), "MIL": ("DM", "MC"),
               "OFF": ("ML", "MR", "AML", "AMR", "AMC"), "ATT": ("STC",)}
GROUP_FR = {"GK": "gardiens", "DC": "défenseurs centraux", "LAT": "latéraux", "MIL": "milieux", "OFF": "milieux offensifs et ailiers",
            "ATT": "attaquants"}
COMP_FR = {"overall": "toutes compétitions", "league": "championnat", "cup": "coupes", "continental": "coupes d'Europe"}
DEPTH_ROLE = {"GB": "gardien", "DC": "dc_stoppeur", "Latéraux": "lateral_offensif", "Milieux défensifs/centraux": "box_to_box",
              "Ailiers/Milieux offensifs": "ailier_interieur", "Attaquants": "avant_centre_complet"}
PERF_METHOD = ("Statistiques de la saison en cours (dernier relevé de la sauvegarde) ramenées à 90 minutes ; percentile = part "
               "des joueurs du même groupe de postes, ayant au moins le minimum de minutes dans la même compétition et le "
               "même championnat, qui font moins bien (100 = meilleur).")


class PlayerArgs(ToolArgs):
    player_uid: int | None = Field(None, description="Identifiant du joueur (uid).")
    name: str | None = Field(None, description="Nom du joueur si l'uid est inconnu.")


class PerformanceArgs(PlayerArgs):
    competitions: Literal["overall", "league", "cup", "continental"] = Field(
        "overall", description="Périmètre : toutes compétitions (overall), championnat, coupes, coupes d'Europe.")
    min_minutes: int = Field(450, ge=0, le=5000, description="Minutes minimum des joueurs de comparaison.")


class PlanArgs(ToolArgs):
    cibles_par_poste: int = Field(3, ge=1, le=6, description="Nombre de cibles proposées par poste à renforcer.")


class DossierArgs(ToolArgs):
    ouverts_seulement: bool = Field(False, description="True : seulement les dossiers encore ouverts.")


def _player(t: ToolContext, uid: int | None, name: str | None) -> dict:
    from clubdirector.tools.transfer_tools import _player as resolve

    return resolve(t, uid, name)


def _rows(t: ToolContext, sql: str, **params) -> list[dict]:
    try:
        with t.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), params)]
    except Exception:  # noqa: BLE001 — miroir absent avant la synchronisation qui le remplit
        return []


def _group(player: dict) -> str | None:
    return POSITION_GROUP.get(main_position(player) or "")


def _league_clubs(t: ToolContext, club_uid: int | None) -> tuple[set[int], str | None]:
    """Clubs du championnat d'un club (classement du dernier relevé) et nom de la compétition."""
    if club_uid is None:
        return set(), None
    own = _rows(t, """
        SELECT snapshot_id, competition_id FROM league_tables WHERE career_id = :k AND club_uid = :c
          AND coalesce(team_slot, 0) = 0 AND competition_id IS NOT NULL
        ORDER BY snapshot_id DESC LIMIT 1""", k=t.ctx.career_id, c=club_uid)
    if not own:
        return set(), None
    rows = _rows(t, """
        SELECT club_uid, competition_name FROM league_tables WHERE career_id = :k AND snapshot_id = :snap
          AND competition_id = :comp AND coalesce(team_slot, 0) = 0""",
                 k=t.ctx.career_id, snap=own[0]["snapshot_id"], comp=own[0]["competition_id"])
    return {r["club_uid"] for r in rows if r["club_uid"]}, next((r["competition_name"] for r in rows if r["competition_name"]), None)


# ------------------------------------------------------------------------------ performance
def performance(t: ToolContext, p: dict, kind: str = "overall", min_minutes: int = 450) -> dict:
    """Profil par 90 minutes d'un joueur, comparé aux joueurs du même groupe de postes dans son championnat."""
    group = _group(p)
    if group is None:
        raise LookupError(f"Poste de {p['name']} inconnu dans la sauvegarde : comparaison impossible.")
    metrics = METRICS[group]
    cols = ", ".join(f'"{m[0]}"' for m in metrics)
    mine = _rows(t, f"SELECT club_name, minutes, starts, substitute_appearances, average_rating, goals, assists, {cols} "
                    "FROM fm_player_season_stats WHERE career_id = :k AND player_uid = :u AND kind = :kind "
                    "ORDER BY coalesce(team_slot, 0) = 0 DESC, minutes DESC LIMIT 1", k=t.ctx.career_id, u=p["uid"], kind=kind)
    if not mine or not mine[0].get("minutes"):
        return {"joueur": p["name"], "club": p.get("club_name"), "minutes": 0, "metriques": [],
                "message": f"Aucune minute de {p['name']} cette saison ({COMP_FR[kind]}) dans la sauvegarde."}
    me = mine[0]
    clubs, comp_name = _league_clubs(t, p.get("club_uid"))
    like = " OR ".join(f"p.positions LIKE '%,{c},%'" for c in GROUP_CODES[group])
    club_filter = f"AND s.club_uid IN ({', '.join(str(int(c)) for c in clubs)})" if clubs else ""
    peers = _rows(t, f"""
        SELECT s.player_uid, s.average_rating, {', '.join(f's."{m[0]}"' for m in metrics)}
        FROM fm_player_season_stats s JOIN players_current p ON p.career_id = s.career_id AND p.uid = s.player_uid
        WHERE s.career_id = :k AND s.kind = :kind AND coalesce(s.minutes, 0) >= :m AND coalesce(s.team_slot, 0) = 0
          AND ({like}) {club_filter}""",
                  k=t.ctx.career_id, kind=kind, m=min_minutes)
    peers = [x for x in peers if x["player_uid"] != p["uid"]]
    out_metrics = []
    for col, label, higher in [*metrics, ("average_rating", "note moyenne", True)]:
        value = me.get(col)
        values = [x[col] for x in peers if x.get(col) is not None]
        if value is None:
            out_metrics.append({"statistique": label, "valeur": None, "percentile": None})
            continue
        better = sum(1 for v in values if (v < value if higher else v > value))
        rank = 1 + sum(1 for v in values if (v > value if higher else v < value))
        pct = round(100 * better / len(values)) if values else None
        out_metrics.append({"statistique": label, "valeur": round(float(value), 2), "percentile": pct,
                            "rang": rank if values else None, "sur": len(values) + 1 if values else None})
    strengths = [m["statistique"] for m in out_metrics if m.get("percentile") is not None and m["percentile"] >= 70]
    weaknesses = [m["statistique"] for m in out_metrics if m.get("percentile") is not None and m["percentile"] <= 30]
    return {
        "joueur": p["name"], "club": me.get("club_name") or p.get("club_name"), "groupe": GROUP_FR[group],
        "competitions": COMP_FR[kind], "minutes": me["minutes"], "titularisations": me.get("starts"),
        "entrees": me.get("substitute_appearances"), "buts": me.get("goals"), "passes_decisives": me.get("assists"),
        "note_moyenne": round(me["average_rating"], 2) if me.get("average_rating") else None,
        "comparaison": f"{len(peers)} {GROUP_FR[group]} avec au moins {min_minutes} minutes"
                       + (f" en {comp_name}" if comp_name and clubs else " (toute la base)"),
        "metriques": out_metrics, "points_forts": strengths, "points_faibles": weaknesses, "methode": PERF_METHOD,
    }


# ------------------------------------------------------------------------------ rapport de recrutement
def _constraints(t: ToolContext, p: dict, rules: CoachRules, val: dict | None) -> list[str]:
    """Décisions de l'entraîneur que le joueur ne respecte pas (âge, indemnité, salaire, vente refusée)."""
    fmt, out = t.prefs.currency.format, []
    ours = p.get("club_uid") == t.ctx.club_uid
    if ours:
        if p["uid"] in rules.never_sell:
            out.append("joueur que l'entraîneur a décidé de ne pas vendre")
        return out
    if rules.max_age is not None and p.get("age") is not None and p["age"] > rules.max_age:
        out.append(f"{p['age']} ans : au-dessus de l'âge maximum fixé par l'entraîneur ({rules.max_age} ans)")
    if val:
        target = val["achat"]["cible"]
        if rules.max_fee is not None and t.prefs.currency.to_display(target) and t.prefs.currency.to_display(target) > rules.max_fee:
            out.append(f"prix cible {fmt(target)} au-dessus de l'indemnité maximale fixée ({rules.max_fee:,.0f} €)".replace(",", " "))
    if rules.max_wage is not None and p.get("wage") and (t.prefs.currency.to_display(p["wage"]) or 0) > rules.max_wage:
        out.append(f"salaire actuel {fmt(p['wage'])} déjà au-dessus du salaire maximum fixé")
    return out


def scout_report(t: ToolContext, p: dict) -> ToolResult:
    fmt = t.prefs.currency.format
    rules = coach_rules(t.engine, t.ctx.career_id, t.prefs)
    market = Market(t.engine, t.ctx.career_id, t.ctx.game_date, t.ctx.club_uid)
    ours = p.get("club_uid") == t.ctx.club_uid
    full = player_full(p, t.prefs)
    attrs = {k: v for k, v in (full.get("attributs") or {}).items() if isinstance(v, int | float)}
    labels = full.get("libelles_attributs") or {}
    top = sorted(attrs.items(), key=lambda kv: kv[1], reverse=True)[:6]
    low = sorted(attrs.items(), key=lambda kv: kv[1])[:4]
    positions = split_positions(p.get("positions"))
    fits = []
    for role in ROLES.values():
        if set(role.positions) & set(positions):
            f = score_player(p, role)
            if f.score is not None:
                fits.append((f.score, role.label))
    fits.sort(reverse=True)
    val = valuation(market, p)
    ranks = market.rankings(p["uid"])
    offers = market.offers(player_uid=p["uid"], limit=50)
    interested = sorted({o["bidding_club_name"] for o in offers if o.get("bidding_club_name") and o.get("bidding_club_uid") != p.get("club_uid")})
    budget = (t.repo.finances(t.ctx, months=1) or [{}])[0].get("transfer_budget_remaining") if t.ctx.club_uid else None
    try:
        perf = performance(t, p)
    except LookupError:
        perf = None
    issues = _constraints(t, p, rules, None if ours else val)
    over_budget = not ours and budget is not None and val["achat"]["cible"] > budget
    best_fit = fits[0][0] if fits else None
    best_rank = ranks[0] if ranks else None
    if ours:
        verdict = "joueur du club (évaluation interne)"
    elif issues:
        verdict = "hors critères de l'entraîneur"
    elif over_budget:
        verdict = "hors budget actuel (à financer par des ventes)"
    elif best_fit is not None and best_fit >= 70 and (best_rank is None or best_rank["rank"] <= 150):
        verdict = "prioritaire"
    elif best_fit is not None and best_fit >= 55:
        verdict = "à suivre"
    else:
        verdict = "pas prioritaire"
    age = f"{p['age']} ans" if p.get("age") is not None else "âge non lu"
    pos_fr = ", ".join(LABEL_FR.get(x, x) for x in positions) or "poste non lu"
    end = p.get("contract_end")
    paras = [f"{p['name']} ({age}, {p.get('club_name') or 'sans club'}) — {pos_fr}. Contrat jusqu'au "
             f"{end.strftime('%d/%m/%Y') if end else 'date non lue'}, salaire {fmt(p['wage']) if p.get('wage') else 'non lu'} "
             f"par semaine, valeur du jeu {fmt(p.get('transfer_value'))}."]
    if top:
        paras.append("Points forts (attributs visibles) : " + ", ".join(f"{labels.get(k, k)} {v}" for k, v in top)
                     + ". Points faibles : " + ", ".join(f"{labels.get(k, k)} {v}" for k, v in low) + ".")
    if fits:
        paras.append("Meilleurs rôles (score de compatibilité 0-100) : " + ", ".join(f"{lbl} {sc:.0f}" for sc, lbl in fits[:2]) + ".")
    if perf and perf.get("metriques"):
        bits = [f"{perf['minutes']} minutes", f"note moyenne {perf['note_moyenne']}" if perf.get("note_moyenne") else None]
        line = "Saison en cours : " + ", ".join(b for b in bits if b)
        if perf["points_forts"]:
            line += " ; au-dessus de ses pairs en " + ", ".join(perf["points_forts"][:4])
        if perf["points_faibles"]:
            line += " ; en dessous en " + ", ".join(perf["points_faibles"][:3])
        paras.append(line + f" ({perf['comparaison']}).")
    elif perf:
        paras.append(perf.get("message", "Pas de minutes cette saison."))
    market_line = (f"Marché : estimation {fmt(val['estimation'])}" + ("" if ours else f", première offre {fmt(val['achat']['premiere_offre'])}, "
                   f"cible {fmt(val['achat']['cible'])}, plafond {fmt(val['achat']['plafond'])}"))
    if best_rank:
        market_line += f" ; classé {best_rank['rank']}e/{best_rank['total']} au poste {best_rank['position']} par le marché du jeu"
    if interested:
        market_line += f" ; offres enregistrées cette saison de : {', '.join(interested[:5])}"
    paras.append(market_line + ".")
    if issues:
        paras.append("Hors critères de l'entraîneur : " + " ; ".join(issues) + ".")
    if over_budget:
        paras.append(f"Budget : prix cible {fmt(val['achat']['cible'])} au-dessus du budget transferts restant ({fmt(budget)}).")
    paras.append(f"Verdict : {verdict}.")
    return ToolResult("", True, data={
        "joueur": p["name"], "uid": p["uid"], "verdict": verdict, "rapport": "\n\n".join(paras),
        "profil": player_summary(p, t.prefs), "attributs_forts": {labels.get(k, k): v for k, v in top},
        "attributs_faibles": {labels.get(k, k): v for k, v in low},
        "roles": [{"role": lbl, "score": sc} for sc, lbl in fits[:3]], "performance": perf,
        "marche": {"estimation": fmt(val["estimation"]), "achat": {k: fmt(v) for k, v in val["achat"].items()},
                   "classements": [{"poste": r["position"], "rang": r["rank"], "sur": r["total"]} for r in ranks[:3]],
                   "clubs_interesses": interested},
        "criteres_entraineur": rules.as_dict(), "alertes": issues, "hors_budget": over_budget,
    }, limitations=([] if ours else [FOG_LIMITATION]) + ["Prix : estimations à règles explicites (moteur du marché), pas des prix du jeu."])


# ------------------------------------------------------------------------------ plan de mercato
def transfer_plan(t: ToolContext, per_position: int = 3) -> ToolResult:
    ctx, fmt = t.ctx, t.prefs.currency.format
    if ctx.club_uid is None or ctx.game_date is None:
        raise LookupError("Club géré ou date du jeu inconnus.")
    rules = coach_rules(t.engine, ctx.career_id, t.prefs)
    market = Market(t.engine, ctx.career_id, ctx.game_date, ctx.club_uid)
    fin = (t.repo.finances(ctx, months=1) or [{}])[0]
    budget = fin.get("transfer_budget_remaining")
    margin = None if fin.get("wage_budget_weekly") is None or fin.get("wage_payroll_weekly") is None else \
        fin["wage_budget_weekly"] - fin["wage_payroll_weekly"]
    squad = t.repo.squad(ctx)
    lines = t.repo.season_lines(ctx, [p["uid"] for p in squad])
    top_minutes = max([(lines.get(p["uid"]) or {}).get("minutes") or 0 for p in squad] or [0]) or 1
    share = {p["uid"]: ((lines.get(p["uid"]) or {}).get("minutes") or 0) / top_minutes for p in squad}

    def months_left(p: dict) -> float | None:
        end = p.get("contract_end")
        return None if end is None else (end - ctx.game_date).days / 30.44

    renew, sell = [], []
    for p in squad:
        if p.get("on_loan") and p.get("loan_parent_club_uid") not in (None, ctx.club_uid):
            continue
        left = months_left(p)
        item = {"joueur": p["name"], "age": p.get("age"), "postes": split_positions(p.get("positions")),
                "valeur": fmt(p.get("transfer_value")), "fin_contrat": p["contract_end"].isoformat() if p.get("contract_end") else None,
                "part_du_temps_de_jeu": round(share[p["uid"]] * 100)}
        if p["uid"] in rules.never_sell:
            if left is not None and left <= 18:
                renew.append(item | {"raison": "joueur que l'entraîneur ne veut pas vendre, contrat à sécuriser"})
            continue
        if p["uid"] in rules.to_sell:
            sell.append(item | {"raison": "mis en vente par l'entraîneur", "priorite": 1})
        elif left is not None and left <= 12 and share[p["uid"]] >= 0.5:
            renew.append(item | {"raison": f"titulaire (≥ 50 % du temps de jeu), contrat fini dans {round(left)} mois"})
        elif left is not None and left <= 12:
            sell.append(item | {"raison": f"contrat fini dans {round(left)} mois et peu utilisé : vendre maintenant ou le "
                                          "laisser partir libre", "priorite": 2})
        elif share[p["uid"]] < 0.2 and (p.get("age") or 0) >= 24 and (p.get("transfer_value") or 0) > 0:
            sell.append(item | {"raison": f"{round(share[p['uid']] * 100)} % du temps de jeu à {p.get('age')} ans : vente ou prêt",
                                "priorite": 3})
    sell.sort(key=lambda x: (x["priorite"], -(x.get("part_du_temps_de_jeu") or 0)))
    sell = sell[:10]
    by_name = {p["name"]: p for p in squad}
    proceeds = sum(valuation(market, by_name[x["joueur"]])["plancher"] for x in sell if x["joueur"] in by_name)
    envelope = (budget or 0) + proceeds  # si les ventes proposées se font, au prix plancher estimé
    needs = depth_alerts(ctx, squad)
    max_raw = envelope
    try:
        if rules.max_fee is not None:
            max_raw = min(max_raw, t.prefs.currency.to_raw(rules.max_fee))
    except Exception:  # noqa: BLE001 — devise non étalonnée : seul le budget filtre
        pass
    arrivals = []
    for need in needs:
        role = ROLES.get(DEPTH_ROLE.get(need["data"]["group"], ""))
        if role is None:
            continue
        pool: dict[int, dict] = {}
        for pos in role.positions:
            _n, rows = t.repo.search_players(ctx, position=pos, max_age=rules.max_age, max_value=max_raw,
                                             exclude_club_uid=ctx.club_uid, order_by="transfer_value", limit=250)
            pool.update({r["uid"]: r for r in rows})
        scored = sorted(((score_player(r, role), r) for r in pool.values()), key=lambda x: x[0].score or 0, reverse=True)
        targets = []
        for fit, r in scored:
            if fit.score is None or len(targets) >= per_position:
                continue
            v = valuation(market, r)
            if v["achat"]["cible"] > max_raw:
                continue  # estimation au-dessus de l'enveloppe, même si la valeur du jeu y entre
            targets.append({"joueur": r["name"], "uid": r["uid"], "age": r.get("age"), "club": r.get("club_name"),
                            "compatibilite": fit.score, "prix_cible": fmt(v["achat"]["cible"]),
                            "plafond": fmt(v["achat"]["plafond"]), "fin_contrat": r["contract_end"].isoformat() if r.get("contract_end") else None})
        arrivals.append({"poste": need["data"]["group"], "constat": need["message"], "role_vise": role.label, "cibles": targets})
    received = market.offers(club_uid=ctx.club_uid, side="recues", state="en_cours", limit=20)
    made = market.offers(club_uid=ctx.club_uid, side="faites", state="en_cours", limit=20)
    dossiers = [dossier_view(d) for d in DossierStore(t.engine).list(ctx.career_id, open_only=True)]
    steps = []
    if rules.window_end:
        steps.append(f"Fenêtre : fermeture le {rules.window_end.strftime('%d/%m/%Y')} (date donnée par l'entraîneur).")
    if received:
        steps.append(f"Répondre aux {len(received)} offre(s) reçue(s) en cours (accepter, contre-proposer ou refuser).")
    if [s for s in sell if s["priorite"] == 1]:
        steps.append("Vendre d'abord les joueurs mis en vente par l'entraîneur : " + ", ".join(s["joueur"] for s in sell if s["priorite"] == 1) + ".")
    if renew:
        steps.append("Prolonger les contrats à sécuriser : " + ", ".join(r["joueur"] for r in renew[:5]) + ".")
    for a in arrivals:
        if a["cibles"]:
            steps.append(f"Renforcer {a['poste']} : cibles {', '.join(c['joueur'] for c in a['cibles'])}.")
    if not arrivals:
        steps.append("Aucun poste sous le seuil de profondeur : recruter seulement une opportunité de marché.")
    return ToolResult("", True, data={
        "date_du_jeu": ctx.game_date.isoformat(),
        "budget": {"transferts_restant": fmt(budget), "marge_salariale_hebdo": fmt(margin), "mois": str(fin.get("month") or "")[:10] or None,
                   "ventes_proposees_plancher": fmt(proceeds), "enveloppe_si_ventes": fmt(envelope)},
        "criteres_entraineur": rules.as_dict(), "priorites": steps, "a_renforcer": arrivals, "a_prolonger": renew,
        "a_vendre_ou_preter": sell, "offres_recues_en_cours": [
            {"joueur": o["player_name"], "club": o.get("bidding_club_name"), "montant": fmt(o.get("amount")),
             "date": str(o.get("offered_on") or "")[:10]} for o in received],
        "nos_offres_en_cours": [{"joueur": o["player_name"], "club": o.get("selling_club_name"), "montant": fmt(o.get("amount"))}
                                for o in made],
        "dossiers_ouverts": dossiers,
        "methode": ("Besoins : seuils de profondeur par poste (proactive/rules.py) ; cibles : compatibilité au rôle sur attributs "
                    "visibles, filtrées par l'âge maximum et l'indemnité maximale de l'entraîneur et par l'enveloppe (budget "
                    "restant + ventes proposées au prix plancher estimé) ; "
                    "ventes : décisions de l'entraîneur, contrat ≤ 12 mois, temps de jeu < 20 % ; prolongations : titulaires "
                    "(≥ 50 % du temps de jeu) dont le contrat finit dans 12 mois."),
    }, limitations=[FOG_LIMITATION, "Prix : estimations à règles explicites (moteur du marché).",
                    "Dates de la fenêtre : la sauvegarde ne rattache pas ses fenêtres de transferts à un pays ; seule une "
                    "date donnée par l'entraîneur est utilisée."])


def register_analysis_tools(reg: ToolRegistry) -> None:
    T = reg.tool

    @T("analyze_player_performance", "Analyse des performances d'un joueur par 90 minutes (saison en cours) : statistiques de "
       "son poste, percentile face aux joueurs du même poste de son championnat, points forts et faibles.", "analyse",
       PerformanceArgs)
    def analyze_player_performance(t: ToolContext, a: PerformanceArgs):
        p = _player(t, a.player_uid, a.name)
        return ToolResult("", True, data=performance(t, p, a.competitions, a.min_minutes),
                          limitations=["Saison en cours seulement (dernier relevé) ; moins de 450 minutes = échantillon faible."])

    @T("generate_scout_report", "Rapport de recrutement rédigé sur un joueur : profil, contrat, attributs forts et faibles, "
       "meilleurs rôles, performances par 90 minutes, prix estimé, classement du marché, clubs intéressés, critères de "
       "l'entraîneur (âge, budget) et verdict.", "analyse", PlayerArgs)
    def generate_scout_report(t: ToolContext, a: PlayerArgs):
        return scout_report(t, _player(t, a.player_uid, a.name))

    @T("plan_transfer_window", "Plan de mercato complet du club : budget, postes à renforcer avec cibles réelles, contrats à "
       "prolonger, joueurs à vendre ou prêter, offres en cours, dossiers ouverts et ordre des priorités (décisions de "
       "l'entraîneur appliquées).", "analyse", PlanArgs)
    def plan_transfer_window(t: ToolContext, a: PlanArgs):
        return transfer_plan(t, a.cibles_par_poste)

    @T("list_dossiers", "Dossiers du directeur sportif (achats, ventes, contre-offres, prolongations préparés) et leur suivi "
       "dans les sauvegardes : offre faite, reçue, conclue, échouée, joueur parti, contrat prolongé.", "lecture", DossierArgs)
    def list_dossiers(t: ToolContext, a: DossierArgs):
        rows = DossierStore(t.engine).list(t.ctx.career_id, open_only=a.ouverts_seulement)
        return {"nombre": len(rows), "dossiers": [dossier_view(r) for r in rows]}


__all__ = ["performance", "register_analysis_tools", "scout_report", "transfer_plan"]
