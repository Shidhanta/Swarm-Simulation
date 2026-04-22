import random

from swarm.agents.state import AgentState
from swarm.graph.base import GraphBackend, utc_now
from swarm.simulation.hashing import event_random, event_random_pair


class TopologyManager:
    """Manages the agent interaction network with adaptive rewiring."""

    def __init__(
        self,
        graph: GraphBackend,
        rewire_prob: float = 0.1,
        rewire_threshold: float | None = None,
        edge_type: str = "COMMUNICATES_WITH",
        seed: int = 42,
    ):
        self._graph = graph
        self._rewire_prob = rewire_prob
        self._rewire_threshold = rewire_threshold
        self._edge_type = edge_type
        self._seed = seed
        self._init_rng = random.Random(seed)
        self._tick = 0

    def set_tick(self, tick: int) -> None:
        self._tick = tick

    def initialize_small_world(
        self, agent_ids: list[str], k: int = 4, p: float = 0.1
    ) -> None:
        """Create Watts-Strogatz-style small-world topology among agents."""
        n = len(agent_ids)
        if n < k + 1:
            for i in range(n):
                for j in range(i + 1, n):
                    self._graph.add_relationship(
                        agent_ids[i], agent_ids[j], self._edge_type
                    )
            return

        for i in range(n):
            for offset in range(1, k // 2 + 1):
                j = (i + offset) % n
                self._graph.add_relationship(
                    agent_ids[i], agent_ids[j], self._edge_type
                )

        for i in range(n):
            for offset in range(1, k // 2 + 1):
                if self._init_rng.random() < p:
                    j = (i + offset) % n
                    self._graph.expire_relationship(
                        agent_ids[i], agent_ids[j], self._edge_type
                    )
                    candidates = [
                        aid for aid in agent_ids
                        if aid != agent_ids[i] and aid != agent_ids[j]
                    ]
                    if candidates:
                        new_target = self._init_rng.choice(candidates)
                        self._graph.add_relationship(
                            agent_ids[i], new_target, self._edge_type
                        )

    def maybe_rewire(
        self,
        agent_a_id: str,
        agent_b_id: str,
        states: dict[str, AgentState],
        confidence_bound: float,
    ) -> bool:
        """After interaction, possibly rewire if agents are too dissimilar."""
        threshold = self._rewire_threshold if self._rewire_threshold is not None else confidence_bound
        state_a = states[agent_a_id]
        state_b = states[agent_b_id]
        distance = state_a.distance(state_b)

        if distance <= threshold:
            return False

        r = event_random_pair(self._seed, self._tick, "rewire", agent_a_id, agent_b_id)
        if r > self._rewire_prob:
            return False

        self._graph.expire_relationship(agent_a_id, agent_b_id, self._edge_type)

        candidates = [
            aid for aid, s in states.items()
            if aid != agent_a_id
            and aid != agent_b_id
            and state_a.distance(s) < threshold
        ]
        if candidates:
            pick_r = event_random_pair(self._seed, self._tick, "rewire_target", agent_a_id, agent_b_id)
            idx = int(pick_r * len(candidates))
            idx = min(idx, len(candidates) - 1)
            new_partner = candidates[idx]
            self._graph.add_relationship(
                agent_a_id,
                new_partner,
                self._edge_type,
                properties={"formed_reason": "homophily_rewiring"},
            )

        return True

    def get_communication_partners(self, agent_id: str) -> list[str]:
        """Get all agents this agent can currently communicate with."""
        rels = self._graph.get_relationships(
            agent_id, direction="both", rel_type=self._edge_type
        )
        partners = set()
        for rel in rels:
            if rel.valid_to is not None:
                continue
            if rel.source_id == agent_id:
                partners.add(rel.target_id)
            else:
                partners.add(rel.source_id)
        return list(partners)
