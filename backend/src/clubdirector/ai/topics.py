"""Qui s'occupe de quoi, et noms inconnus de la carrière (consignes automatiques pour le modèle).

- `topic_owner` : un message dont le sujet relève d'un autre contact (composition → adjoint, staff
  médical → directeur technique, prolongation → directeur sportif…) reçoit une consigne de renvoi.
  Mesuré sur le banc d'évaluation : sans elle, le directeur sportif composait l'équipe et détaillait
  le staff médical à la place de ses collègues.
- `unknown_people` : un nom propre absent de la carrière (« Fais signer Jean-Michel Fictif ») reçoit
  une consigne de démenti ; sans elle, le modèle répondait à côté.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from clubdirector.text import fold

TOPICS: dict[str, re.Pattern] = {
    "entraineur_adjoint": re.compile(
        r"\b(onze|compos?|composition|titulaires?|entra[iî]nements?|s[ée]ances?|tactiques?|syst[eè]me|forme|"
        r"fatigu\w*|causerie|coups? de pied arr[eê]t[ée]s?|adversaires?|rotation|rempla[çc]ants?|banc)\b", re.IGNORECASE),
    "directeur_technique": re.compile(
        r"\b(staff|m[ée]dical|m[ée]dicale|kin[ée]s?|kin[ée]sith[ée]rapeutes?|m[ée]decins?|pr[ée]parateurs?|"
        r"entra[iî]neurs? des gardiens|analystes?|recruteurs?|encadrement|scientifiques?)\b", re.IGNORECASE),
    "directeur_sportif": re.compile(
        r"\b(mercato|transferts?|vends?|vendre|vendez|ach[eè]te\w*|recrute\w*|prolong\w*|contrats?|budgets?|"
        r"salaires?|masse salariale|offres?|clauses?|agents?|pr[eê]t(er)?)\b", re.IGNORECASE),
}
LABELS = {"entraineur_adjoint": "le terrain", "directeur_technique": "le staff", "directeur_sportif": "le mercato et les contrats"}


def topic_owner(message: str, role: str) -> str | None:
    """Le contact à qui revient le sujet, s'il n'est pas `role` ; None si le sujet est le sien ou ambigu."""
    hits = {owner for owner, pattern in TOPICS.items() if pattern.search(message)}
    if not hits or role in hits:
        return None
    if role == "directeur_sportif" and hits == {"directeur_technique"} and re.search(r"\brecrut", message, re.IGNORECASE):
        return None
    return next(iter(hits)) if len(hits) == 1 else None


def redirect_hint(owner: str, name: str | None) -> str:
    who = name or {"entraineur_adjoint": "l'adjoint", "directeur_technique": "le directeur technique",
                   "directeur_sportif": "le directeur sportif"}[owner]
    return (f"[Consigne automatique : ce sujet relève de {who} ({LABELS[owner]}). Réponds en une ou deux phrases en "
            "renvoyant vers lui, sans traiter le fond toi-même ; ajoute seulement l'angle de ton métier s'il y en a un.]")


NAME_RE = re.compile(r"\b([A-ZÀ-Ý][\wà-ÿ'’-]+(?:[ -][A-ZÀ-Ý][\wà-ÿ'’-]+){1,2})\b")
# Mots en tête de phrase qui ne sont pas des noms (verbes, pronoms, formules).
LEADING = {"fais", "mets", "aligne", "vends", "achete", "recrute", "prolonge", "trouve", "prepare", "est", "et", "on",
           "notre", "nos", "le", "la", "les", "un", "une", "que", "qui", "quel", "quelle", "pourquoi", "comment",
           "bonjour", "salut", "merci", "coach", "oui", "non", "ok", "vas", "dis", "donne", "regarde", "analyse",
           "estime", "liste", "virez", "recrutez", "prolongez", "faites", "mettez", "alignez"}


def _candidates(message: str) -> list[str]:
    out = []
    for m in NAME_RE.finditer(message):
        phrase = m.group(1)
        # Retire les mots de tête qui ne sont pas des noms, en gardant les séparateurs d'origine (traits d'union).
        while (first := re.match(r"([^ -]+)[ -]", phrase)) and fold(first.group(1)) in LEADING:
            phrase = phrase[first.end():]
        if len(re.split(r"[ -]", phrase)) >= 2:
            out.append(phrase)
    return out


def unknown_people(engine, career_id: int, message: str) -> list[str]:
    """Noms propres (au moins deux mots) qui ne correspondent à aucun joueur, membre du staff, club ni
    compétition de la carrière."""
    found = []
    for name in _candidates(message):
        key = f"%{fold(name)}%"
        try:
            with engine.connect() as c:
                hit = c.execute(text("SELECT 1 FROM players_current WHERE career_id = :k AND name_search LIKE :n LIMIT 1"),
                                {"k": career_id, "n": key}).first()
                if hit is None:
                    for sql in ("SELECT 1 FROM fm_staff WHERE career_id = :k AND lower(name) LIKE lower(:raw) LIMIT 1",
                                "SELECT 1 FROM fm_clubs WHERE career_id = :k AND (lower(name) LIKE lower(:raw) "
                                "OR lower(short_name) LIKE lower(:raw)) LIMIT 1",
                                "SELECT 1 FROM fm_competitions WHERE career_id = :k AND lower(name) LIKE lower(:raw) LIMIT 1"):
                        try:
                            hit = c.execute(text(sql), {"k": career_id, "raw": f"%{name}%"}).first()
                        except Exception:  # noqa: BLE001 — table absente
                            hit = None
                        if hit is not None:
                            break
        except Exception:  # noqa: BLE001
            continue
        if hit is None:
            found.append(name)
    return found


def unknown_hint(names: list[str]) -> str:
    listed = ", ".join(f"« {n} »" for n in names)
    return (f"[Consigne automatique : {listed} ne correspond à aucun joueur, membre du staff ni club de la carrière. "
            "Dis-le simplement à l'entraîneur, sans inventer qui c'est, et demande-lui de préciser.]")


def people_facts(engine, career_id: int, club_uid: int | None, message: str, money=None) -> list[str]:
    """Faits de la carrière sur les personnes citées qui ne sont pas au club (club, âge, poste, valeur ;
    fonction pour le staff). Évite de traiter « Recrutez Pep Guardiola comme adjoint » comme une piste
    ordinaire ou d'ignorer qu'un joueur appartient à un autre club."""
    from clubdirector.ai.director_identity import staff_function

    facts = []
    for name in _candidates(message):
        key = f"%{fold(name)}%"
        try:
            with engine.connect() as c:
                p = c.execute(text(
                    "SELECT name, club_name, club_uid, age, positions, transfer_value FROM players_current "
                    "WHERE career_id = :k AND name_search LIKE :n ORDER BY transfer_value DESC LIMIT 1"),
                    {"k": career_id, "n": key}).mappings().first()
                s = None if p else c.execute(text(
                    "SELECT name, club_name, club_uid, age, unknown_r4 AS code, list_indexes FROM fm_staff "
                    "WHERE career_id = :k AND lower(name) LIKE lower(:raw) LIMIT 1"),
                    {"k": career_id, "raw": f"%{name}%"}).mappings().first()
        except Exception:  # noqa: BLE001
            continue
        if p and p["club_uid"] != club_uid:
            pos = "/".join(x for x in (p["positions"] or "").split(",") if x)
            value = f", valeur {money(p['transfer_value'])}" if money and p["transfer_value"] else ""
            facts.append(f"{p['name']} : joueur de {p['club_name'] or 'aucun club'}, {p['age']} ans, {pos}{value}")
        elif s and s["club_uid"] != club_uid:
            role = staff_function(s["code"], s["list_indexes"]) or "membre du staff"
            facts.append(f"{s['name']} : {role.lower()} de {s['club_name'] or 'aucun club'}, {s['age']} ans")
    return facts


def facts_hint(facts: list[str]) -> str:
    return ("[Faits de la carrière sur les personnes citées (pas chez nous) : " + " ; ".join(facts)
            + ". Tiens-en compte (club actuel, fonction, prix) et reste réaliste.]")


OFF_TOPIC_RE = re.compile(
    r"\b(films?|s[ée]ries?|netflix|marvel|m[ée]t[ée]o|il fait (beau|chaud|froid)|basket|tennis|rugby|formule ?1|"
    r"politique|musique|concert|jeux? vid[ée]o|vacances|restaurant|resto|cuisine|recette|voiture)\b", re.IGNORECASE)
OFF_TOPIC_HINT = ("[Consigne automatique : message hors sujet. Réponds en UNE bulle courte, en restant dans ton "
                  "personnage, puis reviens au club par une question ; pas de rapport ni de point non demandé.]")
