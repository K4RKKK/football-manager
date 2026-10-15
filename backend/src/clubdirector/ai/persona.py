"""Rôle du directeur sportif : personnalités et construction du prompt système.

Le texte du rôle est dans `role_directeur_sportif.md` (modifiable sans toucher au code) : identité du
directeur EN POSTE dans la carrière (ai/director_identity.py), rôle exact dans FM26, limites,
méthode, façon de parler, situations particulières, dossier du club (ai/club_brief.py) et mémoire.
Les variables `$nom` s'y remplissent avec `string.Template` (les accolades du texte restent libres).
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

ROLE_FILE = Path(__file__).with_name("role_directeur_sportif.md")

PERSONAS: dict[str, dict[str, str]] = {
    "prudent": {
        "label": "Prudent",
        "style": "discipline financière avant tout : joueurs confirmés, contrats raisonnables, risques limités ; "
                 "tu refuses fermement toute dépense qui fragiliserait le club.",
    },
    "ambitieux": {
        "label": "Ambitieux",
        "style": "tu vises haut et pousses pour des recrutements forts quand le projet le justifie, sans jamais "
                 "ignorer les budgets réels : l'ambition sans moyens n'est pas une stratégie.",
    },
    "developpeur": {
        "label": "Développeur",
        "style": "tu crois aux jeunes talents, au centre de formation, aux prêts formateurs et à la plus-value "
                 "à la revente ; tu raisonnes à trois ou cinq ans.",
    },
    "analytique": {
        "label": "Analytique",
        "style": "tu raisonnes par les données : statistiques, comparaisons chiffrées, méthodes explicites, "
                 "toujours avec leur source et leurs limites.",
    },
    "equilibre": {
        "label": "Équilibré",
        "style": "tu combines prudence financière, ambition sportive, développement des jeunes et rigueur "
                 "analytique, en dosant selon la situation du club.",
    },
}

TAKING_OFFICE = """
---------------------------------------------------------------------------------------------------
## PRISE DE POSTE — À FAIRE MAINTENANT
Tu viens d'arriver au club et c'est ta toute première conversation avec $entraineur. Commence ta
réponse par ta présentation : ton prénom et ton nom, ton âge, la date de ton arrivée et la durée
de ton contrat, ta façon de travailler (en t'appuyant sur ton profil). Montre ensuite que tu as
déjà étudié le club grâce au dossier (situation en championnat, forces, points de vigilance,
dossiers urgents), annonce tes trois priorités pour les semaines à venir, puis demande à
l'entraîneur ce qu'il attend de toi. Si sa demande porte sur autre chose, réponds-y ensuite.
Reste naturel et professionnel, sans emphase excessive.
"""

TAKE_OFFICE_REQUEST = (
    "Bienvenue au club. Présentez-vous, faites-moi votre premier état des lieux à partir des données réelles "
    "(effectif, résultats, finances, contrats, jeunes) et dites-moi vos priorités."
)


def _fr(d: str | None) -> str | None:
    if not d:
        return None
    y, m, j = str(d)[:10].split("-")
    return f"{j}/{m}/{y}"


def build_system_prompt(*, director_name: str, club: str | None, persona: str, game_date: str | None,
                        season: str, knowledge: str, memories: list[dict], manager: str | None = None,
                        dossier: str | None = None, taking_office: bool = False, identity: Any = None) -> str:
    """`identity` : DirectorIdentity du directeur en poste (sauvegarde), ou None (nom des préférences)."""
    p = PERSONAS.get(persona, PERSONAS["equilibre"])
    if identity is not None:
        nom_complet = identity.name
        prenom = identity.first_name or identity.name.split(" ")[0]
        parts = []
        if identity.age:
            parts.append(f"Tu as {identity.age} ans.")
        if identity.contract_start:
            parts.append(f"Tu es arrivé au club le {_fr(identity.contract_start)}")
            parts[-1] += f" et ton contrat court jusqu'au {_fr(identity.contract_end)}." if identity.contract_end else "."
        detail = " ".join(parts)
        traits = "\n".join(f"- {t}" for t in identity.traits) or "- (aucune préférence très marquée : profil équilibré)"
    else:
        nom_complet = director_name
        prenom = director_name.split(" ")[0]
        detail = ("La sauvegarde ne désigne actuellement aucun directeur sportif au club : tu occupes la fonction "
                  "sans identité de jeu. Si l'entraîneur en recrute un dans FM26, il prendra ta place.")
        traits = "- (inconnu : aucun directeur sportif dans la sauvegarde)"
    mem = "\n".join(f"- [{m['type']}] {m['texte']}" for m in memories) or "- (aucune pour l'instant)"
    values = {
        "club": club or "(club non détecté)", "nom_complet": nom_complet, "prenom": prenom,
        "identite_detail": detail, "entraineur": manager or "l'entraîneur", "traits": traits,
        "style_persona": p["style"], "date_jeu": game_date or "inconnue", "saison": season,
        "connaissance": knowledge, "dossier": dossier or "- (dossier indisponible : synchronisez la sauvegarde)",
        "souvenirs": mem,
    }
    prompt = Template(ROLE_FILE.read_text(encoding="utf-8")).safe_substitute(values)
    if taking_office:
        prompt += Template(TAKING_OFFICE).safe_substitute(values)
    return prompt
