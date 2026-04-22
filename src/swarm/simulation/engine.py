from datetime import datetime
from typing import Callable

from pydantic import BaseModel, Field

from swarm.agents.society import AgentSociety, TickResult
from swarm.graph.base import utc_now


class SimulationSnapshot(BaseModel):
    """State of all agents at a point in time."""
    tick: int
    timestamp: datetime = Field(default_factory=utc_now)
    states: dict[str, dict] = Field(default_factory=dict)


class SimulationConfig(BaseModel):
    """Runtime parameters for the simulation."""
    max_ticks: int = 100
    snapshot_every: int = 1
    seed: int = 42


class SimulationResult(BaseModel):
    """Final output of a completed simulation run."""

    model_config = {"arbitrary_types_allowed": True}

    ticks_completed: int
    stop_reason: str
    snapshots: list[SimulationSnapshot] = Field(default_factory=list)
    tick_results: list = Field(default_factory=list)


class SimulationEngine:
    """Time-stepped simulation loop over an AgentSociety."""

    def __init__(
        self,
        society: AgentSociety,
        config: SimulationConfig | None = None,
    ):
        self._society = society
        self._config = config or SimulationConfig()
        self._tick = 0
        self._history: list[TickResult] = []
        self._snapshots: list[SimulationSnapshot] = []
        self._stop_conditions: list[Callable[[int, TickResult], bool]] = []
        self._tick_callbacks: list[Callable[[int, TickResult], None]] = []

    def add_stop_condition(self, fn: Callable[[int, TickResult], bool]) -> None:
        """Add a predicate that stops the simulation when it returns True."""
        self._stop_conditions.append(fn)

    def add_tick_callback(self, fn: Callable[[int, TickResult], None]) -> None:
        """Add a function called after each tick (for metrics, logging, etc)."""
        self._tick_callbacks.append(fn)

    def run(self) -> SimulationResult:
        """Execute the simulation loop until completion or stop condition."""
        stop_reason = "max_ticks"

        for tick in range(self._config.max_ticks):
            self._tick = tick
            tick_result = self._society.tick(tick_number=tick)
            self._history.append(tick_result)

            if tick % self._config.snapshot_every == 0:
                snapshot = self._take_snapshot(tick)
                self._snapshots.append(snapshot)

            for callback in self._tick_callbacks:
                callback(tick, tick_result)

            for condition in self._stop_conditions:
                if condition(tick, tick_result):
                    stop_reason = f"stop_condition_at_tick_{tick}"
                    return SimulationResult(
                        ticks_completed=tick + 1,
                        stop_reason=stop_reason,
                        snapshots=self._snapshots,
                        tick_results=self._history,
                    )

        return SimulationResult(
            ticks_completed=self._config.max_ticks,
            stop_reason=stop_reason,
            snapshots=self._snapshots,
            tick_results=self._history,
        )

    def _take_snapshot(self, tick: int) -> SimulationSnapshot:
        """Capture current state of all agents."""
        states = {}
        for agent_id, state in self._society.get_all_states().items():
            states[agent_id] = {
                "vector": state.vector,
                "properties": state.properties,
            }
        return SimulationSnapshot(
            tick=tick,
            timestamp=utc_now(),
            states=states,
        )

    @property
    def current_tick(self) -> int:
        return self._tick

    @property
    def history(self) -> list[TickResult]:
        return self._history
