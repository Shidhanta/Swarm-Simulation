from datetime import datetime

from pydantic import BaseModel, Field

from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.toolkits import FunctionTool
from camel.types import ModelPlatformType

from swarm.agents.base import AgentPersona, persona_to_system_message
from swarm.agents.toolkit import KnowledgeGraphToolkit
from swarm.graph.base import GraphBackend, utc_now


PLATFORM_MAP = {
    "ollama": ModelPlatformType.OLLAMA,
    "gemini": ModelPlatformType.GEMINI,
}


class ConversationTurn(BaseModel):
    speaker: str
    content: str


class ConversationResult(BaseModel):
    agent_a: str
    agent_b: str
    topic: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)


class SwarmAgent:
    """Wraps a CAMEL ChatAgent with our persona and graph tools."""

    def __init__(
        self,
        persona: AgentPersona,
        graph: GraphBackend,
        llm_config: dict,
        enable_tools: bool = False,
    ):
        self.persona = persona
        self._graph = graph
        tools = None
        if enable_tools:
            toolkit = KnowledgeGraphToolkit(graph)
            tools = [FunctionTool(fn) for fn in toolkit.get_tools()]
        platform = PLATFORM_MAP[llm_config["provider"]]
        model = ModelFactory.create(
            model_platform=platform,
            model_type=llm_config["model"],
            url=llm_config.get("base_url", "http://localhost:11434/v1"),
        )
        self._agent = ChatAgent(
            system_message=persona_to_system_message(persona),
            model=model,
            tools=tools,
        )

    def step(self, message: str) -> str:
        response = self._agent.step(message)
        return response.msg.content

    def reset(self) -> None:
        self._agent.reset()


def run_conversation(
    agent_a: SwarmAgent,
    agent_b: SwarmAgent,
    topic: str,
    max_turns: int = 6,
) -> ConversationResult:
    """Run a conversation between two SwarmAgents on a topic."""
    result = ConversationResult(
        agent_a=agent_a.persona.name,
        agent_b=agent_b.persona.name,
        topic=topic,
    )
    message = f"Let's discuss: {topic}"
    for i in range(max_turns):
        if i % 2 == 0:
            response = agent_a.step(message)
            result.turns.append(
                ConversationTurn(speaker=agent_a.persona.name, content=response)
            )
        else:
            response = agent_b.step(message)
            result.turns.append(
                ConversationTurn(speaker=agent_b.persona.name, content=response)
            )
        message = response
    agent_a.reset()
    agent_b.reset()
    return result
