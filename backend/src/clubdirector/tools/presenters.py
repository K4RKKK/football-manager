"""Mise en forme des données pour l'IA et l'UI, selon le mode de connaissance.

- réaliste (défaut) : attributs visibles uniquement ; ni CA/PA, ni attributs cachés, ni personnalité.
- analyste : idem + toutes les statistiques ; toujours pas de CA/PA ni attributs cachés.
- avancé : CA/PA, attributs cachés et personnalité — seulement si l'utilisateur l'a confirmé.
"""

from __future__ import annotations

from datetime import date

from clubdirector.database.repositories import ATTRIBUTE_FR, GK_ONLY, HIDDEN_ATTRIBUTES
from clubdirector.positions import LABEL_FR, split_positions
from clubdirector.preferences import Preferences

FOG_LIMITATION = (
    "Brouillard de recrutement non appliqué : la connaissance de vos recruteurs n'est pas lisible "
    "dans la sauvegarde ; les attributs visibles affichés sont les valeurs réelles du jeu."
)


def advanced_allowed(prefs: Preferences) -> bool:
    return prefs.knowledge_mode == "avance" and prefs.advanced_mode_confirmed


def visible_attributes(row: dict, prefs: Preferences) -> dict[str, int | None]:
    attrs = row.get("attributes") or {}
    is_gk = "GK" in split_positions(row.get("positions"))
    out = {}
    for k, v in attrs.items():
        if k in HIDDEN_ATTRIBUTES and not advanced_allowed(prefs):
            continue
        if k in GK_ONLY and not is_gk:
            continue
        if k not in ATTRIBUTE_FR and k not in HIDDEN_ATTRIBUTES:
            continue
        out[k] = v
    return out


def money(prefs: Preferences, raw: int | None) -> dict:
    return {
        "brut": raw,
        "affiche": prefs.currency.to_display(raw),
        "texte": prefs.currency.format(raw),
    }


def player_summary(row: dict, prefs: Preferences, today: date | None = None) -> dict:
    pos = split_positions(row.get("positions"))
    out = {
        "uid": row["uid"],
        "nom": row["name"],
        "age": row.get("age"),
        "club": row.get("club_name"),
        "club_uid": row.get("club_uid"),
        "equipe_slot": row.get("team_slot"),
        "postes": pos,
        "postes_libelles": [LABEL_FR.get(p, p) for p in pos],
        "valeur": money(prefs, row.get("transfer_value")),
        "salaire": money(prefs, row.get("wage")),
        "fin_contrat": row.get("contract_end").isoformat() if row.get("contract_end") else None,
        "pret": bool(row.get("on_loan")),
    }
    if advanced_allowed(prefs):
        out["ca"] = row.get("current_ability")
        out["pa"] = row.get("potential_ability")
    return out


def player_full(row: dict, prefs: Preferences) -> dict:
    out = player_summary(row, prefs)
    out.update(
        {
            "date_naissance": row.get("birth_date").isoformat() if row.get("birth_date") else None,
            "nation_id": row.get("nation_id"),
            "taille_cm": row.get("height_cm"),
            "pied_gauche": row.get("left_foot"),
            "pied_droit": row.get("right_foot"),
            "postes_secondaires": split_positions(row.get("accomplished_positions")),
            "notes_postes": row.get("position_ratings"),
            "statut_effectif": row.get("squad_status"),
            "debut_contrat": row.get("contract_start").isoformat() if row.get("contract_start") else None,
            "suspendu": bool(row.get("banned")),
            "condition_brute": row.get("condition"),
            "traits": row.get("traits") or [],
            "attributs": visible_attributes(row, prefs),
        }
    )
    out["libelles_attributs"] = {k: ATTRIBUTE_FR.get(k, k) for k in out["attributs"]}
    if advanced_allowed(prefs):
        out["personnalite"] = row.get("personality")
    return out
