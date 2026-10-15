"""Synchronisation : sauvegarde FM26 → copie sûre → lecture → archivage SQLite.

Mode B (lecture de sauvegarde). Le mode A (plugin) alimentera les mêmes tables via
`source='live_plugin'` lorsqu'il sera validé ; le mode C fusionnera les deux.
"""

from __future__ import annotations

import contextlib
import gc
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from clubdirector.database import schema as s
from clubdirector.database.mirror import write_mirror
from clubdirector.domain.models import SaveExtract
from clubdirector.game.interfaces import ISaveReader
from clubdirector.game.snapshot import Snapshot, take_snapshot
from clubdirector.sync.season import resolve_season
from clubdirector.text import fold

log = logging.getLogger(__name__)

HISTORY_FIELDS = ("club_uid", "wage", "transfer_value", "contract_end")


@dataclass
class SyncResult:
    career_id: int
    snapshot_id: int
    game_date: str
    season_start_year: int
    season_source: str
    counts: dict[str, int]
    warnings: list[str]
    duration_ms: int
    reused: bool = False
    alerts_created: int = 0
    history_changes: int = 0
    notes: list[str] = field(default_factory=list)
    mirror_counts: dict[str, int] = field(default_factory=dict)


@contextlib.contextmanager
def gc_paused():
    """Ramasse-miettes cyclique suspendu pendant une synchronisation. La lecture crée des millions
    d'objets d'un coup et ses passes complètes successives coûtaient ≈ 15 % du temps sur une vraie
    carrière (50 s → 42 s) ; le comptage de références libère toujours la mémoire."""
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()


