"""Fournisseur compatible OpenAI (/v1/chat/completions).

Couvre : llama.cpp `llama-server` (lancer avec `--jinja` pour les appels d'outils),
Ollama (`http://127.0.0.1:11434/v1`), LM Studio, OpenRouter, et tout service compatible.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from clubdirector.ai.providers.base import ProviderError, StepResult, ToolCall


class OpenAICompatSession:
    def __init__(self, provider: OpenAICompatProvider, system: str, history: list[dict], tools: list[dict]):
        self.p = provider
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *history]
        self.tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
            for t in tools
        ]

    def step(self) -> StepResult:
        body: dict[str, Any] = {"model": self.p.model, "messages": self.messages, "temperature": 0.3}
        if self.tools:
            body["tools"] = self.tools
            body["tool_choice"] = "auto"
        data = self.p._post("/chat/completions", body)
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Réponse inattendue du serveur : {str(data)[:300]}") from exc
        calls = []
        for tc in msg.get("tool_calls") or []:
            raw = tc.get("function", {}).get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                args = {"__invalid_json__": raw}
            calls.append(ToolCall(tc.get("id") or f"call_{len(calls)}", tc["function"]["name"], args, raw if isinstance(raw, str) else None))
        assistant = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            assistant["tool_calls"] = msg["tool_calls"]
        self.messages.append(assistant)
        usage = data.get("usage") or {}
        return StepResult(
            text=msg.get("content") or "",
            tool_calls=calls,
            stop_reason=choice.get("finish_reason"),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=data.get("model"),
        )

    def add_tool_results(self, results: list[tuple[ToolCall, str, bool]]) -> None:
        for call, content, _is_error in results:
            self.messages.append({"role": "tool", "tool_call_id": call.id, "content": content})


class OpenAICompatProvider:
    def __init__(self, name: str, base_url: str, model: str, *, api_key: str | None = None, tier: int = 1,
                 input_cost_per_mtok: float = 0.0, output_cost_per_mtok: float = 0.0, timeout_s: float = 120.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.tier = tier
        self.input_cost_per_mtok = input_cost_per_mtok
        self.output_cost_per_mtok = output_cost_per_mtok
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.Client(timeout=timeout_s, headers=headers, transport=transport)

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self.client.post(self.base_url + path, json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} injoignable ({self.base_url}) : {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} a répondu {r.status_code} : {r.text[:300]}")
        return r.json()

    def start(self, system: str, history: list[dict], tools: list[dict]) -> OpenAICompatSession:
        return OpenAICompatSession(self, system, history, tools)

    def ping(self) -> str:
        try:
            r = self.client.get(self.base_url + "/models")
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} injoignable ({self.base_url}) : {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} a répondu {r.status_code}")
        models = [m.get("id") for m in (r.json().get("data") or [])]
        return f"OK — modèles disponibles : {', '.join(filter(None, models))[:300] or 'non listés'}"
