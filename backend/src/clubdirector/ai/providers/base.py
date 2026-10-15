"""Interface commune des fournisseurs IA.

Chaque fournisseur garde son historique NATIF pendant une boucle d'outils (ajout seulement),
ce qui évite les conversions avec perte (blocs tool_use/thinking chez Anthropic, tool_calls
chez les API compatibles OpenAI).
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    pass


# Message d'état pour l'entraîneur pendant une demande (ex. relance de l'IA locale figée). Le service
# le diffuse dans le flux de la réponse (`{"type": "status"}`), hors du texte du contact.
status_sink: ContextVar[Callable[[str], None] | None] = ContextVar("status_sink", default=None)


def notify_status(text: str) -> None:
    sink = status_sink.get()
    if sink is not None:
        sink(text)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str | None = None


@dataclass
class StepResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


class ProviderSession(Protocol):
    def step(self) -> StepResult: ...

    def add_tool_results(self, results: list[tuple[ToolCall, str, bool]]) -> None:
        """(appel, contenu JSON, is_error) — tous les résultats d'un tour en un seul message."""


class IAIProvider(Protocol):
    name: str
    model: str
    tier: int
    input_cost_per_mtok: float
    output_cost_per_mtok: float

    def start(self, system: str, history: list[dict], tools: list[dict]) -> ProviderSession:
        """`history` : [{role: user|assistant, content: str}] ; `tools` : schémas JSON neutres
        {name, description, parameters}."""

    def ping(self) -> str: ...