def career_fingerprint(extract: SaveExtract, save_stem: str) -> str:
    """Identité prudente d'une carrière.

    On combine le manager humain, la version de base de données et le nom du fichier de
    sauvegarde : deux carrières différentes ne sont jamais fusionnées automatiquement.
    Un « Enregistrer sous » crée donc une nouvelle carrière ; la fusion est une action
    explicite de l'utilisateur.
    """
    m = extract.managed[0] if extract.managed else None
    parts = [
        str(m.manager_staff_uid if m else "sans-club"),
        (m.manager_name if m else "") or "",
        extract.meta.db_version or "",
        save_stem,
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class SyncService:
    def __init__(self, engine: Engine, reader: ISaveReader, snapshot_dir: Path) -> None:
        self.engine = engine
        self.reader = reader
        self.snapshot_dir = Path(snapshot_dir)

    # -- point d'entrée --------------------------------------------------------------------
    def sync_save(self, save_path: Path) -> SyncResult:
        """Lecture hors transaction (le service continue de répondre sur l'état précédent), puis
        écriture en une seule transaction : les lecteurs voient l'ancien relevé jusqu'à la
        validation (SQLite en WAL), jamais un mélange des deux."""
        t0 = time.perf_counter()
        snap = take_snapshot(Path(save_path), self.snapshot_dir)
        with gc_paused():
            extract = self.reader.read(snap.copy_path)
            return self.import_extract(extract, snap, t0=t0)

    def import_extract(self, extract: SaveExtract, snap: Snapshot, *, t0: float | None = None) -> SyncResult:
        t0 = t0 or time.perf_counter()
        now = datetime.now(UTC)
        stem = snap.source_path.stem
        fp = career_fingerprint(extract, stem)
        managed = extract.managed[0] if extract.managed else None
        season, season_src = resolve_season(
            extract.meta.game_date, extract.fixtures, managed.club_uid if managed else None
        )
        counts = {
            "players": len(extract.players),
            "clubs": len(extract.clubs),
            "fixtures": len(extract.fixtures),
            "season_stats": len(extract.season_stats),
            "finances": len(extract.finances),
            "league_rows": len(extract.league_tables),
            "tactics": len(extract.tactics),
            "injuries": len(extract.injuries),
        }
        with self.engine.begin() as conn:
            career_id = self._upsert_career(conn, fp, extract, stem, now, season, season_src)
            existing = conn.execute(
                select(s.snapshots.c.id, s.snapshots.c.reader).where(
                    s.snapshots.c.career_id == career_id, s.snapshots.c.sha256 == snap.sha256
                )
            ).first()
            if existing is not None and existing.reader == self.reader.name:
                # Même fichier déjà importé par le même lecteur : rien à refaire (idempotence).
                return SyncResult(
                    career_id, existing.id, extract.meta.game_date.isoformat(), season, season_src,
                    counts, extract.reader_warnings, int((time.perf_counter() - t0) * 1000),
                    reused=True,
                )
            values = dict(
                source_path=str(snap.source_path),
                copy_path=str(snap.copy_path),
                size=snap.size,
                copied_at=snap.copied_at,
                game_date=extract.meta.game_date,
                build=extract.meta.build,
                reader=self.reader.name,
                status="ok",
                warnings=extract.reader_warnings,
                field_status=extract.field_status,
                counts=counts,
            )
            if existing is not None:
                # Lecteur plus récent : on relit le même fichier dans le même relevé. Les tables
                # rattachées au relevé (insertion simple) sont vidées pour ne pas se dupliquer.
                snapshot_id = existing.id
                conn.execute(update(s.snapshots).where(s.snapshots.c.id == snapshot_id).values(**values))
                for table in (s.league_tables, s.tactics):
                    conn.execute(delete(table).where(table.c.snapshot_id == snapshot_id))
            else:
                snapshot_id = conn.execute(
                    insert(s.snapshots).values(career_id=career_id, sha256=snap.sha256, **values)
                ).inserted_primary_key[0]
            changes = self._players(conn, career_id, snapshot_id, extract)
            self._clubs(conn, career_id, snapshot_id, extract)
            self._fixtures(conn, career_id, snapshot_id, extract)
            self._season_stats(conn, career_id, snapshot_id, extract, season, season_src)
            self._finances(conn, career_id, snapshot_id, extract)
            self._tables(conn, career_id, snapshot_id, extract)
            self._tactics(conn, career_id, snapshot_id, extract)
            self._injuries(conn, career_id, snapshot_id, extract)
            mirror_counts = write_mirror(conn, career_id, snapshot_id, extract.mirror or [])
            duration = int((time.perf_counter() - t0) * 1000)
            conn.execute(
                update(s.snapshots).where(s.snapshots.c.id == snapshot_id).values(duration_ms=duration)
            )
        from clubdirector.proactive.rules import run_rules  # import tardif : dépend des dépôts

        alerts = run_rules(self.engine, career_id)
        return SyncResult(
            career_id, snapshot_id, extract.meta.game_date.isoformat(), season, season_src,
            counts, extract.reader_warnings, duration, alerts_created=alerts, history_changes=changes,
            mirror_counts=mirror_counts,
        )

    # -- étapes ----------------------------------------------------------------------------
    def _upsert_career(self, conn, fp, extract, stem, now, season, season_src) -> int:
        m = extract.managed[0] if extract.managed else None
        values = dict(
            save_stem=stem,
            manager_name=m.manager_name if m else None,
            manager_staff_uid=m.manager_staff_uid if m else None,
            club_uid=m.club_uid if m else None,
            club_name=m.club_name if m else None,
            db_version=extract.meta.db_version,
            last_sync_at=now,
            last_game_date=extract.meta.game_date,
            current_season_start_year=season,
            season_source=season_src,
        )
        row = conn.execute(select(s.careers.c.id).where(s.careers.c.fingerprint == fp)).first()
        if row:
            conn.execute(update(s.careers).where(s.careers.c.id == row[0]).values(**values))
            return row[0]
        label = f"{m.club_name if m else 'Sans club'} — {stem}"
        return conn.execute(
            insert(s.careers).values(fingerprint=fp, label=label, created_at=now, **values)
        ).inserted_primary_key[0]

    def _players(self, conn, career_id, snapshot_id, extract) -> int:
        previous = {
            r.uid: r
            for r in conn.execute(
                select(
                    s.players_current.c.uid,
                    *(s.players_current.c[f] for f in HISTORY_FIELDS),
                ).where(s.players_current.c.career_id == career_id)
            )
        }
        first_sync = not previous
        conn.execute(delete(s.players_current).where(s.players_current.c.career_id == career_id))
        rows, history = [], []
        gd = extract.meta.game_date
        for p in extract.players:
            rows.append(
                dict(
                    career_id=career_id,
                    uid=p.uid,
                    snapshot_id=snapshot_id,
                    unique_id=p.unique_id,
                    name=p.name,
                    name_search=fold(p.name),
                    birth_date=p.birth_date,
                    age=p.age,
                    nation_id=p.nation_id,
                    height_cm=p.height_cm,
                    club_uid=p.club_uid,
                    club_name=p.club_name,
                    team_slot=p.team_slot,
                    positions="," + ",".join(p.natural_positions) + ",",
                    accomplished_positions="," + ",".join(p.accomplished_positions) + ",",
                    position_ratings=p.position_ratings,
                    left_foot=p.left_foot,
                    right_foot=p.right_foot,
                    current_ability=p.current_ability,
                    potential_ability=p.potential_ability,
                    transfer_value=p.transfer_value,
                    transfer_value_state=p.transfer_value_state,
                    wage=p.wage,
                    contract_start=p.contract_start,
                    contract_end=p.contract_end,
                    squad_status=p.squad_status,
                    on_loan=p.on_loan,
                    loan_parent_club_uid=p.loan_parent_club_uid,
                    condition=p.condition,
                    attributes=p.attributes,
                    personality=p.personality,
                    traits=p.traits,
                    banned=p.banned,
                )
            )
            old = previous.get(p.uid)
            new_vals = {f: getattr(p, f) for f in HISTORY_FIELDS}
            if first_sync or old is None:
                reason = "premier_releve" if first_sync else "nouveau_joueur"
            else:
                diff = [f for f in HISTORY_FIELDS if getattr(old, f) != new_vals[f]]
                reason = ",".join(diff) if diff else None
            if reason:
                history.append(
                    dict(
                        career_id=career_id, uid=p.uid, snapshot_id=snapshot_id, game_date=gd,
                        name=p.name, club_name=p.club_name, change=reason, **new_vals,
                    )
                )
        if rows:
            conn.execute(insert(s.players_current), rows)
        if history:
            conn.execute(insert(s.player_history), history)
        return 0 if first_sync else len(history)

    def _clubs(self, conn, career_id, snapshot_id, extract) -> None:
        conn.execute(delete(s.clubs_current).where(s.clubs_current.c.career_id == career_id))
        rows = [
            dict(career_id=career_id, snapshot_id=snapshot_id, **c.model_dump()) for c in extract.clubs
        ]
        if rows:
            conn.execute(insert(s.clubs_current), rows)

    @staticmethod
    def _match_key(f) -> str:
        return (
            f"{f.stage_id}|{f.date.isoformat()}|{f.home_club_uid}.{f.home_team_slot}"
            f"|{f.away_club_uid}.{f.away_team_slot}"
        )

    # Les upserts sont envoyés en une seule instruction préparée, exécutée pour toutes les lignes
    # (executemany) : ligne par ligne, les 210 000 stats de saison d'une vraie carrière prenaient 84 s.
    @staticmethod
    def _upsert_many(conn, table, rows: list[dict], keys: list[str], set_=None) -> None:
        if not rows:
            return
        stmt = sqlite_insert(table)
        if set_ is None:
            set_ = {k: stmt.excluded[k] for k in rows[0] if k not in keys}
        conn.execute(stmt.on_conflict_do_update(index_elements=keys, set_=set_(stmt) if callable(set_) else set_), rows)

    def _fixtures(self, conn, career_id, snapshot_id, extract) -> None:
        rows = []
        for f in extract.fixtures:
            has_score = f.home_goals is not None and f.away_goals is not None
            rows.append(dict(
                career_id=career_id,
                match_key=self._match_key(f),
                first_seen_snapshot=snapshot_id,
                last_seen_snapshot=snapshot_id,
                score_snapshot=snapshot_id if has_score else None,
                **f.model_dump(),
            ))
        t = s.fixtures.c

        def keep_known_scores(stmt):
            # Ne jamais écraser un score connu par une absence de score.
            ex = stmt.excluded
            return dict(
                home_goals=func.coalesce(ex.home_goals, t.home_goals),
                away_goals=func.coalesce(ex.away_goals, t.away_goals),
                score_snapshot=func.coalesce(ex.score_snapshot, t.score_snapshot),
                played=func.coalesce(ex.played, t.played),
                competition_name=func.coalesce(ex.competition_name, t.competition_name),
                last_seen_snapshot=ex.last_seen_snapshot,
            )

        self._upsert_many(conn, s.fixtures, rows, ["career_id", "match_key"], keep_known_scores)

    def _season_stats(self, conn, career_id, snapshot_id, extract, season, season_src) -> None:
        gd = extract.meta.game_date
        rows = [
            dict(
                career_id=career_id,
                season_start_year=season,
                season_source=season_src,
                snapshot_id=snapshot_id,
                game_date=gd,
                **st.model_dump(),
            )
            for st in extract.season_stats
        ]
        self._upsert_many(conn, s.season_stats, rows,
                          ["career_id", "season_start_year", "player_uid", "kind", "club_uid", "team_slot"])

    def _finances(self, conn, career_id, snapshot_id, extract) -> None:
        rows = [dict(career_id=career_id, snapshot_id=snapshot_id, **f.model_dump()) for f in extract.finances]
        self._upsert_many(conn, s.finances, rows, ["career_id", "club_uid", "month"])

    def _tables(self, conn, career_id, snapshot_id, extract) -> None:
        rows = [
            dict(career_id=career_id, snapshot_id=snapshot_id, game_date=extract.meta.game_date, **r.model_dump())
            for r in extract.league_tables
        ]
        if rows:
            conn.execute(insert(s.league_tables), rows)

    def _tactics(self, conn, career_id, snapshot_id, extract) -> None:
        rows = []
        for t in extract.tactics:
            d = t.model_dump()
            d["idx"] = d.pop("index")
            rows.append(dict(career_id=career_id, snapshot_id=snapshot_id, **d))
        if rows:
            conn.execute(insert(s.tactics), rows)

    def _injuries(self, conn, career_id, snapshot_id, extract) -> None:
        rows = [
            dict(career_id=career_id, injury_key=f"{i.kind}|{i.player_uid}|{i.date}|{i.type_name}",
                 snapshot_id=snapshot_id, **i.model_dump())
            for i in extract.injuries
        ]
        if rows:
            conn.execute(sqlite_insert(s.injuries).on_conflict_do_nothing(index_elements=["career_id", "injury_key"]), rows)
