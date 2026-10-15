"""Découverte des sauvegardes FM26. Les chemins sont configurables ; rien n'est supposé."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SaveFile:
    path: Path
    size: int
    modified: datetime


def discover_saves(dirs: list[Path]) -> list[SaveFile]:
    found: dict[Path, SaveFile] = {}
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for p in d.rglob("*.fm"):
            if p.is_file():
                st = p.stat()
                found[p.resolve()] = SaveFile(p, st.st_size, datetime.fromtimestamp(st.st_mtime, UTC))
    return sorted(found.values(), key=lambda s: s.modified, reverse=True)
