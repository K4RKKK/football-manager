"""Composition d'équipe déterministe à partir des notes de poste de FM26.

L'entraîneur adjoint ne devine pas qui joue où : il appelle `propose_lineup`, qui place chaque
joueur de l'équipe première sur un poste du système choisi par une affectation optimale (méthode
hongroise) en maximisant :
- la familiarité au poste (note 1-20 de la sauvegarde : 20 = naturel, ≥ 15 = compétent ; en
  dessous de 10, le poste est interdit) ;
- un indice de niveau visible (rang de valeur dans l'effectif, note moyenne et temps de jeu de la
  saison) — jamais le CA/PA caché ;
- la condition physique (pénalité sous 75 %).
Les suspendus (sauvegarde) et les absents signalés par l'entraîneur sont écartés. La sauvegarde
n'expose pas l'infirmerie du jour : l'outil le dit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from clubdirector.positions import LABEL_FR
from clubdirector.text import fold
from clubdirector.tools.registry import ToolArgs, ToolContext, ToolRegistry, ToolResult

SYSTEMS: dict[str, tuple[str, ...]] = {
    "4-2-3-1": ("GK", "DR", "DC", "DC", "DL", "DM", "DM", "AMR", "AMC", "AML", "STC"),
    "4-3-3": ("GK", "DR", "DC", "DC", "DL", "DM", "MC", "MC", "AMR", "AML", "STC"),
    "4-4-2": ("GK", "DR", "DC", "DC", "DL", "MR", "MC", "MC", "ML", "STC", "STC"),
    "4-1-4-1": ("GK", "DR", "DC", "DC", "DL", "DM", "MR", "MC", "MC", "ML", "STC"),
    "4-3-1-2": ("GK", "DR", "DC", "DC", "DL", "DM", "MC", "MC", "AMC", "STC", "STC"),
    "3-5-2": ("GK", "DC", "DC", "DC", "WBR", "WBL", "DM", "MC", "MC", "STC", "STC"),
    "3-4-3": ("GK", "DC", "DC", "DC", "WBR", "WBL", "MC", "MC", "AMR", "AML", "STC"),
    "3-4-2-1": ("GK", "DC", "DC", "DC", "WBR", "WBL", "MC", "MC", "AMC", "AMC", "STC"),
    "5-3-2": ("GK", "DC", "DC", "DC", "WBR", "WBL", "DM", "MC", "MC", "STC", "STC"),
}
INFEASIBLE = 1e6
MIN_RATING = 10
BENCH = 9


def familiarity(rating: int | None) -> float | None:
    """Poids de la note de poste (None : poste interdit)."""
    if rating is None or rating < MIN_RATING:
        return None
    if rating >= 20:
        return 1.0
    if rating >= 18:
        return 0.9
    if rating >= 15:
        return 0.72
    if rating >= 12:
        return 0.3
    return 0.12


def hungarian(cost: list[list[float]]) -> list[int]:
    """Affectation de coût minimal : pour chaque ligne (poste), l'indice de colonne (joueur).

    Lignes ≤ colonnes. Méthode hongroise avec potentiels, O(n²m)."""
    n, m = len(cost), len(cost[0])
    inf = float("inf")
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    out = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            out[p[j] - 1] = j - 1
    return out


def _quality(players: list[dict], seasons: dict[int, dict], rotation: bool) -> dict[int, float]:
    """Indice de niveau visible (0-1) : valeur dans l'effectif, note moyenne, temps de jeu."""
    by_value = sorted(players, key=lambda p: p.get("transfer_value") or 0)
    rank = {p["uid"]: i / max(1, len(by_value) - 1) for i, p in enumerate(by_value)}
    max_minutes = max([(seasons.get(p["uid"]) or {}).get("minutes") or 0 for p in players] + [1])
    out = {}
    for p in players:
        s = seasons.get(p["uid"]) or {}
        starts = (s.get("starts") or 0) + (s.get("substitute_appearances") or 0)
        rating = s.get("average_rating")
        form = min(1.0, max(0.0, (float(rating) - 6.2) / 1.3)) if rating and starts >= 2 else 0.5
        share = (s.get("minutes") or 0) / max_minutes
        # Le temps de jeu reflète la hiérarchie que l'entraîneur a déjà établie dans le jeu ; la valeur
        # seule favoriserait les jeunes chers au détriment des cadres en forme.
        if rotation:
            out[p["uid"]] = 0.35 * (1 - share) + 0.35 * form + 0.3 * rank[p["uid"]]
        else:
            out[p["uid"]] = 0.45 * share + 0.33 * form + 0.22 * rank[p["uid"]]
    return out


