"""Fixtures de test.

Les sauvegardes de `tests/fixtures/saves/` sont des fichiers .fm SYNTHÉTIQUES au vrai format
conteneur FM26, générés par le constructeur de tests de fmsave (MIT) — voir NOTICE.md.
Ils ne contiennent aucune donnée de carrière réelle.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from clubdirector.config import Settings
from clubdirector.database.db import open_database
from clubdirector.database.repositories import Repository
from clubdirector.game.fmsave_reader import FmsaveSaveReader
from clubdirector.preferences import Preferences
from clubdirector.sync.service import SyncService
from clubdirector.tools.catalog import build_registry
from clubdirector.tools.registry import ToolContext

SAVES = Path(__file__).parent / "fixtures" / "saves"
SCORED = SAVES / "synthetic-career-scored.fm"
PLAIN = SAVES / "synthetic-career.fm"


@pytest.fixture
def game_dir(tmp_path: Path) -> Path:
    """Copie des sauvegardes dans un faux dossier « games » (on ne touche jamais aux fixtures)."""
    d = tmp_path / "Sports Interactive" / "Football Manager 26" / "games"
    d.mkdir(parents=True)
    shutil.copy2(SCORED, d / SCORED.name)
    shutil.copy2(PLAIN, d / PLAIN.name)
    return d


@pytest.fixture
def settings(tmp_path: Path, game_dir: Path) -> Settings:
    s = Settings(home=tmp_path / "home", save_dirs=[game_dir])
    s.ensure_dirs()
    return s


@pytest.fixture
def engine(settings: Settings):
    return open_database(settings.db_path)


@pytest.fixture
def sync(engine, settings) -> SyncService:
    return SyncService(engine, FmsaveSaveReader(), settings.snapshot_dir)


@pytest.fixture
def synced(sync: SyncService, game_dir: Path):
    return sync.sync_save(game_dir / SCORED.name)


@pytest.fixture
def registry():
    return build_registry()


@pytest.fixture
def tctx(engine, synced) -> ToolContext:
    repo = Repository(engine)
    return ToolContext(engine, repo, repo.context(synced.career_id), Preferences())
