"""État de la connexion au plugin FM26 (mode A), alimenté par ses battements de cœur."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel

from clubdirector.game.interfaces import LiveStatus

HEARTBEAT_TIMEOUT = timedelta(seconds=15)


class Heartbeat(BaseModel):
    plugin_version: str
    game_version: str | None = None
    state: str = "connecte"  # connecte | carriere_chargee | incompatible
    game_date: date | None = None
    managed_club_name: str | None = None
    current_screen: str | None = None
    in_match: bool = False
    detail: str | None = None


class PluginBridge:
    """Implémente IGameConnection à partir des battements reçus du plugin."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: Heartbeat | None = None
        self._at: datetime | None = None

    def heartbeat(self, hb: Heartbeat) -> None:
        with self._lock:
            self._last, self._at = hb, datetime.now(UTC)

    def status(self) -> LiveStatus:
        with self._lock:
            hb, at = self._last, self._at
        if hb is None or at is None or datetime.now(UTC) - at > HEARTBEAT_TIMEOUT:
            return LiveStatus("absent", detail="Aucun battement du plugin FM26 récent (plugin non installé, jeu fermé ou plugin non validé).",
                              last_heartbeat=at)
        state = hb.state if hb.state in ("connecte", "carriere_chargee", "incompatible") else "connecte"
        return LiveStatus(state, hb.plugin_version, hb.game_version, hb.game_date, hb.managed_club_name, at, hb.detail)  # type: ignore[arg-type]

    def in_match(self) -> bool:
        st = self.status()
        return st.state != "absent" and bool(self._last and self._last.in_match)