def best_lineup(players: list[dict], seasons: dict[int, dict], system: str, *, rotation: bool = False) -> dict:
    """Meilleur onze (et banc) pour `system` ; `players` : lignes players_current disponibles."""
    slots = SYSTEMS[system]
    quality = _quality(players, seasons, rotation)
    if len(players) < len(slots):
        raise ValueError(f"Seulement {len(players)} joueurs disponibles pour {len(slots)} postes.")

    def score(p: dict, slot: str) -> float | None:
        fam = familiarity((p.get("position_ratings") or {}).get(slot.lower()))
        if fam is None:
            return None
        cond = p.get("condition")
        tired = max(0.0, (7500 - cond) / 2500) if cond is not None else 0.0
        return 0.6 * fam + 0.4 * quality[p["uid"]] - (0.35 if rotation else 0.2) * tired

    cost = [[-(sc) if (sc := score(p, slot)) is not None else INFEASIBLE for p in players] for slot in slots]
    picks = hungarian(cost)
    lineup, alerts, used = [], [], set()
    for row, (slot, idx) in enumerate(zip(slots, picks, strict=True)):
        p = players[idx]
        rating = (p.get("position_ratings") or {}).get(slot.lower())
        if cost[row][idx] >= INFEASIBLE or rating is None or rating < MIN_RATING:
            alerts.append(f"Aucun joueur disponible ne sait jouer {LABEL_FR.get(slot, slot)} : poste à combler.")
        elif rating < 15:
            alerts.append(f"{p['name']} dépanne en {LABEL_FR.get(slot, slot)} (note {rating}/20).")
        used.add(idx)
        lineup.append({"poste": slot, "libelle": LABEL_FR.get(slot, slot), "joueur": p["name"], "uid": p["uid"],
                       "note_poste": rating, "condition": _pct(p.get("condition"))})
    rest = [p for i, p in enumerate(players) if i not in used]

    def best_role(p: dict) -> tuple[str, int]:
        ratings = p.get("position_ratings") or {}
        code, val = max(ratings.items(), key=lambda kv: kv[1]) if ratings else ("?", 0)
        return code.upper(), val
    bench = []
    keeper_on_bench = False
    for p in sorted(rest, key=lambda p: -quality[p["uid"]]):
        code, val = best_role(p)
        if code == "GK":
            if keeper_on_bench:
                continue
            keeper_on_bench = True
        bench.append({"joueur": p["name"], "uid": p["uid"], "meilleur_poste": LABEL_FR.get(code, code), "note_poste": val,
                      "condition": _pct(p.get("condition"))})
        if len(bench) >= BENCH:
            break
    return {"systeme": system, "onze": lineup, "banc": bench, "alertes": alerts}


def _pct(condition: int | None) -> str | None:
    return f"{round(condition / 100)} %" if condition is not None else None


class LineupArgs(ToolArgs):
    systeme: Literal["4-2-3-1", "4-3-3", "4-4-2", "4-1-4-1", "4-3-1-2", "3-5-2", "3-4-3", "3-4-2-1", "5-3-2"] = Field(
        "4-2-3-1", description="Système de jeu. Par défaut 4-2-3-1 (la tactique active n'est pas toujours lisible).")
    absents: list[str] = Field(default_factory=list, description="Joueurs à écarter (blessés, suspendus, choix de l'entraîneur).")
    rotation: bool = Field(False, description="Vrai pour faire tourner : favorise les joueurs frais et moins utilisés.")


def register_lineup_tools(reg: ToolRegistry) -> None:
    @reg.tool("propose_lineup",
              "Composition calculée sur les notes de poste de FM26 (familiarité 1-20), le niveau visible et la condition : "
              "onze par poste, banc, alertes. À appeler AVANT de proposer une équipe ; ne place jamais un joueur hors de ses postes.",
              "analyse", LineupArgs)
    def propose_lineup(t: ToolContext, a: LineupArgs):
        rows = t.repo.squad(t.ctx)
        wanted_out = {fold(n) for n in a.absents}
        excluded, available = [], []
        for r in rows:
            name = fold(r["name"])
            if any(w and (w == name or w in name.split() or name.endswith(" " + w)) for w in wanted_out):
                excluded.append({"joueur": r["name"], "raison": "écarté par l'entraîneur"})
            elif r.get("banned"):
                excluded.append({"joueur": r["name"], "raison": "suspendu (sauvegarde)"})
            else:
                available.append(r)
        seasons = t.repo.season_lines(t.ctx, [r["uid"] for r in available])
        try:
            out = best_lineup(available, seasons, a.systeme, rotation=a.rotation)
        except ValueError as exc:
            return ToolResult("", False, error=str(exc))
        out["exclus"] = excluded
        out["methode"] = ("Affectation optimale : note de poste FM26 (20 = naturel), valeur dans l'effectif, note moyenne et "
                          "minutes de la saison, condition physique. Aucun attribut caché.")
        return ToolResult("", True, data=out, limitations=[
            "La sauvegarde n'indique pas l'infirmerie du jour : demandez à l'entraîneur ses absents et passez-les dans « absents ».",
        ])
