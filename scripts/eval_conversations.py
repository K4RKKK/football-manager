"""Banc d'évaluation des conversations du téléphone (directeur sportif, directeur technique, adjoint).

Joue les scénarios de scripts/eval/conversations.json sur une COPIE de la carrière (base copiée dans
un dossier de travail, jamais la vraie), avec l'IA locale, et vérifie automatiquement chaque réponse :
type de message détecté, outils appelés, joueurs réels uniquement, composition calculée, forme
d'adresse (vous/tu), réponse courte pour la politesse, renvois vers le bon contact, pièges (joueur
absent, budget irréaliste), aucune promesse de travail différé ni d'action dans le jeu, aucun jargon
technique, français.

Partage de l'IA locale : avant chaque message, le banc attend que llama-server soit libre (une seule
requête à la fois ; l'entraîneur peut être en train de jouer ou de discuter).

Usage (racine du dépôt) :
  uv run --project backend python scripts/eval_conversations.py --copy DOSSIER [--roles ds,dt,adj] [--ids a,b] [--label avant]
Sorties dans DOSSIER/reports : eval-conversations-<label>.md (réponses, avec données de carrière : reste
local) et .json (résultats pour comparer deux passages : --compare avant.json apres.json).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import statistics
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scripts" / "eval" / "conversations.json"
ROLES = {"ds": "directeur_sportif", "dt": "directeur_technique", "adj": "entraineur_adjoint"}
FORMAL = {"directeur_sportif", "directeur_technique"}
LLM = "http://127.0.0.1:8080"
MARKET_TOOLS = {"get_transfer_offers", "get_market_ranking", "evaluate_transfer_value", "find_buyers", "prepare_sale",
                "prepare_transfer_offer", "prepare_counter_offer", "prepare_contract_proposal"}
# Joueurs connus du football réel souvent associés au club mais absents de cette carrière : les citer
# comme les nôtres est une invention (la liste est filtrée sur l'effectif réel à l'exécution).
FAMOUS_ELSEWHERE = ["Rui Patrício", "Chris Smalling", "Tammy Abraham", "Nicolò Zaniolo", "Leonardo Spinazzola",
                    "Romelu Lukaku", "Leandro Paredes", "Diego Llorente", "Marash Kumbulla", "Sardar Azmoun",
                    "Andrea Belotti", "Houssem Aouar", "Edoardo Bove", "Rick Karsdorp", "Nicola Zalewski",
                    "Mats Hummels", "Stephan Lichtsteiner", "Francesco Totti", "Daniele De Rossi"]

DEFERRED_RE = re.compile(
    r"je (?:te|vous) (?:fais|ferai|enverrai|envoie|recontacte|recontacterai|tiens au courant|tiendrai au courant|"
    r"redis|redirai|reviens)|je reviens vers|dès que j'ai (?:fini|terminé|avancé)|je m'en occupe et je|"
    r"laisse[z]?-moi (?:un peu de temps|vérifier et)|je regarde ça et je|je vais me pencher dessus et|plus tard dans la journée",
    re.IGNORECASE)
ACTION_RE = re.compile(
    r"j'ai (?:contacté|appelé|envoyé|soumis|signé|prolongé|transmis|fait une offre|lancé les négociations|parlé (?:à|avec) (?:l'agent|son agent))|"
    r"je viens (?:d'envoyer|de contacter|de faire une offre|de signer)|offre (?:envoyée|transmise)|c'est signé",
    re.IGNORECASE)
JARGON_RE = re.compile(
    r"\b(outils?|base de données|tables? de données|décod\w*|prompt|modèle (?:de langage|d'ia)|intelligence artificielle|"
    r"consigne automatique|message automatique|dossier automatique|requête|json|niveau 0)\b|\bIA\b", re.IGNORECASE)
TOOL_NARRATION_RE = re.compile(r"\b(je consulte|en consultant|consulté les données|je vérifie dans la base)\b", re.IGNORECASE)
TU_RE = re.compile(r"(?<![\w'])(tu|toi|ton|ta|tes|t'(?=[aeiouyhéèê]))(?![\w'])", re.IGNORECASE)
VOUS_RE = re.compile(r"(?<![\w'])(vous|votre|vos)(?![\w'])", re.IGNORECASE)
ENGLISH = {"the", "and", "with", "your", "you", "player", "players", "team", "season", "match", "goals", "should", "would",
           "this", "that", "here", "there", "what", "which", "will", "can", "best"}
NEGATION = ["n'est pas", "ne fait pas partie", "n'est plus", "pas chez nous", "pas dans", "aucun", "inconnu", "introuvable",
            "ne figure", "n'a jamais", "pas de", "ne connais", "n'existe", "pas à nous", "pas de chez nous", "n'appartient",
            "pas un joueur", "n'est pas dans", "ne joue pas", "ailleurs", "pas notre"]
BUDGET_WORDS = ["budget", "moyens", "hors de portée", "irréaliste", "impossible", "trop cher", "dépasse", "pas les fonds",
                "pas possible", "inaccessible", "irraisonnable", "folie", "pas réaliste"]
STAT_RE = re.compile(r"\d+\s*(?:buts?|minutes?|passes?|pd\b|matchs?)|note (?:moyenne )?(?:de )?\d", re.IGNORECASE)


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)).replace("’", "'")


def last(name: str | None) -> str:
    return (name or "").split()[-1] if name else ""


# ------------------------------------------------------------------ copie de la carrière
def make_copy(dst: Path) -> Path:
    """Copie la base, les préférences et le jeton de l'utilisateur dans `dst` (la vraie base n'est jamais touchée)."""
    src = Path(os.path.expandvars(r"%LOCALAPPDATA%\ClubDirectorAI")) if sys.platform == "win32" else Path.home() / ".local/share/clubdirector"
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("clubdirector.sqlite3", "clubdirector.sqlite3-wal", "clubdirector.sqlite3-shm"):
        (dst / f).unlink(missing_ok=True)
    a, b = sqlite3.connect(src / "clubdirector.sqlite3"), sqlite3.connect(dst / "clubdirector.sqlite3")
    a.backup(b)
    b.close()
    a.close()
    for f in ("preferences.json", "plugin.token"):
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    (dst / "config.toml").write_text(
        'port = 8769\nauto_sync = false\n\n[ai]\nmode = "local"\nmax_tool_rounds = 6\n\n[[ai.providers]]\n'
        'name = "llama.cpp local"\nkind = "openai_compat"\nbase_url = "http://127.0.0.1:8080/v1"\n'
        'model = "clubdirector-local"\ntier = 1\n', encoding="utf-8")
    return dst


# ------------------------------------------------------------------ partage de l'IA locale
def wait_llm_free(max_wait_s: float = 900) -> None:
    """Attend que llama-server ne traite plus aucune requête (celle de l'entraîneur passe avant)."""
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        try:
            slots = httpx.get(f"{LLM}/slots", timeout=3).json()
            if not any(s.get("is_processing") for s in slots):
                return
        except (httpx.HTTPError, ValueError):
            pass  # serveur occupé ou en redémarrage : on patiente
        time.sleep(8)


# ------------------------------------------------------------------ variables tirées de la carrière
def career_vars(state, tctx) -> dict[str, str]:
    from sqlalchemy import text

    repo, ctx, orch = state.repo, tctx.ctx, state.orchestrator
    v: dict[str, str] = {}
    for key, role in (("ds", "directeur_sportif"), ("dt", "directeur_technique"), ("adj", "entraineur_adjoint")):
        m = orch.staff(tctx, role)
        v[key] = (m.first_name or m.name.split()[0]) if m else role
        v[f"{key}_full"] = m.name if m else ""
        if key == "adj" and m and m.contract_end:
            v["adj_contract_year"] = str(m.contract_end)[:4]
    squad = repo.squad(ctx)
    season = repo.season_lines(ctx, [r["uid"] for r in squad])
    s = lambda r: season.get(r["uid"]) or {}  # noqa: E731
    outfield = [r for r in squad if "GK" not in (r.get("positions") or "")]
    top = max(squad, key=lambda r: (s(r).get("goals") or 0, s(r).get("minutes") or 0))
    v["top_scorer"], v["top_scorer_goals"] = top["name"], str(s(top).get("goals") or 0)
    rated = [r for r in squad if s(r).get("average_rating") and (s(r).get("starts") or 0) + (s(r).get("substitute_appearances") or 0) >= 3]
    v["best_rated_last"] = last(max(rated, key=lambda r: float(s(r)["average_rating"]))["name"]) if rated else ""
    v["most_minutes_last"] = last(max(squad, key=lambda r: s(r).get("minutes") or 0)["name"])
    passers = [r for r in squad if s(r).get("assists")]
    v["best_passer_last"] = last(max(passers, key=lambda r: s(r)["assists"])["name"]) if passers else ""
    v["low_minutes"] = min(outfield, key=lambda r: (s(r).get("minutes") or 0, -(r.get("age") or 0)))["name"]
    young = [r for r in outfield if (s(r).get("minutes") or 0) > 0]
    v["young"] = min(young, key=lambda r: r.get("age") or 99)["name"] if young else outfield[0]["name"]
    keepers = [r for r in squad if "GK" in (r.get("positions") or "")]
    keeper = max(keepers, key=lambda r: s(r).get("minutes") or 0) if keepers else squad[0]
    v["keeper"], v["keeper_last"] = keeper["name"], last(keeper["name"])
    mids = [r for r in outfield if (r.get("position_ratings") or {}).get("mc", 0) >= 18 and (r.get("position_ratings") or {}).get("amr", 0) < 10]
    v["midfielder"] = max(mids, key=lambda r: s(r).get("minutes") or 0)["name"] if mids else outfield[0]["name"]
    expiring = sorted((r for r in squad if r.get("contract_end")), key=lambda r: r["contract_end"])
    exp = expiring[0] if expiring else squad[0]
    v["expiring"], v["expiring_last"] = exp["name"], last(exp["name"])
    v["expiring_year"] = str(exp.get("contract_end") or "")[:4]
    with state.engine.connect() as c:
        star = c.execute(text("SELECT name FROM players_current WHERE career_id = :k AND coalesce(club_uid, 0) != :u "
                              "ORDER BY transfer_value DESC LIMIT 1"), {"k": ctx.career_id, "u": ctx.club_uid}).scalar()
        names_in_save = {n for (n,) in c.execute(text("SELECT name FROM players_current WHERE career_id = :k"), {"k": ctx.career_id})}
        staff = c.execute(text("SELECT name, unknown_r4 AS code, contract_end, coalesce(team_slot, 0) AS slot, is_human_manager "
                               "FROM fm_staff WHERE career_id = :k AND club_uid = :u"), {"k": ctx.career_id, "u": ctx.club_uid}).mappings().all()
    v["foreign_star"] = star or "Kylian Mbappé"
    squad_names = {r["name"] for r in squad}
    v["ex_player"] = next((n for n in FAMOUS_ELSEWHERE if n not in names_in_save), FAMOUS_ELSEWHERE[0])
    v["_absent_famous"] = json.dumps([n for n in FAMOUS_ELSEWHERE if n not in squad_names])
    v["_squad"] = json.dumps(sorted(squad_names))
    by_code = lambda code: sorted((r for r in staff if r["code"] == code), key=lambda r: r["slot"])  # noqa: E731
    v["gk_coach_last"] = last(by_code(34)[0]["name"]) if by_code(34) else ""
    v["fitness_last"] = last(by_code(26)[0]["name"]) if by_code(26) else ""
    st = sorted((r for r in staff if r["contract_end"] and not r["is_human_manager"]), key=lambda r: str(r["contract_end"]))
    v["staff_expiring"] = st[0]["name"] if st else v["adj_full"]
    nxt = (state.registry.execute("get_upcoming_matches", {"limit": 1}, tctx).data or [])
    if nxt:
        m = nxt[0]
        opp = m["exterieur"] if m["domicile"] == ctx.club_name else m["domicile"]
        v["next_opponent"] = (repo.club_short_names(ctx, {opp}) or {}).get(opp, opp)
    rec = (state.registry.execute("get_recent_matches", {"limit": 1}, tctx).data or [])
    v["last_score"] = rec[0]["score"] if rec and rec[0].get("score") else ""
    table = state.registry.execute("get_league_table", {}, tctx).data or []
    ours = next((r for r in table if r.get("est_notre_club")), None)
    v["position"] = str(ours["position"]) if ours else ""
    return v


def fill(text: str, v: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: v.get(m.group(1), m.group(0)), text)


# ------------------------------------------------------------------ contrôles
def check(role: str, question: str, reply: str, tools: list[str], expect: dict, v: dict, team_names: dict,
          lineup_xi: list[str] | None, kind: str) -> list[str]:
    fails: list[str] = []
    f_reply, f_q = fold(reply), fold(question)
    bubbles = [b for b in re.split(r"\n\s*\n", reply.strip()) if b.strip()]
    words = len(re.findall(r"\w+", reply))
    if not reply.strip():
        return ["réponse vide"]
    if expect.get("kind") and kind != expect["kind"]:
        fails.append(f"type détecté {kind} au lieu de {expect['kind']}")
    if expect.get("short") and (len(bubbles) > 2 or words > 45):
        fails.append(f"trop long ({len(bubbles)} bulles, {words} mots)")
    if expect.get("tools_none") and tools:
        fails.append(f"outils inutiles : {tools}")
    if expect.get("tools_any") and not set(tools) & set(expect["tools_any"]):
        fails.append(f"outil attendu absent (appelés : {tools or 'aucun'})")
    for s in expect.get("must_any", []):
        pass
    if expect.get("must_any") and not any(fold(fill(s, v)) in f_reply for s in expect["must_any"] if fill(s, v)):
        fails.append(f"attendu : un de {[fill(s, v) for s in expect['must_any']]}")
    for s in expect.get("must_not", []):
        if fill(s, v) and last(fold(fill(s, v))) in f_reply:
            fails.append(f"ne devait pas citer {fill(s, v)}")
    if expect.get("redirect"):
        target = team_names.get(expect["redirect"], "")
        if target and not any(fold(p) in f_reply for p in target.split()):
            fails.append(f"pas de renvoi vers {target}")
    if expect.get("no_player_stats") and STAT_RE.search(reply):
        fails.append("statistiques de joueur données hors de son rôle")
    if expect.get("budget_trap") and not any(w in f_reply for w in map(fold, BUDGET_WORDS)):
        fails.append("piège budget non relevé")
    if expect.get("trap"):
        trap = fill(expect["trap"], v)
        if not any(fold(n) in f_reply for n in NEGATION):
            fails.append(f"piège non démenti ({trap})")
    if expect.get("lineup"):
        if "propose_lineup" not in tools:
            fails.append("composition non calculée")
        squad = json.loads(v["_squad"])
        named = [n for n in squad if fold(last(n)) in f_reply]
        if lineup_xi:
            hit = sum(1 for n in lineup_xi if fold(last(n)) in f_reply)
            if hit < 8:
                fails.append(f"onze calculé non repris ({hit}/11)")
        if len(named) < 8:
            fails.append(f"composition incomplète ({len(named)} joueurs de l'effectif cités)")
    # Contrôles communs à toutes les réponses.
    for n in json.loads(v["_absent_famous"]):
        if fold(last(n)) in f_reply and fold(last(n)) not in f_q:
            fails.append(f"joueur absent de l'effectif cité : {n}")
    if DEFERRED_RE.search(reply):
        fails.append(f"promesse différée : « {DEFERRED_RE.search(reply).group(0)} »")
    if ACTION_RE.search(reply):
        fails.append(f"action dans le jeu prétendue : « {ACTION_RE.search(reply).group(0)} »")
    if JARGON_RE.search(reply) or TOOL_NARRATION_RE.search(reply):
        m = JARGON_RE.search(reply) or TOOL_NARRATION_RE.search(reply)
        fails.append(f"jargon technique : « {m.group(0)} »")
    clean = re.sub(r"«[^»]*»|\"[^\"]*\"", "", reply)
    if role in FORMAL and TU_RE.search(clean):
        fails.append(f"tutoiement : « {TU_RE.search(clean).group(0)} »")
    if role not in FORMAL and VOUS_RE.search(clean):
        fails.append(f"vouvoiement : « {VOUS_RE.search(clean).group(0)} »")
    tokens = re.findall(r"[a-zA-Z']+", reply.lower())
    if tokens and sum(t in ENGLISH for t in tokens) / len(tokens) > 0.04:
        fails.append("pas en français")
    return fails


# ------------------------------------------------------------------ exécution
def run(copy: Path, roles: list[str], ids: set[str] | None, label: str) -> Path:
    os.environ["CLUBDIRECTOR_HOME"] = str(copy)
    os.environ["CLUBDIRECTOR_CONFIG"] = str(copy / "config.toml")
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from clubdirector.ai.orchestrator import message_kind
    from clubdirector.api.app import AppState
    from clubdirector.config import load_settings

    state = AppState(load_settings())
    tctx = state.tool_context()
    orch = state.orchestrator
    v = career_vars(state, tctx)
    team_names = {r: (orch.staff(tctx, r).name if orch.staff(tctx, r) else "") for r in ROLES.values()}
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    results = []
    for role in roles:
        for conv in scenarios[role]:
            if ids and conv["id"] not in ids:
                continue
            member = orch.staff(tctx, role)
            cid = orch.conversations.create(tctx.ctx.career_id, f"eval:{conv['id']}")
            previous = None
            for i, turn in enumerate(conv["turns"]):
                question = fill(turn["text"], v)
                kind = message_kind(question, previous)
                wait_llm_free()
                events: list[dict] = []
                t0 = time.perf_counter()
                ans = orch.ask(tctx, question, conversation_id=cid, role=role, member=member, on_event=events.append)
                dt = time.perf_counter() - t0
                tools = [t["tool"] for t in ans.tools]
                xi = None
                lineup_call = next((t for t in ans.tools if t["tool"] == "propose_lineup" and t.get("ok")), None)
                if lineup_call:
                    data = state.registry.execute("propose_lineup", lineup_call["args"], tctx).data or {}
                    xi = [x["joueur"] for x in data.get("onze", [])]
                fails = check(role, question, ans.text, tools, turn.get("expect", {}), v, team_names, xi, kind)
                results.append({"id": f"{conv['id']}#{i + 1}", "role": role, "question": question, "kind": kind,
                                "route": ans.route, "seconds": round(dt, 1), "tools": tools, "fails": fails, "reply": ans.text})
                status = "OK " if not fails else "ÉCHEC"
                print(f"[{status}] {conv['id']}#{i + 1} ({dt:.1f} s, {ans.route}, {tools or '-'}) {question}")
                for f in fails:
                    print(f"        - {f}")
                previous = ans.text
    return write_report(copy, label, results)


def write_report(copy: Path, label: str, results: list[dict]) -> Path:
    out_dir = copy / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = out_dir / f"eval-conversations-{label}-{stamp}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Banc d'évaluation des conversations — {label} — {stamp}", "", summary(results), ""]
    for r in results:
        lines += [f"## {r['id']} — {'OK' if not r['fails'] else 'ÉCHEC'}", f"**Q** : {r['question']}",
                  f"- type {r['kind']} · {r['route']} · {r['seconds']} s · outils {', '.join(r['tools']) or 'aucun'}",
                  *(f"- ❌ {f}" for f in r["fails"]), "", r["reply"], ""]
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + summary(results) + f"\nRapport : {path.with_suffix('.md')}")
    return path


