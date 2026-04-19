from typing import Any

from swarm.llm.base import LLMProvider
from swarm.llm.fallback import FallbackProvider
from swarm.llm.ollama_provider import OllamaProvider


def _build_provider(config: dict[str, Any]) -> LLMProvider:
    provider_type = config.get("provider", "ollama")

    if provider_type == "ollama":
        return OllamaProvider(
            model=config.get("model", "llama3"),
            base_url=config.get("base_url", "http://localhost:11434"),
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 2048),
        )
    elif provider_type == "gemini":
        from swarm.llm.gemini_provider import GeminiProvider

        return GeminiProvider(
            model=config.get("model", "gemini-2.0-flash"),
            api_key=config.get("api_key", ""),
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 2048),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")


def create_provider(config: dict[str, Any]) -> LLMProvider:
    primary = _build_provider(config)

    fallback_config = config.get("fallback")
    if fallback_config:
        fallback = _build_provider(fallback_config)
        return FallbackProvider(primary, fallback)

    return primary
