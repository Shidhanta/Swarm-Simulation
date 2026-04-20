from abc import ABC, abstractmethod

from swarm.agents.base import AgentPersona
from swarm.agents.communication import ConversationResult
from swarm.agents.state import AgentState
from swarm.graph.base import GraphBackend
from swarm.graph.similarity import DomainWeighting


class DomainSpec(ABC):
    """Defines how a simulation domain shapes agent state and behavior."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def vector_dimensions(self) -> list[str]:
        """Names of belief vector dimensions for this domain."""
        pass

    @abstractmethod
    def initial_state(self, persona: AgentPersona, graph: GraphBackend) -> AgentState:
        """Derive initial agent state from persona and graph position."""
        pass

    @abstractmethod
    def confidence_bound(self) -> float:
        """Max distance in belief space for agents to interact."""
        pass

    @abstractmethod
    def post_interaction_update(
        self,
        agent_state: AgentState,
        other_state: AgentState,
        conversation: ConversationResult,
    ) -> None:
        """Update agent_state after a conversation with other. Mutates in place."""
        pass

    @abstractmethod
    def weighting(self) -> DomainWeighting:
        """Similarity collapse strategy for this domain."""
        pass
