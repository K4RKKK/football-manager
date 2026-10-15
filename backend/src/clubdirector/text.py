"""Petites fonctions de normalisation de texte (recherche insensible aux accents)."""

from __future__ import annotations

import unicodedata


def fold(text: str | None) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).casefold().strip()
