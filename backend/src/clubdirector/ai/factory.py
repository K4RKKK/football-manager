"""Construction des fournisseurs à partir de la configuration."""

from __future__ import annotations

import logging

from clubdirector.ai.providers.base import IAIProvider, ProviderError
from clubdirector.ai.providers.openai_compat import OpenAICompatProvider
from clubdirector.config import AIProviderConfig, Settings
from clubdirector.security.secrets import get_secret

log = logging.getLogger(__name__)


def build_provider(cfg: AIProviderConfig) -> IAIProvider:
    key = get_secret(cfg.api_key_ref)
    if cfg.kind == "anthropic":
        from clubdirector.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(cfg.name, cfg.model, key, tier=cfg.tier, input_cost_per_mtok=cfg.input_cost_per_mtok,
                                 output_cost_per_mtok=cfg.output_cost_per_mtok, timeout_s=cfg.timeout_s)
    return OpenAICompatProvider(cfg.name, cfg.base_url, cfg.model, api_key=key, tier=cfg.tier,
                                input_cost_per_mtok=cfg.input_cost_per_mtok,
                                output_cost_per_mtok=cfg.output_cost_per_mtok, timeout_s=cfg.timeout_s)


def build_providers(settings: Settings) -> tuple[list[IAIProvider], list[str]]:
    providers, errors = [], []
    for cfg in settings.ai.providers:
        try:
            providers.append(build_provider(cfg))
        except ProviderError as exc:
            errors.append(f"{cfg.name} : {exc}")
            log.warning("Fournisseur %s ignoré : %s", cfg.name, exc)
    return providers, errors
