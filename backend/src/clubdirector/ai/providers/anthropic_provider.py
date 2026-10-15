"""Fournisseur Anthropic (SDK officiel `anthropic`, extra optionnel).

- Niveau 2 (économique) : `claude-haiku-5-5`, effort `low`.
- Niveau 3 (avancé) : `claude-opus-5-5`, effort `medium` explicite, avec repli serveur
  `fallbacks: "default"` en cas de refus de sécurité (bêta server-side-fallback-2026-07-01).
- `tool_choice` reste `auto` (le forçage d'outil renvoie 400 sur les modèles actuels).
- L'historique de la boucle d'outils est conservé tel quel (ajout seulement), blocs de
  réflexion compris, comme l'exige l'API.
"""

from __future__ import annotations

import json
from typing import Any

from clubdirector.ai.providers.base import ProviderError, StepResult, ToolCall

FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


class AnthropicSession:
    def __init__(self, provider: AnthropicProvider, system: str, history: list[dict], tools: list[dict]):
        self.p = provider
        self.system = system
        self.messages: list[Any] = [{"role": m["role"], "content": m["content"]} for m in history]
        self.tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]

    def step(self) -> StepResult:
        import anthropic

        kwargs: dict[str, Any] = dict(
            model=self.p.model,
            max_tokens=self.p.max_tokens,
            system=self.system,
            messages=self.messages,
            output_config={"effort": self.p.effort},
        )
        if self.tools:
            kwargs["tools"] = self.tools
            kwargs["tool_choice"] = {"type": "auto"}
        try:
            if self.p.model in FALLBACK_MODELS:
                resp = self.p.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                resp = self.p.client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ProviderError("Clé API Anthropic invalide ou absente.") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Limite de débit Anthropic atteinte ; réessayez plus tard.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Erreur API Anthropic {exc.status_code} : {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("API Anthropic injoignable (réseau).") from exc

        if resp.stop_reason == "refusal":
            raise ProviderError("Le modèle a refusé cette demande (stop_reason=refusal).")
        # Historique natif : on renvoie le contenu complet (réflexion + tool_use) tel quel.
        self.messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = []
        for b in resp.content:
            if b.type == "tool_use":
                args = b.input if isinstance(b.input, dict) else json.loads(b.input)
                calls.append(ToolCall(b.id, b.name, args))
        return StepResult(
            text=text,
            tool_calls=calls,
            stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=resp.model,
        )

    def add_tool_results(self, results: list[tuple[ToolCall, str, bool]]) -> None:
        # Tous les tool_result d'un tour dans UN SEUL message utilisateur.
        self.messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": c.id, "content": content, "is_error": is_error}
                for c, content, is_error in results
            ],
        })


class AnthropicProvider:
    def __init__(self, name: str, model: str, api_key: str | None, *, tier: int = 2,
                 input_cost_per_mtok: float = 0.0, output_cost_per_mtok: float = 0.0,
                 effort: str | None = None, max_tokens: int = 16000, timeout_s: float = 120.0) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError("SDK anthropic non installé : `uv sync --extra anthropic`.") from exc
        if not api_key:
            raise ProviderError("Aucune clé API Anthropic configurée (CLUBDIRECTOR_SECRET_<REF> ou trousseau).")
        self.name = name
        self.model = model
        self.tier = tier
        self.input_cost_per_mtok = input_cost_per_mtok
        self.output_cost_per_mtok = output_cost_per_mtok
        self.effort = effort or ("low" if "haiku" in model else "medium")
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)

    def start(self, system: str, history: list[dict], tools: list[dict]) -> AnthropicSession:
        return AnthropicSession(self, system, history, tools)

    def ping(self) -> str:
        import anthropic

        try:
            m = self.client.models.retrieve(self.model)
        except anthropic.APIError as exc:
            raise ProviderError(f"Test Anthropic échoué : {exc}") from exc
        return f"OK — {m.display_name} ({m.id})"
