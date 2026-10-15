"""Rôles du staff (contacts du téléphone) : personnalités et construction des prompts.

Trois scripts de rôle, modifiables sans toucher au code : `role_directeur_sportif.md`,
`role_directeur_technique.md`, `role_entraineur_adjoint.md`, suivis du format commun des messages
(`style_messagerie.md`). L'identité vient de la personne EN POSTE dans la carrière
(ai/director_identity.py). Les variables `$nom` s'y remplissent avec `string.Template`.

Rapidité : le prompt système ne contient que ce qui change rarement (rôle, identité, collègues).
Le dossier du club, la date du jeu et la mémoire, qui changent à chaque sauvegarde, vont dans un
premier message « DOSSIER » placé après les outils : le serveur local réutilise ainsi le calcul du
prompt système et des outils d'une sauvegarde à l'autre.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

HERE = Path(__file__).parent
ROLE_FILES = {
    "directeur_sportif": "role_directeur_sportif.md",
    "directeur_technique": "role_directeur_technique.md",
    "entraineur_adjoint": "role_entraineur_adjoint.md",
}
ROLE_FILE = HERE / ROLE_FILES["directeur_sportif"]
STYLE_FILE = HERE / "style_messagerie.md"
ROLE_LABELS = {
    "directeur_sportif": "Directeur sportif",
    "directeur_technique": "Directeur technique",
    "entraineur_adjoint": "Entraîneur adjoint",
}
ROLE_DOMAINS = {
    "directeur_sportif": "mercato, contrats des joueurs, budgets",
    "directeur_technique": "staff technique : entraîneurs, préparateurs, médical, recruteurs, organisation de l'encadrement",
    "entraineur_adjoint": "terrain : matchs, statistiques, joueurs, entraînement, onze type, notes, jeu",
}

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

TAKING_OFFICE = """[Message automatique, invisible pour l'entraîneur] Tu viens de prendre tes fonctions de
directeur sportif et l'entraîneur vient d'enregistrer ton numéro. Envoie-lui tes tout premiers messages :
présente-toi (prénom, nom, âge, date d'arrivée, durée de contrat, ta façon de travailler d'après ton profil),
montre en une ou deux phrases chiffrées que tu as déjà étudié le club grâce au dossier (situation, forces,
points de vigilance, dossiers urgents), annonce tes trois priorités pour les semaines à venir, puis
demande-lui ce qu'il attend de toi. 3 à 5 bulles courtes séparées par une ligne vide, ton naturel et
professionnel, sans titres, sans listes numérotées. Ne consulte aucune donnée : le dossier suffit."""

FIRST_CONTACT = """[Message automatique, invisible pour l'entraîneur] L'entraîneur vient d'enregistrer ton
numéro dans son téléphone. Envoie-lui ton premier message, comme le ferait un vrai {label_lower} :
salue-le, présente-toi en une phrase (prénom, poste), cite un ou deux faits concrets du dossier qui
relèvent de ton domaine ({domain}), puis demande-lui comment il veut travailler avec toi. 2 ou 3 bulles
courtes séparées par une ligne vide. Ne consulte aucune donnée : le dossier suffit."""

TAKE_OFFICE_REQUEST = (
    "Bienvenue au club. Présentez-vous, faites-moi votre premier état des lieux à partir des données réelles "
    "(effectif, résultats, finances, contrats, jeunes) et dites-moi vos priorités."
)


def _fr(d: str | None) -> str | None:
    if not d:
        return None
    y, m, j = str(d)[:10].split("-")
    return f"{j}/{m}/{y}"


def _identity_values(role: str, identity: Any, fallback_name: str) -> dict[str, str]:
    label = ROLE_LABELS[role].lower()
    if identity is not None:
        prenom = identity.first_name or identity.name.split(" ")[0]
        parts = []
        if identity.age:
            parts.append(f"Tu as {identity.age} ans.")
        if identity.contract_start:
            parts.append(f"Tu es arrivé au club le {_fr(identity.contract_start)}")
            parts[-1] += f" et ton contrat court jusqu'au {_fr(identity.contract_end)}." if identity.contract_end else "."
        traits = "\n".join(f"- {t}" for t in identity.traits) or "- (aucune préférence très marquée : profil équilibré)"
        return {"nom_complet": identity.name, "prenom": prenom, "identite_detail": " ".join(parts), "traits": traits}
    return {
        "nom_complet": fallback_name, "prenom": fallback_name.split(" ")[0],
        "identite_detail": (f"La sauvegarde ne désigne actuellement aucun {label} au club : tu occupes la fonction "
                            f"sans identité de jeu. Si l'entraîneur en recrute un dans FM26, il prendra ta place."),
        "traits": f"- (inconnu : aucun {label} dans la sauvegarde)",
    }


def _colleagues(role: str, team: dict[str, Any]) -> tuple[str, dict[str, str]]:
    lines, names = [], {}
    for other, label in ROLE_LABELS.items():
        member = team.get(other)
        short = {"directeur_sportif": "nom_ds", "directeur_technique": "nom_dt", "entraineur_adjoint": "nom_adjoint"}[other]
        names[short] = member.name if member is not None else f"le {label.lower()}"
        if other == role:
            continue
        who = member.name if member is not None else "poste vacant dans la sauvegarde"
        lines.append(f"- {label} : {who} ({ROLE_DOMAINS[other]})")
    text = ("## LE STAFF AVEC QUI TU TRAVAILLES (les autres contacts du téléphone de l'entraîneur)\n"
            + "\n".join(lines)
            + "\nTu peux les citer par leur prénom et renvoyer vers eux ; tu ne parles jamais à leur place.")
    return text, names


def build_system_prompt(*, director_name: str = "Directeur sportif", club: str | None, persona: str = "equilibre",
                        knowledge: str = "realiste", manager: str | None = None, identity: Any = None,
                        role: str = "directeur_sportif", team: dict[str, Any] | None = None, **_ignored: Any) -> str:
    """Prompt système stable d'un contact. `identity` : la personne en poste (sauvegarde) ou None.

    `team` : {rôle: personne ou None} pour présenter les collègues. Les données qui changent à chaque
    sauvegarde n'y figurent pas (voir `build_context_message`)."""
    team = dict(team or {})
    team.setdefault(role, identity)
    p = PERSONAS.get(persona, PERSONAS["equilibre"])
    fallback = director_name if role == "directeur_sportif" else ROLE_LABELS[role]
    collegues, names = _colleagues(role, team)
    values = {
        "club": club or "(club non détecté)", "entraineur": manager or "l'entraîneur",
        "style_persona": p["style"], "connaissance": knowledge, "collegues": collegues,
        **names, **_identity_values(role, identity, fallback),
    }
    script = (HERE / ROLE_FILES[role]).read_text(encoding="utf-8")
    style = STYLE_FILE.read_text(encoding="utf-8")
    return Template(script.rstrip("\n") + "\n\n" + style).safe_substitute(values)


def build_context_message(*, club: str | None, game_date: str | None, season: str, dossier: str | None,
                          memories: list[dict]) -> str:
    """Premier message de chaque conversation : l'état du club à la dernière sauvegarde."""
    mem = "\n".join(f"- [{m['type']}] {m['texte']}" for m in memories) or "- (aucune pour l'instant)"
    when = _fr(game_date) or "inconnue"
    return (f"DOSSIER — message automatique du service ClubDirector, pas de l'entraîneur.\n"
            f"Club : {club or '(non détecté)'} · saison {season} · date du jeu à la dernière sauvegarde : {when}\n\n"
            f"{dossier or '- (dossier indisponible : synchronisez la sauvegarde)'}\n\n"
            f"MÉMOIRE — préférences et décisions de l'entraîneur :\n{mem}")


def first_contact_request(role: str, *, taking_office: bool) -> str:
    if role == "directeur_sportif" and taking_office:
        return TAKING_OFFICE
    return FIRST_CONTACT.format(label_lower=ROLE_LABELS[role].lower(), domain=ROLE_DOMAINS[role])
