from ollama import Client, ResponseError

from swarm.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = Client(host=base_url)

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": self._temperature,
                    "num_predict": self._max_tokens,
                },
            )
        except ResponseError as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e
        except Exception as e:
            raise ConnectionError(
                f"Cannot reach Ollama at {self._client._client._base_url}. "
                "Is Ollama running? Install: https://ollama.com"
            ) from e
        return response["message"]["content"]

    @property
    def model(self) -> str:
        return self._model
