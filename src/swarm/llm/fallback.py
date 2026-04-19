from swarm.llm.base import LLMProvider


class FallbackProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def complete(self, prompt: str) -> str:
        try:
            return self._primary.complete(prompt)
        except (RuntimeError, ConnectionError):
            return self._fallback.complete(prompt)

    @property
    def model(self) -> str:
        return f"{self._primary.model} -> {self._fallback.model}"
