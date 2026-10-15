"""Service local ClubDirector (FastAPI).

Sécurité :
- écoute 127.0.0.1 par défaut ;
- en-tête Host vérifié (protection DNS rebinding) ;
- toutes les routes /api (sauf /api/health) exigent l'en-tête X-ClubDirector-Token ;
- aucune route CORS : un site web tiers ne peut pas lire les réponses ;
- l'IA n'exécute que des outils du registre ; aucune exécution de code arbitraire.
"""

from __future__ import annotations

import hmac
import json
import logging
import queue
import threading
from dataclasses import asdict
from datetime import UTC
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from clubdirector import __version__
from clubdirector.ai.director_identity import staff_candidates
from clubdirector.ai.factory import build_providers
from clubdirector.ai.llm_watchdog import build_watchdog
from clubdirector.ai.orchestrator import CONTACT_ROLES, Orchestrator, tool_label
from clubdirector.ai.persona import ROLE_LABELS
from clubdirector.ai.providers.base import status_sink
from clubdirector.api.live import Heartbeat, PluginBridge
from clubdirector.api.staff_routes import register_staff_routes, run_after_sync_in_background
from clubdirector.config import Settings, load_settings
from clubdirector.database.db import open_database
from clubdirector.database.repositories import CareerNotFound, Repository
from clubdirector.game.discovery import discover_saves
from clubdirector.game.fmsave_reader import FmsaveSaveReader
from clubdirector.game.snapshot import SaveBusyError, prune_snapshots
from clubdirector.memory.store import ConversationStore
from clubdirector.money import calibrate, from_save_table
from clubdirector.preferences import Preferences, PreferenceStore
from clubdirector.security.secrets import load_or_create_token, redact
from clubdirector.sync.service import SyncService
from clubdirector.sync.watcher import SaveWatcher
from clubdirector.tools.catalog import build_registry
from clubdirector.tools.presenters import player_full, player_summary
from clubdirector.tools.registry import ToolContext

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class SyncRequest(BaseModel):
    path: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: int | None = None
    force_tier: int | None = Field(None, ge=1, le=3)


class ToolCallRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class PhoneMessage(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class ReactionRequest(BaseModel):
    # Réactions iMessage : cœur, pouce levé, pouce baissé, rire, « !! », « ? » ; None : retirer.
    reaction: Literal["love", "like", "dislike", "laugh", "emphasize", "question"] | None = None


class StaffAssignment(BaseModel):
    uid: int | None = None  # None : retour à la détection automatique


class CalibrationRequest(BaseModel):
    player_uid: int
    displayed_value: float = Field(..., gt=0)
    symbol: str = "€"


class AppState:
    def __init__(self, settings: Settings) -> None:
        settings.ensure_dirs()
        self.settings = settings
        self.engine = open_database(settings.db_path)
        self.repo = Repository(self.engine)
        self.registry = build_registry()
        self.prefs_store = PreferenceStore(settings.home / "preferences.json")
        self.token = load_or_create_token(settings.token_path)
        self.bridge = PluginBridge()
        self.sync_service = SyncService(self.engine, FmsaveSaveReader(), settings.snapshot_dir)
        # Une seule synchronisation à la fois (manuelle ou automatique).
        self.sync_lock = threading.Lock()
        self.watcher = SaveWatcher(settings.save_dirs, self.sync_and_activate, poll_s=settings.auto_sync_poll_s,
                                   settle_s=settings.auto_sync_settle_s)
        self.watcher.status.enabled = settings.auto_sync
        providers, self.provider_errors = build_providers(settings)
        # Surveillance de l'IA locale : un llama-server figé ou arrêté est relancé (ai/llm_watchdog.py).
        self.llm_watchdog = build_watchdog(settings, providers)
        self.orchestrator = Orchestrator(self.engine, self.registry, providers, mode=settings.ai.mode,
                                         monthly_budget_usd=settings.ai.monthly_budget_usd,
                                         max_tool_rounds=settings.ai.max_tool_rounds,
                                         prefs_store=self.prefs_store, thinking=settings.ai.thinking)
        self._warm_lock = threading.Lock()

    def sync_and_activate(self, path: Path) -> dict:
        """Synchronise une sauvegarde et en fait la carrière active (copie sûre, verrou commun)."""
        with self.sync_lock:
            res = self.sync_service.sync_save(path)
            prune_snapshots(self.settings.snapshot_dir, self.settings.snapshot_retention)
            prefs = self.prefs
            prefs.active_career_id = res.career_id
            self.prefs_store.save(prefs)
        if self.settings.proactive_enabled and not res.reused:
            run_after_sync_in_background(self)  # résumés, messages proactifs du staff, puis préchauffage
        else:
            self.warm_in_background()
        return asdict(res)

    def warm_in_background(self) -> None:
        """Prépare le prompt des trois contacts sur l'IA locale (réponses rapides après une sauvegarde)."""
        def run() -> None:
            if not self._warm_lock.acquire(blocking=False):
                return
            try:
                done = self.orchestrator.warm(self.tool_context())
                log.info("Contacts préparés sur l'IA locale : %s", ", ".join(done) or "aucun")
            except Exception as exc:  # noqa: BLE001 — le préchauffage n'est qu'une optimisation
                log.info("Préchauffage ignoré : %s", exc)
            finally:
                self._warm_lock.release()
        threading.Thread(target=run, name="warm-llm", daemon=True).start()

    @property
    def prefs(self) -> Preferences:
        return self.prefs_store.load()

    def tool_context(self) -> ToolContext:
        prefs = self.prefs
        try:
            ctx = self.repo.context(prefs.active_career_id)
        except CareerNotFound:
            if prefs.active_career_id is None:
                raise
            ctx = self.repo.context(None)
        self._apply_save_currency(prefs, ctx)
        return ToolContext(self.engine, self.repo, ctx, prefs)

    def _apply_save_currency(self, prefs: Preferences, ctx) -> None:
        """Conversion des montants par la table des devises de la sauvegarde, sauf étalonnage manuel."""
        if prefs.currency.manual:
            return
        row = self.repo.currency(ctx, prefs.display_currency)
        if row and row.get("rate"):
            prefs.currency = from_save_table(row["name"], row.get("symbol") or "", float(row["rate"]))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    state = AppState(settings)
    app = FastAPI(title="ClubDirector AI", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cd = state
    if settings.auto_sync:
        state.watcher.start()  # relit chaque nouvelle sauvegarde FM26 (copie sûre)
        state.warm_in_background()  # même interrupteur : pas de travail de fond pendant les tests
        if state.llm_watchdog is not None:
            state.llm_watchdog.start()
    allowed_hosts = {f"127.0.0.1:{settings.port}", f"localhost:{settings.port}", "127.0.0.1", "localhost", "testserver"}

    @app.middleware("http")
    async def host_guard(request: Request, call_next):
        if request.headers.get("host", "") not in allowed_hosts:
            return JSONResponse({"detail": "Hôte non autorisé"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(CareerNotFound)
    async def no_career(_req: Request, exc: CareerNotFound):
        return JSONResponse({"detail": str(exc), "code": "no_career"}, status_code=409)

    def auth(request: Request) -> None:
        token = request.headers.get("x-clubdirector-token", "")
        if not hmac.compare_digest(token, state.token):
            raise HTTPException(401, "Jeton ClubDirector invalide ou absent.")

    A = [Depends(auth)]
    register_staff_routes(app, state, A)  # dossiers, faits signalés, travail d'après synchronisation

    # ----------------------------------------------------------------- interface diagnostic
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        return html.replace("__CLUBDIRECTOR_TOKEN__", state.token)

    @app.get("/overlay", response_class=HTMLResponse)
    def overlay() -> str:
        """Téléphone ClubDirector (fenêtre au-dessus de FM26) : Contacts et Messages."""
        page = WEB_DIR / "phone.html"
        html = (page if page.exists() else WEB_DIR / "overlay.html").read_text(encoding="utf-8")
        return html.replace("__CLUBDIRECTOR_TOKEN__", state.token)

    @app.get("/overlay/panneau", response_class=HTMLResponse)
    def overlay_panel() -> str:
        """Ancien panneau compact de discussion."""
        html = (WEB_DIR / "overlay.html").read_text(encoding="utf-8")
        return html.replace("__CLUBDIRECTOR_TOKEN__", state.token)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    # ----------------------------------------------------------------- état / synchro
    @app.get("/api/status", dependencies=A)
    def status():
        careers = state.repo.list_careers()
        live = state.bridge.status()
        ctx = None
        currency = state.prefs.currency
        try:
            t = state.tool_context()
            ctx, currency = t.ctx, t.prefs.currency
        except CareerNotFound:
            pass
        return {
            "version": __version__,
            "careers": careers,
            "active": asdict(ctx) if ctx else None,
            "live_plugin": asdict(live),
            "ai": {"mode": settings.ai.mode, "providers": [
                {"name": p.name, "model": p.model, "tier": p.tier} for p in state.orchestrator.providers],
                "errors": state.provider_errors, "month_spend_usd": state.orchestrator.month_spend(),
                "monthly_budget_usd": settings.ai.monthly_budget_usd,
                "local": state.llm_watchdog.as_dict() if state.llm_watchdog else None},
            "auto_sync": state.watcher.as_dict(),
            "director": _director_status(),
            "currency": currency.model_dump(),
            "save_dirs": [str(d) for d in settings.save_dirs],
            "data_dir": str(settings.home),
        }

    def _director_status() -> dict:
        prefs = state.prefs
        try:
            t = state.tool_context()
        except CareerNotFound:
            return {"name": prefs.director_name, "persona": prefs.persona, "office_taken": False, "identity": None}
        d = state.orchestrator.director(t)
        return {"name": d.name if d else prefs.director_name, "persona": prefs.persona,
                "office_taken": not state.orchestrator.office_pending(t, d),
                "identity": d.as_dict() if d else None}

    @app.get("/api/saves", dependencies=A)
    def saves():
        return [{"path": str(s.path), "size": s.size, "modified": s.modified.isoformat()} for s in discover_saves(settings.save_dirs)]

    @app.post("/api/sync", dependencies=A)
    def sync(req: SyncRequest):
        return _sync(Path(req.path))

    @app.post("/api/sync/latest", dependencies=A)
    def sync_latest():
        """Synchronise la sauvegarde la plus récente (celle que l'entraîneur vient d'enregistrer)."""
        found = discover_saves(settings.save_dirs)
        if not found:
            raise HTTPException(404, "Aucune sauvegarde FM26 trouvée dans les dossiers configurés.")
        return _sync(found[0].path) | {"source": found[0].path.name}

    def _sync(path: Path) -> dict:
        if path.suffix.lower() != ".fm":
            raise HTTPException(400, "Seuls les fichiers de sauvegarde .fm sont acceptés.")
        if state.sync_lock.locked():
            raise HTTPException(409, "Une synchronisation est déjà en cours (automatique ou manuelle).")
        try:
            return state.sync_and_activate(path)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SaveBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:  # lecture impossible : on informe sans planter le service
            log.exception("Synchronisation échouée")
            raise HTTPException(422, redact(f"Lecture de la sauvegarde impossible : {type(exc).__name__}: {exc}")) from exc

    @app.post("/api/careers/{career_id}/activate", dependencies=A)
    def activate(career_id: int):
        state.repo.context(career_id)
        prefs = state.prefs
        prefs.active_career_id = career_id
        state.prefs_store.save(prefs)
        return {"active_career_id": career_id}

    # ----------------------------------------------------------------- données
    @app.get("/api/dashboard", dependencies=A)
    def dashboard():
        t = state.tool_context()
        def run(name, args=None):
            return state.registry.execute(name, args or {}, t).as_dict()
        return {
            "save": run("get_current_save"),
            "club": run("get_managed_club"),
            "last_matches": run("get_recent_matches", {"limit": 5}),
            "next_matches": run("get_upcoming_matches", {"limit": 3}),
            "transfer_budget": run("get_transfer_budget"),
            "wage_budget": run("get_wage_budget"),
            "alerts": run("get_alerts"),
            "contracts": run("analyze_contract_risks"),
            "weak_positions": run("identify_weak_positions"),
            "table": run("get_league_table"),
        }

    @app.get("/api/squad", dependencies=A)
    def squad():
        t = state.tool_context()
        return [player_full(r, t.prefs) for r in state.repo.squad(t.ctx)]

    @app.get("/api/players/{uid}", dependencies=A)
    def player(uid: int):
        t = state.tool_context()
        row = state.repo.player(t.ctx, uid)
        if row is None:
            raise HTTPException(404, "Joueur introuvable dans la carrière active.")
        out = player_full(row, t.prefs)
        out["stats"] = state.registry.execute("get_player_season_history", {"player_uid": uid}, t).as_dict()
        return out

    @app.get("/api/players", dependencies=A)
    def search(position: str | None = None, min_age: int | None = None, max_age: int | None = None,
               name: str | None = None, limit: int = 50, offset: int = 0, order_by: str = "transfer_value"):
        t = state.tool_context()
        try:
            total, rows = state.repo.search_players(t.ctx, position=position, min_age=min_age, max_age=max_age,
                                                    name=name, limit=min(limit, 200), offset=offset, order_by=order_by)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"total": total, "items": [player_summary(r, t.prefs) for r in rows]}

    # ----------------------------------------------------------------- outils / chat
    @app.get("/api/tools", dependencies=A)
    def tools():
        return [t.describe() for t in state.registry.all()]

    @app.post("/api/tools/{name}", dependencies=A)
    def call_tool(name: str, req: ToolCallRequest):
        return state.registry.execute(name, req.args, state.tool_context()).as_dict()

    @app.post("/api/chat", dependencies=A)
    def chat(req: ChatRequest):
        return state.orchestrator.ask(state.tool_context(), req.question, conversation_id=req.conversation_id,
                                      force_tier=req.force_tier).as_dict()

    @app.post("/api/director/take-office", dependencies=A)
    def take_office():
        return state.orchestrator.take_office(state.tool_context()).as_dict()

    # ----------------------------------------------------------------- téléphone (contacts du staff)
    def _role(role: str) -> str:
        if role not in CONTACT_ROLES:
            raise HTTPException(404, "Contact inconnu.")
        return role

    def _photo_path(unique_id: int | None) -> Path | None:
        if not unique_id:
            return None
        for d in settings.faces_dirs:
            for ext in (".png", ".jpg"):
                f = d / f"{int(unique_id)}{ext}"
                if f.is_file():
                    return f
        return None

    def _message_out(m: dict, reaction: str | None = None) -> dict:
        trace = m.get("tool_trace") or []
        labels = list(dict.fromkeys(tool_label(t.get("tool", "")) for t in trace if t.get("ok")))
        at = m.get("created_at")
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=UTC)  # SQLite rend les dates sans fuseau : elles sont enregistrées en UTC
        return {"id": m["id"], "from": "me" if m["role"] == "user" else "them", "text": m["content"],
                "at": at.isoformat() if at else None,
                "game_date": m["game_date"].isoformat() if m.get("game_date") else None,
                "sources": labels, "route": m.get("route"), "reaction": reaction}

    def _contact(t: ToolContext, role: str) -> dict:
        o = state.orchestrator
        member = o.staff(t, role)
        conv = o.conversations.find_thread(t.ctx.career_id, role, member.uid if member else 0)
        last = o.conversations.messages(conv, limit=1) if conv else []
        can_chat = member is not None or role == "directeur_sportif"
        return {
            "role": role, "label": ROLE_LABELS[role], "person": member.as_dict() if member else None,
            "name": member.name if member else (t.prefs.director_name if role == "directeur_sportif" else None),
            "wage": member.wage if member else None, "photo": bool(member and _photo_path(member.unique_id)),
            "wage_text": t.prefs.currency.format(member.wage) if member and member.wage else None,
            "can_chat": can_chat, "corrected": role in t.prefs.staff_overrides,
            "intro_pending": can_chat and o.intro_pending(t, role, member),
            "unread": o.conversations.unread(conv) if conv else 0,
            "last": _message_out(last[-1]) if last else None,
        }

    def _stream(job) -> StreamingResponse:
        """Réponse diffusée au fil de l'écriture (Server-Sent Events). La réponse est enregistrée même si
        la page se ferme avant la fin."""
        q: queue.Queue = queue.Queue()

        def run() -> None:
            # Messages d'état pendant la réponse (ex. relance de l'IA locale figée) : {"type": "status"}.
            status_sink.set(lambda text: q.put({"type": "status", "text": text}))
            try:
                q.put({"type": "done", **(job(q.put) or {})})
            except Exception as exc:  # noqa: BLE001
                log.exception("Message en échec")
                q.put({"type": "error", "message": redact(str(exc))})
            finally:
                q.put(None)

        threading.Thread(target=run, name="phone-reply", daemon=True).start()

        def events():
            yield ": ok\n\n"
            while (ev := q.get()) is not None:
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def _answer_out(a) -> dict:
        if a is None or a.message_id is None:
            return {"message": None}
        msgs = state.orchestrator.conversations.messages(a.conversation_id, limit=1)
        return {"message": _message_out(msgs[-1]) if msgs else None, "route": a.route, "limitations": a.limitations}

    @app.post("/api/ai/warm", dependencies=A)
    def ai_warm():
        """Prépare les trois contacts sur l'IA locale (ouverture du téléphone)."""
        state.warm_in_background()
        return {"ok": True}

    @app.get("/api/contacts", dependencies=A)
    def contacts():
        t = state.tool_context()
        return [_contact(t, role) for role in CONTACT_ROLES]

    @app.get("/api/contacts/{role}/messages", dependencies=A)
    def contact_messages(role: str, limit: int = 200):
        t = state.tool_context()
        o = state.orchestrator
        member = o.staff(t, _role(role))
        conv = o.conversations.find_thread(t.ctx.career_id, role, member.uid if member else 0)
        if not conv:
            return []
        reactions = o.conversations.reactions(conv)
        return [_message_out(m, reactions.get(m["id"])) for m in o.conversations.messages(conv, limit=min(limit, 500))]

    @app.put("/api/contacts/{role}/messages/{message_id}/reaction", dependencies=A)
    def contact_react(role: str, message_id: int, req: ReactionRequest):
        """Réaction (tapback) de l'entraîneur à un message, enregistrée avec le fil."""
        t = state.tool_context()
        o = state.orchestrator
        member = o.staff(t, _role(role))
        conv = o.conversations.find_thread(t.ctx.career_id, role, member.uid if member else 0)
        if not conv or not o.conversations.set_reaction(conv, message_id, req.reaction):
            raise HTTPException(404, "Message introuvable dans cette conversation.")
        return {"id": message_id, "reaction": req.reaction}

    @app.post("/api/contacts/{role}/messages", dependencies=A)
    def contact_send(role: str, req: PhoneMessage):
        t = state.tool_context()
        if not _contact(t, _role(role))["can_chat"]:
            raise HTTPException(409, "Poste vacant dans la sauvegarde : aucun interlocuteur.")
        return _stream(lambda emit: _answer_out(state.orchestrator.send(t, role, req.text, emit)))

    @app.post("/api/contacts/{role}/intro", dependencies=A)
    def contact_intro(role: str):
        t = state.tool_context()
        if not _contact(t, _role(role))["can_chat"]:
            raise HTTPException(409, "Poste vacant dans la sauvegarde : aucun interlocuteur.")
        return _stream(lambda emit: _answer_out(state.orchestrator.introduce(t, role, emit)))

    @app.post("/api/contacts/{role}/read", dependencies=A)
    def contact_read(role: str):
        t = state.tool_context()
        o = state.orchestrator
        member = o.staff(t, _role(role))
        conv = o.conversations.find_thread(t.ctx.career_id, role, member.uid if member else 0)
        if conv:
            o.conversations.mark_read(conv)
        return {"ok": True}

    @app.get("/api/contacts/{role}/candidates", dependencies=A)
    def contact_candidates(role: str):
        t = state.tool_context()
        return staff_candidates(state.engine, t.ctx.career_id, t.ctx.club_uid, _role(role))

    @app.put("/api/contacts/{role}/person", dependencies=A)
    def contact_assign(role: str, req: StaffAssignment):
        _role(role)
        prefs = state.prefs
        if req.uid is None:
            prefs.staff_overrides.pop(role, None)
        else:
            t = state.tool_context()
            if not any(c["uid"] == req.uid for c in staff_candidates(state.engine, t.ctx.career_id, t.ctx.club_uid, role)):
                raise HTTPException(400, "Cette personne ne fait pas partie du staff du club.")
            prefs.staff_overrides[role] = req.uid
        state.prefs_store.save(prefs)
        state.warm_in_background()
        return _contact(state.tool_context(), role)

    @app.get("/api/photos/{unique_id}", dependencies=A)
    @app.get("/api/staff/{unique_id}/photo", dependencies=A)
    def staff_photo(unique_id: int):
        f = _photo_path(unique_id)
        if f is None:
            raise HTTPException(404, "Pas de photo pour cette personne (pack de visages).")
        return FileResponse(f, headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/phone/home", dependencies=A)
    def phone_home():
        t = state.tool_context()

        def data(name, args=None):
            r = state.registry.execute(name, args or {}, t)
            return r.data if r.ok else None
        nxt = data("get_upcoming_matches", {"limit": 1}) or []
        last = data("get_recent_matches", {"limit": 1}) or []
        table = data("get_league_table") or []
        ours = next((row for row in table if isinstance(row, dict) and row.get("est_notre_club")), None)
        short = state.repo.club_short_name(t.ctx, t.ctx.club_uid)
        names = {m[k] for m in (nxt[:1] + last[:1]) for k in ("domicile", "exterieur") if m.get(k)}
        return {"club": t.ctx.club_name, "club_short": short or t.ctx.club_name, "manager": t.ctx.manager_name,
                "club_uid": t.ctx.club_uid,
                "short_names": state.repo.club_short_names(t.ctx, names),
                "game_date": t.ctx.game_date.isoformat() if t.ctx.game_date else None,
                "next_match": nxt[0] if nxt else None, "last_match": last[0] if last else None,
                "league": ours, "sync": state.watcher.as_dict()}

    @app.get("/api/phone/table", dependencies=A)
    def phone_table():
        """Classement du championnat du club (app Classement)."""
        t = state.tool_context()
        rows = state.repo.league_table(t.ctx)
        short = state.repo.club_short_names(t.ctx, {r["club_name"] for r in rows if r.get("club_name")})
        return {"competition": next((r.get("competition_name") for r in rows if r.get("competition_name")), None),
                "rows": [{"position": r["position"], "club": r["club_name"], "short": short.get(r["club_name"], r["club_name"]),
                          "played": r["played"], "won": r["won"], "drawn": r["drawn"], "lost": r["lost"],
                          "goals_for": r["goals_for"], "goals_against": r["goals_against"], "points": r["points"],
                          "ours": r.get("club_uid") == t.ctx.club_uid} for r in rows]}

    @app.get("/api/phone/fixtures", dependencies=A)
    def phone_fixtures():
        """Matchs à venir et récents du club (app Calendrier)."""
        t = state.tool_context()

        def data(name, args):
            r = state.registry.execute(name, args, t)
            return r.data if r.ok and isinstance(r.data, list) else []
        upcoming = data("get_upcoming_matches", {"limit": 30})
        recent = data("get_recent_matches", {"limit": 30})
        names = {m[k] for m in upcoming + recent for k in ("domicile", "exterieur") if m.get(k)}
        short = state.repo.club_short_names(t.ctx, names)

        def out(m):
            home = m.get("domicile") == t.ctx.club_name
            return {**m, "home": home, "opponent": short.get(m.get("exterieur" if home else "domicile"),
                                                             m.get("exterieur" if home else "domicile")),
                    "short_home": short.get(m.get("domicile"), m.get("domicile")),
                    "short_away": short.get(m.get("exterieur"), m.get("exterieur"))}
        return {"upcoming": [out(m) for m in upcoming], "recent": [out(m) for m in recent]}

    @app.get("/api/phone/squad", dependencies=A)
    def phone_squad():
        """Effectif de l'équipe première avec la ligne de saison (app Effectif)."""
        t = state.tool_context()
        rows = state.repo.squad(t.ctx)
        lines = state.repo.season_lines(t.ctx, [r["uid"] for r in rows])
        out = []
        for r in rows:
            p = player_summary(r, t.prefs)
            p["unique_id"] = r.get("unique_id")
            p["photo"] = bool(_photo_path(r.get("unique_id")))
            p["saison"] = lines.get(r["uid"])
            p["notes_postes"] = r.get("position_ratings")
            p["condition"] = round(r["condition"] / 100) if r.get("condition") is not None else None
            out.append(p)
        return out

    def _players_media(t: ToolContext, uids) -> dict[int, dict]:
        """Photo (pack de visages) et appartenance au club de joueurs cités par un outil."""
        out = {}
        for uid in {u for u in uids if u}:
            row = state.repo.player(t.ctx, uid)
            if row:
                out[uid] = {"unique_id": row.get("unique_id"), "photo": bool(_photo_path(row.get("unique_id"))),
                            "notre_joueur": row.get("club_uid") == t.ctx.club_uid}
        return out

    @app.get("/api/phone/mercato", dependencies=A)
    def phone_mercato():
        """Offres reçues et faites par le club, budgets (app Mercato). Offres réelles de la sauvegarde."""
        t = state.tool_context()

        def run(name, args=None):
            r = state.registry.execute(name, args or {}, t)
            return (r.data if r.ok else None), r.limitations
        recues, lim = run("get_transfer_offers", {"direction": "recues", "limit": 100})
        faites, _ = run("get_transfer_offers", {"direction": "faites", "limit": 100})
        recues, faites = (recues or {}).get("offres", []), (faites or {}).get("offres", [])
        transfers, _ = run("get_transfer_budget")
        wages, _ = run("get_wage_budget")
        short = state.repo.club_short_names(t.ctx, {o[k] for o in recues + faites for k in ("acheteur", "vendeur") if o.get(k)})
        media = _players_media(t, [o.get("player_uid") for o in recues + faites])

        def out(o):
            return {**o, **media.get(o.get("player_uid"), {}), "acheteur_court": short.get(o.get("acheteur"), o.get("acheteur")),
                    "vendeur_court": short.get(o.get("vendeur"), o.get("vendeur"))}
        return {"recues": [out(o) for o in recues], "faites": [out(o) for o in faites],
                "budget_transferts": transfers, "budget_salaires": wages, "limitations": lim}

    @app.get("/api/phone/sale/{uid}", dependencies=A)
    def phone_sale(uid: int):
        """Plan de vente d'un de nos joueurs (fiche d'une offre reçue). Préparation uniquement."""
        t = state.tool_context()
        r = state.registry.execute("prepare_sale", {"player_uid": uid}, t)
        if not r.ok:
            raise HTTPException(400, r.error or "Plan de vente impossible.")
        return {"plan": r.data, "limitations": r.limitations}

    @app.get("/api/phone/lineup", dependencies=A)
    def phone_lineup(systeme: str = "4-2-3-1", rotation: bool = False):
        """Onze type calculé sur les notes de poste de FM26 (app Effectif)."""
        t = state.tool_context()
        r = state.registry.execute("propose_lineup", {"systeme": systeme, "rotation": rotation}, t)
        if not r.ok:
            raise HTTPException(400, r.error or "Composition impossible.")
        media = _players_media(t, [p.get("uid") for p in r.data["onze"] + r.data["banc"]])
        for p in r.data["onze"] + r.data["banc"]:
            p.update(media.get(p.get("uid"), {}))
        return {**r.data, "limitations": r.limitations}

    @app.get("/api/conversations", dependencies=A)
    def conversations():
        return ConversationStore(state.engine).list(state.tool_context().ctx.career_id)

    @app.get("/api/conversations/{cid}", dependencies=A)
    def conversation(cid: int):
        return ConversationStore(state.engine).messages(cid, limit=500)

    @app.post("/api/ai/test", dependencies=A)
    def ai_test():
        out = []
        for p in state.orchestrator.providers:
            try:
                out.append({"provider": p.name, "ok": True, "detail": p.ping()})
            except Exception as exc:  # noqa: BLE001
                out.append({"provider": p.name, "ok": False, "detail": redact(str(exc))})
        return out

    # ----------------------------------------------------------------- préférences
    @app.get("/api/preferences", dependencies=A)
    def get_prefs():
        return state.prefs.model_dump(mode="json")

    @app.put("/api/preferences", dependencies=A)
    def put_prefs(prefs: Preferences):
        if prefs.knowledge_mode != "avance":
            prefs.advanced_mode_confirmed = False
        state.prefs_store.save(prefs)
        return prefs.model_dump(mode="json")

    @app.post("/api/currency/calibrate", dependencies=A)
    def calibrate_currency(req: CalibrationRequest):
        t = state.tool_context()
        row = state.repo.player(t.ctx, req.player_uid)
        if row is None or not row.get("transfer_value"):
            raise HTTPException(400, "Joueur introuvable ou sans valeur lisible dans la sauvegarde.")
        game_date = t.ctx.game_date.strftime("%d/%m/%Y") if t.ctx.game_date else "?"
        cal = calibrate(row["transfer_value"], req.displayed_value, req.symbol,
                        f"Valeur de {row['name']} : {req.displayed_value:,.0f} {req.symbol} vue en jeu le {game_date}")
        prefs = state.prefs
        prefs.currency = cal
        state.prefs_store.save(prefs)
        return cal.model_dump()

    # ----------------------------------------------------------------- plugin FM26
    @app.post("/api/plugin/heartbeat", dependencies=A)
    def heartbeat(hb: Heartbeat):
        state.bridge.heartbeat(hb)
        return {"ok": True, "server_version": __version__, "silent": state.prefs.silent_during_matches and hb.in_match}

    @app.get("/api/plugin/status", dependencies=A)
    def plugin_status():
        return asdict(state.bridge.status())

    return app