def summary(results: list[dict]) -> str:
    out = ["| Contact | Réussite | Temps médian | Temps p90 |", "|---|---|---|---|"]
    for role in sorted({r["role"] for r in results}):
        rs = [r for r in results if r["role"] == role]
        ok = sum(1 for r in rs if not r["fails"])
        times = sorted(r["seconds"] for r in rs)
        p90 = times[min(len(times) - 1, int(len(times) * 0.9))]
        out.append(f"| {role} | {ok}/{len(rs)} ({100 * ok // max(1, len(rs))} %) | {statistics.median(times):.1f} s | {p90:.1f} s |")
    allr = results
    ok = sum(1 for r in allr if not r["fails"])
    out.append(f"| **total** | **{ok}/{len(allr)} ({100 * ok // max(1, len(allr))} %)** | "
               f"{statistics.median(r['seconds'] for r in allr):.1f} s | |")
    counts: dict[str, int] = {}
    for r in allr:
        for f in r["fails"]:
            key = f.split(" :")[0].split(" (")[0].split(" «")[0]
            counts[key] = counts.get(key, 0) + 1
    if counts:
        out += ["", "Échecs par contrôle : " + ", ".join(f"{k} × {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))]
    return "\n".join(out)


def compare(before: Path, after: Path) -> None:
    a = {r["id"]: r for r in json.loads(before.read_text(encoding="utf-8"))}
    b = {r["id"]: r for r in json.loads(after.read_text(encoding="utf-8"))}
    print("Avant :\n" + summary(list(a.values())) + "\n\nAprès :\n" + summary(list(b.values())))
    fixed = [k for k in b if k in a and a[k]["fails"] and not b[k]["fails"]]
    broken = [k for k in b if k in a and not a[k]["fails"] and b[k]["fails"]]
    print(f"\nCorrigés : {len(fixed)} {fixed}\nRégressions : {len(broken)} {broken}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", type=Path, help="dossier de la copie de carrière (créé ou rafraîchi)")
    ap.add_argument("--refresh", action="store_true", help="recopier la base de l'utilisateur avant de jouer")
    ap.add_argument("--roles", default="ds,dt,adj")
    ap.add_argument("--ids", default="")
    ap.add_argument("--label", default="passage")
    ap.add_argument("--compare", nargs=2, type=Path)
    args = ap.parse_args()
    if args.compare:
        compare(*args.compare)
        return 0
    if not args.copy:
        ap.error("--copy est obligatoire")
    if args.refresh or not (args.copy / "clubdirector.sqlite3").exists():
        make_copy(args.copy)
    roles = [ROLES[r.strip()] for r in args.roles.split(",") if r.strip()]
    run(args.copy, roles, {i for i in args.ids.split(",") if i} or None, args.label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
