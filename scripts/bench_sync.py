"""Banc de performance (MODE DÉVELOPPEMENT — données générées, jamais présentées comme réelles).

Mesure l'import SQLite et les recherches sur un volume comparable à une vraie base FM26.
Usage : uv run --project backend python scripts/bench_sync.py [nb_joueurs]
"""

from __future__ import annotations

import random
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path

from clubdirector.config import Settings
from clubdirector.database.db import open_database
from clubdirector.database.repositories import Repository
from clubdirector.domain.models import ManagedClubInfo, PlayerRecord, SaveExtract, SaveMeta
from clubdirector.game.fmsave_reader import FmsaveSaveReader
from clubdirector.game.snapshot import Snapshot
from clubdirector.money import calibrate
from clubdirector.positions import CODES
from clubdirector.preferences import Preferences
from clubdirector.recruitment.roles import ROLES
from clubdirector.sync.service import SyncService
from clubdirector.tools.catalog import build_registry
from clubdirector.tools.registry import ToolContext

ATTRS = sorted({a for r in ROLES.values() for a in r.weights} | {"consistency", "dirtiness"})


def make_extract(n: int, seed: int = 7) -> SaveExtract:
    rnd = random.Random(seed)
    players = []
    for i in range(n):
        pos = rnd.sample(CODES, k=rnd.randint(1, 3))
        players.append(PlayerRecord(
            uid=i + 1, unique_id=i + 1, name=f"Joueur Dev {i}", birth_date=date(1990 + i % 18, 1 + i % 12, 1),
            age=16 + i % 20, nation_id=rnd.randint(1, 200), height_cm=rnd.randint(165, 200),
            club_uid=rnd.randint(1, 2000), club_name=f"Club Dev {i % 2000}", natural_positions=pos,
            position_ratings={c.lower(): (20 if c in pos else rnd.randint(1, 14)) for c in CODES},
            transfer_value=rnd.randint(10_000, 80_000_000), wage=rnd.randint(500, 300_000),
            contract_end=date(2031 + rnd.randint(0, 4), 6, 30), attributes={a: rnd.randint(1, 20) for a in ATTRS},
        ))
    return SaveExtract(meta=SaveMeta(game="FM26", build="dev", db_version="dev", game_date=date(2031, 3, 1), known_build=False),
                       managed=[ManagedClubInfo(club_uid=1, club_name="Club Dev 1", club_short_name=None, manager_name="Dev", manager_staff_uid=1)],
                       players=players, clubs=[], fixtures=[], season_stats=[], finances=[], league_tables=[], tactics=[], injuries=[])


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    with tempfile.TemporaryDirectory() as tmp:
        st = Settings(home=Path(tmp), save_dirs=[])
        st.ensure_dirs()
        eng = open_database(st.db_path)
        svc = SyncService(eng, FmsaveSaveReader(), st.snapshot_dir)
        t0 = time.perf_counter()
        ex = make_extract(n)
        gen = time.perf_counter() - t0
        snap = Snapshot(Path("dev.fm"), Path("dev.fm"), "a" * 64, 0, 0.0, datetime.now(UTC))
        t0 = time.perf_counter()
        r = svc.import_extract(ex, snap)
        first = time.perf_counter() - t0
        ex.meta.game_date = date(2031, 3, 8)
        for p in ex.players[: n // 100]:
            p.club_uid = 1
        t0 = time.perf_counter()
        svc.import_extract(ex, Snapshot(Path("dev.fm"), Path("dev.fm"), "b" * 64, 0, 0.0, datetime.now(UTC)))
        second = time.perf_counter() - t0
        repo = Repository(eng)
        t = ToolContext(eng, repo, repo.context(r.career_id), Preferences(currency=calibrate(1, 1.0, "€", "dev")))
        reg = build_registry()
        timings = {}
        for label, tool, args in [
            ("search DC <23 ans <10M", "search_players", {"position": "DC", "max_age": 23, "max_value": 10_000_000, "limit": 20}),
            ("search nom", "search_players", {"name": "Dev 4242"}),
            ("search attributs", "search_players", {"position": "AMR", "attribute_min": {"crossing": 16, "pace": 15}}),
            ("cibles ailier centreur", "find_recruitment_targets", {"role": "ailier_centreur", "max_value": 15_000_000, "candidate_pool": 400}),
            ("analyse effectif", "analyze_squad", {}),
        ]:
            t0 = time.perf_counter()
            res = reg.execute(tool, args, t)
            timings[label] = (time.perf_counter() - t0) * 1000
            assert res.ok, res.error
        print(f"Joueurs : {n}  (génération {gen:.1f} s, données de DÉVELOPPEMENT)")
        print(f"Import initial : {first:.2f} s ; synchro suivante (1 % de transferts) : {second:.2f} s")
        for k, v in timings.items():
            print(f"  {k:28s} {v:8.1f} ms")
        print(f"Taille base SQLite : {st.db_path.stat().st_size / 1e6:.1f} Mo")


if __name__ == "__main__":
    main()
