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
    p_serve = sub.add_parser("serve", help="Lancer le service local (127.0.0.1)")
    p_serve.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from clubdirector.config import load_settings

    settings = load_settings()
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
    if args.cmd == "tool":
        r = state.registry.execute(args.name, json.loads(args.args), state.tool_context())
        print(json.dumps(r.as_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if r.ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
