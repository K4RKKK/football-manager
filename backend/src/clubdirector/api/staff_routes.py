"""Staff vivant côté service : travail de fond après chaque synchronisation, dossiers et faits signalés.

Après une nouvelle sauvegarde : (1) résumé des fils devenus longs, (2) messages proactifs des trois
contacts (faits nouveaux, dossiers suivis), (3) préchauffage des prompts sur l'IA locale. Un seul
travail de fond à la fois ; une vraie conversation reste prioritaire (l'IA locale traite une
demande à la fois).
"""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI

from clubdirector.proactive.staff_messages import NoticeStore, run_proactive
from clubdirector.transfers.dossiers import DossierStore, dossier_view

log = logging.getLogger(__name__)
_lock = threading.Lock()


def after_sync_job(state) -> dict:
    """Résumés, messages proactifs puis préchauffage, pour la carrière active."""
    t = state.tool_context()
    o = state.orchestrator
    out: dict = {"resumes": o.summarize_threads(t)}
    out["proactif"] = run_proactive(t, o, state.registry).as_dict()
    out["prechauffes"] = o.warm(t)
    log.info("Après synchronisation : %d fait(s) nouveau(x), %d message(s) du staff", out["proactif"]["new"],
             len(out["proactif"]["messages"]))
    return out


def run_after_sync_in_background(state) -> None:
    def run() -> None:
        if not _lock.acquire(blocking=False):
            return  # un travail de fond est déjà en cours : il relira l'état le plus récent
        try:
            after_sync_job(state)
        except Exception:  # noqa: BLE001 — le travail de fond ne doit jamais faire tomber le service
            log.exception("Travail après synchronisation en échec")
        finally:
            _lock.release()
    threading.Thread(target=run, name="staff-after-sync", daemon=True).start()


def register_staff_routes(app: FastAPI, state, deps: list) -> None:
    @app.get("/api/staff/dossiers", dependencies=deps)
    def staff_dossiers(open_only: bool = False):
        """Dossiers du directeur sportif et leur suivi dans les sauvegardes."""
        t = state.tool_context()
        return [dossier_view(r) for r in DossierStore(state.engine).list(t.ctx.career_id, open_only=open_only)]

    @app.get("/api/staff/notices", dependencies=deps)
    def staff_notices(limit: int = 100):
        """Faits déjà signalés par les contacts (un fait = un message, une seule fois)."""
        t = state.tool_context()
        return [{"id": n["id"], "role": n["role"], "fait": n["fact_key"], "type": n["kind"], "message_id": n["message_id"],
                 "texte": (n.get("data") or {}).get("texte"), "date_jeu": n["game_date"].isoformat() if n.get("game_date") else None}
                for n in NoticeStore(state.engine).recent(t.ctx.career_id, min(limit, 500))]

    @app.post("/api/staff/proactive", dependencies=deps)
    def staff_proactive():
        """Lance maintenant le travail d'après synchronisation (diagnostic ; normalement automatique)."""
        with _lock:
            return after_sync_job(state)


__all__ = ["after_sync_job", "register_staff_routes", "run_after_sync_in_background"]
