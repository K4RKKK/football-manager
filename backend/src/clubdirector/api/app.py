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
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from clubdirector import __version__
from clubdirector.ai.factory import build_providers
from clubdirector.ai.orchestrator import Orchestrator
from clubdirector.api.live import Heartbeat, PluginBridge
from clubdirector.config import Settings, load_settings
from clubdirector.database.db import open_database
from clubdirector.database.repositories import CareerNotFound, Repository
from clubdirector.game.discovery import discover_saves
from clubdirector.game.fmsave_reader import FmsaveSaveReader
from clubdirector.game.snapshot import SaveBusyError, prune_snapshots
from clubdirector.memory.store import ConversationStore
from clubdirector.money import calibrate
from clubdirector.preferences import Preferences, PreferenceStore
from clubdirector.security.secrets import load_or_create_token, redact
from clubdirector.sync.service import SyncService
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
        providers, self.provider_errors = build_providers(settings)
        self.orchestrator = Orchestrator(self.engine, self.registry, providers, mode=settings.ai.mode,
                                         monthly_budget_usd=settings.ai.monthly_budget_usd,
                                         max_tool_rounds=settings.ai.max_tool_rounds,
                                         prefs_store=self.prefs_store)

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
        return ToolContext(self.engine, self.repo, ctx, prefs)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    state = AppState(settings)
    app = FastAPI(title="ClubDirector AI", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cd = state
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

    # ----------------------------------------------------------------- interface diagnostic
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
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
        try:
            ctx = state.tool_context().ctx
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
                "monthly_budget_usd": settings.ai.monthly_budget_usd},
            "save_dirs": [str(d) for d in settings.save_dirs],
            "data_dir": str(settings.home),
        }

    @app.get("/api/saves", dependencies=A)
    def saves():
        return [{"path": str(s.path), "size": s.size, "modified": s.modified.isoformat()} for s in discover_saves(settings.save_dirs)]

    @app.post("/api/sync", dependencies=A)
    def sync(req: SyncRequest):
        path = Path(req.path)
        if path.suffix.lower() != ".fm":
            raise HTTPException(400, "Seuls les fichiers de sauvegarde .fm sont acceptés.")
        try:
            res = state.sync_service.sync_save(path)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SaveBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:  # lecture impossible : on informe sans planter le service
            log.exception("Synchronisation échouée")
            raise HTTPException(422, redact(f"Lecture de la sauvegarde impossible : {type(exc).__name__}: {exc}")) from exc
        prune_snapshots(settings.snapshot_dir, settings.snapshot_retention)
        prefs = state.prefs
        prefs.active_career_id = res.career_id
        state.prefs_store.save(prefs)
        return asdict(res)

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
