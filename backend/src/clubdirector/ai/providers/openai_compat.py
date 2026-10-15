"""Fournisseur compatible OpenAI (/v1/chat/completions).

Couvre : llama.cpp `llama-server` (lancer avec `--jinja` pour les appels d'outils),
Ollama (`http://127.0.0.1:11434/v1`), LM Studio, OpenRouter, et tout service compatible.

Rapidité (mesurée en mode jeu, Gemma 4 26B-A4B, session 3) :
- `thinking` : la réflexion préalable du modèle coûte 1 200 à 1 500 tokens (40-54 s) ; elle est coupée
  par défaut (`chat_template_kwargs.enable_thinking`) et réservée aux analyses demandées ;
- `step_stream` : la réponse s'affiche au fil de l'écriture ;
- `warm` : pré-calcul du prompt (système + outils + dossier) que llama-server garde en cache.
"""

from __future__ import annotations

import json
from collections.abc import Callable
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
        # None : réglage du serveur ; True / False : réflexion du modèle activée ou coupée (llama.cpp).
        self.thinking: bool | None = None

    def _body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.p.model, "messages": self.messages, "temperature": 0.3}
        if self.tools:
            body["tools"] = self.tools
            body["tool_choice"] = "auto"
        if self.thinking is not None:
            body["chat_template_kwargs"] = {"enable_thinking": self.thinking}
        return body

    def step(self) -> StepResult:
        data = self.p._post("/chat/completions", self._body())
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

    def step_stream(self, on_text: Callable[[str], None]) -> StepResult:
        """Comme `step`, mais chaque morceau de texte est transmis dès qu'il arrive."""
        body = self._body() | {"stream": True, "stream_options": {"include_usage": True}}
        text, calls, finish, usage, model = [], {}, None, {}, None
        try:
            with self.p.client.stream("POST", self.p.base_url + "/chat/completions", json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    raise ProviderError(f"{self.p.name} a répondu {r.status_code} : {r.text[:300]}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage") or usage
                    model = chunk.get("model") or model
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text.append(delta["content"])
                            on_text(delta["content"])
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", len(calls)), {"id": None, "name": "", "arguments": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.p.name} injoignable ({self.p.base_url}) : {type(exc).__name__}") from exc
        tool_calls, raw_calls = [], []
        for i, slot in sorted(calls.items()):
            call_id = slot["id"] or f"call_{i}"
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": slot["arguments"]}
            tool_calls.append(ToolCall(call_id, slot["name"], args if isinstance(args, dict) else {}, slot["arguments"]))
            raw_calls.append({"id": call_id, "type": "function",
                              "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"}})
        content = "".join(text)
        assistant: dict[str, Any] = {"role": "assistant", "content": content}
        if raw_calls:
            assistant["tool_calls"] = raw_calls
        self.messages.append(assistant)
        return StepResult(text=content, tool_calls=tool_calls, stop_reason=finish,
                          input_tokens=int(usage.get("prompt_tokens") or 0),
                          output_tokens=int(usage.get("completion_tokens") or 0), model=model)

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

    def warm(self, system: str, history: list[dict], tools: list[dict], *, thinking: bool | None = False) -> None:
        """Fait calculer le début du prompt par le serveur (1 token généré) : il le garde en cache."""
        session = OpenAICompatSession(self, system, history, tools)
        session.thinking = thinking
        self._post("/chat/completions", session._body() | {"max_tokens": 1})

    def ping(self) -> str:
        try:
            r = self.client.get(self.base_url + "/models")
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} injoignable ({self.base_url}) : {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} a répondu {r.status_code}")
        models = [m.get("id") for m in (r.json().get("data") or [])]
        return f"OK — modèles disponibles : {', '.join(filter(None, models))[:300] or 'non listés'}"
