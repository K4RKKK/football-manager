"""Synchronisation automatique : dès que FM26 enregistre une sauvegarde, ClubDirector la relit.

Sans plugin dans le jeu, la sauvegarde est la source de vérité ; la relire à chaque enregistrement
(manuel ou automatique) maintient le directeur sportif à la date du jeu. Scrutation simple, sans
dépendance : toutes les `poll_s` secondes on relève (taille, date) des fichiers `.fm`. Un fichier
modifié n'est synchronisé qu'une fois STABLE pendant `settle_s` secondes (le jeu a fini d'écrire) ;
la lecture se fait toujours sur une copie (SyncService → take_snapshot), jamais sur l'original.
Au démarrage, l'état existant sert de référence : rien n'est relu tant que le jeu n'enregistre pas.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

Signature = tuple[float, int]  # (date de modification, taille)


@dataclass
class WatcherStatus:
    enabled: bool = True
    watching: list[str] = field(default_factory=list)
    in_progress: str | None = None
    last_file: str | None = None
    last_sync_at: str | None = None
    last_game_date: str | None = None
    last_duration_s: float | None = None
    last_error: str | None = None
    syncs: int = 0


class SaveWatcher:
    def __init__(self, dirs: Iterable[Path], on_stable: Callable[[Path], dict], *, poll_s: float = 5.0,
                 settle_s: float = 20.0, ignore: Iterable[str] = ("*backup*",),
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.dirs = [Path(d) for d in dirs]
        self.on_stable = on_stable
        self.poll_s = poll_s
        self.settle_s = settle_s
        self.ignore = [p.lower() for p in ignore]
        self.clock = clock
        self._known: dict[Path, Signature] = {}
        self._pending: dict[Path, tuple[Signature, float]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = WatcherStatus(watching=[str(d) for d in self.dirs if d.is_dir()])

    # ------------------------------------------------------------------ détection (testable)
    def _scan(self) -> dict[Path, Signature]:
        found: dict[Path, Signature] = {}
        for d in self.dirs:
            if not d.is_dir():
                continue
            for p in d.rglob("*.fm"):
                if any(fnmatch.fnmatch(p.name.lower(), pat) for pat in self.ignore):
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                found[p] = (st.st_mtime, st.st_size)
        return found

    def baseline(self) -> None:
        self._known = self._scan()
        self._pending.clear()

    def check(self) -> list[Path]:
        """Fichiers modifiés et stables depuis `settle_s`, du plus ancien au plus récent."""
        now = self.clock()
        current = self._scan()
        for path, sig in current.items():
            if self._known.get(path) == sig:
                continue
            pending = self._pending.get(path)
            if pending is None or pending[0] != sig:
                self._pending[path] = (sig, now)  # nouvelle écriture : on (re)démarre l'attente
        ready = []
        for path, (sig, since) in list(self._pending.items()):
            if path not in current:
                self._pending.pop(path)
            elif now - since >= self.settle_s:
                ready.append((sig[0], path))
                self._pending.pop(path)
                self._known[path] = sig
        return [p for _mtime, p in sorted(ready)]

    # ------------------------------------------------------------------ boucle
    def run_once(self) -> None:
        for path in self.check():
            self._sync(path)

    def _sync(self, path: Path) -> None:
        self.status.in_progress = path.name
        t0 = time.perf_counter()
        try:
            res = self.on_stable(path)
            self.status.last_error = None
            self.status.last_game_date = res.get("game_date") if isinstance(res, dict) else None
            self.status.syncs += 1
        except Exception as exc:  # noqa: BLE001 — une sauvegarde illisible n'arrête pas la surveillance
            log.warning("Synchronisation automatique échouée pour %s : %s", path.name, exc)
            self.status.last_error = f"{path.name} : {type(exc).__name__}: {exc}"
        finally:
            self.status.in_progress = None
            self.status.last_file = path.name
            self.status.last_sync_at = datetime.now(UTC).isoformat(timespec="seconds")
            self.status.last_duration_s = round(time.perf_counter() - t0, 1)

    def start(self) -> None:
        if self._thread is not None:
            return
        self.baseline()
        self._thread = threading.Thread(target=self._loop, name="clubdirector-save-watcher", daemon=True)
        self._thread.start()
        log.info("Synchronisation automatique active sur : %s", ", ".join(self.status.watching) or "(aucun dossier)")

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_s):
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                log.warning("Surveillance des sauvegardes : %s", exc)

    def stop(self) -> None:
        self._stop.set()

    def as_dict(self) -> dict:
        return asdict(self.status)
