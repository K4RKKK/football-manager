"""Données préparées avant l'appel du modèle (rapidité).

Mesuré sur le banc d'évaluation (mode jeu) : une réponse sans consultation prend ≈ 3 s, mais 2-3
consultations successives ≈ 18 s (chaque tour : écrire la demande, lire le résultat, réécrire). Pour les
demandes les plus courantes du directeur sportif sur un joueur nommé (vendre, prolonger, estimer, offres
reçues, contre-offre), le service lance lui-même l'outil complet AVANT le modèle et lui donne le
résultat : le modèle rédige directement, en un seul tour.
"""

from __future__ import annotations

import json
import re

from clubdirector.text import fold
from clubdirector.tools.registry import ToolContext

MAX_BRIEF_CHARS = 5000
RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"contre[- ]?(offre|proposition)", re.IGNORECASE), "prepare_counter_offer"),
    (re.compile(r"\bprolong\w*", re.IGNORECASE), "prepare_contract_proposal"),
    (re.compile(r"\b(vend(s|re|ez|ons|u|ue|us|ra|rait)?|ventes?|s'en s[ée]parer|c[ée]der)\b", re.IGNORECASE),
     "prepare_sale"),
    (re.compile(r"\b(acheteurs?|s'int[ée]ress\w*|int[ée]ress[ée]s?)\b", re.IGNORECASE), "find_buyers"),
    (re.compile(r"\b(combien vaut|vaut combien|valeur|estime\w*|prix)\b", re.IGNORECASE), "evaluate_transfer_value"),
    (re.compile(r"\boffres?\b", re.IGNORECASE), "get_transfer_offers"),
]
# Un achat (offre à faire, recrue) : plan d'achat préparé ailleurs, jamais la liste de nos offres reçues.
OUR_OFFER_RE = re.compile(r"\b(fai|propos|envoi|envoy|lanc|pr[ée]par)\w*(-moi|-nous)?( \w+)? (une |des |notre |nos )?offres?\b|"
                          r"\b(recrut\w*|faire venir|achet(er|e|ons|ez))\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(\d{1,3}(?:[ .]\d{3})+|\d+(?:[.,]\d+)?)\s*(m|millions?|k|milles?)?\s*(€|eur\w*|d'euros)",
                       re.IGNORECASE)
UNITS = {"m": 1_000_000, "million": 1_000_000, "millions": 1_000_000, "k": 1_000, "mille": 1_000, "milles": 1_000}


def amount_in(message: str) -> float | None:
    """« 15 M€ » → 15 000 000 ; « 800 k€ » → 800 000 (devise affichée). None si aucun montant."""
    m = AMOUNT_RE.search(message.replace(" ", "").replace("\xa0", ""))
    if m is None:
        return None
    number = m.group(1)
    number = re.sub(r"[ .]", "", number) if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", number) else number.replace(",", ".")
    return float(number) * UNITS.get((m.group(2) or "").lower(), 1)


def _player_in(tctx: ToolContext, message: str) -> dict | None:
    """Joueur du club cité dans le message (nom de famille ou nom complet), le plus utilisé d'abord."""
    folded = fold(message)
    words = set(re.findall(r"[\w-]+", folded))  # « d'Ndicka » → « ndicka »
    try:
        squad = tctx.repo.squad(tctx.ctx, team_slot=None)
    except Exception:  # noqa: BLE001
        return None
    hits = []
    for p in squad:
        parts = [w for w in re.findall(r"[\w-]+", fold(p["name"])) if len(w) > 2]
        if parts and (parts[-1] in words or fold(p["name"]) in folded):
            hits.append(p)
    if not hits:
        return None
    return max(hits, key=lambda p: (fold(p["name"]) in folded, p.get("team_slot") in (0, None), p.get("transfer_value") or 0))


def prefetch_calls(role: str, message: str, tctx: ToolContext, allowed: set[str] | None) -> list[tuple[str, dict]]:
    """Outils à exécuter avant le modèle pour ce message (directeur sportif, joueur du club nommé)."""
    if role != "directeur_sportif" or OUR_OFFER_RE.search(message):  # une offre à faire : plan d'achat, pas ici
        return []
    player = _player_in(tctx, message)
    for pattern, tool in RULES:
        if not pattern.search(message):
            continue
        if allowed is not None and tool not in allowed:
            return []
        if player is None:
            return [(tool, {})] if tool == "get_transfer_offers" else []
        args = {"player_uid": player["uid"]}
        if tool == "prepare_counter_offer" and (amount := amount_in(message)) is not None:
            args["montant_recu"] = amount
        return [(tool, args)]
    return []


def prefetch_brief(tool: str, data) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(payload) > MAX_BRIEF_CHARS:
        payload = payload[:MAX_BRIEF_CHARS] + "…"
    return (f"[Données déjà consultées pour toi ({tool}) — réponds directement à partir de ces chiffres, sans "
            f"reconsulter les mêmes : {payload}]")
