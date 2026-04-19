from abc import ABC, abstractmethod
from collections.abc import Callable


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        pass

    def as_callable(self) -> Callable[[str], str]:
        return self.complete
