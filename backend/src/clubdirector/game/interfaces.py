"""Contrats d'adaptateurs. Chaque source de données est remplaçable indépendamment.

Le chatbot ne voit jamais ces interfaces directement : il passe par le registre d'outils
(`clubdirector.tools`), qui lui-même passe par les dépôts (`clubdirector.database.repositories`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from clubdirector.domain.models import SaveExtract


@runtime_checkable
class ISaveReader(Protocol):
    """Lit une COPIE d'une sauvegarde .fm et la normalise."""

    name: str

    def read(self, snapshot_path: Path) -> SaveExtract: ...


ConnectionState = Literal["absent", "connecte", "carriere_chargee", "incompatible"]


@dataclass(frozen=True)
class LiveStatus:
    state: ConnectionState
    plugin_version: str | None = None
    game_version: str | None = None
    game_date: date | None = None
    managed_club_name: str | None = None
    last_heartbeat: datetime | None = None
    detail: str | None = None


@runtime_checkable
class IGameConnection(Protocol):
    """Connexion au plugin BepInEx exécuté dans FM26 (mode A : lecture directe)."""

    def status(self) -> LiveStatus: ...


@dataclass(frozen=True)
class ActionAvailability:
    available: bool
    reason: str


@runtime_checkable
class IGameActionExecutor(Protocol):
    """Exécute une action dans FM26 et lit sa confirmation. Aucune implémentation validée."""

    def availability(self, action: str) -> ActionAvailability: ...

    def execute(self, action: str, payload: dict, operation_id: str) -> dict: ...


class UnavailableActionExecutor:
    """Exécuteur par défaut : refuse tout, explicitement. Ne simule jamais un succès."""

    REASON = (
        "Exécution dans FM26 non prouvée : aucun mécanisme d'action n'a encore été validé "
        "dans le jeu (voir docs/TECHNICAL_FEASIBILITY.md)."
    )

    def availability(self, action: str) -> ActionAvailability:
        return ActionAvailability(False, self.REASON)

    def execute(self, action: str, payload: dict, operation_id: str) -> dict:
        raise RuntimeError(self.REASON)
