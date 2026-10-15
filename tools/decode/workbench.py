"""Atelier de décodage des sections d'une sauvegarde FM26 (outil de développement, lecture seule).

Pour chaque section demandée, repère automatiquement ce qu'elle contient :
  - flux balisé du jeu (étiquette ASCII de 4 octets inversée, séparateur 0x01, octet de type) ;
  - chaînes UTF-8 précédées de leur longueur (u32) ;
  - dates de jeu (u16 jour de l'année + u16 année) ;
  - références aux entités déjà connues (joueurs, clubs, staff, compétitions, stades…), sous
    leur uid public ou stocké (uid - 1), avec le pas dominant entre deux références : c'est en
    général la taille d'un enregistrement.

Sorties :
  - <out>/<section>.md : rapport détaillé AVEC des valeurs réelles (noms, extraits) → reste local,
    `third_party/fmsave/.local/` est ignoré par Git ;
  - <out>/summary.json : structure seulement (comptes, pas, étiquettes), sans valeur de carrière.

Usage (depuis la racine du dépôt) :
  uv run --project backend python tools/decode/workbench.py <copie.fm> [section ...] [--out DIR]
Sans section : toutes celles qu'aucun lecteur fmsave n'ouvre (voir clubdirector inventory).
Toujours travailler sur une COPIE (dossier snapshots de ClubDirector).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import warnings
from pathlib import Path

import fmsave
import numpy as np

MIN_ID = 1000  # en dessous, trop de collisions avec des petits entiers quelconques
TAG_TYPES = (0x00, 0x01, 0x02, 0x03, 0x0A, 0x0B, 0x0F, 0x11, 0x12, 0x1A)  # types connus du flux balisé
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "third_party" / "fmsave" / ".local" / "workbench"


# ---------------------------------------------------------------- entités connues
def load_entities(save, cache: Path) -> dict[str, np.ndarray]:
    """Identifiants de toutes les entités que fmsave sait déjà lire (mis en cache localement)."""
    if cache.exists():
        with np.load(cache) as z:
            return {k: z[k] for k in z.files}
    ent: dict[str, set[int]] = collections.defaultdict(set)

    def add(kind: str, value) -> None:
        if isinstance(value, int) and value >= MIN_ID:
            ent[kind].add(value)

    for p in save.players():
        add("joueur.uid", p.uid)
        add("joueur.unique_id", p.unique_id)
    # Index interne de personne (« pindex ») : joueurs et staff partagent cet espace.
    records = save._context.player_records()
    for pindex in records.pindexes:
        add("personne.pindex", pindex)
    for club_index in save._context.club_index().uid_by_club_index:
        add("club.index", club_index)
    for c in save.clubs():
        add("club.uid", c.uid)
        add("club.unique_id", c.unique_id)
        for t in c.teams:
            add("equipe.id", t.team_id)
    for s in save.staff():
        add("staff.uid", s.uid)
        add("staff.unique_id", s.unique_id)
    for c in save.competitions():
        add("competition.id", c.id)
        add("competition.database_id", c.database_id)
    for st in save.stages():
        add("phase.id", st.id)
    for sd in save.stadiums():
        add("stade.uid", sd.uid)
    arrays = {k: np.array(sorted(v), dtype=np.uint32) for k, v in ent.items()}
    # Variantes : de nombreuses structures rangent uid - 1, d'autres un sélecteur (id + 1).
    for k in list(arrays):
        arrays[k + " (stocké -1)"] = arrays[k] - 1
        arrays[k + " (+1)"] = arrays[k] + 1
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **arrays)
    return arrays


# ---------------------------------------------------------------- détecteurs
def u32_views(buf: bytes) -> list[tuple[int, np.ndarray]]:
    """Le tampon lu en u32 little-endian à chacun des 4 alignements possibles."""
    out = []
    for shift in range(4):
        n = (len(buf) - shift) // 4
        if n > 0:
            out.append((shift, np.frombuffer(buf, dtype="<u4", count=n, offset=shift)))
    return out


def entity_refs(buf: bytes, entities: dict[str, np.ndarray]) -> dict[str, dict]:
    views = u32_views(buf)
    res = {}
    for kind, ids in entities.items():
        positions = []
        for shift, view in views:
            hit = np.nonzero(np.isin(view, ids, assume_unique=False))[0]
            positions.append(hit * 4 + shift)
        pos = np.sort(np.concatenate(positions)) if positions else np.array([], dtype=np.int64)
        if len(pos) == 0:
            continue
        distinct = len(np.unique(np.concatenate([
            view[(p - shift) // 4] for shift, view in views
            for p in [pos[(pos % 4) == shift]] if len(p)
        ])))
        stride, share = dominant_stride(pos)
        # Témoin : mêmes identifiants décalés d'un nombre premier. Une vraie référence ressort
        # très au-dessus du témoin ; une plage d'identifiants dense (équipes…) non.
        control = ids + np.uint32(7919)
        control_hits = sum(int(np.isin(view, control).sum()) for _shift, view in views)
        lift = round(len(pos) / (control_hits + 1), 1)
        res[kind] = {"refs": int(len(pos)), "distincts": int(distinct), "temoin": control_hits, "lift": lift,
                     "pas": stride, "part_pas": share, "premiere": int(pos[0]), "derniere": int(pos[-1])}
    return res


def dominant_stride(pos: np.ndarray) -> tuple[int | None, float]:
    if len(pos) < 3:
        return None, 0.0
    d = np.diff(pos)
    d = d[d > 0]
    if len(d) == 0:
        return None, 0.0
    vals, counts = np.unique(d, return_counts=True)
    i = int(np.argmax(counts))
    return int(vals[i]), round(float(counts[i]) / len(d), 3)


def tagged_records(buf: bytes) -> collections.Counter:
    a = np.frombuffer(buf, dtype=np.uint8)
    if len(a) < 6:
        return collections.Counter()
    n = len(a) - 5
    ok = np.ones(n, dtype=bool)
    for k in range(4):
        c = a[k:k + n]
        ok &= ((c >= 0x61) & (c <= 0x7A)) | ((c >= 0x30) & (c <= 0x39)) | (c == 0x5F)
    ok &= a[4:4 + n] == 0x01
    ok &= np.isin(a[5:5 + n], TAG_TYPES)
    tags = collections.Counter()
    for p in np.nonzero(ok)[0]:
        tags[(bytes(a[p:p + 4])[::-1].decode("ascii"), int(a[p + 5]))] += 1
    return tags


def strings(buf: bytes, limit: int = 200_000) -> tuple[int, list[tuple[int, str]]]:
    found = []
    seen_end = -1
    for shift, view in u32_views(buf):
        cand = np.nonzero((view >= 2) & (view <= 160))[0]
        for i in cand[:limit]:
            p = int(i) * 4 + shift
            if p < seen_end:
                continue
            ln = int(view[i])
            raw = buf[p + 4:p + 4 + ln]
            if len(raw) != ln or min(raw) < 0x20:
                continue
            try:
                txt = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if sum(ch.isalpha() for ch in txt) < max(2, len(txt) // 3):
                continue
            found.append((p, txt))
    found.sort()
    return len(found), found


def dates(buf: bytes) -> collections.Counter:
    a = np.frombuffer(buf[: len(buf) - len(buf) % 2], dtype="<u2")
    if len(a) < 2:
        return collections.Counter()
    years = a[1:]
    days = a[:-1] & 0x1FF
    ok = (years >= 1990) & (years <= 2100) & (days >= 1) & (days <= 366)
    return collections.Counter(int(y) for y in years[ok])


# ---------------------------------------------------------------- rapport
def analyse(name: str, buf: bytes, entities: dict[str, np.ndarray]) -> tuple[dict, str]:
    a = np.frombuffer(buf, dtype=np.uint8)
    zero = float((a == 0).mean()) if len(a) else 0.0
    ff = float((a == 0xFF).mean()) if len(a) else 0.0
    refs = entity_refs(buf, entities)
    tags = tagged_records(buf)
    n_str, strs = strings(buf)
    yrs = dates(buf)
    summary = {
        "section": name, "octets": len(buf), "part_00": round(zero, 3), "part_ff": round(ff, 3),
        "entetes_hex": buf[:16].hex(" "),
        "etiquettes": [{"tag": t, "type": f"0x{k:02x}", "n": n} for (t, k), n in tags.most_common(60)],
        "chaines": n_str,
        "annees_plausibles": dict(sorted(yrs.items())) if sum(yrs.values()) else {},
        "references": refs,
    }
    lines = [f"# {name}", "", f"{len(buf):,} octets · 00 : {zero:.0%} · FF : {ff:.0%}", "",
             "## Références à des entités connues", "",
             "| Entité | Réfs | Distinctes | Témoin | Lift | Pas dominant | Part | Première | Dernière |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, v in sorted(refs.items(), key=lambda kv: -kv[1]["lift"]):
        lines.append(f"| {k} | {v['refs']} | {v['distincts']} | {v['temoin']} | {v['lift']} | {v['pas']} | "
                     f"{v['part_pas']} | {v['premiere']} | {v['derniere']} |")
    lines += ["", "## Flux balisé (étiquette, type, occurrences)", ""]
    lines += [f"- `{t}` 0x{k:02x} × {n}" for (t, k), n in tags.most_common(80)] or ["(aucun)"]
    lines += ["", f"## Chaînes ({n_str})", ""]
    lines += [f"- @{p}: {t!r}" for p, t in strs[:80]] or ["(aucune)"]
    lines += ["", "## Années plausibles (u16 jour + u16 année)", "", json.dumps(summary["annees_plausibles"]),
              "", "## Début de section (hex)", "", "```", *(buf[i:i + 32].hex(" ") for i in range(0, min(len(buf), 512), 32)), "```"]
    return summary, "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("save", type=Path)
    ap.add_argument("sections", nargs="*")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--all", action="store_true", help="toutes les sections, y compris déjà lues")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.simplefilter("ignore")
    args.out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(args.save.name.encode()).hexdigest()[:12]
    with fmsave.open(args.save) as save:
        entities = load_entities(save, args.out / f"entites-{digest}.npz")
        listed = [s.name for s in save.info.sections]
        if args.sections:
            todo = args.sections
        elif args.all:
            todo = listed
        else:
            decoded = {"game_db", "game_info", "save_game_summary", "humans", "tactics_man", "training_man",
                       "injury_manager", "feeder_man", "job_centre", "news", "tc_record_man"}
            todo = [s for s in listed if s not in decoded]
        summaries = []
        for name in todo:
            buf = save._read_section(name)
            summary, md = analyse(name, buf, entities)
            (args.out / f"{name}.md").write_text(md, encoding="utf-8")
            summaries.append(summary)
            signals = sorted(((k, v) for k, v in summary["references"].items() if v["lift"] >= 3 and v["refs"] >= 5),
                             key=lambda kv: -kv[1]["refs"])[:3]
            sig = ", ".join(f"{k}×{v['refs']} (lift {v['lift']}, pas {v['pas']})" for k, v in signals) or "—"
            print(f"{name:40} {len(buf):>11,} o  tags={len(summary['etiquettes']):3} chaînes={summary['chaines']:6}  {sig}")
    (args.out / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
