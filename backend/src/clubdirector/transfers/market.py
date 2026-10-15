"""Moteur du marché des transferts : offres réelles, valeur, acheteurs, ventes, achats, contrats.

Sources (sauvegarde FM26, miroirs fmsave) :
- `fm_transfer_offers` : toutes les offres de la fenêtre (transferts, prêts), avec club acheteur,
  club vendeur, montant, état et dates — l'intérêt RÉEL des clubs ;
- `fm_player_rankings` : classements du marché par poste tenus par le jeu (meilleur = rang 1) ;
- `fm_finances` : budget transferts restant, budget et masse salariale de 489 clubs ;
- `fm_clubs` (réputation), `players_current` (valeur, salaire, contrat, postes, âge).

Tout est calculé en unité stockée (« brut ») ; la présentation convertit en euros. Les prix,
plafonds et salaires proposés sont des ESTIMATIONS à règles explicites : chaque résultat porte sa
méthode et ses composantes, que le directeur cite sans les inventer.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Engine, text

# Postes des classements du jeu (fmsave PlayerRanking.position) ↔ codes ClubDirector.
RANKING_POSITION = {"GK": "GK", "DR": "DR", "DL": "DL", "DC": "DC", "WBR": "WBR", "WBL": "WBL", "DM": "DM",
                    "MR": "MR", "ML": "ML", "MC": "MC", "AMR": "AMR", "AML": "AML", "AMC": "AMC", "STC": "ST"}
POSITION_GROUP = {
    "GK": "GK", "SW": "DC", "DC": "DC", "DL": "LAT", "DR": "LAT", "WBL": "LAT", "WBR": "LAT",
    "DM": "MIL", "MC": "MIL", "ML": "OFF", "MR": "OFF", "AML": "OFF", "AMR": "OFF", "AMC": "OFF", "STC": "ATT",
}
OPEN, COMPLETED, FAILED = "en_cours", "conclue", "echouee"
STATE_LABEL = {"en_cours": "en cours", "conclue": "conclue", "echouee": "échouée", "accord_a_venir": "accord pour plus tard",
               "sans_suite": "sans suite"}
KIND_LABEL = {"transfer": "transfert", "loan": "prêt"}
METHOD_VALUE = (
    "Estimation = valeur de transfert du jeu × facteur contrat (durée restante) × facteur âge × facteur rang "
    "(place dans le classement du marché du poste) × facteur marché (prix réellement payés cette saison pour des "
    "joueurs de valeur comparable, médiane, mélangée à 50 %). Prix demandé = estimation × 1,15 ; plancher = × 0,9 ; "
    "à l'achat : première offre = × 0,8, cible = × 1,0, plafond = × 1,15."
)
METHOD_BUYERS = (
    "Score sur 100 : offre réelle déjà faite pour ce joueur (40), clubs ayant visé ce profil cette saison (15), "
    "budget transferts restant face au prix plancher (20), besoin au poste dans leur équipe première (15), "
    "réputation du club par rapport au nôtre (10). Clubs sans budget suffisant écartés (sauf offre réelle)."
)


def _rows(conn, sql: str, **params) -> list[dict]:
    try:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]
    except Exception:  # noqa: BLE001 — table miroir absente avant la première synchronisation r9
        return []


def months_between(a: date | None, b: date | None) -> float | None:
    if a is None or b is None:
        return None
    return round((b - a).days / 30.44, 1)


def positions_of(player: dict) -> list[str]:
    return [p for p in (player.get("positions") or "").split(",") if p]


def main_position(player: dict) -> str | None:
    pos = positions_of(player)
    ratings = player.get("position_ratings") or {}
    if isinstance(ratings, str):
        try:
            ratings = json.loads(ratings)
        except ValueError:
            ratings = {}
    if ratings:
        best = max(pos or ratings, key=lambda p: ratings.get(p) or 0, default=None)
        return best
    return pos[0] if pos else None


@dataclass
class Market:
    """Accès en lecture aux tables du marché pour une carrière."""

    engine: Engine
    career_id: int
    game_date: date | None
    club_uid: int | None

    # ------------------------------------------------------------------ données de base
    def player(self, uid: int) -> dict | None:
        with self.engine.connect() as c:
            rows = _rows(c, "SELECT * FROM players_current WHERE career_id = :k AND uid = :u", k=self.career_id, u=uid)
        if not rows:
            return None
        row = rows[0]
        for key in ("position_ratings", "attributes"):
            if isinstance(row.get(key), str):
                try:
                    row[key] = json.loads(row[key])
                except ValueError:
                    row[key] = None
        for key in ("contract_end", "contract_start", "birth_date"):
            if isinstance(row.get(key), str):
                row[key] = date.fromisoformat(row[key][:10])
        return row

    def club(self, uid: int | None) -> dict | None:
        if uid is None:
            return None
        with self.engine.connect() as c:
            rows = _rows(c, "SELECT uid, name, short_name, reputation FROM fm_clubs WHERE career_id = :k AND uid = :u",
                         k=self.career_id, u=uid)
        return rows[0] if rows else None

    def finances(self) -> dict[int, dict]:
        """Dernier mois connu de chaque club : budget transferts restant, budget et masse salariale."""
        with self.engine.connect() as c:
            rows = _rows(c, """
                SELECT f.club_uid, f.club_name, f.month, f.transfer_budget_allocated, f.transfer_budget_remaining,
                       f.wage_budget_weekly, f.wage_payroll_weekly, f.balance, c.reputation, c.short_name
                FROM fm_finances f
                JOIN (SELECT club_uid, max(month) AS m FROM fm_finances WHERE career_id = :k GROUP BY club_uid) last
                  ON last.club_uid = f.club_uid AND last.m = f.month
                LEFT JOIN fm_clubs c ON c.career_id = f.career_id AND c.uid = f.club_uid
                WHERE f.career_id = :k""", k=self.career_id)
        return {r["club_uid"]: r for r in rows}

    def ranking_sizes(self) -> dict[str, int]:
        """Nombre de joueurs de chaque classement (hommes), calculé une fois."""
        if not hasattr(self, "_sizes"):
            with self.engine.connect() as c:
                rows = _rows(c, "SELECT position, max(rank) AS n FROM fm_player_rankings WHERE career_id = :k AND women = 0 "
                                "GROUP BY position", k=self.career_id)
            self._sizes = {r["position"]: r["n"] for r in rows}
        return self._sizes

    def rankings(self, player_uid: int) -> list[dict]:
        """Places du joueur dans les classements du marché (hommes), du meilleur rang au moins bon."""
        with self.engine.connect() as c:
            rows = _rows(c, """
                SELECT position, rank, score FROM fm_player_rankings
                WHERE career_id = :k AND player_uid = :u AND women = 0 ORDER BY rank""", k=self.career_id, u=player_uid)
        sizes = self.ranking_sizes()
        for r in rows:
            r["total"] = sizes.get(r["position"])
        return rows

    def ranking_table(self, position: str, limit: int = 20, offset: int = 0) -> list[dict]:
        with self.engine.connect() as c:
            return _rows(c, """
                SELECT r.rank, r.score, r.player_uid, r.player_name, p.age, p.club_uid, p.club_name, p.transfer_value,
                       p.wage, p.contract_end
                FROM fm_player_rankings r
                LEFT JOIN players_current p ON p.career_id = r.career_id AND p.uid = r.player_uid
                WHERE r.career_id = :k AND r.position = :pos AND r.women = 0
                ORDER BY r.rank LIMIT :lim OFFSET :off""", k=self.career_id, pos=position, lim=limit, off=offset)

    # ------------------------------------------------------------------ offres réelles
    def offers(self, *, player_uid: int | None = None, club_uid: int | None = None, side: str = "toutes",
               state: str = "toutes", since: date | None = None, limit: int = 50) -> list[dict]:
        """Offres de transfert et de prêt (pas les mouvements internes ni le staff)."""
        conds = ["career_id = :k", "kind IN ('transfer', 'loan')", "player_uid IS NOT NULL"]
        params: dict[str, Any] = {"k": self.career_id, "lim": limit}
        if player_uid is not None:
            conds.append("player_uid = :p")
            params["p"] = player_uid
        if club_uid is not None:
            if side == "recues":
                conds.append("selling_club_uid = :c")
            elif side == "faites":
                conds.append("bidding_club_uid = :c")
            else:
                conds.append("(selling_club_uid = :c OR bidding_club_uid = :c)")
            params["c"] = club_uid
        if state == "en_cours":
            conds.append("status IS NULL")
        elif state == "conclues":
            conds.append("status = 'completed'")
        elif state == "echouees":
            conds.append("status = 'failed'")
        if since is not None:
            conds.append("offered_on >= :since")
            params["since"] = since.isoformat()
        with self.engine.connect() as c:
            rows = _rows(c, f"SELECT * FROM fm_transfer_offers WHERE {' AND '.join(conds)} "
                            "ORDER BY offered_on DESC, \"index\" DESC LIMIT :lim", **params)
        for r in rows:
            r["etat"] = offer_state(r, self.game_date)
        return rows

    def market_rows(self) -> list[dict]:
        """Toutes les offres (transferts, prêts) de la saison avec la valeur et les postes du joueur, lues une fois.

        Les offres d'abord, puis le joueur par sa clé : la base ne parcourt pas tous les joueurs."""
        if not hasattr(self, "_market"):
            with self.engine.connect() as c:
                self._market = _rows(c, """
                    SELECT o.bidding_club_uid, o.kind, o.status, o.amount, p.transfer_value, p.positions
                    FROM fm_transfer_offers o CROSS JOIN players_current p
                    WHERE o.career_id = :k AND o.kind IN ('transfer', 'loan') AND o.player_uid IS NOT NULL
                      AND p.career_id = o.career_id AND p.uid = o.player_uid""", k=self.career_id)
        return self._market

    def comparable_ratio(self, value: int | None) -> tuple[float | None, int]:
        """Médiane (montant payé / valeur actuelle) des transferts conclus de valeur comparable."""
        if not value:
            return None, 0
        ratios = [r["amount"] / r["transfer_value"] for r in self.market_rows()
                  if r["kind"] == "transfer" and r["status"] == "completed" and (r["amount"] or 0) > 0
                  and r["transfer_value"] and value // 2 <= r["transfer_value"] <= value * 2]
        if not ratios:
            return None, 0
        return round(statistics.median(ratios), 3), len(ratios)

    def position_depth(self, club_uid: int, position: str) -> list[dict]:
        """Joueurs de l'équipe première d'un club à ce poste, avec leur rang au classement du poste."""
        rank_pos = RANKING_POSITION.get(position)
        with self.engine.connect() as c:
            return _rows(c, """
                SELECT p.uid, p.name, p.age, p.transfer_value,
                       (SELECT min(r.rank) FROM fm_player_rankings r WHERE r.career_id = p.career_id
                         AND r.player_uid = p.uid AND r.position = :rp AND r.women = 0) AS rank
                FROM players_current p
                WHERE p.career_id = :k AND p.club_uid = :c AND coalesce(p.team_slot, 0) = 0
                  AND p.positions LIKE :like AND coalesce(p.on_loan, 0) = 0""",
                         k=self.career_id, c=club_uid, like=f"%,{position},%", rp=rank_pos)

    def wage_structure(self, club_uid: int) -> dict:
        with self.engine.connect() as c:
            wages = sorted(r["wage"] for r in _rows(c, """
                SELECT wage FROM players_current WHERE career_id = :k AND club_uid = :c AND coalesce(team_slot, 0) = 0
                  AND wage IS NOT NULL AND wage > 0""", k=self.career_id, c=club_uid))
        if not wages:
            return {}

        def pct(q: float) -> int:
            return wages[min(len(wages) - 1, max(0, round(q * (len(wages) - 1))))]

        return {"n": len(wages), "p25": pct(0.25), "median": pct(0.5), "p75": pct(0.75), "p90": pct(0.9), "max": wages[-1]}


def offer_state(offer: dict, today: date | None) -> str:
    if offer.get("status") == "completed":
        return COMPLETED
    if offer.get("status") == "failed":
        return FAILED
    deadline = offer.get("deadline")
    if isinstance(deadline, str):
        deadline = date.fromisoformat(deadline[:10])
    effective = offer.get("effective_on")
    if isinstance(effective, str):
        effective = date.fromisoformat(effective[:10])
    if today and effective and effective > today:
        return "accord_a_venir"
    if today and deadline and deadline < today:
        return "sans_suite"
    return OPEN


# ---------------------------------------------------------------------- valeur et prix
def valuation(m: Market, player: dict) -> dict:
    value = player.get("transfer_value") or 0
    age = player.get("age")
    months_left = months_between(m.game_date, player.get("contract_end"))
    contract = 1.0
    if months_left is not None:
        contract = (0.45 if months_left <= 6 else 0.65 if months_left <= 12 else 0.85 if months_left <= 18
                    else 0.95 if months_left <= 24 else 1.1 if months_left > 36 else 1.0)
    age_f = 1.0
    if age is not None:
        age_f = 1.15 if age <= 21 else 1.08 if age <= 24 else 1.0 if age <= 28 else 0.9 if age <= 30 else 0.75 if age <= 32 else 0.6
    ranks = m.rankings(player["uid"])
    best = ranks[0] if ranks else None
    rank_f = 1.0
    if best:
        rank_f = 1.2 if best["rank"] <= 20 else 1.1 if best["rank"] <= 100 else 1.0
    ratio, n = m.comparable_ratio(value)
    market_f = 1.0
    if ratio is not None and n >= 5:
        market_f = round(0.5 + 0.5 * min(2.0, max(0.6, ratio)), 3)
    estimate = int(value * contract * age_f * rank_f * market_f)
    return {
        "valeur_jeu": value,
        "estimation": estimate,
        "prix_demande": int(estimate * 1.15),
        "plancher": int(estimate * 0.9),
        "achat": {"premiere_offre": int(estimate * 0.8), "cible": estimate, "plafond": int(estimate * 1.15)},
        "composantes": {
            "contrat_mois_restants": months_left, "facteur_contrat": contract,
            "age": age, "facteur_age": age_f,
            "meilleur_classement": ({"poste": best["position"], "rang": best["rank"], "sur": best["total"]} if best else None),
            "facteur_rang": rank_f,
            "marche_ratio_median": ratio, "marche_transferts_comparables": n, "facteur_marche": market_f,
        },
        "methode": METHOD_VALUE,
    }


# ---------------------------------------------------------------------- acheteurs
def find_buyers(m: Market, player: dict, *, exclude: set[int] | None = None, limit: int = 8) -> dict:
    exclude = set(exclude or ()) | ({player.get("club_uid")} if player.get("club_uid") else set())
    val = valuation(m, player)
    floor = val["plancher"]
    wage = player.get("wage") or 0
    pos = main_position(player)
    group = POSITION_GROUP.get(pos or "", "")
    finances = m.finances()
    own = finances.get(player.get("club_uid")) or {}
    own_rep = own.get("reputation") or (m.club(player.get("club_uid")) or {}).get("reputation") or 0

    # 1. Offres réelles déjà faites pour CE joueur.
    real = m.offers(player_uid=player["uid"], limit=100)
    real_by_club: dict[int, list[dict]] = {}
    for o in real:
        if o.get("bidding_club_uid") and o["bidding_club_uid"] not in exclude:
            real_by_club.setdefault(o["bidding_club_uid"], []).append(o)

    # 2. Clubs ayant visé ce profil (même groupe de postes, valeur comparable) cette saison.
    profile: dict[int, int] = {}
    if value := player.get("transfer_value"):
        for r in m.market_rows():
            club = r["bidding_club_uid"]
            if club is None or club in exclude or not r["transfer_value"] or not value // 2 <= r["transfer_value"] <= value * 2:
                continue
            groups = {POSITION_GROUP.get(x) for x in (r["positions"] or "").split(",") if x}
            if group in groups:
                profile[club] = profile.get(club, 0) + 1

    candidates = set(real_by_club) | set(profile) | {
        uid for uid, f in finances.items() if (f.get("transfer_budget_remaining") or 0) >= floor * 0.7
    }
    candidates -= exclude
    # Les plus pertinents d'abord (offre réelle, profil visé, budget), puis examen détaillé des 60 premiers.
    shortlist = sorted(candidates, key=lambda u: (u not in real_by_club, -profile.get(u, 0),
                                                 -((finances.get(u) or {}).get("transfer_budget_remaining") or 0)))[:60]
    our_rank = (m.rankings(player["uid"]) or [{}])[0].get("rank")
    out = []
    for uid in shortlist:
        f = finances.get(uid) or {}
        club = f or (m.club(uid) or {})
        budget = f.get("transfer_budget_remaining")
        has_offer = uid in real_by_club
        if not has_offer and (budget is None or budget < floor * 0.7):
            continue
        wage_room = (f.get("wage_budget_weekly") or 0) - (f.get("wage_payroll_weekly") or 0) if f else None
        depth = m.position_depth(uid, pos) if pos else []
        ranks = [d["rank"] for d in depth if d["rank"]]
        starter = our_rank is not None and (not ranks or our_rank < min(ranks))
        score = 0.0
        reasons = []
        if has_offer:
            score += 40
            last = real_by_club[uid][0]
            reasons.append(f"{KIND_LABEL.get(last['kind'], 'offre')} proposé le {last['offered_on']} "
                           f"({STATE_LABEL.get(last['etat'], last['etat'])})")
        if profile.get(uid):
            score += min(15, 5 * profile[uid])
            reasons.append(f"a visé {profile[uid]} joueur(s) de ce profil cette saison")
        if budget is not None and floor:
            ratio = budget / floor
            score += 20 if ratio >= 1.5 else 14 if ratio >= 1 else 6
            if ratio < 1:
                reasons.append("budget juste : paiement échelonné nécessaire")
        if len(depth) < 2 or starter:
            score += 15
            reasons.append("serait titulaire" if starter else f"seulement {len(depth)} joueur(s) au poste")
        elif len(depth) < 3:
            score += 7
        rep = club.get("reputation") or 0
        if own_rep:
            rel = rep / own_rep
            score += 10 if rel >= 0.9 else 6 if rel >= 0.7 else 2
            if rel < 0.7:
                reasons.append("club de moindre standing : le joueur pourrait refuser")
        if wage_room is not None and wage and wage_room < wage * 0.6:
            score -= 5
            reasons.append("masse salariale tendue")
        out.append({
            "club_uid": uid, "club": club.get("short_name") or club.get("club_name") or club.get("name"),
            "score": round(score), "budget_transferts_restant": budget, "marge_salariale_hebdo": wage_room,
            "reputation": rep, "joueurs_au_poste": len(depth), "meilleur_rang_au_poste": min(ranks) if ranks else None,
            "offres_reelles": [{"date": o["offered_on"], "montant": o["amount"], "type": o["kind"], "etat": o["etat"]}
                               for o in real_by_club.get(uid, [])[:3]],
            "raisons": reasons,
        })
    out.sort(key=lambda x: (-x["score"], -(x["budget_transferts_restant"] or 0)))
    return {"valeur": val, "poste": pos, "acheteurs": out[:limit], "clubs_examines": len(shortlist),
            "methode": METHOD_BUYERS}


# ---------------------------------------------------------------------- contrats
def contract_proposal(m: Market, player: dict, club_uid: int, *, renewal: bool) -> dict:
    age = player.get("age") or 26
    current = player.get("wage") or 0
    structure = m.wage_structure(club_uid)
    years = 5 if age <= 23 else 4 if age <= 27 else 3 if age <= 30 else 2 if age <= 32 else 1
    if renewal:
        raise_f = 1.15 if age <= 27 else 1.05 if age <= 30 else 0.9
    else:
        raise_f = 1.35 if age <= 27 else 1.2
    target = int(current * raise_f) if current else structure.get("median", 0)
    ceiling = int(target * 1.15)
    notes = []
    if structure:
        if target > structure["max"]:
            notes.append("au-dessus du plus gros salaire actuel de l'équipe : risque pour la grille salariale")
        ceiling = min(ceiling, max(structure["max"], target))
    finances = m.finances().get(club_uid) or {}
    room = None
    if finances:
        room = (finances.get("wage_budget_weekly") or 0) - (finances.get("wage_payroll_weekly") or 0)
    extra = target - (current if renewal else 0)
    if room is not None and extra > room:
        notes.append("dépasse la marge salariale actuelle : libérer un salaire ou demander une rallonge à la direction")
    end_year = (m.game_date or date.today()).year + years
    return {
        "type": "prolongation" if renewal else "nouveau contrat",
        "duree_ans": years, "fin_proposee": f"{end_year}-06-30",
        "salaire_actuel_hebdo": current, "salaire_cible_hebdo": target, "salaire_plafond_hebdo": ceiling,
        "prime_signature": int(target * 52 * 0.1),
        "primes": (["prime de but"] if POSITION_GROUP.get(main_position(player) or "") in ("ATT", "OFF") else [])
                  + ["prime d'apparition", "prime de fidélité en fin de contrat"],
        "clauses": (["clause libératoire élevée (protège la plus-value)"] if age <= 24 else [])
                   + (["augmentation annuelle de 5 %"] if age <= 23 else [])
                   + (["option d'une année supplémentaire au profit du club"] if age >= 30 else []),
        "grille_equipe": structure, "marge_salariale_hebdo": room, "impact_hebdo": extra,
        "alertes": notes,
        "methode": ("Durée selon l'âge (≤23 : 5 ans … ≥33 : 1 an) ; salaire = actuel × 1,15 (≤27 ans), × 1,05 (28-30), "
                    "× 0,9 (31+) pour une prolongation, × 1,35 / × 1,2 pour une recrue ; plafond +15 % borné par la "
                    "grille de l'équipe première ; prime à la signature = 10 % du salaire annuel."),
    }


# ---------------------------------------------------------------------- plans
def sale_plan(m: Market, player: dict, *, exclude: set[int] | None = None) -> dict:
    buyers = find_buyers(m, player, exclude=exclude)
    val = buyers["valeur"]
    age = player.get("age") or 26
    received = m.offers(player_uid=player["uid"], club_uid=player.get("club_uid"), side="recues", limit=20)
    return {
        "joueur": player["name"], "valeur": val, "acheteurs": buyers["acheteurs"],
        "offres_recues": received,
        "strategie": {
            "prix_affiche": val["prix_demande"], "plancher": val["plancher"],
            "pourcentage_revente": 20 if age <= 21 else 15 if age <= 24 else 0,
            "echeancier": "accepter 2 à 3 versements annuels si le total dépasse le prix demandé" if val["estimation"] else None,
            "alternative": "prêt avec option d'achat obligatoire" if age <= 23 else "résiliation à l'amiable si aucun acheteur",
            "contre_offre": "si une offre est sous le plancher : contre-proposer au prix demandé moins 5 %, puis rester au-dessus du plancher",
        },
        "methode_acheteurs": buyers["methode"],
    }


def purchase_plan(m: Market, player: dict, club_uid: int) -> dict:
    val = valuation(m, player)
    finances = m.finances()
    ours = finances.get(club_uid) or {}
    seller = finances.get(player.get("club_uid")) or {}
    budget = ours.get("transfer_budget_remaining")
    all_offers = m.offers(player_uid=player["uid"], limit=50)
    competition = [o for o in all_offers if o["bidding_club_uid"] != club_uid and o["etat"] in (OPEN, "accord_a_venir")]
    ours_already = [o for o in all_offers if o["bidding_club_uid"] == club_uid]
    months_left = months_between(m.game_date, player.get("contract_end"))
    notes = []
    if any(o["etat"] == "accord_a_venir" for o in ours_already):
        notes.append("accord déjà trouvé avec le club vendeur pour une arrivée à venir : ne pas refaire d'offre")
    if months_left is not None and months_left <= 6:
        notes.append("contrat qui finit dans moins de 6 mois : pré-contrat possible (arrivée libre) au lieu d'une indemnité")
    if seller and (seller.get("balance") or 0) < 0:
        notes.append("club vendeur en déficit : plus enclin à vendre, privilégier un paiement comptant")
    structure = {"comptant_pct": 100}
    if budget is not None and val["achat"]["cible"] > budget:
        notes.append("cible au-dessus du budget transferts restant : échelonner ou vendre d'abord")
        structure = {"comptant_pct": 40, "versements": "2 versements annuels égaux", "bonus_max_pct": 15}
    if (player.get("age") or 30) <= 23:
        structure["pourcentage_revente_concede"] = "jusqu'à 15 % pour faire baisser l'indemnité"
    return {
        "joueur": player["name"], "club_vendeur": player.get("club_name"), "valeur": val,
        "offre": {"premiere": val["achat"]["premiere_offre"], "cible": val["achat"]["cible"], "plafond": val["achat"]["plafond"],
                  "structure": structure},
        "budget_transferts_restant": budget, "concurrence": competition[:5], "nos_offres": ours_already[:5],
        "contrat": contract_proposal(m, player, club_uid, renewal=False),
        "alertes": notes,
        "negociation": [
            "Ouvrir à la première offre, sans dévoiler le plafond.",
            "Monter par paliers de 5 % maximum ; préférer des bonus conditionnels à une hausse du fixe.",
            "Au plafond : s'arrêter et passer à l'alternative.",
        ],
    }


def counter_offer(m: Market, player: dict, received_amount: int | None) -> dict:
    val = valuation(m, player)
    if received_amount is None:
        open_offers = [o for o in m.offers(player_uid=player["uid"], club_uid=player.get("club_uid"), side="recues")
                       if o["etat"] == OPEN]
        received_amount = open_offers[0]["amount"] if open_offers else None
    if received_amount is None:
        raise LookupError("Aucune offre en cours trouvée pour ce joueur : indiquez le montant reçu.")
    if received_amount >= val["prix_demande"]:
        decision, counter = "accepter", None
    elif received_amount >= val["plancher"]:
        decision, counter = "contre-proposer", int((received_amount + val["prix_demande"]) / 2)
    else:
        decision, counter = "contre-proposer", int(val["prix_demande"] * 0.95)
    return {"joueur": player["name"], "offre_recue": received_amount, "decision": decision, "contre_offre": counter,
            "plancher": val["plancher"], "prix_demande": val["prix_demande"], "valeur": val}


__all__ = [
    "Market", "contract_proposal", "counter_offer", "find_buyers", "offer_state", "purchase_plan", "sale_plan", "valuation",
]
