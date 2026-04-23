"""Loads experiment data from JSONL logs and YAML configs."""

import json
from pathlib import Path

import numpy as np
import yaml


class ExperimentData:
    """Parsed data from a single experiment's JSONL log."""

    def __init__(self, log_path: Path):
        self._path = log_path
        self._header: dict | None = None
        self._ticks: list[dict] = []
        self._footer: dict | None = None
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = record.get("type")
                if rtype == "header":
                    self._header = record
                elif rtype == "footer":
                    self._footer = record
                else:
                    self._ticks.append(record)
        self._loaded = True

    @property
    def agent_map(self) -> dict[str, str]:
        if self._header and "agent_map" in self._header:
            return self._header["agent_map"]
        if self._ticks:
            ids = list(self._ticks[0].get("belief_vectors", {}).keys())
            return {aid: f"Agent_{i}" for i, aid in enumerate(ids)}
        return {}

    @property
    def dimensions(self) -> list[str]:
        if self._header and "dimensions" in self._header:
            return self._header["dimensions"]
        return ["belief"]

    @property
    def config(self) -> dict:
        if self._header and "config" in self._header:
            return self._header["config"]
        return {}

    @property
    def tick_count(self) -> int:
        return len(self._ticks)

    def get_tick(self, n: int) -> dict:
        if 0 <= n < len(self._ticks):
            return self._ticks[n]
        return {}

    def get_all_ticks_summary(self) -> list[dict]:
        summaries = []
        for t in self._ticks:
            vecs = t.get("belief_vectors", {})
            arr = np.array(list(vecs.values())) if vecs else np.array([[]])
            summaries.append({
                "tick": t.get("tick", 0),
                "pairs_formed": t.get("pairs_formed", 0),
                "conversations": t.get("conversations", 0),
                "rewires": t.get("rewires", 0),
                "mean_belief": float(arr.mean()) if arr.size > 0 else 0,
                "variance": float(np.var(arr)) if arr.size > 0 else 0,
            })
        return summaries

    def get_metrics(self) -> dict[str, list[float]]:
        metrics: dict[str, list[float]] = {}
        for t in self._ticks:
            tick_metrics = t.get("metrics", {})
            for name, value in tick_metrics.items():
                metrics.setdefault(name, []).append(value)
        if not metrics and self._ticks:
            for t in self._ticks:
                vecs = list(t.get("belief_vectors", {}).values())
                if vecs:
                    arr = np.array(vecs)
                    metrics.setdefault("variance", []).append(float(np.var(arr)))
                    metrics.setdefault("mean_belief", []).append(float(arr.mean()))
        return metrics

    def get_events(self) -> list[dict]:
        if self._footer and "events" in self._footer:
            return self._footer["events"]
        events = []
        for t in self._ticks:
            for e in t.get("events", []):
                events.append(e)
        return events

    def get_network(self, tick: int) -> dict:
        if tick >= len(self._ticks):
            return {"nodes": [], "edges": []}
        t = self._ticks[tick]
        agent_map = self.agent_map
        edges_raw = t.get("network_edges", [])
        vectors = t.get("belief_vectors", {})

        nodes = []
        for aid, vec in vectors.items():
            nodes.append({
                "id": aid,
                "name": agent_map.get(aid, aid[:8]),
                "belief": vec,
            })

        edges = []
        for edge in edges_raw:
            if len(edge) == 2:
                edges.append({"source": edge[0], "target": edge[1]})

        return {"nodes": nodes, "edges": edges}

    def get_conversations(self, tick: int) -> list[dict]:
        if tick >= len(self._ticks):
            return []
        return self._ticks[tick].get("conversation_text", [])

    def get_beliefs_timeseries(self) -> dict[str, list[list[float]]]:
        agent_map = self.agent_map
        series: dict[str, list[list[float]]] = {}
        for t in self._ticks:
            vecs = t.get("belief_vectors", {})
            for aid, vec in vecs.items():
                name = agent_map.get(aid, aid[:8])
                series.setdefault(name, []).append(vec)
        return series

    @property
    def footer(self) -> dict:
        return self._footer or {}


class ExperimentIndex:
    """Scans logs/ and configs/ to build experiment list."""

    def __init__(
        self,
        logs_dir: str = "logs",
        configs_dir: str = "configs/experiments",
        reports_dir: str = "reports",
    ):
        self._logs_dir = Path(logs_dir)
        self._configs_dir = Path(configs_dir)
        self._reports_dir = Path(reports_dir)

    def list_experiments(self) -> list[dict]:
        experiments = []
        if not self._logs_dir.exists():
            return experiments
        for log_file in sorted(self._logs_dir.glob("*.jsonl")):
            name = log_file.stem
            config_file = self._configs_dir / f"{name}.yaml"
            report_dir = self._reports_dir / name
            experiments.append({
                "name": name,
                "log_file": str(log_file),
                "has_config": config_file.exists(),
                "has_report": report_dir.exists(),
            })
        return experiments

    def get_config(self, name: str) -> dict:
        config_file = self._configs_dir / f"{name}.yaml"
        if config_file.exists():
            with open(config_file) as f:
                return yaml.safe_load(f)
        return {}

    def get_log_path(self, name: str) -> Path:
        return self._logs_dir / f"{name}.jsonl"

    def get_report_dir(self, name: str) -> Path:
        return self._reports_dir / name
