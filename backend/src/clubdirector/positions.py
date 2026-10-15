"""Codes de poste FM26 (tels que lus par fmsave) et alias français."""

from __future__ import annotations

from clubdirector.text import fold

# Ordre et libellés issus de fmsave/_layouts/fm26_26_3_2.py (position_codes).
CODES = ("GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "AML", "AMC", "AMR", "STC", "WBL", "WBR")

LABEL_FR = {
    "GK": "Gardien", "SW": "Libéro", "DL": "Défenseur gauche", "DC": "Défenseur central",
    "DR": "Défenseur droit", "DM": "Milieu défensif", "ML": "Milieu gauche", "MC": "Milieu central",
    "MR": "Milieu droit", "AML": "Ailier gauche", "AMC": "Milieu offensif central",
    "AMR": "Ailier droit", "STC": "Attaquant", "WBL": "Piston gauche", "WBR": "Piston droit",
}

ALIASES = {
    "gb": "GK", "gk": "GK", "gardien": "GK",
    "lib": "SW", "libero": "SW", "sw": "SW",
    "dg": "DL", "dl": "DL", "lateral gauche": "DL", "arriere gauche": "DL",
    "dc": "DC", "defenseur central": "DC", "central": "DC",
    "dd": "DR", "dr": "DR", "lateral droit": "DR", "arriere droit": "DR",
    "mdc": "DM", "dm": "DM", "milieu defensif": "DM", "sentinelle": "DM",
    "mg": "ML", "ml": "ML", "milieu gauche": "ML",
    "mc": "MC", "milieu central": "MC", "milieu": "MC",
    "md": "MR", "mr": "MR", "milieu droit": "MR",
    "mog": "AML", "aml": "AML", "ailier gauche": "AML",
    "moc": "AMC", "amc": "AMC", "meneur": "AMC", "milieu offensif": "AMC", "numero 10": "AMC",
    "mod": "AMR", "amr": "AMR", "ailier droit": "AMR",
    "bu": "STC", "st": "STC", "stc": "STC", "att": "STC", "attaquant": "STC", "buteur": "STC",
    "avant-centre": "STC", "avant centre": "STC", "9": "STC",
    "dlg": "WBL", "wbl": "WBL", "piston gauche": "WBL",
    "dld": "WBR", "wbr": "WBR", "piston droit": "WBR",
}


def normalize_position(text: str | None) -> str | None:
    """Convertit un code ou libellé (français ou FM) en code FM26 ; None si inconnu."""
    if not text:
        return None
    key = fold(text).replace("_", " ")
    if key.upper() in CODES:
        return key.upper()
    return ALIASES.get(key)


def split_positions(stored: str | None) -> list[str]:
    return [p for p in (stored or "").split(",") if p]
