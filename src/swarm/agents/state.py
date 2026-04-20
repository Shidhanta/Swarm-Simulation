import numpy as np
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """Domain-agnostic runtime state for a simulation agent."""

    model_config = {"arbitrary_types_allowed": True}

    entity_id: str
    vector: list[float] = Field(default_factory=list)
    initial_vector: list[float] = Field(default_factory=list)
    stubbornness: float = 0.3
    activity_rate: float = 0.5
    properties: dict = Field(default_factory=dict)

    def distance(self, other: "AgentState") -> float:
        """Euclidean distance between belief vectors."""
        a = np.array(self.vector)
        b = np.array(other.vector)
        return float(np.linalg.norm(a - b))

    def apply_anchoring(self, influence_vector: list[float]) -> list[float]:
        """Friedkin-Johnsen: blend social influence with initial anchor."""
        inf = np.array(influence_vector)
        anchor = np.array(self.initial_vector)
        result = (1 - self.stubbornness) * inf + self.stubbornness * anchor
        return result.tolist()

    def update_vector(self, new_vector: list[float]) -> None:
        """Replace current belief vector."""
        self.vector = new_vector
