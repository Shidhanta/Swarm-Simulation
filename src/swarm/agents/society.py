from datetime import datetime

from swarm.agents.base import AgentPersona, persona_to_system_message
from swarm.agents.communication import ConversationResult, SwarmAgent, run_conversation
from swarm.agents.domain import DomainSpec
from swarm.agents.scheduler import InteractionScheduler
from swarm.agents.state import AgentState
from swarm.agents.topology import TopologyManager
from swarm.graph.base import GraphBackend, utc_now
from swarm.graph.similarity import SimilarityEngine


class TickResult:
    """Outcome of a single simulation tick."""

    def __init__(self):
        self.conversations: list[ConversationResult] = []
        self.active_agents: list[str] = []
        self.pairs_formed: list[tuple[str, str]] = []
        self.rewires: list[tuple[str, str, str]] = []
        self.timestamp: datetime = utc_now()


class AgentSociety:
    """Orchestrates multi-agent simulation with adaptive topology."""

    def __init__(
        self,
        graph: GraphBackend,
        domain: DomainSpec,
        similarity_engine: SimilarityEngine,
        llm_config: dict,
        topology_config: dict | None = None,
        scheduler_seed: int | None = None,
    ):
        self._graph = graph
        self._domain = domain
        self._similarity = similarity_engine
        self._llm_config = llm_config

        topo_cfg = topology_config or {}
        self._topology = TopologyManager(
            graph=graph,
            rewire_prob=topo_cfg.get("rewire_prob", 0.1),
            edge_type=topo_cfg.get("edge_type", "COMMUNICATES_WITH"),
            seed=scheduler_seed,
        )
        self._scheduler = InteractionScheduler(seed=scheduler_seed)

        self._agents: dict[str, SwarmAgent] = {}
        self._states: dict[str, AgentState] = {}
        self._personas: dict[str, AgentPersona] = {}

    def register_agent(self, persona: AgentPersona) -> None:
        """Add an agent to the society with domain-derived initial state."""
        state = self._domain.initial_state(persona, self._graph)
        agent = SwarmAgent(
            persona=persona,
            graph=self._graph,
            llm_config=self._llm_config,
        )
        self._agents[persona.entity_id] = agent
        self._states[persona.entity_id] = state
        self._personas[persona.entity_id] = persona

    def initialize_topology(self, k: int = 4, p: float = 0.1) -> None:
        """Set up initial Watts-Strogatz small-world communication network."""
        agent_ids = list(self._agents.keys())
        self._topology.initialize_small_world(agent_ids, k=k, p=p)

    def tick(self) -> TickResult:
        """Execute one simulation step."""
        result = TickResult()

        activity_agents = self._scheduler.get_active_agents(self._states)
        event_agents = self._scheduler.get_event_driven_agents()
        all_active = list(set(activity_agents + event_agents))
        result.active_agents = all_active

        pairs = self._scheduler.select_pairs(
            active_agents=all_active,
            get_partners_fn=self._topology.get_communication_partners,
            states=self._states,
            confidence_bound=self._domain.confidence_bound(),
        )
        result.pairs_formed = pairs

        for agent_a_id, agent_b_id in pairs:
            conversation = run_conversation(
                agent_a=self._agents[agent_a_id],
                agent_b=self._agents[agent_b_id],
                topic=self._generate_topic(agent_a_id, agent_b_id),
            )
            result.conversations.append(conversation)

            self._domain.post_interaction_update(
                self._states[agent_a_id],
                self._states[agent_b_id],
                conversation,
            )

            rewired = self._topology.maybe_rewire(
                agent_a_id,
                agent_b_id,
                self._states,
                self._domain.confidence_bound(),
            )
            if rewired:
                result.rewires.append((agent_a_id, agent_b_id, "dissimilar"))

            neighbors_a = self._topology.get_communication_partners(agent_a_id)
            neighbors_b = self._topology.get_communication_partners(agent_b_id)
            self._scheduler.notify_change(agent_a_id, neighbors_a)
            self._scheduler.notify_change(agent_b_id, neighbors_b)

        return result

    def get_state(self, agent_id: str) -> AgentState:
        return self._states[agent_id]

    def get_all_states(self) -> dict[str, AgentState]:
        return self._states.copy()

    def agent_count(self) -> int:
        return len(self._agents)

    def _generate_topic(self, agent_a_id: str, agent_b_id: str) -> str:
        """Generate a conversation topic from shared graph context."""
        neighbors_a = set(
            e.id for e in self._graph.get_neighbours(agent_a_id, depth=1)
        )
        neighbors_b = set(
            e.id for e in self._graph.get_neighbours(agent_b_id, depth=1)
        )
        shared = neighbors_a & neighbors_b
        if shared:
            shared_id = next(iter(shared))
            entity = self._graph.get_entity(shared_id)
            if entity:
                name = entity.properties.get("name", entity.type)
                return f"the situation regarding {name}"
        return "recent developments in our shared domain"
