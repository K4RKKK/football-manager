"""Synchronisation automatique : une sauvegarde n'est relue qu'une fois écrite et stable."""

import os
import time

from clubdirector.sync.watcher import SaveWatcher


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def touch(path, content=b"x", mtime=None):
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_existing_saves_are_not_resynced_at_startup(tmp_path):
    touch(tmp_path / "carriere.fm")
    w = SaveWatcher([tmp_path], lambda p: {}, settle_s=20, clock=Clock())
    w.baseline()
    assert w.check() == []


def test_a_new_save_is_synced_once_stable(tmp_path):
    clock, synced = Clock(), []
    w = SaveWatcher([tmp_path], lambda p: synced.append(p.name) or {"game_date": "2025-10-28"}, settle_s=20, clock=clock)
    w.baseline()
    touch(tmp_path / "carriere.fm", b"v1", mtime=time.time())
    w.run_once()
    assert synced == []                          # écriture en cours : on attend
    clock.t = 10
    touch(tmp_path / "carriere.fm", b"v1-suite", mtime=time.time() + 1)
    w.run_once()
    clock.t = 25                                 # 15 s seulement depuis la dernière écriture
    w.run_once()
    assert synced == []
    clock.t = 31
    w.run_once()
    assert synced == ["carriere.fm"]
    assert w.status.last_game_date == "2025-10-28" and w.status.syncs == 1
    clock.t = 100
    w.run_once()
    assert synced == ["carriere.fm"]             # pas de nouvelle écriture : pas de relecture


def test_backups_are_ignored_and_errors_do_not_stop_the_watcher(tmp_path):
    clock = Clock()

    def boom(path):
        raise ValueError("sauvegarde illisible")

    w = SaveWatcher([tmp_path], boom, settle_s=0, clock=clock)
    w.baseline()
    touch(tmp_path / "last save overwrite backup.fm")
    touch(tmp_path / "carriere.fm")
    w.run_once()
    assert w.status.last_file == "carriere.fm" and "illisible" in w.status.last_error
    assert w.status.in_progress is None

