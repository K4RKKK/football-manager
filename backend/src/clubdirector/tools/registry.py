"""Registre d'outils exposés à l'IA.

Règles :
- chaque outil a un schéma d'arguments Pydantic (validation stricte, champs inconnus refusés) ;
- l'IA ne peut appeler QUE des outils enregistrés et disponibles ;
- les outils d'action sont enregistrés mais indisponibles tant que leur exécution réelle dans
  FM26 n'est pas prouvée : leur appel renvoie une erreur explicite, jamais un faux succès ;
- chaque appel est journalisé (table tool_audit).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Engine, insert

from clubdirector.database import schema as s
from clubdirector.database.repositories import CareerContext, Repository
from clubdirector.game.interfaces import IGameActionExecutor, UnavailableActionExecutor
from clubdirector.preferences import Preferences

Category = Literal["lecture", "analyse", "action", "memoire"]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(ToolArgs):
    pass


@dataclass
class ToolContext:
    engine: Engine
    repo: Repository
    ctx: CareerContext
    prefs: Preferences
    executor: IGameActionExecutor = field(default_factory=UnavailableActionExecutor)


@dataclass
class ToolResult:
    tool: str
    ok: bool
    data: Any = None
    error: str | None = None
    provenance: dict | None = None
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "provenance": self.provenance,
            "limitations": self.limitations,
        }


Handler = Callable[[ToolContext, Any], ToolResult | dict]


@dataclass
class ToolSpec:
    name: str
    description: str
    category: Category
    args_model: type[ToolArgs]
    handler: Handler | None
    available: bool = True
    unavailable_reason: str | None = None
    requires_approval: bool = False

    def json_schema(self) -> dict:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return schema

    def openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.json_schema()},
        }

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "requires_approval": self.requires_approval,
            "parameters": self.json_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Outil déjà enregistré : {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def tool(self, name: str, description: str, category: Category, args_model: type[ToolArgs] = NoArgs):
        def deco(fn: Handler) -> Handler:
            self.register(ToolSpec(name, description, category, args_model, fn))
            return fn

        return deco

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def for_llm(self) -> list[ToolSpec]:
        """Outils proposés au modèle : uniquement ceux réellement disponibles."""
        return [t for t in self._tools.values() if t.available]

    def execute(self, name: str, args: dict | None, tctx: ToolContext) -> ToolResult:
        t0 = time.perf_counter()
        spec = self._tools.get(name)
        if spec is None:
            result = ToolResult(name, False, error=f"Outil inconnu ou non autorisé : {name}")
        elif not spec.available:
            result = ToolResult(name, False, error=f"Outil indisponible : {spec.unavailable_reason}")
        else:
            try:
                parsed = spec.args_model.model_validate(args or {})
            except ValidationError as exc:
                result = ToolResult(name, False, error=f"Arguments invalides : {exc.errors(include_url=False)}")
            else:
                try:
                    out = spec.handler(tctx, parsed)  # type: ignore[misc]
                    result = out if isinstance(out, ToolResult) else ToolResult(name, True, data=out)
                    result.tool = name
                except (ValueError, LookupError, RuntimeError) as exc:
                    result = ToolResult(name, False, error=str(exc))
        if result.ok and result.provenance is None:
            result.provenance = tctx.ctx.provenance().model_dump(mode="json")
        self._audit(tctx, spec, name, args, result, int((time.perf_counter() - t0) * 1000))
        return result

    @staticmethod
    def _audit(tctx: ToolContext, spec: ToolSpec | None, name: str, args, result: ToolResult, ms: int) -> None:
        with tctx.engine.begin() as conn:
            conn.execute(
                insert(s.tool_audit).values(
                    career_id=tctx.ctx.career_id,
                    tool=name,
                    category=spec.category if spec else "inconnu",
                    args=args,
                    ok=result.ok,
                    error=result.error,
                    created_at=datetime.now(UTC),
                    duration_ms=ms,
                )
            )
