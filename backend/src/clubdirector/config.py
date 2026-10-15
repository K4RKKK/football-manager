"""Configuration locale.

Ordre de résolution : valeurs par défaut < fichier TOML < variables d'environnement.
Aucun secret (clé API) n'est lu depuis le fichier TOML : voir `security.secrets`.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

KnowledgeMode = Literal["realiste", "analyste", "avance"]
AutonomyMode = Literal["conseiller", "supervise", "delegue"]


def default_home() -> Path:
    """Répertoire des données utilisateur (hors dépôt, hors dossier du jeu)."""
    env = os.environ.get("CLUBDIRECTOR_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ClubDirectorAI"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "clubdirector"


def default_save_dirs() -> list[Path]:
    """Emplacements connus des sauvegardes FM26 (README fmsave). Jamais supposés exister."""
    home = Path.home()
    candidates = [
        home / "Documents" / "Sports Interactive" / "Football Manager 26" / "games",
        home / "OneDrive" / "Documents" / "Sports Interactive" / "Football Manager 26" / "games",
        home / "Library" / "Application Support" / "Sports Interactive" / "Football Manager 26" / "games",
    ]
    return candidates


class AIProviderConfig(BaseModel):
    name: str
    kind: Literal["openai_compat", "anthropic"] = "openai_compat"
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "local-model"
    # Nom de la clé dans le coffre de secrets (jamais la clé elle-même).
    api_key_ref: str | None = None
    tier: Literal[1, 2, 3] = 1
    # Coûts en USD par million de tokens (0 pour un modèle local).
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    # Le modèle local traite une requête à la fois : une réponse peut attendre la précédente.
    timeout_s: float = 300.0


class WatchdogConfig(BaseModel):
    """Surveillance de l'IA locale (ai/llm_watchdog.py) : un llama-server figé ou arrêté est relancé."""

    enabled: bool = True
    interval_s: float = 10.0
    # Sans aucun jeton lu ni généré pendant ce délai, une demande en cours est déclarée figée.
    stall_s: float = 60.0
    ready_timeout_s: float = 240.0
    max_restarts_per_hour: int = 3
    start_script: Path | None = None  # défaut : scripts/start_llm.ps1 du dépôt


class AIConfig(BaseModel):
    mode: Literal["local", "hybride", "premium"] = "local"
    providers: list[AIProviderConfig] = Field(
        default_factory=lambda: [AIProviderConfig(name="llama.cpp local")]
    )
    monthly_budget_usd: float = 0.0
    max_tool_rounds: int = 6
    # Réflexion préalable du modèle : "auto" (seulement pour les analyses demandées), "on", "off".
    thinking: Literal["auto", "on", "off"] = "auto"
    max_context_tokens: int = 8000
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)


class Settings(BaseModel):
    home: Path = Field(default_factory=default_home)
    save_dirs: list[Path] = Field(default_factory=default_save_dirs)
    host: str = "127.0.0.1"
    port: int = 8765
    knowledge_mode: KnowledgeMode = "realiste"
    autonomy: AutonomyMode = "conseiller"
    persona: str = "equilibre"
    snapshot_retention: int = 10
    # Synchronisation automatique dès que FM26 enregistre (sync/watcher.py).
    auto_sync: bool = True
    auto_sync_settle_s: float = 20.0
    auto_sync_poll_s: float = 5.0
    ai: AIConfig = Field(default_factory=AIConfig)

    @property
    def db_path(self) -> Path:
        return self.home / "clubdirector.sqlite3"

    @property
    def snapshot_dir(self) -> Path:
        return self.home / "snapshots"

    @property
    def token_path(self) -> Path:
        return self.home / "plugin.token"

    @property
    def faces_dirs(self) -> list[Path]:
        """Photos (pack de visages installé par l'utilisateur) : graphics/faces à côté du dossier games."""
        out = []
        for d in self.save_dirs:
            out += [Path(d).parent / "graphics" / "faces", Path(d).parent / "graphics" / "iconfaces"]
        return out

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)


def load_settings(path: Path | None = None) -> Settings:
    data: dict = {}
    path = path or (Path(os.environ["CLUBDIRECTOR_CONFIG"]) if "CLUBDIRECTOR_CONFIG" in os.environ else None)
    if path is None:
        candidate = default_home() / "config.toml"
        path = candidate if candidate.exists() else None
    if path is not None:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    if "CLUBDIRECTOR_SAVE_DIRS" in os.environ:
        data["save_dirs"] = os.environ["CLUBDIRECTOR_SAVE_DIRS"].split(os.pathsep)
    if "CLUBDIRECTOR_HOME" in os.environ:
        data["home"] = os.environ["CLUBDIRECTOR_HOME"]
    if data.get("save_dirs") == []:
        data.pop("save_dirs")
    return Settings.model_validate(data)
