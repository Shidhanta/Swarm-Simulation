"""Intervention + counterfactual replay system.

Allows rewinding to a snapshot, applying interventions (remove agent,
modify belief, add/remove relationship), replaying, and comparing
N trajectories against a baseline.
"""

import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from swarm.simulation.runner import ExperimentRunner


class Intervention(BaseModel):
    """A single change to apply at a rewind point."""
    type: str
    target: str = ""
    source: str = ""
    vector: list[float] = Field(default_factory=list)
    key: str = ""
    value: float = 0.0


class Scenario(BaseModel):
    """One counterfactual: rewind point + interventions."""
    name: str
    rewind_to_tick: int
    interventions: list[Intervention] = Field(default_factory=list)


class TrajectoryResult(BaseModel):
    """Metrics from one trajectory (baseline or scenario)."""
    name: str
    metrics: dict[str, list[float]] = Field(default_factory=dict)
    ticks_completed: int = 0


class DivergencePoint(BaseModel):
    """Where a scenario diverges from baseline."""
    scenario: str
    metric: str
    tick: int
    baseline_value: float
    scenario_value: float
    delta: float


class ComparisonResult(BaseModel):
    """Side-by-side comparison of all trajectories."""

    model_config = {"arbitrary_types_allowed": True}

    baseline: TrajectoryResult
    scenarios: list[TrajectoryResult] = Field(default_factory=list)
    divergence_points: list[DivergencePoint] = Field(default_factory=list)


