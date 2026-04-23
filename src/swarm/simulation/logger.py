import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from swarm.agents.society import AgentSociety, TickResult
from swarm.graph.base import utc_now


class SimulationLogger:
    """First-class logging for simulation runs. Registers as tick callback."""

    def __init__(
        self,
        society: AgentSociety,
        level: str = "summary",
        file_path: str | None = None,
    ):
        self._society = society
        self._level = level
        self._file_path = file_path
        self._file = None
        self._start_time: datetime | None = None
        self._detector = None
        self._prev_event_count = 0

        if self._file_path:
            path = Path(self._file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "w")

    def set_detector(self, detector) -> None:
        self._detector = detector

    def on_tick(self, tick: int, tick_result: TickResult) -> None:
        """Tick callback — registered on SimulationEngine."""
        if self._start_time is None:
            self._start_time = utc_now()

        if self._level == "silent":
            pass
        elif self._level == "summary":
            self._print_summary(tick, tick_result)
        elif self._level == "verbose":
            self._print_verbose(tick, tick_result)

        if self._file:
            self._write_structured(tick, tick_result)

    def on_start(self, config: dict) -> None:
        """Called before simulation begins."""
        if self._level != "silent":
            name = config.get("experiment", {}).get("name", "Unnamed")
            agents = self._society.agent_count()
            max_ticks = config.get("simulation", {}).get("max_ticks", "?")
            print(f"{'='*60}")
            print(f"  EXPERIMENT: {name}")
            print(f"  Agents: {agents} | Max ticks: {max_ticks}")
            print(f"  Started: {utc_now().strftime('%H:%M:%S UTC')}")
            print(f"{'='*60}")
            print()

        if self._file:
            agent_map = {}
            for aid, persona in self._society._personas.items():
                agent_map[aid] = persona.name
            domain = self._society._domain
            header = {
                "type": "header",
                "config": config,
                "agent_map": agent_map,
                "dimensions": domain.vector_dimensions() if domain else [],
            }
            self._file.write(json.dumps(header) + "\n")
            self._file.flush()

    def on_complete(self, ticks_completed: int, stop_reason: str) -> None:
        """Called after simulation ends."""
        if self._level != "silent":
            elapsed = (utc_now() - self._start_time).total_seconds() if self._start_time else 0
            print()
            print(f"{'='*60}")
            print(f"  COMPLETE: {ticks_completed} ticks in {elapsed:.1f}s")
            print(f"  Stop reason: {stop_reason}")
            if self._file_path:
                print(f"  Log written to: {self._file_path}")
            print(f"{'='*60}")

        if self._file:
            events = []
            if self._detector:
                events = [
                    {"event_type": e.event_type, "tick": e.tick,
                     "confidence": e.confidence, "description": e.description}
                    for e in self._detector.events
                ]
            footer = {
                "type": "footer",
                "ticks_completed": ticks_completed,
                "stop_reason": stop_reason,
                "events": events,
            }
            self._file.write(json.dumps(footer) + "\n")
            self._file.flush()
            self._file.close()
            self._file = None

    def _print_summary(self, tick: int, tick_result: TickResult) -> None:
        n_pairs = len(tick_result.pairs_formed)
        n_rewires = len(tick_result.rewires)
        states = self._society.get_all_states()
        vectors = np.array([s.vector for s in states.values()])
        variance = float(np.var(vectors)) if len(vectors) > 1 else 0.0
        print(f"  tick {tick:3d} | pairs={n_pairs} rewires={n_rewires} variance={variance:.4f}")

    def _print_verbose(self, tick: int, tick_result: TickResult) -> None:
        n_active = len(tick_result.active_agents)
        n_pairs = len(tick_result.pairs_formed)
        n_convos = len(tick_result.conversations)
        n_rewires = len(tick_result.rewires)

        states = self._society.get_all_states()
        vectors = np.array([s.vector for s in states.values()])
        mean_vec = vectors.mean(axis=0)
        variance = float(np.var(vectors)) if len(vectors) > 1 else 0.0

        print(f"\n  --- Tick {tick} ---")
        print(f"  Active: {n_active}/{self._society.agent_count()}")
        print(f"  Pairs: {n_pairs} | Conversations: {n_convos} | Rewires: {n_rewires}")
        print(f"  Belief mean: [{', '.join(f'{v:.3f}' for v in mean_vec)}]")
        print(f"  Belief variance: {variance:.4f}")

        if tick_result.rewires:
            for a, b, reason in tick_result.rewires:
                print(f"    Rewire: {a[:8]}.. <-> {b[:8]}.. ({reason})")

        if n_convos > 0:
            for conv in tick_result.conversations[:2]:
                snippet = conv.turns[0].content[:80] if conv.turns else ""
                print(f"    Conv [{conv.agent_a} <-> {conv.agent_b}]: \"{snippet}...\"")

    def _write_structured(self, tick: int, tick_result: TickResult) -> None:
        states = self._society.get_all_states()
        vectors = {aid: s.vector for aid, s in states.items()}

        conversations = []
        for conv in tick_result.conversations:
            conversations.append({
                "agent_a": conv.agent_a,
                "agent_b": conv.agent_b,
                "topic": conv.topic,
                "turns": [{"speaker": t.speaker, "content": t.content} for t in conv.turns],
            })

        pairs_detail = []
        for a_id, b_id in tick_result.pairs_formed:
            a_name = self._society._personas.get(a_id, None)
            b_name = self._society._personas.get(b_id, None)
            pairs_detail.append([
                a_name.name if a_name else a_id,
                b_name.name if b_name else b_id,
            ])

        network_edges = []
        agent_ids = list(self._society._agents.keys())
        graph = self._society._graph
        seen_edges = set()
        for aid in agent_ids:
            rels = graph.get_relationships(aid, direction="out", rel_type="COMMUNICATES_WITH")
            for rel in rels:
                if rel.valid_to is None and rel.target_id in self._society._agents:
                    edge_key = tuple(sorted([rel.source_id, rel.target_id]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        network_edges.append([rel.source_id, rel.target_id])

        metrics = {}
        new_events = []
        if self._detector:
            all_metrics = self._detector.metric_history
            for name, series in all_metrics.items():
                if series:
                    metrics[name] = series[-1]
            current_events = self._detector.events
            new_events = [
                {"event_type": e.event_type, "tick": e.tick,
                 "confidence": e.confidence, "description": e.description}
                for e in current_events[self._prev_event_count:]
            ]
            self._prev_event_count = len(current_events)

        record = {
            "type": "tick",
            "tick": tick,
            "timestamp": utc_now().isoformat(),
            "active_agents": len(tick_result.active_agents),
            "pairs_formed": len(tick_result.pairs_formed),
            "pairs_detail": pairs_detail,
            "conversations": len(tick_result.conversations),
            "conversation_text": conversations,
            "rewires": len(tick_result.rewires),
            "rewire_details": [
                {"agent_a": a, "agent_b": b, "reason": r}
                for a, b, r in tick_result.rewires
            ],
            "belief_vectors": vectors,
            "network_edges": network_edges,
            "metrics": metrics,
            "events": new_events,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
