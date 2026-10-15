"""Banc d'essai de l'IA du directeur sportif sur la carrière active (service et modèle réels).

Pose une série de questions, enregistre pour chacune : la route (niveau 0 sans IA / niveau 1 local…),
les outils appelés, les limitations, la durée et la réponse. Rapport Markdown dans
<données>/reports/eval-ia-<date>.md (contient des données de carrière : reste local).

Usage : uv run --project backend python scripts/eval_ai.py [question ...]
Prérequis : une carrière synchronisée et le serveur d'IA démarré (scripts/start_llm.ps1).
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from clubdirector.api.app import AppState
from clubdirector.config import load_settings

QUESTIONS = [
    "Bonjour, fais-moi un bilan complet de notre effectif.",
    "Qui sont nos joueurs les plus dangereux cette saison en xG et en passes décisives attendues ?",
    "Notre ailier droit manque de régularité. Trouve-moi cinq ailiers droits de moins de 24 ans qui conviendraient.",
    "Quels contrats de l'équipe première arrivent à échéance dans les 18 prochains mois ?",
    "Comment avons-nous fini en Serie A ces cinq dernières saisons ?",
    "Qui compose notre staff technique et jusqu'à quand sont-ils sous contrat ?",
    "Je veux recruter un joueur à 200 millions. Qu'en penses-tu ?",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    questions = sys.argv[1:] or QUESTIONS
    settings = load_settings()
    state = AppState(settings)
    tctx = state.tool_context()
    out = [f"# Banc d'essai IA — {datetime.now():%Y-%m-%d %H:%M}", "",
           f"Carrière : {tctx.ctx.label} · date du jeu {tctx.ctx.game_date}", ""]
    for q in questions:
        t0 = time.perf_counter()
        ans = state.orchestrator.ask(tctx, q)
        dt = time.perf_counter() - t0
        tools = [f"{t['tool']}{'' if t.get('ok', True) else ' (échec)'}" for t in ans.tools]
        print(f"\n=== {q}\n[{ans.route} · {dt:.1f} s · outils : {', '.join(tools) or 'aucun'}]\n{ans.text}\n")
        out += [f"## {q}", "", f"- route : {ans.route} · durée : {dt:.1f} s", f"- outils : {', '.join(tools) or 'aucun'}",
                *(f"- limitation : {lim}" for lim in ans.limitations), "", ans.text, ""]
    report = settings.home / "reports" / f"eval-ia-{datetime.now():%Y%m%d-%H%M}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(out), encoding="utf-8")
    print(f"Rapport : {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
