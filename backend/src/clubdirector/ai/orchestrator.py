"""Orchestrateur de conversation : routage → (niveau 0 | boucle d'outils LLM) → réponse tracée."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, func, insert, select

from clubdirector.ai.club_brief import build_club_dossier
from clubdirector.ai.persona import TAKE_OFFICE_REQUEST, build_system_prompt
from clubdirector.ai.providers.base import IAIProvider, ProviderError
from clubdirector.ai.router import answer_intent, classify, wants_premium
from clubdirector.database import schema as s
from clubdirector.memory.store import ConversationStore, MemoryStore
from clubdirector.sync.season import season_label
from clubdirector.tools.registry import ToolContext, ToolRegistry

log = logging.getLogger(__name__)
MAX_TOOL_RESULT_CHARS = 12000


@dataclass
class ChatAnswer:
    text: str
    route: str  # niveau0 | niveau1 | niveau2 | niveau3 | indisponible
    conversation_id: int
    tools: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provider: str | None = None
    cost_usd: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _compact(data: str) -> str:
    if len(data) <= MAX_TOOL_RESULT_CHARS:
        return data
    return data[:MAX_TOOL_RESULT_CHARS] + '…"[tronqué : affinez la requête (filtres, limit)]"'


class Orchestrator:
    def __init__(self, engine: Engine, registry: ToolRegistry, providers: list[IAIProvider], *,
                 mode: str = "local", monthly_budget_usd: float = 0.0, max_tool_rounds: int = 6,
                 history_messages: int = 8, prefs_store: Any = None) -> None:
        self.engine = engine
        self.prefs_store = prefs_store
        self.registry = registry
        self.providers = sorted(providers, key=lambda p: p.tier)
        self.mode = mode
        self.monthly_budget_usd = monthly_budget_usd
        self.max_tool_rounds = max_tool_rounds
        self.history_messages = history_messages
        self.conversations = ConversationStore(engine)

    # ------------------------------------------------------------------ budget
    def month_spend(self) -> float:
        start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with self.engine.connect() as c:
            return float(c.execute(select(func.coalesce(func.sum(s.ai_usage.c.cost_usd), 0.0))
                                   .where(s.ai_usage.c.created_at >= start)).scalar_one())

    def _record_usage(self, p: IAIProvider, model: str | None, tin: int, tout: int) -> float:
        cost = tin / 1e6 * p.input_cost_per_mtok + tout / 1e6 * p.output_cost_per_mtok
        with self.engine.begin() as c:
            c.execute(insert(s.ai_usage).values(provider=p.name, model=model or p.model, tier=p.tier,
                                                input_tokens=tin, output_tokens=tout, cost_usd=cost,
                                                created_at=datetime.now(UTC)))
        return cost

    def choose_provider(self, question: str, force_tier: int | None = None) -> IAIProvider | None:
        if not self.providers:
            return None
        allowed = {"local": {1}, "hybride": {1, 2}, "premium": {1, 2, 3}}.get(self.mode, {1})
        if force_tier is not None:
            wanted = force_tier
        elif wants_premium(question) and 3 in allowed:
            wanted = 3
        else:
            wanted = min(allowed)
        candidates = [p for p in self.providers if p.tier == wanted and p.tier in allowed]
        if not candidates:
            candidates = [p for p in self.providers if p.tier in allowed]
        if not candidates:
            return None
        p = candidates[0]
        paid = p.input_cost_per_mtok > 0 or p.output_cost_per_mtok > 0
        if paid and self.monthly_budget_usd > 0 and self.month_spend() >= self.monthly_budget_usd:
            free = [x for x in self.providers if x.input_cost_per_mtok == 0 and x.output_cost_per_mtok == 0]
            return free[0] if free else None
        return p

    # ------------------------------------------------------------------ conversation
    def take_office(self, tctx: ToolContext) -> ChatAnswer:
        """Prise de poste explicite du directeur sportif dans la carrière active."""
        conv = self.conversations.create(tctx.ctx.career_id, "Prise de poste")
        return self.ask(tctx, TAKE_OFFICE_REQUEST, conversation_id=conv, force_tier=1, taking_office=True)

    def _office_pending(self, tctx: ToolContext) -> bool:
        return tctx.ctx.career_id not in tctx.prefs.office_taken

    def _mark_office_taken(self, tctx: ToolContext) -> None:
        if tctx.ctx.career_id in tctx.prefs.office_taken:
            return
        tctx.prefs.office_taken.append(tctx.ctx.career_id)
        if self.prefs_store is not None:
            prefs = self.prefs_store.load()
            if tctx.ctx.career_id not in prefs.office_taken:
                prefs.office_taken.append(tctx.ctx.career_id)
                self.prefs_store.save(prefs)

    def ask(self, tctx: ToolContext, question: str, *, conversation_id: int | None = None,
            force_tier: int | None = None, taking_office: bool | None = None) -> ChatAnswer:
        conv = conversation_id or self.conversations.create(tctx.ctx.career_id, question[:80])
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in self.conversations.messages(conv, limit=self.history_messages)
            if m["role"] in ("user", "assistant")
        ]
        self.conversations.add_message(conv, "user", question, game_date=tctx.ctx.game_date)
        trace: list[dict] = []

        def run(tool: str, args: dict):
            r = self.registry.execute(tool, args, tctx)
            trace.append({"tool": tool, "args": args, "ok": r.ok, "error": r.error})
            return r

        answer: ChatAnswer
        intent = classify(question) if force_tier is None else None
        if intent is not None:
            try:
                text, lim = answer_intent(intent, run)
                answer = ChatAnswer(text, "niveau0", conv, trace, sorted(set(lim)))
            except LookupError as exc:
                answer = ChatAnswer(f"Donnée non disponible : {exc}", "niveau0", conv, trace)
        else:
            office = self._office_pending(tctx) if taking_office is None else taking_office
            answer = self._llm(tctx, question, history, conv, trace, force_tier, office)
            if office and answer.route.startswith("niveau"):
                self._mark_office_taken(tctx)
        self.conversations.add_message(conv, "assistant", answer.text, game_date=tctx.ctx.game_date,
                                       route=answer.route, tool_trace=trace)
        return answer

    def _llm(self, tctx: ToolContext, question: str, history: list[dict], conv: int, trace: list[dict],
             force_tier: int | None, taking_office: bool = False) -> ChatAnswer:
        provider = self.choose_provider(question, force_tier)
        if provider is None:
            return ChatAnswer(
                "Cette question demande une analyse par le modèle IA, mais aucun moteur n'est disponible "
                "(non configuré, mode local sans serveur, ou budget mensuel atteint). Les questions factuelles "
                "(scores, buteurs, classement, budgets, effectif par poste) restent disponibles sans IA.",
                "indisponible", conv, trace)
        ctx = tctx.ctx
        system = build_system_prompt(
            director_name=tctx.prefs.director_name, club=ctx.club_name, persona=tctx.prefs.persona,
            game_date=ctx.game_date.isoformat() if ctx.game_date else None,
            season=season_label(ctx.season_start_year), knowledge=tctx.prefs.knowledge_mode,
            memories=MemoryStore(self.engine).list(ctx.career_id),
            manager=ctx.manager_name, dossier=build_club_dossier(self.registry, tctx),
            taking_office=taking_office,
        )
        tools = [{"name": t.name, "description": t.description, "parameters": t.json_schema()}
                 for t in self.registry.for_llm()]
        cost = 0.0
        limitations: list[str] = []
        try:
            session = provider.start(system, [*history, {"role": "user", "content": question}], tools)
            for _ in range(self.max_tool_rounds + 1):
                step = session.step()
                cost += self._record_usage(provider, step.model, step.input_tokens, step.output_tokens)
                if not step.tool_calls:
                    return ChatAnswer(step.text.strip() or "(réponse vide du modèle)", f"niveau{provider.tier}", conv,
                                      trace, sorted(set(limitations)), provider.name, cost)
                results = []
                for call in step.tool_calls:
                    r = self.registry.execute(call.name, call.arguments, tctx)
                    trace.append({"tool": call.name, "args": call.arguments, "ok": r.ok, "error": r.error})
                    limitations.extend(r.limitations)
                    payload = json.dumps(r.as_dict(), ensure_ascii=False, default=str)
                    results.append((call, _compact(payload), not r.ok))
                session.add_tool_results(results)
            return ChatAnswer("J'ai atteint la limite d'appels d'outils sans conclure ; reformulez ou précisez la demande.",
                              f"niveau{provider.tier}", conv, trace, sorted(set(limitations)), provider.name, cost)
        except ProviderError as exc:
            log.warning("Fournisseur IA en échec : %s", exc)
            return ChatAnswer(f"Le moteur IA « {provider.name} » est indisponible : {exc}", "indisponible", conv,
                              trace, sorted(set(limitations)), provider.name, cost)
