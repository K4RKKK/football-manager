"""Demandes d'achat de l'entraîneur au directeur sportif, reconnues sans IA.

« Prépare une offre pour Juanlu », « recrute Lewis Thomas, le gardien sans club » : le plan d'achat
(`prepare_transfer_offer`) est calculé AVANT le modèle, le dossier est ouvert (suivi dans les
sauvegardes suivantes) et les chiffres sont imposés comme base de la réponse : le modèle ne chiffre
pas autrement et n'invente pas de montants. Les opérations sur NOS joueurs (vente, prolongation,
contre-offre) sont préparées par `ai/prefetch.py`. Un joueur introuvable ou ambigu (homonymes sans
indice) laisse la main au modèle, qui demande.
"""

from __future__ import annotations

import json
import re

from clubdirector.memory.decisions import fold1
from clubdirector.positions import split_positions

_END = r"(?=[,.;:!?\n(]|\s+(?:et|mais|car|pour\s+(?:qu|le|la|les|voir|savoir)|avant|stp|svp|s'il)\b|$)"
_N = r"(?P<n>[^,.;:!?\n(]{2,60}?)"
PATTERNS = [
    rf"\b(?:offre|proposition)\s+(?:de\s+transfert\s+)?(?:pour|sur|a)\s+{_N}{_END}",
    rf"\b(?:achete[rz]?|recrute[rz]?|faire\s+venir|fais\s+venir)\s+{_N}{_END}",
]
ASK = re.compile(r"\b(?:pr[eé]pare|fais|faire|monte|lance|chiffre|propose|ach[eè]te|recrute|venir)", re.IGNORECASE)
POSITION_WORDS = {"gardien": {"GK"}, "goal": {"GK"}, "defenseur central": {"DC"}, "central": {"DC"}, "lateral droit": {"DR", "WBR"},
                  "lateral gauche": {"DL", "WBL"}, "lateral": {"DR", "DL", "WBR", "WBL"}, "piston": {"WBR", "WBL"},
                  "milieu": {"DM", "MC", "AMC"}, "sentinelle": {"DM"}, "meneur": {"AMC"}, "ailier": {"AMR", "AML", "MR", "ML"},
                  "attaquant": {"STC"}, "avant-centre": {"STC"}, "buteur": {"STC"}}
FREE_WORDS = re.compile(r"\b(sans club|libre|chomeur|en fin de contrat libre)\b")
STOP = {"le", "la", "les", "de", "du", "des", "un", "une", "notre", "ce", "cet", "cette", "mon", "ton", "jeune", "joueur"}


def _candidates(tctx, chunk: str) -> list[dict]:
    """Joueurs de la base dont le nom correspond au début de `chunk` (du plus long au plus court)."""
    words = [w for w in re.findall(r"[\w'-]+", chunk) if fold1(w) not in STOP]
    for n in range(min(4, len(words)), 0, -1):
        name = " ".join(words[:n])
        if len(name) < 3:
            continue
        rows = tctx.repo.find_players_by_name(tctx.ctx, name, limit=15)
        exact = [r for r in rows if fold1(r["name"]) == fold1(name)]
        if exact:
            return exact
        if rows and n > 1:
            return rows
    return []


def _pick(tctx, rows: list[dict], text: str) -> dict | None:
    """Le joueur visé parmi des homonymes, d'après les indices de la phrase (poste, « sans club », club)."""
    if len(rows) == 1:
        return rows[0]
    low = fold1(text)
    wanted = set().union(*(codes for word, codes in POSITION_WORDS.items() if word in low)) if any(
        w in low for w in POSITION_WORDS) else set()

    def score(r: dict) -> int:
        s = 0
        if wanted and wanted & set(split_positions(r.get("positions"))):
            s += 2
        if FREE_WORDS.search(low) and not r.get("club_uid"):
            s += 3
        club = fold1(r.get("club_name") or "")
        if club and any(len(w) > 3 and w in low for w in re.findall(r"[a-z]+", club)):
            s += 3
        if r.get("club_uid") == tctx.ctx.club_uid:
            s += 1
        return s

    ranked = sorted(rows, key=lambda r: (score(r), r.get("transfer_value") or 0), reverse=True)
    if score(ranked[0]) == 0 or (len(ranked) > 1 and score(ranked[0]) == score(ranked[1])):
        return None  # ambigu : le modèle demande de préciser
    return ranked[0]


def operation_request(tctx, text: str) -> tuple[str, dict, dict] | None:
    """("prepare_transfer_offer", arguments, joueur) si le message demande d'acheter un joueur d'un autre club."""
    if tctx.ctx.club_uid is None or not ASK.search(text):
        return None
    low = fold1(text)
    for pattern in PATTERNS:
        m = re.search(pattern, low)
        if not m:
            continue
        player = _pick(tctx, _candidates(tctx, text[m.start("n"):m.end("n")]), text)
        if player is None or player.get("club_uid") == tctx.ctx.club_uid:
            return None  # ambigu, introuvable, ou l'un des nôtres (prolongation : ai/prefetch.py)
        return "prepare_transfer_offer", {"player_uid": player["uid"]}, player
    return None


def operation_brief(tool: str, data: dict) -> str:
    """Consigne ajoutée au message de l'entraîneur : le plan calculé, base obligatoire de la réponse."""
    keep = {
        "prepare_transfer_offer": ("joueur", "club_vendeur", "offre", "budget_transferts_restant", "contrat", "alertes",
                                   "concurrence", "nos_offres", "negociation"),
        "prepare_sale": ("joueur", "strategie", "acheteurs", "offres_recues"),
        "prepare_counter_offer": ("joueur", "offre_recue", "decision", "contre_offre", "plancher", "prix_demande"),
        "prepare_contract_proposal": ("joueur", "fin_contrat_actuel", "type", "duree_ans", "fin_proposee",
                                      "salaire_actuel_hebdo", "salaire_cible_hebdo", "salaire_plafond_hebdo",
                                      "prime_signature", "impact_hebdo", "marge_salariale_hebdo", "alertes"),
    }[tool]
    plan = {k: data[k] for k in keep if k in data and data[k] not in (None, [], {})}
    if isinstance(plan.get("contrat"), dict):
        plan["contrat"] = {k: v for k, v in plan["contrat"].items() if k in (
            "duree_ans", "salaire_cible_hebdo", "salaire_plafond_hebdo", "prime_signature", "alertes")}
    for key in ("concurrence", "nos_offres", "acheteurs", "offres_recues"):
        if isinstance(plan.get(key), list):
            plan[key] = plan[key][:4]
    return (f"[Préparation calculée par l'outil {tool} sur les données réelles de la sauvegarde — base OBLIGATOIRE de ta "
            f"réponse, chiffres à reprendre tels quels (n'en invente aucun autre) : "
            f"{json.dumps(plan, ensure_ascii=False, default=str)}. Le dossier est ouvert : tu le suivras dans les prochaines "
            "sauvegardes. Rien n'est envoyé dans FM26 : dis à l'entraîneur ce qu'il doit faire dans le jeu.]")


__all__ = ["operation_brief", "operation_request"]