class CounterfactualRunner:
    """Rewinds to a snapshot, applies interventions, replays, compares."""

    def __init__(self, config: dict):
        self._config = config
        self._cf_config = config["counterfactual"]
        self._source_log = self._cf_config["source_log"]
        self._source_experiment = self._cf_config["source_experiment"]
        self._scenarios = [
            Scenario(**s) for s in self._cf_config.get("scenarios", [])
        ]
        self._divergence_threshold = self._cf_config.get("divergence_threshold", 0.05)

    def run(self) -> ComparisonResult:
        """Run baseline + all scenarios, compare trajectories."""
        baseline = self._run_baseline()
        scenario_results = []
        for scenario in self._scenarios:
            result = self._run_scenario(scenario)
            scenario_results.append(result)

        divergences = self._detect_divergences(baseline, scenario_results)

        comparison = ComparisonResult(
            baseline=baseline,
            scenarios=scenario_results,
            divergence_points=divergences,
        )
        self._print_comparison(comparison)
        return comparison

    def _run_baseline(self) -> TrajectoryResult:
        """Load baseline metrics from the source log."""
        log_path = Path(self._source_log)
        if not log_path.exists():
            print(f"  Source log not found: {self._source_log}")
            print(f"  Running baseline experiment first...")
            runner = ExperimentRunner(self._source_experiment)
            runner.run()

        metrics: dict[str, list[float]] = {}
        ticks = 0
        with open(log_path) as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("type") in ("header", "footer"):
                    continue
                if "tick" not in record:
                    continue
                ticks = record["tick"] + 1
                vectors = list(record["belief_vectors"].values())
                arr = np.array(vectors)
                metrics.setdefault("mean_belief", []).append(float(arr.mean()))
                metrics.setdefault("variance", []).append(float(np.var(arr)))
                metrics.setdefault("num_pairs", []).append(float(record["pairs_formed"]))
                metrics.setdefault("num_rewires", []).append(float(record["rewires"]))

        return TrajectoryResult(name="baseline", metrics=metrics, ticks_completed=ticks)

    def _run_scenario(self, scenario: Scenario) -> TrajectoryResult:
        """Replay from a snapshot with interventions applied."""
        print(f"\n  Running scenario: {scenario.name} (rewind to tick {scenario.rewind_to_tick})")

        runner = ExperimentRunner(self._source_experiment)
        runner._config["logging"] = {"level": "silent"}
        runner._setup_graph()
        runner._setup_domain()
        runner._seed_graph()
        runner._setup_society()
        runner._setup_engine()

        rewind_tick = scenario.rewind_to_tick
        print(f"  Fast-forwarding to tick {rewind_tick}...")
        for tick in range(rewind_tick):
            tick_result = runner._society.tick(tick_number=tick)
            states = runner._society.get_all_states()
            vectors = np.array([s.vector for s in states.values()])
            print(f"    tick {tick:3d} | pairs={len(tick_result.pairs_formed)} "
                  f"variance={np.var(vectors):.4f} (fast-forward)")

        self._apply_interventions(runner, scenario.interventions)

        max_ticks = self._config.get("simulation", {}).get(
            "max_ticks",
            runner._config.get("simulation", {}).get("max_ticks", 15),
        )
        print(f"  Replaying ticks {rewind_tick}-{max_ticks-1} with interventions...")
        metrics: dict[str, list[float]] = {}
        for tick in range(rewind_tick, max_ticks):
            tick_result = runner._society.tick(tick_number=tick)

            states = runner._society.get_all_states()
            vectors = np.array([s.vector for s in states.values()])
            mean_belief = float(vectors.mean())
            variance = float(np.var(vectors))
            n_pairs = len(tick_result.pairs_formed)
            n_rewires = len(tick_result.rewires)

            metrics.setdefault("mean_belief", []).append(mean_belief)
            metrics.setdefault("variance", []).append(variance)
            metrics.setdefault("num_pairs", []).append(float(n_pairs))
            metrics.setdefault("num_rewires", []).append(float(n_rewires))

            print(f"    tick {tick:3d} | pairs={n_pairs} rewires={n_rewires} "
                  f"mean={mean_belief:.4f} variance={variance:.4f}")

        return TrajectoryResult(
            name=scenario.name,
            metrics=metrics,
            ticks_completed=max_ticks - rewind_tick,
        )

    def _apply_interventions(self, runner: ExperimentRunner, interventions: list[Intervention]) -> None:
        """Apply interventions to the society state."""
        society = runner._society
        graph = runner._graph

        for iv in interventions:
            if iv.type == "remove_agent":
                agent_id = self._resolve_agent_name(society, iv.target)
                if agent_id and agent_id in society._agents:
                    del society._agents[agent_id]
                    del society._states[agent_id]
                    del society._personas[agent_id]
                    graph.remove_entity(agent_id)
                    print(f"    Applied: removed agent '{iv.target}'")

            elif iv.type == "modify_belief":
                agent_id = self._resolve_agent_name(society, iv.target)
                if agent_id and agent_id in society._states:
                    society._states[agent_id].update_vector(iv.vector)
                    print(f"    Applied: modified belief of '{iv.target}' to {iv.vector}")

            elif iv.type == "modify_property":
                agent_id = self._resolve_agent_name(society, iv.target)
                if agent_id and agent_id in society._states:
                    if iv.key == "stubbornness":
                        society._states[agent_id].stubbornness = iv.value
                    elif iv.key == "activity_rate":
                        society._states[agent_id].activity_rate = iv.value
                    else:
                        society._states[agent_id].properties[iv.key] = iv.value
                    print(f"    Applied: set '{iv.target}'.{iv.key} = {iv.value}")

            elif iv.type == "add_relationship":
                source_id = self._resolve_agent_name(society, iv.source)
                target_id = self._resolve_agent_name(society, iv.target)
                if source_id and target_id:
                    graph.add_relationship(
                        source_id, target_id, "COMMUNICATES_WITH",
                        properties={"formed_reason": "intervention"},
                    )
                    print(f"    Applied: added edge '{iv.source}' -> '{iv.target}'")

            elif iv.type == "remove_relationship":
                source_id = self._resolve_agent_name(society, iv.source)
                target_id = self._resolve_agent_name(society, iv.target)
                if source_id and target_id:
                    try:
                        graph.expire_relationship(source_id, target_id, "COMMUNICATES_WITH")
                        print(f"    Applied: removed edge '{iv.source}' -> '{iv.target}'")
                    except ValueError:
                        print(f"    Skipped: no edge '{iv.source}' -> '{iv.target}'")

    def _resolve_agent_name(self, society, name: str) -> str | None:
        """Resolve agent name (e.g. 'Agent_3') to entity ID."""
        for agent_id, persona in society._personas.items():
            if persona.name == name:
                return agent_id
        for agent_id in society._agents:
            if agent_id.startswith(name):
                return agent_id
        return None

    def _detect_divergences(
        self, baseline: TrajectoryResult, scenarios: list[TrajectoryResult]
    ) -> list[DivergencePoint]:
        """Find where each scenario diverges from baseline."""
        divergences = []
        for scenario in scenarios:
            for metric_name in baseline.metrics:
                if metric_name not in scenario.metrics:
                    continue
                base_vals = baseline.metrics[metric_name]
                scen_vals = scenario.metrics[metric_name]
                offset = len(base_vals) - len(scen_vals)

                for i, scen_val in enumerate(scen_vals):
                    base_idx = offset + i
                    if base_idx < 0 or base_idx >= len(base_vals):
                        continue
                    base_val = base_vals[base_idx]
                    delta = abs(scen_val - base_val)
                    if delta > self._divergence_threshold:
                        divergences.append(DivergencePoint(
                            scenario=scenario.name,
                            metric=metric_name,
                            tick=offset + i,
                            baseline_value=base_val,
                            scenario_value=scen_val,
                            delta=delta,
                        ))
                        break

        return divergences

    def _print_comparison(self, comparison: ComparisonResult) -> None:
        """Print human-readable comparison."""
        print(f"\n{'='*60}")
        print(f"COUNTERFACTUAL COMPARISON")
        print(f"{'='*60}")
        print(f"  Baseline ticks: {comparison.baseline.ticks_completed}")
        print(f"  Scenarios: {len(comparison.scenarios)}")

        for metric_name in ["mean_belief", "variance"]:
            base_vals = comparison.baseline.metrics.get(metric_name, [])
            if not base_vals:
                continue
            print(f"\n  {metric_name}:")
            header = f"  {'Tick':>5} | {'Baseline':>10}"
            for s in comparison.scenarios:
                header += f" | {s.name[:15]:>15}"
            print(header)
            print(f"  {'-'*5}-+-{'-'*10}" + "".join(f"-+-{'-'*15}" for _ in comparison.scenarios))

            max_ticks = max(len(base_vals), max((len(s.metrics.get(metric_name, [])) for s in comparison.scenarios), default=0))
            for t in range(min(max_ticks, len(base_vals))):
                row = f"  {t:5d} | {base_vals[t]:10.4f}"
                for s in comparison.scenarios:
                    s_vals = s.metrics.get(metric_name, [])
                    offset = len(base_vals) - len(s_vals)
                    s_idx = t - offset
                    if 0 <= s_idx < len(s_vals):
                        row += f" | {s_vals[s_idx]:15.4f}"
                    else:
                        row += f" | {'---':>15}"
                print(row)

        if comparison.divergence_points:
            print(f"\n  Divergence points:")
            for dp in comparison.divergence_points:
                direction = "higher" if dp.scenario_value > dp.baseline_value else "lower"
                print(f"    {dp.scenario}: {dp.metric} diverges at tick {dp.tick} "
                      f"(baseline={dp.baseline_value:.4f}, scenario={dp.scenario_value:.4f}, {direction})")
        else:
            print(f"\n  No significant divergences detected (threshold={self._divergence_threshold})")
