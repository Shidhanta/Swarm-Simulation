import heapq

from swarm.agents.state import AgentState
from swarm.simulation.hashing import event_random, event_random_pair


class InteractionScheduler:
    """Activity-driven scheduling with event-driven overlay."""

    def __init__(self, seed: int = 42):
        self._seed = seed
        self._pending: list[tuple[float, int, str]] = []
        self._event_counter = 0
        self._tick = 0

    def set_tick(self, tick: int) -> None:
        self._tick = tick

    def get_active_agents(
        self, states: dict[str, AgentState], dt: float = 1.0
    ) -> list[str]:
        """Select agents that activate this tick based on activity rates."""
        active = []
        for agent_id, state in states.items():
            r = event_random(self._seed, self._tick, "activation", agent_id)
            if r < state.activity_rate * dt:
                active.append(agent_id)
        return active

    def notify_change(self, changed_agent_id: str, neighbor_ids: list[str], priority: float = 1.0) -> None:
        """When an agent's state changes, schedule its neighbors for activation."""
        for neighbor_id in neighbor_ids:
            self._event_counter += 1
            heapq.heappush(
                self._pending, (-priority, self._event_counter, neighbor_id)
            )

    def get_event_driven_agents(self, max_batch: int = 5) -> list[str]:
        """Return highest-priority agents from the event queue."""
        batch = []
        seen: set[str] = set()
        while self._pending and len(batch) < max_batch:
            _, _, agent_id = heapq.heappop(self._pending)
            if agent_id not in seen:
                batch.append(agent_id)
                seen.add(agent_id)
        return batch

    def select_pairs(
        self,
        active_agents: list[str],
        get_partners_fn,
        states: dict[str, AgentState],
        confidence_bound: float,
    ) -> list[tuple[str, str]]:
        """From active agents, form conversation pairs with valid partners."""
        pairs = []
        used: set[str] = set()

        for agent_id in active_agents:
            if agent_id in used:
                continue
            partners = get_partners_fn(agent_id)
            valid = [
                p for p in partners
                if p not in used
                and states[agent_id].distance(states[p]) < confidence_bound
            ]
            if not valid:
                continue
            weights = [
                1.0 / (1.0 + states[agent_id].distance(states[p]))
                for p in valid
            ]
            total_w = sum(weights)
            pick = event_random(self._seed, self._tick, "pair_selection", agent_id) * total_w
            cumulative = 0.0
            partner = valid[0]
            for p, w in zip(valid, weights):
                cumulative += w
                if cumulative >= pick:
                    partner = p
                    break
            pairs.append((agent_id, partner))
            used.add(agent_id)
            used.add(partner)

        return pairs
