"""Inventaire d'une sauvegarde FM26 : quelles sections existent, qui les décode, qui les utilise.

But : rendre visible TOUTE la donnée de la sauvegarde, pas seulement ce que ClubDirector lit déjà.
Pour chaque section du répertoire `.fm` on indique sa taille, les lecteurs fmsave qui l'ouvrent
réellement (mesuré en instrumentant fmsave pendant `validate_save`, pas deviné), l'état de ces
lecteurs sur ce build, et les tables ClubDirector qui en importent le résultat.

Le rapport ne contient que des faits structurels (noms de sections, tailles, comptes, états),
jamais de nom, d'uid ni de valeur tirés de la sauvegarde. Lecture seule, sur une copie.
"""

from __future__ import annotations

import time
import warnings
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import fmsave
from fmsave import _context, _save

# Lecteur fmsave -> usage dans ClubDirector (code de ce dépôt : sync/service.py).
# « partiel » : seuls certains champs du lecteur sont importés.
CLUBDIRECTOR_USAGE: dict[str, str] = {
    "managed_clubs": "careers (club géré, manager)",
    "players": "players_current + player_history",
    "contracts": "partiel : salaire, début, fin, statut (pas les clauses ni l'historique)",
    "suspensions": "partiel : indicateur « suspendu » du joueur",
    "clubs": "clubs_current",
    "fixtures": "fixtures",
    "player_season_stats": "season_stats",
    "finances": "finances",
    "league_tables": "league_tables",
    "tactics": "tactics (nom, mentalité, postes)",
    "injuries": "injuries",
}

# Méthodes de `fmsave.Save` qui produisent une table (ordre de `validate_save`).
READER_METHODS = (
    "clubs", "players", "contracts", "suspensions", "managed_clubs", "stages", "competitions",
    "fixtures", "league_tables", "transfer_windows", "competition_rules", "player_match_stats",
    "player_season_stats", "stadiums", "finances", "sponsorships", "affiliates", "job_vacancies",
    "staff", "staff_lists", "injury_types", "injuries", "training", "mentoring", "tactics",
    "set_pieces", "facilities",
)
# Les statistiques de saison sont lues dans des trames non listées dans le répertoire.
SPAN_SECTION = "(trames non listées : statistiques de saison)"
# Lues à l'ouverture pour `Save.info` (build, date, schémas), hors de tout lecteur de table.
INFO_SECTIONS = {"game_info": "info (build, date de jeu)", "save_game_summary": "info (résumé)"}


@dataclass
class SectionEntry:
    name: str
    extension: str
    schema: int
    compressed_bytes: int
    decompressed_bytes: int
    readers: list[str] = field(default_factory=list)
    reader_status: dict[str, str] = field(default_factory=dict)
    used_by_clubdirector: list[str] = field(default_factory=list)

    @property
    def state(self) -> str:
        if not self.readers:
            return "non décodée"
        if any(s != "ok" for s in self.reader_status.values()):
            return "décodée avec échecs"
        return "importée" if self.used_by_clubdirector else "décodée, non importée"


@dataclass
class ReaderEntry:
    name: str
    status: str
    record_count: int | None
    failed_checks: list[str]
    sections: list[str]
    clubdirector: str | None
    seconds: float


@dataclass
class Inventory:
    file: str
    build: str
    known_build: bool
    sections: list[SectionEntry]
    readers: list[ReaderEntry]

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "build": self.build,
            "known_build": self.known_build,
            "sections": [asdict(s) | {"state": s.state} for s in self.sections],
            "readers": [asdict(r) for r in self.readers],
        }


class _Tracker:
    """Note les sections ouvertes par chaque lecteur, y compris via les décodages partagés en cache."""

    def __init__(self) -> None:
        self.current: str | None = None
        self.by_reader: dict[str, set[str]] = defaultdict(set)
        self.by_key: dict[str, set[str]] = defaultdict(set)
        self.building: list[str] = []
        self.seconds: dict[str, float] = {}

    def touch(self, section: str) -> None:
        if self.current:
            self.by_reader[self.current].add(section)
        for key in self.building:
            self.by_key[key].add(section)

    def install(self):
        tracker = self
        orig_section = _context.SaveContext.section
        orig_cached = _context.SaveContext.cached
        orig_span = _save.read_season_stats_section
        originals = {m: getattr(fmsave.Save, m) for m in READER_METHODS}

        def section(self, name):
            tracker.touch(name)
            return orig_section(self, name)

        def cached(self, key, build):
            def tracked_build():
                tracker.building.append(key)
                try:
                    return build()
                finally:
                    tracker.building.pop()

            if tracker.current and key in tracker.by_key:
                tracker.by_reader[tracker.current] |= tracker.by_key[key]
            return orig_cached(self, key, tracked_build)

        def span(*args, **kwargs):
            tracker.touch(SPAN_SECTION)
            return orig_span(*args, **kwargs)

        def wrap(name, fn):
            def reader(self, *a, **kw):
                # Un décodage partagé range plusieurs tables à la fois (ex. joueurs + contrats) :
                # toute valeur apparue dans le cache pendant ce lecteur hérite de ses sections,
                # pour que le lecteur qui la réutilisera plus tard y soit rattaché.
                cache = getattr(self._context, "_cache", {})
                before = set(cache)
                outer = tracker.current
                tracker.current = name
                t0 = time.perf_counter()
                try:
                    return fn(self, *a, **kw)
                finally:
                    tracker.seconds[name] = tracker.seconds.get(name, 0.0) + time.perf_counter() - t0
                    for key in set(cache) - before:
                        tracker.by_key[key] |= tracker.by_reader[name]
                    tracker.current = outer
                    if outer:  # lecteur appelé par un autre lecteur : ses sources comptent aussi
                        tracker.by_reader[outer] |= tracker.by_reader[name]

            return reader

        _context.SaveContext.section = section
        _context.SaveContext.cached = cached
        _save.read_season_stats_section = span
        for m, fn in originals.items():
            setattr(fmsave.Save, m, wrap(m, fn))

        def uninstall():
            _context.SaveContext.section = orig_section
            _context.SaveContext.cached = orig_cached
            _save.read_season_stats_section = orig_span
            for m, fn in originals.items():
                setattr(fmsave.Save, m, fn)

        return uninstall


