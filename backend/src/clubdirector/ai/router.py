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
    if re.search(r"budget salari|masse salariale", q):
        return Intent("wage_budget")
    if re.search(r"contrats? (?:qui )?(?:expir|se termin|arriv)|fins? de contrat", q):
        return Intent("expiring")
    return None


def wants_premium(question: str) -> bool:
    q = fold(question)
    return bool(re.search(r"analyse (?:approfondie|detaillee|complete)|en profondeur|strategie (?:a long terme|globale)|plan(?:ifie)? (?:notre|le) mercato", q))


# ------------------------------------------------------------------ réponses déterministes
def fr_date(iso: str | None) -> str:
    if not iso:
        return "date inconnue"
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def _fmt_match(m: dict) -> str:
    score = m["score"] if m["score_disponible"] else "score non disponible dans la sauvegarde"
    res = f" ({m['resultat']})" if m.get("resultat") else ""
    return f"{fr_date(m['date'])} — {m['domicile']} {score} {m['exterieur']}{res}"


def answer_intent(intent: Intent, run) -> tuple[str, list[str]]:
    """`run(tool, args)` exécute un outil du registre et renvoie un ToolResult."""
    lim: list[str] = []

    def call(tool: str, args: dict | None = None):
        r = run(tool, args or {})
        if not r.ok:
            raise LookupError(r.error)
        lim.extend(r.limitations)
        return r.data

    n = intent.name
    a = intent.args
    if n == "count_position":
        squad = call("get_club_squad")
        pos = a["position"]
        natural = [p for p in squad if pos in p["postes"]]
        names = ", ".join(p["nom"] for p in natural) or "aucun"
        return (f"Nous avons {len(natural)} joueur(s) au poste naturel de {LABEL_FR[pos].lower()} ({pos}) : {names}.", lim)
    if n == "squad_size":
        squad = call("get_club_squad")
        return (f"L'effectif compte {len(squad)} joueurs sous contrat avec le club (sauvegarde synchronisée).", lim)
    if n == "top_stat":
        d = call("get_top_players_stat", {"stat": a["stat"], "relative_season": a["relative_season"], "limit": 3})
        label = "buts" if a["stat"] == "goals" else "passes décisives"
        if not d["classement"]:
            return (f"Je n'ai aucune statistique archivée pour la saison {d['saison']}.", lim)
        if not d["classement"][0]["valeur"]:
            return (f"Saison {d['saison']} : aucun joueur du club n'a encore de {label} enregistré(e)s dans les statistiques archivées.", lim)
        top = d["classement"][0]
        others = "; ".join(f"{x['joueur']} {x['valeur']}" for x in d["classement"][1:])
        txt = f"Saison {d['saison']} (toutes compétitions) : {top['joueur']} est en tête avec {top['valeur']} {label}."
        if others:
            txt += f" Suivent : {others}."
        return (txt, lim)
    if n == "player_goals":
        d = call("get_player_statistics", {"name": a["name"], "relative_season": a["relative_season"]})
        overall = [x for x in d["lignes"] if x["type"] == "overall"]
        if not overall:
            return (f"Aucune statistique archivée pour {d['joueur']} en {d['saison']}.", lim)
        goals = sum(x["buts"] or 0 for x in overall)
        clubs = ", ".join(sorted({x["club"] or "?" for x in overall}))
        detail = "; ".join(f"{x['type']} {x['club'] or '?'} : {x['buts']}" for x in d["lignes"] if x["type"] != "overall")
        txt = f"{d['joueur']} a marqué {goals} but(s) en {d['saison']} toutes compétitions ({clubs})."
        if detail:
            txt += f" Détail : {detail}."
        last = overall[-1]["releve_le"]
        if last:
            txt += f" Relevé à la date de jeu du {fr_date(last)}."
        return (txt, lim)
    if n == "match_days_ago":
        d = call("get_match_details", {"days_ago": a["days_ago"]})
        if not d["matchs"]:
            txt = f"Aucun match de l'équipe première autour du {fr_date(d['date_cible'])} (date du jeu)."
            if d.get("match_precedent"):
                txt += f" Match précédent : {_fmt_match(d['match_precedent'])}."
            if d.get("match_suivant"):
                txt += f" Match suivant : {_fmt_match(d['match_suivant'])}."
            return (txt, lim)
        m = d["matchs"][0]
        return (f"Autour du {fr_date(d['date_cible'])} (date du jeu) : {_fmt_match(m)}.", lim)
    if n == "recent_matches":
        rows = call("get_recent_matches", {"limit": a["limit"]})
        if not rows:
            return ("Aucun match joué trouvé dans la sauvegarde.", lim)
        return ("\n".join(_fmt_match(m) for m in rows), lim)
    if n == "upcoming":
        rows = call("get_upcoming_matches", {"limit": a["limit"]})
        if not rows:
            return ("Aucun match à venir trouvé dans la sauvegarde.", lim)
        return ("Prochains matchs :\n" + "\n".join(f"{fr_date(m['date'])} — {m['domicile']} vs {m['exterieur']}" for m in rows), lim)
    if n == "table":
        rows = call("get_league_table")
        if not rows:
            return ("Aucun classement disponible dans la sauvegarde.", lim)
        me = next((r for r in rows if r["est_notre_club"]), None)
        head = f"Nous sommes {me['position']}e avec {me['points']} points ({me['won']}V {me['drawn']}N {me['lost']}D, {me['goals_for']}-{me['goals_against']})." if me else ""
        table = "\n".join(f"{r['position']}. {r['club_name']} — {r['points']} pts" for r in rows[:10])
        return ((head + "\n" + table).strip(), lim)
    if n == "transfer_budget":
        d = call("get_transfer_budget")
        return (f"Budget transferts ({d['mois']}) : restant {d['restant']['texte']}, alloué {d['alloue']['texte']}.", lim)
    if n == "wage_budget":
        d = call("get_wage_budget")
        return (f"Budget salarial hebdomadaire ({d['mois']}) : {d['budget_hebdo']['texte']} ; masse actuelle {d['masse_hebdo']['texte']} ; marge {d['marge_hebdo']['texte']}.", lim)
    if n == "expiring":
        d = call("search_expiring_contracts", {"months": 12})
        if not d["joueurs"]:
            return (f"Aucun contrat du club n'expire avant le {fr_date(d['jusqu_au'])} (date du jeu).", lim)
        return ("Contrats expirant dans les 12 mois :\n" + "\n".join(f"- {p['nom']} : fin le {fr_date(p['fin_contrat'])}" for p in d["joueurs"]), lim)
    raise ValueError(f"Intention inconnue : {n}")
