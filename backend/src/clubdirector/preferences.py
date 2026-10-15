"""Préférences utilisateur modifiables depuis l'UI (fichier JSON dans le dossier de données).

Distinct de `config.toml` (installation) et de la mémoire conversationnelle (SQLite).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clubdirector.money import CurrencyCalibration


class MercatoLimits(BaseModel):
    """Enveloppe de contrôle des dépenses (section 10.4). Montants en devise affichée."""

    max_fee: float | None = None
    max_wage: float | None = None
    total_budget: float | None = None
    max_bonus: float | None = None
    max_sell_on_pct: float | None = None
    max_counter_offers: int = 2
    max_attempts: int = 3
    excluded_clubs: list[int] = Field(default_factory=list)
    never_sell: list[int] = Field(default_factory=list)


class Preferences(BaseModel):
    knowledge_mode: Literal["realiste", "analyste", "avance"] = "realiste"
    advanced_mode_confirmed: bool = False
    autonomy: Literal["conseiller", "supervise", "delegue"] = "conseiller"
    persona: str = "equilibre"
    director_name: str = "Directeur sportif"
    currency: CurrencyCalibration = Field(default_factory=CurrencyCalibration)
    limits: MercatoLimits = Field(default_factory=MercatoLimits)
    silent_during_matches: bool = True
    active_career_id: int | None = None


class PreferenceStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Preferences:
        if self.path.exists():
            return Preferences.model_validate_json(self.path.read_text(encoding="utf-8"))
        return Preferences()

    def save(self, prefs: Preferences) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(prefs.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
