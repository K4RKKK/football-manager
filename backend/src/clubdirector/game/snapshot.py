"""Copie sécurisée des sauvegardes.

Règles :
- l'original n'est ouvert qu'en lecture binaire ('rb') ;
- on copie vers le dossier de données de ClubDirector, jamais à côté de l'original ;
- on vérifie que le fichier n'a pas changé pendant la copie (FM peut être en train d'écrire) ;
- on lit ensuite uniquement la copie.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class SaveBusyError(RuntimeError):
    """La sauvegarde a changé pendant la copie (écriture en cours par le jeu)."""


@dataclass(frozen=True)
class Snapshot:
    source_path: Path
    copy_path: Path
    sha256: str
    size: int
    source_mtime: float
    copied_at: datetime


def _fingerprint(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def take_snapshot(source: Path, snapshot_dir: Path, *, attempts: int = 3, settle_s: float = 0.5) -> Snapshot:
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Sauvegarde introuvable : {source}")
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if snapshot_dir.resolve() == source.parent.resolve():
        raise ValueError("Le dossier de copies ne doit pas être le dossier des sauvegardes du jeu.")

    for attempt in range(attempts):
        before = _fingerprint(source)
        tmp = snapshot_dir / f".{source.stem}.{os.getpid()}.{time.time_ns()}.partial"
        with open(source, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        after = _fingerprint(source)
        if before == after:
            digest = _sha256(tmp)
            final = snapshot_dir / f"{source.stem}.{digest[:16]}.fm"
            if final.exists():
                tmp.unlink()
            else:
                tmp.replace(final)
            return Snapshot(
                source_path=source,
                copy_path=final,
                sha256=digest,
                size=before[0],
                source_mtime=before[1] / 1e9,
                copied_at=datetime.now(UTC),
            )
        tmp.unlink(missing_ok=True)
        time.sleep(settle_s * (attempt + 1))
    raise SaveBusyError(f"La sauvegarde {source.name} change pendant la copie ; réessayer après l'enregistrement.")


def prune_snapshots(snapshot_dir: Path, keep: int) -> list[Path]:
    """Supprime les plus anciennes COPIES (jamais les originaux) au-delà de `keep` par sauvegarde."""
    groups: dict[str, list[Path]] = {}
    for p in Path(snapshot_dir).glob("*.fm"):
        stem = p.name.rsplit(".", 2)[0]
        groups.setdefault(stem, []).append(p)
    removed = []
    for files in groups.values():
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink()
            removed.append(old)
    return removed
