from swarm.llm.base import LLMProvider

try:
    import google.generativeai as genai

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> None:
        if not _GENAI_AVAILABLE:
            raise ImportError(
                "google-generativeai is not installed. "
                "Install with: pip install -e '.[gemini]'"
            )
        if not api_key:
            raise ValueError(
                "Gemini API key required. Set llm.gemini.api_key in config "
                "or pass api_key directly."
            )
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        response = self._model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
            ),
        )
        return response.text

    @property
    def model(self) -> str:
        return self._model_name
