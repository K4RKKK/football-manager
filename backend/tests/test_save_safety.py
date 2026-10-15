"""Section 2.3 / 19 — la sauvegarde originale n'est jamais modifiée."""

import hashlib
from pathlib import Path

import pytest

from clubdirector.game import snapshot as snapmod
from clubdirector.game.snapshot import SaveBusyError, prune_snapshots, take_snapshot

from .conftest import SCORED


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_sync_never_modifies_original(sync, game_dir):
    original = game_dir / SCORED.name
    before = (digest(original), original.stat().st_mtime_ns, original.stat().st_size)
    sync.sync_save(original)
    sync.sync_save(original)
    assert (digest(original), original.stat().st_mtime_ns, original.stat().st_size) == before
    # aucun fichier ajouté à côté des sauvegardes du jeu
    assert sorted(p.name for p in game_dir.iterdir()) == ["synthetic-career-scored.fm", "synthetic-career.fm"]


def test_snapshot_is_byte_identical_copy(settings, game_dir):
    snap = take_snapshot(game_dir / SCORED.name, settings.snapshot_dir)
    assert snap.copy_path.parent == settings.snapshot_dir
    assert digest(snap.copy_path) == digest(game_dir / SCORED.name) == snap.sha256


def test_snapshot_dir_cannot_be_game_dir(game_dir):
    with pytest.raises(ValueError):
        take_snapshot(game_dir / SCORED.name, game_dir)


def test_save_being_written_is_detected(settings, game_dir, monkeypatch):
    calls = iter(range(100))
    monkeypatch.setattr(snapmod, "_fingerprint", lambda p: (next(calls), 0))
    with pytest.raises(SaveBusyError):
        take_snapshot(game_dir / SCORED.name, settings.snapshot_dir, attempts=2, settle_s=0)
    assert not list(settings.snapshot_dir.glob("*.partial"))


def test_prune_only_touches_copies(settings, game_dir):
    for i in range(4):
        p = settings.snapshot_dir / f"career.{i:016x}.fm"
        p.write_bytes(b"x")
    removed = prune_snapshots(settings.snapshot_dir, keep=2)
    assert len(removed) == 2
    assert all(r.parent == settings.snapshot_dir for r in removed)
    assert (game_dir / SCORED.name).exists()


def test_missing_save(settings, tmp_path):
    with pytest.raises(FileNotFoundError):
        take_snapshot(tmp_path / "absent.fm", settings.snapshot_dir)