def build_inventory(snapshot_path: Path) -> Inventory:
    """Ouvre la copie, exécute tous les lecteurs fmsave instrumentés et dresse l'inventaire."""
    tracker = _Tracker()
    uninstall = tracker.install()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with fmsave.open(snapshot_path) as save:
                info = save.info
                report = fmsave.validate_save(save)
    finally:
        uninstall()

    readers: list[ReaderEntry] = []
    status_by_section: dict[str, dict[str, str]] = defaultdict(dict)
    readers_by_section: dict[str, list[str]] = defaultdict(list)
    for v in report.readers:
        name = v.reader
        status = getattr(v.status, "value", str(v.status))
        secs = sorted(tracker.by_reader.get(name, set()))
        failed = [
            f"{g.name}={g.observed:.3g}" if g.observed is not None else g.name for g in (v.gates or ()) if g.applied and not g.passed
        ]
        readers.append(ReaderEntry(name, status, v.record_count, failed, secs,
                                   CLUBDIRECTOR_USAGE.get(name), round(tracker.seconds.get(name, 0.0), 2)))
        for sec in secs:
            readers_by_section[sec].append(name)
            status_by_section[sec][name] = status

    sections = [
        SectionEntry(
            name=s.name, extension=s.extension, schema=s.schema,
            compressed_bytes=s.compressed_size, decompressed_bytes=s.decompressed_size,
            readers=readers_by_section.get(s.name, []) + ([INFO_SECTIONS[s.name]] if s.name in INFO_SECTIONS else []),
            reader_status=status_by_section.get(s.name, {}),
            used_by_clubdirector=[r for r in readers_by_section.get(s.name, []) if r in CLUBDIRECTOR_USAGE]
            + (["careers (build, date)"] if s.name in INFO_SECTIONS else []),
        )
        for s in info.sections
    ]
    if SPAN_SECTION in readers_by_section:
        sections.append(SectionEntry(
            SPAN_SECTION, "", 0, 0, 0, readers_by_section[SPAN_SECTION], status_by_section[SPAN_SECTION],
            [r for r in readers_by_section[SPAN_SECTION] if r in CLUBDIRECTOR_USAGE],
        ))
    return Inventory(Path(snapshot_path).name, info.build, bool(info.known_build), sections, readers)


def render_markdown(inv: Inventory) -> str:
    total = sum(s.decompressed_bytes for s in inv.sections)
    by_state: dict[str, int] = defaultdict(int)
    for s in inv.sections:
        by_state[s.state] += s.decompressed_bytes
    lines = [
        f"# Inventaire de la sauvegarde — build {inv.build}",
        "",
        f"Build connu de fmsave : {'oui' if inv.known_build else 'non'} · {len(inv.sections)} sections · "
        f"{total / 1e6:.1f} Mo décompressés.",
        "",
        "| État | Volume (Mo) | Part |",
        "|---|---:|---:|",
    ]
    for state, size in sorted(by_state.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {state} | {size / 1e6:.1f} | {100 * size / max(1, total):.1f} % |")
    lines += [
        "",
        "> Une section « décodée » peut ne l'être que partiellement (ex. `game_db`) : l'état indique",
        "> qu'au moins un lecteur l'exploite, pas que chaque octet est compris.",
        "",
        "## Lecteurs fmsave",
        "",
        "| Lecteur | État | Lignes | Sections lues | ClubDirector | Contrôles en échec | s |",
        "|---|---|---:|---|---|---|---:|",
    ]
    for r in inv.readers:
        lines.append(
            f"| {r.name} | {r.status} | {r.record_count if r.record_count is not None else '—'} | "
            f"{', '.join(r.sections) or '—'} | {r.clubdirector or '**non importé**'} | "
            f"{', '.join(r.failed_checks) or '—'} | {r.seconds} |"
        )
    lines += ["", "## Sections", "", "| Section | Schéma | Mo | Lecteurs | État |", "|---|---:|---:|---|---|"]
    for s in sorted(inv.sections, key=lambda s: -s.decompressed_bytes):
        lines.append(
            f"| {s.name}{s.extension} | {s.schema} | {s.decompressed_bytes / 1e6:.2f} | "
            f"{', '.join(s.readers) or '—'} | {s.state} |"
        )
    return "\n".join(lines) + "\n"
