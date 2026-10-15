"""Ligne de commande : synchroniser, interroger, lancer le service."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clubdirector", description="ClubDirector AI — directeur sportif IA pour FM26")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("saves", help="Lister les sauvegardes FM26 trouvées")
    p_sync = sub.add_parser("sync", help="Synchroniser une sauvegarde .fm (copie sûre puis lecture)")
    p_sync.add_argument("path", type=Path)
    p_ask = sub.add_parser("ask", help="Poser une question au directeur sportif")
    p_ask.add_argument("question")
    p_ask.add_argument("--tier", type=int, choices=[1, 2, 3])
    p_tool = sub.add_parser("tool", help="Exécuter un outil (diagnostic)")
    p_tool.add_argument("name")
    p_tool.add_argument("args", nargs="?", default="{}")
    sub.add_parser("prise-de-poste", help="Le directeur sportif prend ses fonctions (présentation + état des lieux)")
    p_inv = sub.add_parser("inventory", help="Inventaire des sections d'une sauvegarde (décodées, utilisées)")
    p_inv.add_argument("path", type=Path)
    p_inv.add_argument("--out", type=Path, help="Dossier du rapport (défaut : <données>/reports)")
    p_serve = sub.add_parser("serve", help="Lancer le service local (127.0.0.1)")
    p_serve.add_argument("--port", type=int)
    p_llm = sub.add_parser("llm", help="État de l'IA locale (llama-server) : prête, occupée, figée, arrêtée")
    p_llm.add_argument("--surveiller", action="store_true",
                       help="Surveiller en continu et relancer un serveur figé ou arrêté (sans le service)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from clubdirector.config import load_settings

    settings = load_settings()
    if args.cmd == "llm":
        from clubdirector.ai.factory import build_providers
        from clubdirector.ai.llm_watchdog import build_watchdog

        wd = build_watchdog(settings, build_providers(settings)[0])
        if wd is None:
            print("Aucune IA locale (127.0.0.1) configurée, ou surveillance désactivée.")
            return 1
        if args.surveiller:
            print(f"Surveillance de {wd.root} (journal : {wd.log_path}) — Ctrl+C pour arrêter.")
            wd.start()
            try:
                while True:
                    wd._stop.wait(60)
                    print(json.dumps(wd.as_dict(), ensure_ascii=False))
            except KeyboardInterrupt:
                return 0
        wd.check(act=False)  # diagnostic seul : jamais de relance depuis cette commande
        print(json.dumps(wd.as_dict() | {"slots": wd.last_slots}, ensure_ascii=False, indent=2, default=str))
        return 0 if wd.status.state in ("pret", "occupe") else 1
    if args.cmd == "serve":
        import uvicorn

        from clubdirector.api.app import create_app

        if args.port:
            settings.port = args.port
        if settings.host not in ("127.0.0.1", "localhost"):
            print("Refus : le service n'écoute que sur 127.0.0.1.", file=sys.stderr)
            return 2
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")
        return 0

    from clubdirector.api.app import AppState

    state = AppState(settings)
    if args.cmd == "saves":
        from clubdirector.game.discovery import discover_saves

        found = discover_saves(settings.save_dirs)
        if not found:
            print("Aucune sauvegarde trouvée dans :", *map(str, settings.save_dirs), sep="\n  ")
        for s in found:
            print(f"{s.modified:%Y-%m-%d %H:%M}  {s.size / 1e6:7.1f} Mo  {s.path}")
        return 0
    if args.cmd == "sync":
        res = state.sync_service.sync_save(args.path)
        prefs = state.prefs
        prefs.active_career_id = res.career_id
        state.prefs_store.save(prefs)
        print(json.dumps(asdict(res), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.cmd == "ask":
        ans = state.orchestrator.ask(state.tool_context(), args.question, force_tier=args.tier)
        print(ans.text)
        for lim in ans.limitations:
            print("  ⚠", lim)
        print(f"  [route={ans.route} outils={[t['tool'] for t in ans.tools]}]")
        return 0
    if args.cmd == "prise-de-poste":
        ans = state.orchestrator.take_office(state.tool_context())
        print(ans.text)
        for lim in ans.limitations:
            print("  ⚠", lim)
        print(f"  [route={ans.route} outils={[t['tool'] for t in ans.tools]}]")
        return 0
    if args.cmd == "inventory":
        from clubdirector.game.inventory import build_inventory, render_markdown
        from clubdirector.game.snapshot import take_snapshot

        snap = take_snapshot(args.path, settings.snapshot_dir)
        inv = build_inventory(snap.copy_path)
        out = args.out or settings.home / "reports"
        out.mkdir(parents=True, exist_ok=True)
        md = out / f"inventaire-{args.path.stem}.md"
        md.write_text(render_markdown(inv), encoding="utf-8")
        (out / f"inventaire-{args.path.stem}.json").write_text(
            json.dumps(inv.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Rapport : {md}")
        return 0
    if args.cmd == "tool":
        r = state.registry.execute(args.name, json.loads(args.args), state.tool_context())
        print(json.dumps(r.as_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if r.ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
