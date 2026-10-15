"""Décisions durables de l'entraîneur, reconnues sans IA dans ses messages et retenues pour les trois contacts.

« On ne vend pas Soulé », « Soulé n'est pas à vendre », « âge max 26 ans », « pas plus de 30 M€ par
transfert », « le mercato ferme le 2 février », « retiens que… » : chaque décision devient un souvenir
structuré (clé + valeur) de la table `memories`. Il figure dans le dossier des trois contacts et les
outils l'appliquent (vente déconseillée, âge maximum des cibles, plafond d'indemnité, fin de fenêtre
annoncée). Une décision contraire remplace la précédente (même clé). Un joueur n'est retenu que s'il
est de notre club et reconnu sans ambiguïté : sinon rien n'est enregistré.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Engine

from clubdirector.memory.store import MemoryStore

MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
          "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
_STOP = r"(?=[.;:!?\n]|\s+(?:mais|car|parce|sauf|si|tant|meme|cet|cette|ce|cela|a\s+aucun|quoi|sous)\b|$)"
_NAMES = r"(?P<n>[^.;:!?\n]{2,80}?)"
NEVER_SELL = [
    rf"\b(?:on|je|nous)\s+ne\s+(?:le\s+|la\s+)?vend(?:s|ons)?\s+pas\s+{_NAMES}{_STOP}",
    rf"\bon\s+(?:le\s+)?vend\s+pas\s+{_NAMES}{_STOP}",
    rf"\bpas\s+question\s+de\s+vendre\s+{_NAMES}{_STOP}",
    rf"\b(?:ne\s+)?(?:jamais|surtout\s+pas)\s+vendre\s+{_NAMES}{_STOP}",
    rf"\bon\s+garde\s+{_NAMES}\s+(?:quoi\s+qu.il\s+arrive|a\s+tout\s+prix|coute\s+que\s+coute)",
    rf"(?:^|[,.;:!?\n]\s*|\bet\s+){_NAMES}\s+(?:n.est|est)\s+(?:pas\s+a\s+vendre|intransferable|non\s+transferable)",
    rf"\bintransferables?\s*:\s*{_NAMES}{_STOP}",
]
TO_SELL = [
    rf"\b(?:on\s+(?:peut|va|doit)|je\s+veux|il\s+faut|j.aimerais)\s+vendre\s+{_NAMES}{_STOP}",
    rf"\bon\s+vend\s+(?!pas\b){_NAMES}{_STOP}",
    rf"\bmets?\s+{_NAMES}\s+sur\s+la\s+liste\s+des\s+transferts",
    rf"(?:^|[,.;:!?\n]\s*|\bet\s+){_NAMES}\s+est\s+(?:a\s+vendre|transferable|sur\s+le\s+marche)",
]
MAX_AGE = [
    r"\bages?\s*(?:max(?:imum|imal|i)?|limite|plafond)\s*(?:de|:|=|a)?\s*(\d{2})\s*(?:ans)?\b",
    r"\bpas\s+(?:de\s+(?:joueurs?|recrues?)\s+)?(?:de\s+)?plus\s+de\s+(\d{2})\s*ans\b",
    r"\b(\d{2})\s*ans\s+(?:max(?:imum)?|maxi|au\s+maximum|au\s+plus)\b",
]
UNDER_AGE = r"\b(?:que\s+des|uniquement\s+des|seulement\s+des)\s+(?:joueurs?|recrues?)\s+de\s+moins\s+de\s+(\d{2})\s*ans\b"
AMOUNT = r"(\d+(?:[.,]\d+)?)\s*(millions?|million|mds?|m|k|000)?\s*(?:€|euros?|eur)?"
MAX_FEE = [
    rf"\b(?:indemnite|transfert|achat|recrue)s?\s*(?:max(?:imum|imale)?|plafond|maxi)\s*(?:de|:|=|a)?\s*{AMOUNT}",
    rf"\b(?:pas\s+plus\s+de|jamais\s+plus\s+de|au\s+maximum|maximum|max)\s+{AMOUNT}\s*(?:€|euros?)?\s*(?:par|pour\s+un|pour\s+une)\s+"
    r"(?:transfert|joueur|recrue|achat)",
]
MAX_WAGE = [
    rf"\bsalaires?\s*(?:max(?:imum|imal)?|plafond|maxi)\s*(?:de|:|=|a)?\s*{AMOUNT}\s*(?:€|euros?)?\s*(?P<per>par\s+(?:semaine|an|mois)|/\s*(?:sem|an|mois))?",
]
WINDOW_END = [
    r"\b(?:mercato|fenetre(?:\s+des\s+transferts|\s+de\s+transferts)?|marche\s+des\s+transferts)\s+"
    r"(?:ferme|se\s+ferme|fermera|termine|se\s+termine|finit|s.acheve|cloture)\s+(?:le\s+)?(\d{1,2})(?:er)?\s+([a-z]+)",
    r"\bfin\s+(?:du\s+mercato|de\s+la\s+fenetre(?:\s+des\s+transferts|\s+de\s+transferts)?)\s+(?:le\s+|au\s+|:\s*)?(\d{1,2})(?:er)?\s+([a-z]+)",
]
REMEMBER = r"\b(?:retiens|note|n.oublie\s+pas|souviens-toi|rappelle-toi|garde\s+en\s+tete)\s+(?:bien\s+)?(?:que|qu.)\s*(?P<t>[^\n]{6,300})"


@dataclass
class Decision:
    kind: str  # type de souvenir (memories.kind)
    key: str | None
    value: dict
    text: str


@dataclass
class CoachRules:
    """Décisions en vigueur pour une carrière (mémoire + limites des préférences)."""

    never_sell: dict[int, str] = field(default_factory=dict)
    to_sell: dict[int, str] = field(default_factory=dict)
    max_age: int | None = None
    max_fee: float | None = None  # devise affichée
    max_wage: float | None = None  # devise affichée, par semaine
    window_end: date | None = None
    sources: dict[str, str] = field(default_factory=dict)  # règle -> texte du souvenir

    def as_dict(self) -> dict:
        return {"ne_pas_vendre": sorted(self.never_sell.values()), "a_vendre": sorted(self.to_sell.values()),
                "age_max_recrue": self.max_age, "indemnite_max": self.max_fee, "salaire_max_hebdo": self.max_wage,
                "fin_fenetre_transferts": self.window_end.isoformat() if self.window_end else None}


def fold1(text: str) -> str:
    """Minuscules sans accents, MÊME longueur que le texte (les positions restent valables)."""
    out = []
    for ch in text.replace("’", "'"):
        base = unicodedata.normalize("NFD", ch)[:1] or ch
        out.append(base.lower()[:1] or base)
    return "".join(out)


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9'-]+", fold1(text)) if len(w) > 2]


def match_players(chunk: str, squad: list[dict]) -> list[dict]:
    """Joueurs de l'effectif nommés dans `chunk` (nom complet, ou nom de famille sans ambiguïté).

    « Soulé, Koné et Dybala » : tous ; « Soulé et on prolonge Koné » : Soulé seulement (après le
    premier nom, une partie qui n'est pas uniquement un nom arrête la liste)."""
    found: dict[int, dict] = {}
    for i, part in enumerate(re.split(r",|\bet\b|\bni\b|&", fold1(chunk))):
        words = set(_tokens(part)) - {"pas", "non", "plus", "les", "lui", "aussi"}
        if not words:
            continue
        full = [p for p in squad if (toks := _tokens(p["name"])) and set(toks) <= words]
        last = [p for p in squad if (toks := _tokens(p["name"])) and toks[-1] in words]
        hit = full[0] if len(full) == 1 else last[0] if len(last) == 1 else None
        if hit is None or (i > 0 and not words <= set(_tokens(hit["name"]))):
            if found:
                break
            continue
        found[hit["uid"]] = hit
    return list(found.values())


def _amount(num: str, unit: str | None) -> float | None:
    try:
        x = float(num.replace(",", "."))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit.startswith("m") and not unit.startswith("md"):
        x *= 1_000_000
    elif unit.startswith("md"):
        x *= 1_000_000_000
    elif unit == "k":
        x *= 1_000
    elif unit == "000":
        x *= 1_000
    return x if x > 0 else None


def _next_date(day: int, month: int, today: date | None) -> date | None:
    if not 1 <= month <= 12:
        return None
    ref = today or date.today()
    for year in (ref.year, ref.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= ref:
            return d
    return None


def _fmt_eur(x: float) -> str:
    if x >= 1_000_000:
        return f"{x / 1_000_000:.1f}".replace(".0", "").replace(".", ",") + " M€"
    return f"{x:,.0f}".replace(",", " ") + " €"


def detect_decisions(text: str, squad: list[dict], game_date: date | None) -> list[Decision]:
    """Décisions durables exprimées dans un message de l'entraîneur (aucune IA)."""
    low = fold1(text)
    out: list[Decision] = []
    taken: list[tuple[int, int]] = []

    def free(span: tuple[int, int]) -> bool:
        return not any(a < span[1] and span[0] < b for a, b in taken)

    for patterns, rule in ((NEVER_SELL, "ne_pas_vendre"), (TO_SELL, "a_vendre")):
        for pat in patterns:
            for m in re.finditer(pat, low):
                if not free(m.span()):
                    continue
                players = match_players(text[m.start("n"):m.end("n")], squad)
                if not players:
                    continue
                taken.append(m.span())
                for p in players:
                    label = "ne pas vendre" if rule == "ne_pas_vendre" else "à vendre"
                    out.append(Decision(
                        "decision" if rule == "ne_pas_vendre" else "a_vendre", f"vente:{p['uid']}",
                        {"regle": rule, "player_uid": p["uid"], "joueur": p["name"]},
                        f"{p['name']} : {label} (décision de l'entraîneur)."))
    ages = [int(m.group(1)) for pat in MAX_AGE for m in re.finditer(pat, low)]
    ages += [int(m.group(1)) - 1 for m in re.finditer(UNDER_AGE, low)]
    ages = [a for a in ages if 16 <= a <= 40]
    if ages:
        out.append(Decision("preference", "age_max_recrue", {"regle": "age_max_recrue", "value": min(ages)},
                            f"Recrues : {min(ages)} ans maximum (décision de l'entraîneur)."))
    for pat in MAX_FEE:
        m = re.search(pat, low)
        if m and (x := _amount(m.group(1), m.group(2))) and x >= 100_000:
            out.append(Decision("preference", "indemnite_max", {"regle": "indemnite_max", "value": x},
                                f"Indemnité de transfert : {_fmt_eur(x)} maximum par joueur (décision de l'entraîneur)."))
            break
    for pat in MAX_WAGE:
        m = re.search(pat, low)
        if m and (x := _amount(m.group(1), m.group(2))):
            per = m.group("per") or ""
            if re.search(r"\ban\b", per):
                x = x / 52
            elif "mois" in per:
                x = x * 12 / 52
            out.append(Decision("preference", "salaire_max_hebdo", {"regle": "salaire_max_hebdo", "value": round(x)},
                                f"Salaire : {_fmt_eur(round(x))} par semaine maximum (décision de l'entraîneur)."))
            break
    for pat in WINDOW_END:
        m = re.search(pat, low)
        if m and m.group(2) in MONTHS and (d := _next_date(int(m.group(1)), MONTHS[m.group(2)], game_date)):
            out.append(Decision("preference", "fin_fenetre_transferts", {"regle": "fin_fenetre_transferts",
                                                                          "value": d.isoformat()},
                                f"Fenêtre des transferts : fermeture le {d.strftime('%d/%m/%Y')} (indiquée par l'entraîneur)."))
            break
    if not out:
        m = re.search(REMEMBER, low)
        if m:
            said = text[m.start("t"):m.end("t")].strip().rstrip(".!")
            out.append(Decision("decision", None, {"regle": "note"}, said[:1].upper() + said[1:] + "."))
    return out


def capture_decisions(engine: Engine, career_id: int, text: str, squad: list[dict],
                      game_date: date | None) -> list[Decision]:
    """Enregistre les décisions du message, datées (date du jeu) et avec la phrase de l'entraîneur ; une décision
    identique déjà en vigueur n'est pas dupliquée."""
    found = detect_decisions(text, squad, game_date)
    if not found:
        return []
    store = MemoryStore(engine)
    active = store.list(career_id)
    source = " ".join(text.split())
    source = source if len(source) <= 160 else source[:159] + "…"
    saved = []
    for d in found:
        same = [m for m in active if (d.key and m["cle"] == d.key and (m["valeur"] or {}).get("regle") == d.value.get("regle")
                                      and (m["valeur"] or {}).get("value") == d.value.get("value"))
                or (not d.key and m["texte"].startswith(d.text))]
        if same:
            continue
        d.value = d.value | {"phrase": source}
        when = f" le {game_date.strftime('%d/%m/%Y')}" if game_date else ""
        store.add(career_id, d.kind, f"{d.text} Dit{when} : « {source} »", key=d.key, value=d.value, game_date=game_date)
        saved.append(d)
    return saved


def coach_rules(engine: Engine, career_id: int, prefs=None) -> CoachRules:
    """Décisions en vigueur : souvenirs structurés de la carrière, puis limites des préférences."""
    rules = CoachRules()
    for m in MemoryStore(engine).list(career_id):
        v = m.get("valeur") or {}
        rule = v.get("regle")
        if rule == "ne_pas_vendre" and v.get("player_uid"):
            rules.never_sell[int(v["player_uid"])] = v.get("joueur") or str(v["player_uid"])
        elif rule == "a_vendre" and v.get("player_uid"):
            rules.to_sell[int(v["player_uid"])] = v.get("joueur") or str(v["player_uid"])
        elif rule == "age_max_recrue" and v.get("value"):
            rules.max_age, rules.sources["age_max_recrue"] = int(v["value"]), m["texte"]
        elif rule == "indemnite_max" and v.get("value"):
            rules.max_fee, rules.sources["indemnite_max"] = float(v["value"]), m["texte"]
        elif rule == "salaire_max_hebdo" and v.get("value"):
            rules.max_wage, rules.sources["salaire_max_hebdo"] = float(v["value"]), m["texte"]
        elif rule == "fin_fenetre_transferts" and v.get("value"):
            rules.window_end, rules.sources["fin_fenetre_transferts"] = date.fromisoformat(v["value"]), m["texte"]
    if prefs is not None:
        lim = prefs.limits
        for uid in lim.never_sell:
            rules.never_sell.setdefault(int(uid), str(uid))
        if rules.max_fee is None and lim.max_fee is not None:
            rules.max_fee = lim.max_fee
        if rules.max_wage is None and lim.max_wage is not None:
            rules.max_wage = lim.max_wage
    return rules


def decisions_hint(saved: list[Decision]) -> str:
    """Consigne ajoutée au message de l'entraîneur quand une décision vient d'être retenue."""
    items = " ; ".join(d.text for d in saved)
    return (f"[Consigne automatique : décision de l'entraîneur retenue dans la mémoire du club, partagée avec tout le "
            f"staff : {items} Accuse-la en une phrase et applique-la désormais ; inutile d'appeler « remember ».]")


__all__ = ["CoachRules", "Decision", "capture_decisions", "coach_rules", "decisions_hint", "detect_decisions",
           "fold1", "match_players"]
