"""Agent layer — persona generation, communication, and society management."""

from swarm.agents.base import AgentPersona, PersonaGenerator, persona_to_system_message
from swarm.agents.communication import (
    ConversationResult,
    ConversationTurn,
    SwarmAgent,
    run_conversation,
)
from swarm.agents.domain import DomainSpec
from swarm.agents.persona import GraphPersonaGenerator
from swarm.agents.scheduler import InteractionScheduler
from swarm.agents.society import AgentSociety, TickResult
from swarm.agents.state import AgentState
from swarm.agents.toolkit import KnowledgeGraphToolkit
from swarm.agents.topology import TopologyManager

__all__ = [
    "AgentPersona",
    "AgentSociety",
    "AgentState",
    "ConversationResult",
    "ConversationTurn",
    "DomainSpec",
    "GraphPersonaGenerator",
    "InteractionScheduler",
    "KnowledgeGraphToolkit",
    "PersonaGenerator",
    "SwarmAgent",
    "TickResult",
    "TopologyManager",
    "persona_to_system_message",
    "run_conversation",
]
