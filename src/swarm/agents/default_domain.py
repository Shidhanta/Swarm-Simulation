import numpy as np

from swarm.agents.base import AgentPersona
from swarm.agents.communication import ConversationResult
from swarm.agents.domain import DomainSpec
from swarm.agents.state import AgentState
from swarm.graph.base import GraphBackend
from swarm.graph.similarity import DomainWeighting


class DefaultWeighting(DomainWeighting):
    """Config-driven similarity collapse."""

    def __init__(self, weights: dict[str, float] | None = None):
        self._weights = weights or {"ppr": 0.5, "adamic_adar": 0.2, "causal_walk": 0.3}

    def collapse(self, scores: dict[str, float]) -> tuple[float, dict[str, float]]:
        total = 0.0
        used = {}
        for key, weight in self._weights.items():
            if key in scores:
                total += weight * scores[key]
                used[key] = weight
        return total, used


class DefaultDomainSpec(DomainSpec):
    """Config-driven domain — no subclassing needed for standard experiments."""

    def __init__(self, config: dict):
        self._config = config
        self._dimensions = config.get("belief_dimensions", ["opinion"])
        self._confidence = config.get("confidence_bound", 0.3)
        self._stubbornness = config.get("stubbornness", 0.3)
        self._mu = config.get("convergence_rate", 0.3)
        self._interaction_mode = config.get("interaction_mode", "deffuant")
        self._similarity_weights = config.get("similarity_weights", None)
        self._groups = config.get("groups", None)
        self._group_queue: list[dict] = []
        self._rng = np.random.default_rng(config.get("seed", 42))

    @property
    def name(self) -> str:
        return self._config.get("name", "default")

    def vector_dimensions(self) -> list[str]:
        return self._dimensions

    def initial_state(self, persona: AgentPersona, graph: GraphBackend) -> AgentState:
        if self._groups:
            return self._group_initial_state(persona)
        return self._distribution_initial_state(persona)

    def _group_initial_state(self, persona: AgentPersona) -> AgentState:
        D = len(self._dimensions)
        if not self._group_queue:
            for group in self._groups:
                count = group.get("count", 1)
                for _ in range(count):
                    self._group_queue.append(group)
            self._rng.shuffle(self._group_queue)

        group = self._group_queue.pop(0)
        low = group.get("range", [0.0, 1.0])[0]
        high = group.get("range", [0.0, 1.0])[1]
        stubbornness = group.get("stubbornness", self._stubbornness)
        activity = group.get("activity_rate", 0.5)
        vector = self._rng.uniform(low, high, size=D).tolist()

        if isinstance(activity, dict):
            activity = float(self._rng.uniform(activity.get("min", 0.3), activity.get("max", 0.8)))

        return AgentState(
            entity_id=persona.entity_id,
            vector=vector,
            initial_vector=vector.copy(),
            stubbornness=stubbornness,
            activity_rate=float(activity),
            properties={"group": group.get("name", "unknown")},
        )

    def _distribution_initial_state(self, persona: AgentPersona) -> AgentState:
        D = len(self._dimensions)
        init_cfg = self._config.get("initial_beliefs", {})
        distribution = init_cfg.get("distribution", "uniform")
        low = init_cfg.get("range", [0.0, 1.0])[0]
        high = init_cfg.get("range", [0.0, 1.0])[1]

        if distribution == "uniform":
            vector = self._rng.uniform(low, high, size=D).tolist()
        elif distribution == "normal":
            mean = init_cfg.get("mean", 0.5)
            std = init_cfg.get("std", 0.15)
            vector = np.clip(self._rng.normal(mean, std, size=D), low, high).tolist()
        elif distribution == "bimodal":
            if self._rng.random() < 0.5:
                vector = self._rng.uniform(low, low + (high - low) * 0.3, size=D).tolist()
            else:
                vector = self._rng.uniform(high - (high - low) * 0.3, high, size=D).tolist()
        else:
            vector = self._rng.uniform(low, high, size=D).tolist()

        activity_cfg = self._config.get("activity_rate", {})
        if isinstance(activity_cfg, dict):
            activity = float(self._rng.uniform(
                activity_cfg.get("min", 0.3),
                activity_cfg.get("max", 0.8),
            ))
        else:
            activity = float(activity_cfg)

        return AgentState(
            entity_id=persona.entity_id,
            vector=vector,
            initial_vector=vector.copy(),
            stubbornness=self._stubbornness,
            activity_rate=activity,
        )

    def confidence_bound(self) -> float:
        return self._confidence

    def post_interaction_update(
        self,
        agent_state: AgentState,
        other_state: AgentState,
        conversation: ConversationResult,
    ) -> None:
        if self._interaction_mode == "deffuant":
            self._deffuant_update(agent_state, other_state)
        elif self._interaction_mode == "mean_field":
            self._mean_field_update(agent_state, other_state)
        elif self._interaction_mode == "degroot":
            self._degroot_update(agent_state, other_state)
        elif self._interaction_mode == "repulsive":
            self._repulsive_update(agent_state, other_state)

    def weighting(self) -> DomainWeighting:
        return DefaultWeighting(self._similarity_weights)

    def _deffuant_update(self, agent: AgentState, other: AgentState) -> None:
        """Standard Deffuant: move toward other by mu if within confidence bound."""
        a = np.array(agent.vector)
        b = np.array(other.vector)
        direction = b - a
        influenced = a + self._mu * direction
        anchored = agent.apply_anchoring(influenced.tolist())
        agent.update_vector(anchored)

    def _mean_field_update(self, agent: AgentState, other: AgentState) -> None:
        """Move toward other's position (no distance weighting)."""
        a = np.array(agent.vector)
        b = np.array(other.vector)
        influenced = a + self._mu * (b - a)
        anchored = agent.apply_anchoring(influenced.tolist())
        agent.update_vector(anchored)

    def _degroot_update(self, agent: AgentState, other: AgentState) -> None:
        """DeGroot: simple weighted average."""
        a = np.array(agent.vector)
        b = np.array(other.vector)
        weight = 0.5
        influenced = weight * a + (1 - weight) * b
        anchored = agent.apply_anchoring(influenced.tolist())
        agent.update_vector(anchored)

    def _repulsive_update(self, agent: AgentState, other: AgentState) -> None:
        """Repulsive bounded confidence: if too far apart, push AWAY (backfire effect)."""
        a = np.array(agent.vector)
        b = np.array(other.vector)
        distance = agent.distance(other)
        if distance < self._confidence:
            influenced = a + self._mu * (b - a)
        else:
            repulsion_strength = self._mu * 0.5
            influenced = a - repulsion_strength * (b - a) / max(distance, 1e-10)
            influenced = np.clip(influenced, 0.0, 1.0)
        anchored = agent.apply_anchoring(influenced.tolist())
        agent.update_vector(anchored)
