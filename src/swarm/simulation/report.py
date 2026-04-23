"""Report generation — text summaries and publication-quality plots."""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import networkx as nx

from swarm.agents.society import AgentSociety
from swarm.graph.base import GraphBackend, utc_now
from swarm.simulation.emergence import EmergenceDetector
from swarm.simulation.engine import SimulationResult


def _setup_style():
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 10,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.5,
    })


class ReportGenerator:
    """Generates text summaries and plots from simulation results."""

    def __init__(
        self,
        result: SimulationResult,
        detector: EmergenceDetector,
        society: AgentSociety,
        config: dict,
        output_dir: str = "reports",
    ):
        self._result = result
        self._detector = detector
        self._society = society
        self._config = config
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        _setup_style()

    def generate(self, include_plots: bool = True) -> str:
        """Generate full report. Returns the text summary."""
        text = self._generate_text()
        report_path = self._output_dir / "report.txt"
        report_path.write_text(text)

        if include_plots:
            self._plot_opinion_trajectories()
            self._plot_opinion_density()
            self._plot_final_distribution()
            self._plot_metric_timeseries()
            self._plot_network_snapshots()
            self._plot_interaction_heatmap()
            self._plot_early_warnings()
            print(f"\n  Plots saved to: {self._output_dir}/")

        print(f"  Report saved to: {report_path}")
        return text

    def _generate_text(self) -> str:
        exp = self._config.get("experiment", {})
        sim = self._config.get("simulation", {})
        domain = self._config.get("domain", {})
        metrics = self._detector.metric_history
        events = self._detector.events

        lines = []
        lines.append("=" * 60)
        lines.append("EXPERIMENT REPORT")
        lines.append("=" * 60)
        lines.append(f"  Name: {exp.get('name', 'Unnamed')}")
        lines.append(f"  Description: {exp.get('description', '')}")
        if exp.get("reference"):
            lines.append(f"  Reference: {exp['reference']}")
        lines.append(f"  Date: {utc_now().strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"  Ticks: {self._result.ticks_completed}")
        lines.append(f"  Stop reason: {self._result.stop_reason}")

        lines.append(f"\n--- CONFIGURATION ---")
        lines.append(f"  Agents: {self._society.agent_count()}")
        lines.append(f"  Topology: {self._config.get('topology', {}).get('type', 'unknown')}")
        lines.append(f"  Interaction: {domain.get('interaction_mode', 'unknown')} "
                      f"(mu={domain.get('convergence_rate', '?')}, "
                      f"epsilon={domain.get('confidence_bound', '?')})")
        lines.append(f"  Stubbornness: {domain.get('stubbornness', '?')}")
        groups = domain.get("groups")
        if groups:
            for g in groups:
                lines.append(f"    Group '{g['name']}': count={g['count']}, "
                              f"range={g.get('range', '?')}, stubbornness={g.get('stubbornness', '?')}")

        lines.append(f"\n--- EMERGENCE EVENTS ---")
        if events:
            for event in events:
                lines.append(f"  [tick {event.tick:3d}] {event.event_type}: {event.description}")
        else:
            lines.append("  No emergence events detected.")

        lines.append(f"\n--- KEY METRICS (first -> last) ---")
        key_metrics = ["consensus", "variance", "polarization_bc", "modularity",
                       "echo_chamber_index", "algebraic_connectivity", "centralization"]
        for name in key_metrics:
            if name in metrics and metrics[name]:
                first = metrics[name][0]
                last = metrics[name][-1]
                delta = last - first
                sign = "+" if delta >= 0 else ""
                lines.append(f"  {name:25s}: {first:.4f} -> {last:.4f} ({sign}{delta:.4f})")

        lines.append(f"\n--- BELIEF SUMMARY ---")
        if self._result.snapshots:
            first_snap = self._result.snapshots[0]
            last_snap = self._result.snapshots[-1]
            first_vecs = np.array([s["vector"] for s in first_snap.states.values()])
            last_vecs = np.array([s["vector"] for s in last_snap.states.values()])
            lines.append(f"  Start mean: [{', '.join(f'{v:.3f}' for v in first_vecs.mean(axis=0))}]")
            lines.append(f"  Final mean: [{', '.join(f'{v:.3f}' for v in last_vecs.mean(axis=0))}]")
            lines.append(f"  Start variance: {np.var(first_vecs):.4f}")
            lines.append(f"  Final variance: {np.var(last_vecs):.4f}")

            drifts = np.linalg.norm(last_vecs - first_vecs, axis=1)
            lines.append(f"  Agents that moved (drift > 0.01): {np.sum(drifts > 0.01)}/{len(drifts)}")
            lines.append(f"  Max drift: {drifts.max():.4f}")
            lines.append(f"  Mean drift: {drifts.mean():.4f}")

        lines.append(f"\n--- INTERPRETATION ---")
        if "consensus" in metrics and metrics["consensus"]:
            con = metrics["consensus"][-1]
            if con > 0.9:
                lines.append("  * CONSENSUS reached — agents converged to shared beliefs.")
            elif con > 0.7:
                lines.append("  * PARTIAL CONSENSUS — agents trending toward agreement.")
            else:
                lines.append("  * NO CONSENSUS — significant belief diversity remains.")

        if "polarization_bc" in metrics and metrics["polarization_bc"]:
            bc = metrics["polarization_bc"][-1]
            if bc > 0.555:
                lines.append("  * POLARIZATION detected — beliefs split into opposing camps.")
            else:
                lines.append("  * No significant polarization.")

        if "modularity" in metrics and metrics["modularity"]:
            mod = metrics["modularity"][-1]
            if mod > 0.3:
                lines.append(f"  * ECHO CHAMBERS forming — network modularity {mod:.3f}.")
            else:
                lines.append("  * No significant echo chamber formation.")

        if "variance" in metrics and len(metrics["variance"]) > 1:
            var_start = metrics["variance"][0]
            var_end = metrics["variance"][-1]
            if var_end < var_start * 0.5:
                lines.append("  * Opinions CONVERGING rapidly (variance halved).")
            elif var_end > var_start * 1.5:
                lines.append("  * Opinions DIVERGING (variance increased 50%+).")
            else:
                lines.append("  * Opinions relatively STABLE.")

        lines.append("")
        return "\n".join(lines)

    def _get_belief_history(self) -> tuple[list[int], dict[str, list[float]]]:
        """Extract per-agent belief trajectories from snapshots."""
        ticks = []
        agent_series: dict[str, list[float]] = {}
        for snap in self._result.snapshots:
            ticks.append(snap.tick)
            for aid, state in snap.states.items():
                agent_series.setdefault(aid, []).append(state["vector"][0])
        return ticks, agent_series

    def _plot_opinion_trajectories(self) -> None:
        ticks, agent_series = self._get_belief_history()
        if not ticks:
            return

        fig, ax = plt.subplots(figsize=(10, 6))
        for aid, opinions in agent_series.items():
            ax.plot(ticks[:len(opinions)], opinions, linewidth=0.8, alpha=0.5, color="steelblue")

        ax.set_xlabel("Time Step")
        ax.set_ylabel("Belief")
        ax.set_ylim(-0.05, 1.05)
        ax.set_title("Opinion Trajectories")
        fig.tight_layout()
        fig.savefig(self._output_dir / "opinion_trajectories.png")
        plt.close(fig)

    def _plot_opinion_density(self) -> None:
        ticks, agent_series = self._get_belief_history()
        if not ticks:
            return

        n_ticks = len(ticks)
        n_bins = 30
        density = np.zeros((n_bins, n_ticks))
        bin_edges = np.linspace(0, 1, n_bins + 1)

        for i in range(n_ticks):
            opinions = [series[i] for series in agent_series.values() if i < len(series)]
            counts, _ = np.histogram(opinions, bins=bin_edges)
            density[:, i] = counts

        fig, ax = plt.subplots(figsize=(10, 6))
        im = ax.imshow(density, aspect="auto", origin="lower",
                        extent=[ticks[0], ticks[-1], 0, 1],
                        cmap="inferno", interpolation="bilinear")
        ax.set_xlabel("Time Step")
        ax.set_ylabel("Belief")
        ax.set_title("Opinion Density Over Time")
        plt.colorbar(im, ax=ax, label="Agent Count")
        fig.tight_layout()
        fig.savefig(self._output_dir / "opinion_density.png")
        plt.close(fig)

    def _plot_final_distribution(self) -> None:
        if not self._result.snapshots:
            return
        last = self._result.snapshots[-1]
        opinions = [s["vector"][0] for s in last.states.values()]

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(opinions, bins=20, color="steelblue", edgecolor="white",
                linewidth=0.5, density=True)
        ax.set_xlabel("Belief")
        ax.set_ylabel("Density")
        ax.set_xlim(-0.05, 1.05)
        ax.set_title("Final Belief Distribution")
        fig.tight_layout()
        fig.savefig(self._output_dir / "final_distribution.png")
        plt.close(fig)

    def _plot_metric_timeseries(self) -> None:
        metrics = self._detector.metric_history
        plot_metrics = ["consensus", "variance", "polarization_bc", "modularity",
                        "algebraic_connectivity", "centralization"]
        available = [m for m in plot_metrics if m in metrics and metrics[m]]
        if not available:
            return

        n = len(available)
        fig, axes = plt.subplots(n, 1, figsize=(10, 2.5 * n), sharex=True)
        if n == 1:
            axes = [axes]

        for ax, name in zip(axes, available):
            values = metrics[name]
            ax.plot(range(len(values)), values, color="steelblue", linewidth=1.5)
            ax.set_ylabel(name.replace("_", " ").title())

            events = [e for e in self._detector.events if e.event_type in name]
            for event in events:
                ax.axvline(event.tick, color="red", linestyle="--", alpha=0.5)

        axes[-1].set_xlabel("Time Step")
        fig.suptitle("Metric Evolution", fontsize=14, y=1.01)
        fig.tight_layout()
        fig.savefig(self._output_dir / "metric_timeseries.png")
        plt.close(fig)

    def _plot_network_snapshots(self) -> None:
        if not self._result.snapshots:
            return
        snaps = self._result.snapshots
        indices = [0, len(snaps) // 2, -1]
        selected = [snaps[i] for i in indices if i < len(snaps)]

        fig, axes = plt.subplots(1, len(selected), figsize=(5 * len(selected), 5))
        if len(selected) == 1:
            axes = [axes]

        graph = self._society._graph
        agent_ids = list(self._society._agents.keys())

        G = nx.Graph()
        G.add_nodes_from(agent_ids)
        rels = []
        for aid in agent_ids:
            for rel in graph.get_relationships(aid, direction="out", rel_type="COMMUNICATES_WITH"):
                if rel.valid_to is None and rel.target_id in G:
                    G.add_edge(rel.source_id, rel.target_id)

        pos = nx.spring_layout(G, seed=42, k=1.5 / max(np.sqrt(len(G)), 1))

        for ax, snap in zip(axes, selected):
            opinions = {aid: s["vector"][0] for aid, s in snap.states.items()}
            node_colors = [cm.RdYlBu(opinions.get(n, 0.5)) for n in G.nodes()]
            nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.15, width=0.5)
            nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                                   node_size=60, edgecolors="none")
            ax.set_title(f"Tick {snap.tick}")
            ax.axis("off")

        fig.suptitle("Network Snapshots (nodes colored by belief)", fontsize=13)
        fig.tight_layout()
        fig.savefig(self._output_dir / "network_snapshots.png")
        plt.close(fig)

    def _plot_interaction_heatmap(self) -> None:
        agent_ids = list(self._society._agents.keys())
        n = len(agent_ids)
        if n == 0:
            return
        id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
        matrix = np.zeros((n, n))

        for tick_result in self._result.tick_results:
            for conv in tick_result.conversations:
                a_name = conv.agent_a
                b_name = conv.agent_b
                a_id = next((aid for aid, p in self._society._personas.items() if p.name == a_name), None)
                b_id = next((aid for aid, p in self._society._personas.items() if p.name == b_name), None)
                if a_id and b_id and a_id in id_to_idx and b_id in id_to_idx:
                    matrix[id_to_idx[a_id], id_to_idx[b_id]] += 1
                    matrix[id_to_idx[b_id], id_to_idx[a_id]] += 1

        if matrix.sum() == 0:
            return

        if self._result.snapshots:
            last = self._result.snapshots[-1]
            opinions = [last.states.get(aid, {}).get("vector", [0.5])[0] for aid in agent_ids]
            sort_idx = np.argsort(opinions)
            matrix = matrix[sort_idx][:, sort_idx]

        fig, ax = plt.subplots(figsize=(8, 7))
        im = ax.imshow(matrix, cmap="YlOrRd", interpolation="nearest")
        ax.set_xlabel("Agent (sorted by belief)")
        ax.set_ylabel("Agent (sorted by belief)")
        ax.set_title("Interaction Frequency")
        plt.colorbar(im, ax=ax, label="Conversation Count")
        fig.tight_layout()
        fig.savefig(self._output_dir / "interaction_heatmap.png")
        plt.close(fig)

    def _plot_early_warnings(self) -> None:
        metrics = self._detector.metric_history
        variance = metrics.get("variance", [])
        ar1 = metrics.get("ar1", [])
        if len(variance) < 5:
            return

        panels = []
        if variance:
            panels.append(("Opinion Variance", variance, "steelblue"))
        if ar1:
            panels.append(("AR(1) Coefficient", ar1, "darkorange"))

        fig, axes = plt.subplots(len(panels), 1, figsize=(10, 3 * len(panels)), sharex=True)
        if len(panels) == 1:
            axes = [axes]

        for ax, (label, data, color) in zip(axes, panels):
            ax.plot(range(len(data)), data, color=color, linewidth=1.5)
            ax.set_ylabel(label)

        axes[-1].set_xlabel("Time Step")
        fig.suptitle("Early Warning Signals", fontsize=13, y=1.01)
        fig.tight_layout()
        fig.savefig(self._output_dir / "early_warnings.png")
        plt.close(fig)
