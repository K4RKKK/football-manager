"""Routage économique.

Niveau 0 : questions factuelles reconnues → outils + gabarit de réponse, AUCUN appel IA.
Niveau 1 : modèle local. Niveau 2 : petit modèle API. Niveau 3 : modèle avancé (sur demande
ou selon la politique). Le classement est déterministe (expressions régulières) et testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from clubdirector.positions import LABEL_FR, normalize_position
from clubdirector.text import fold

NUM_FR = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
          "neuf": 9, "dix": 10, "quinze": 15, "quatorze": 14}


@dataclass
class Intent:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


def _num(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return NUM_FR.get(token)


POSITION_WORDS = (
    r"(gardiens?|liberos?|defenseurs? centraux|defenseur central|centraux|lateraux gauches?|lateral gauche|"
    r"lateraux droits?|lateral droit|milieux? defensifs?|milieux? centraux|milieu central|ailiers? gauches?|"
    r"ailiers? droits?|milieux? offensifs?|attaquants?|buteurs?|avant-centres?|pistons? gauches?|pistons? droits?|"
    r"gb|dc|dg|dd|mdc|mc|moc|mog|mod|bu)"
)

_SINGULAR = {
    "gardiens": "gardien", "liberos": "libero", "defenseurs centraux": "defenseur central", "centraux": "central",
    "lateraux gauches": "lateral gauche", "lateraux gauche": "lateral gauche", "lateraux droits": "lateral droit",
    "lateraux droit": "lateral droit", "milieux defensifs": "milieu defensif", "milieux defensif": "milieu defensif",
    "milieu defensifs": "milieu defensif", "milieux centraux": "milieu central", "ailiers gauches": "ailier gauche",
    "ailiers gauche": "ailier gauche", "ailiers droits": "ailier droit", "ailiers droit": "ailier droit",
    "milieux offensifs": "milieu offensif", "milieux offensif": "milieu offensif", "attaquants": "attaquant",
    "buteurs": "buteur", "avant-centres": "avant-centre", "pistons gauches": "piston gauche", "pistons droits": "piston droit",
}


def _position(word: str) -> str | None:
    w = _SINGULAR.get(word, word)
    return normalize_position(w)


ADVICE_RE = re.compile(
    r"surveiller|pourquoi|analyse|conseil|recommand|penses?[- ]tu|pensez[- ]vous|avis|que faut[- ]il|faudrait[- ]il|"
    r"devrions|dois[- ]je|doit[- ]on|comment (?:ameliorer|faire|expliquer|corriger)|strategie|priorit|bilan|"
    r"compar|explique|propose|suggere|que faire"
)


def classify(question: str) -> Intent | None:
    """Reconnaît les questions résolubles exactement par les données. None → IA."""
    q = fold(question).replace("’", "'")
    q = re.sub(r"\s+", " ", q)
    # Une demande d'avis ou d'analyse, même accolée à une question factuelle, va à l'IA :
    # le niveau 0 ne sait répondre qu'au fait, pas au conseil.
    if ADVICE_RE.search(q):
        return None

    if m := re.search(r"combien (?:de |d')?(?:joueurs? )?" + POSITION_WORDS + r"(?: avons[- ]nous| a[- ]t[- ]on| on a| dans)", q) \
            or re.search(r"combien (?:avons[- ]nous|a[- ]t[- ]on|on a) (?:de |d')" + POSITION_WORDS, q):
        pos = _position(m.group(1))
        if pos:
            return Intent("count_position", {"position": pos})

    if re.search(r"combien (?:de joueurs|avons[- ]nous de joueurs)|taille de (?:notre |l')effectif", q):
        return Intent("squad_size")

    previous = bool(re.search(r"saison (?:derniere|precedente|passee)|l'an dernier|l'annee derniere|dernier exercice|exercice precedent", q))
    rel = -1 if previous else 0

    if re.search(r"meilleur (?:buteur|marqueur)|qui (?:a |est )?(?:le plus )?marque le plus|top buteurs?", q):
        return Intent("top_stat", {"stat": "goals", "relative_season": rel})
    if re.search(r"meilleur passeur|plus de passes decisives|top passeurs?", q):
        return Intent("top_stat", {"stat": "assists", "relative_season": rel})

    if m := re.search(r"combien (?:de buts )?(?P<name>[a-z' .-]{2,40}?) a(?:[- ]t[- ](?:il|elle))? (?:t[- ]il |t[- ]elle )?marque", q):
        name = m.group("name").strip()
        if name not in {"nous", "on", "l'equipe", "le club"}:
            return Intent("player_goals", {"name": name, "relative_season": rel})

    if m := re.search(r"il y a (\w+) (jours?|semaines?)", q):
        n = _num(m.group(1))
        if n is not None and re.search(r"score|resultat|match|joue", q):
            days = n * 7 if m.group(2).startswith("semaine") else n
            return Intent("match_days_ago", {"days_ago": days})
    if re.search(r"(?:score|resultat).{0,30}semaine derniere|semaine derniere.{0,30}(?:score|resultat|match)", q):
        return Intent("match_days_ago", {"days_ago": 7})
    if re.search(r"dernier (?:match|resultat|score)|derniers? resultats?", q):
        return Intent("recent_matches", {"limit": 5 if "derniers" in q else 1})
    if re.search(r"prochain match|prochains matchs|calendrier", q):
        return Intent("upcoming", {"limit": 3})
    if re.search(r"classement|on est (?:ou|combien)ieme|position au classement", q):
        return Intent("table")
    if re.search(r"budget (?:des )?transferts?|budget mercato", q):
        return Intent("transfer_budget")
    if re.search(r"budget salari|masse salariale|marge salariale", q):
        return Intent("wage_budget")
    if re.search(r"contrats? (?:qui )?(?:expir|se termin|arriv)|fins? de contrat", q):
        return Intent("expiring")
    return None


def wants_premium(question: str) -> bool:
    q = fold(question)
    return bool(re.search(r"analyse (?:approfondie|detaillee|complete)|en profondeur|strategie (?:a long terme|globale)|plan(?:ifie)? (?:notre|le) mercato", q))


# ------------------------------------------------------------------ réponses déterministes
# Écrites comme un message d'un membre du staff (phrases courtes, « on », jamais « vous »/« tu ») :
# elles doivent se fondre dans la conversation au même titre que les réponses du modèle.
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
STAT_TYPES = {"league": "en championnat", "cup": "en coupe", "continental": "en coupe d'Europe",
              "international": "en sélection", "non_competitive": "en amical"}

# Intentions sans IA autorisées par contact : le directeur technique s'occupe du staff (aucune), l'adjoint
# du terrain (pas des budgets ni des contrats), le directeur sportif de tout.
ROLE_INTENTS: dict[str, set[str] | None] = {
    "directeur_sportif": None,
    "directeur_technique": set(),
    "entraineur_adjoint": {"count_position", "squad_size", "top_stat", "player_goals", "match_days_ago",
                           "recent_matches", "upcoming", "table"},
}


def intent_allowed(role: str, intent: Intent | None) -> bool:
    allowed = ROLE_INTENTS.get(role)
    return intent is not None and (allowed is None or intent.name in allowed)


def fr_date(iso: str | None) -> str:
    if not iso:
        return "date inconnue"
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def day_month(iso: str | None) -> str:
    """« 19 octobre »."""
    if not iso:
        return "à une date inconnue"
    _y, m, d = iso[:10].split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def answer_intent(intent: Intent, run, short_names=None) -> tuple[str, list[str]]:
    """`run(tool, args)` exécute un outil du registre et renvoie un ToolResult ; `short_names(set)` donne
    les noms courts des clubs (« Roma » plutôt que « Associazione Sportiva Roma »)."""
    lim: list[str] = []

    def call(tool: str, args: dict | None = None):
        r = run(tool, args or {})
        if not r.ok:
            raise LookupError(r.error)
        lim.extend(r.limitations)
        return r.data

    def names(matches: list[dict]) -> dict:
        wanted = {m[k] for m in matches for k in ("domicile", "exterieur") if m.get(k)}
        try:
            return (short_names(wanted) if short_names else {}) or {}
        except Exception:  # noqa: BLE001 — noms courts facultatifs
            return {}

    def match_line(m: dict, sn: dict) -> str:
        home, away = sn.get(m["domicile"], m["domicile"]), sn.get(m["exterieur"], m["exterieur"])
        comp = f" en {m['competition']}" if m.get("competition") else ""
        if m.get("score_disponible"):
            return f"{home} {m['score']} {away}{comp}, le {day_month(m['date'])}"
        return f"{home} – {away}{comp}, le {day_month(m['date'])}"

    n = intent.name
    a = intent.args
    if n == "count_position":
        squad = call("get_club_squad")
        pos = a["position"]
        natural = [p for p in squad if pos in p["postes"]]
        label = LABEL_FR[pos].lower()
        if not natural:
            return (f"Aucun joueur de métier au poste de {label} dans l'effectif.", lim)
        who = ", ".join(p["nom"] for p in natural)
        return (f"Nous avons {_plural(len(natural), 'joueur')} de métier au poste de {label} : {who}.", lim)
    if n == "squad_size":
        squad = call("get_club_squad")
        return (f"On est {len(squad)} dans l'effectif de l'équipe première.", lim)
    if n == "top_stat":
        d = call("get_top_players_stat", {"stat": a["stat"], "relative_season": a["relative_season"], "limit": 3})
        label = "buts" if a["stat"] == "goals" else "passes décisives"
        when = "la saison dernière" if a["relative_season"] else "cette saison"
        if not d["classement"] or not d["classement"][0]["valeur"]:
            return (f"Personne n'a encore de {label} {when} d'après nos relevés.", lim)
        top = d["classement"][0]
        txt = f"C'est {top['joueur']} avec {top['valeur']} {label} {when}, toutes compétitions."
        others = [x for x in d["classement"][1:] if x["valeur"]]
        if others:
            txt += " Derrière : " + ", ".join(f"{x['joueur']} ({x['valeur']})" for x in others) + "."
        return (txt, lim)
    if n == "player_goals":
        d = call("get_player_statistics", {"name": a["name"], "relative_season": a["relative_season"]})
        when = "la saison dernière" if a["relative_season"] else "cette saison"
        overall = [x for x in d["lignes"] if x["type"] == "overall"]
        if not overall:
            return (f"Je n'ai pas de statistiques de {d['joueur']} pour {when} : donnée non disponible dans nos relevés.", lim)
        goals = sum(x["buts"] or 0 for x in overall)
        txt = f"{d['joueur']} en est à {_plural(goals, 'but')} {when}, toutes compétitions."
        detail = [f"{x['buts']} {STAT_TYPES.get(x['type'], x['type'])}" for x in d["lignes"]
                  if x["type"] in STAT_TYPES and x.get("buts")]
        if detail:
            txt += " Dont " + ", ".join(detail) + "."
        return (txt, lim)
    if n == "match_days_ago":
        d = call("get_match_details", {"days_ago": a["days_ago"]})
        if not d["matchs"]:
            near = [m for m in (d.get("match_precedent"), d.get("match_suivant")) if m]
            sn = names(near)
            txt = f"On n'a pas joué autour du {day_month(d['date_cible'])}."
            if d.get("match_precedent"):
                txt += f" Le match d'avant : {match_line(d['match_precedent'], sn)}."
            if d.get("match_suivant"):
                txt += f" Le suivant : {match_line(d['match_suivant'], sn)}."
            return (txt, lim)
        m = d["matchs"][0]
        return (f"C'était {match_line(m, names([m]))}.", lim)
    if n == "recent_matches":
        rows = call("get_recent_matches", {"limit": a["limit"]})
        if not rows:
            return ("On n'a pas encore de match joué dans nos relevés.", lim)
        sn = names(rows)
        if len(rows) == 1:
            return (f"Dernier match : {match_line(rows[0], sn)}.", lim)
        return ("Nos derniers résultats :\n" + "\n".join(f"- {match_line(m, sn)}" for m in rows), lim)
    if n == "upcoming":
        rows = call("get_upcoming_matches", {"limit": a["limit"]})
        if not rows:
            return ("Pas de match programmé dans nos relevés pour l'instant.", lim)
        sn = names(rows)
        txt = f"Prochain match : {match_line(rows[0], sn)}."
        if len(rows) > 1:
            txt += " Ensuite : " + " ; ".join(match_line(m, sn) for m in rows[1:]) + "."
        return (txt, lim)
    if n == "table":
        rows = call("get_league_table")
        if not rows:
            return ("Pas de classement disponible dans nos relevés.", lim)
        me = next((r for r in rows if r["est_notre_club"]), None)
        leader = rows[0]
        if not me:
            return (f"En tête : {leader['club_name']} avec {leader['points']} points.", lim)
        txt = (f"On est {me['position']}{'er' if me['position'] == 1 else 'e'} avec {me['points']} points "
               f"({_plural(me['won'], 'victoire')}, {_plural(me['drawn'], 'nul')}, {_plural(me['lost'], 'défaite')} ; "
               f"{me['goals_for']} buts marqués, {me['goals_against']} encaissés).")
        if leader is not me:
            gap = leader["points"] - me["points"]
            sn = (short_names({leader["club_name"]}) if short_names else {}) or {}
            txt += f" {sn.get(leader['club_name'], leader['club_name'])} est en tête avec {leader['points']} points, {_plural(gap, 'point')} devant nous."
        return (txt, lim)
    if n == "transfer_budget":
        d = call("get_transfer_budget")
        rest, total = d["restant"]["texte"], d["alloue"]["texte"]
        if d["restant"].get("brut") == 0:
            return (f"Le budget transferts est à sec : plus rien sur les {total} alloués.", lim)
        return (f"Il nous reste {rest} sur le budget transferts ({total} alloués au départ).", lim)
    if n == "wage_budget":
        d = call("get_wage_budget")
        return (f"Côté salaires, on a {d['marge_hebdo']['texte']} de marge par semaine : {d['masse_hebdo']['texte']} de masse "
                f"salariale pour un budget de {d['budget_hebdo']['texte']}.", lim)
    if n == "expiring":
        d = call("search_expiring_contracts", {"months": 12, "limit": 100})
        if not d["joueurs"]:
            return (f"Aucun contrat ne se termine avant le {day_month(d['jusqu_au'])}.", lim)
        # Les cadres d'abord : l'équipe première nommément, les jeunes et la réserve en nombre.
        first = [p for p in d["joueurs"] if p.get("equipe_slot") in (0, None)]
        others = len(d["joueurs"]) - len(first)
        if not first:
            return (f"Aucun contrat de l'équipe première ne se termine dans l'année ; {_plural(others, 'contrat')} "
                    "chez les jeunes et en réserve.", lim)
        who = ", ".join(f"{p['nom']} ({day_month(p['fin_contrat'])} {p['fin_contrat'][:4]})" for p in first)
        txt = f"Dans l'équipe première, {_plural(len(first), 'contrat')} se termine{'nt' if len(first) > 1 else ''} dans l'année : {who}."
        if others:
            txt += f" Il y en a aussi {others} chez les jeunes et en réserve."
        return (txt, lim)
    raise ValueError(f"Intention inconnue : {n}")
