import importlib
import json
from pathlib import Path
from typing import Callable

import yaml

from swarm.agents.base import AgentPersona
from swarm.agents.communication import SwarmAgent
from swarm.agents.default_domain import DefaultDomainSpec
from swarm.agents.domain import DomainSpec
from swarm.agents.persona import GraphPersonaGenerator
from swarm.agents.society import AgentSociety
from swarm.graph.base import GraphBackend
from swarm.graph.networkx_backend import NetworkXBackend
from swarm.graph.similarity import (
    AdamicAdarScorer,
    CausalWalkScorer,
    PPRScorer,
    SimilarityEngine,
)
from swarm.llm.factory import create_provider
from swarm.simulation.emergence import EmergenceDetector
from swarm.simulation.engine import SimulationConfig, SimulationEngine, SimulationResult
from swarm.simulation.logger import SimulationLogger
from swarm.simulation.report import ReportGenerator


class ExperimentRunner:
    """Config-driven experiment execution. One YAML in, results out."""

    def __init__(self, config_path: str):
        self._config_path = Path(config_path)
        with open(self._config_path) as f:
            self._config = yaml.safe_load(f)
        self._graph: GraphBackend | None = None
        self._domain: DomainSpec | None = None
        self._society: AgentSociety | None = None
        self._engine: SimulationEngine | None = None
        self._detector: EmergenceDetector | None = None
        self._logger: SimulationLogger | None = None

    def run(self) -> SimulationResult:
        """Execute the full experiment pipeline."""
        self._setup_graph()
        self._setup_domain()
        self._seed_graph()
        self._setup_society()
        self._setup_engine()
        if self._logger:
            self._logger.on_start(self._config)
        result = self._engine.run()
        if self._logger:
            self._logger.on_complete(result.ticks_completed, result.stop_reason)

        report_cfg = self._config.get("report", {})
        if report_cfg.get("enabled", False):
            report = ReportGenerator(
                result=result,
                detector=self._detector,
                society=self._society,
                config=self._config,
                output_dir=report_cfg.get("output", "reports"),
            )
            include_plots = report_cfg.get("format", "text") == "text+plots"
            report.generate(include_plots=include_plots)

        return result

    def _setup_graph(self) -> None:
        graph_cfg = self._config.get("graph", {})
        backend = graph_cfg.get("backend", "networkx")
        if backend == "networkx":
            self._graph = NetworkXBackend()
        else:
            raise ValueError(f"Unknown graph backend: {backend}")

    def _setup_domain(self) -> None:
        domain_cfg = self._config.get("domain", {})
        plugin = domain_cfg.get("plugin")

        if plugin:
            module_path, class_name = plugin.rsplit(".", 1)
            module = importlib.import_module(module_path)
            domain_class = getattr(module, class_name)
            self._domain = domain_class(domain_cfg)
        else:
            domain_cfg["seed"] = self._config.get("simulation", {}).get("seed", 42)
            if "initial_beliefs" not in domain_cfg:
                domain_cfg["initial_beliefs"] = self._config.get("agents", {}).get("initial_beliefs", {})
            if "activity_rate" not in domain_cfg:
                domain_cfg["activity_rate"] = self._config.get("agents", {}).get("activity_rate", 0.5)
            self._domain = DefaultDomainSpec(domain_cfg)

    def _seed_graph(self) -> None:
        seed_cfg = self._config.get("seed", {})
        for entity_def in seed_cfg.get("entities", []):
            self._graph.add_entity(
                entity_type=entity_def["type"],
                properties=entity_def.get("properties", {}),
            )

    def _setup_society(self) -> None:
        llm_cfg = self._config.get("llm", {})
        agents_cfg = self._config.get("agents", {})
        topo_cfg = self._config.get("topology", {})
        sim_cfg = self._config.get("simulation", {})

        scorers = [AdamicAdarScorer(), PPRScorer(), CausalWalkScorer(seed=sim_cfg.get("seed", 42))]
        similarity_engine = SimilarityEngine(
            graph=self._graph,
            scorers=scorers,
            weighting=self._domain.weighting(),
        )

        self._society = AgentSociety(
            graph=self._graph,
            domain=self._domain,
            similarity_engine=similarity_engine,
            llm_config=llm_cfg,
            topology_config=topo_cfg,
            scheduler_seed=sim_cfg.get("seed", 42),
        )

        agent_count = agents_cfg.get("count", 10)
        persona_source = agents_cfg.get("persona_source", "generate")
        personas = self._create_personas(agent_count, persona_source, llm_cfg)

        for persona in personas:
            self._society.register_agent(persona)

        k = topo_cfg.get("k", 4)
        p = topo_cfg.get("p", 0.1)
        topo_type = topo_cfg.get("type", "small_world")

        if topo_type == "full_mesh":
            agent_ids = list(self._society._agents.keys())
            for i, a in enumerate(agent_ids):
                for b in agent_ids[i + 1:]:
                    self._graph.add_relationship(a, b, "COMMUNICATES_WITH")
        else:
            self._society.initialize_topology(k=k, p=p)

    def _setup_engine(self) -> None:
        sim_cfg = self._config.get("simulation", {})
        config = SimulationConfig(
            max_ticks=sim_cfg.get("max_ticks", 100),
            snapshot_every=sim_cfg.get("snapshot_every", 1),
            seed=sim_cfg.get("seed", 42),
        )
        self._engine = SimulationEngine(society=self._society, config=config)

        detect_cfg = self._config.get("detection", {})
        self._detector = EmergenceDetector(
            society=self._society,
            config=detect_cfg.get("thresholds", {}),
        )
        self._engine.add_tick_callback(self._detector.on_tick)

        log_cfg = self._config.get("logging", {})
        self._logger = SimulationLogger(
            society=self._society,
            level=log_cfg.get("level", "summary"),
            file_path=log_cfg.get("file", None),
        )
        self._logger.set_detector(self._detector)
        self._engine.add_tick_callback(self._logger.on_tick)

    def _create_personas(self, count: int, source: str, llm_cfg: dict) -> list[AgentPersona]:
        if source == "generate":
            return self._generate_personas(count, llm_cfg)
        elif source == "manual":
            return self._manual_personas()
        elif source == "minimal":
            return self._minimal_personas(count)
        else:
            return self._minimal_personas(count)

    def _generate_personas(self, count: int, llm_cfg: dict) -> list[AgentPersona]:
        provider = create_provider(llm_cfg)
        llm_fn = provider.as_callable()
        generator = GraphPersonaGenerator()
        personas = []
        for i in range(count):
            entity = self._graph.add_entity("Agent", {"name": f"Agent_{i}"})
            persona = generator.generate(entity.id, self._graph, llm_fn)
            personas.append(persona)
        return personas

    def _manual_personas(self) -> list[AgentPersona]:
        agents_cfg = self._config.get("agents", {})
        personas = []
        for agent_def in agents_cfg.get("definitions", []):
            entity = self._graph.add_entity("Agent", {"name": agent_def["name"]})
            personas.append(AgentPersona(
                entity_id=entity.id,
                name=agent_def["name"],
                role=agent_def.get("role", "participant"),
                traits=agent_def.get("traits", []),
                goals=agent_def.get("goals", []),
                backstory=agent_def.get("backstory", ""),
                communication_style=agent_def.get("communication_style", ""),
            ))
        return personas

    def _minimal_personas(self, count: int) -> list[AgentPersona]:
        """Create simple personas without LLM — for fast experiments."""
        personas = []
        for i in range(count):
            entity = self._graph.add_entity("Agent", {"name": f"Agent_{i}"})
            personas.append(AgentPersona(
                entity_id=entity.id,
                name=f"Agent_{i}",
                role="participant",
                traits=[],
                goals=[],
                backstory="",
                communication_style="",
            ))
        return personas

    @property
    def detector(self) -> EmergenceDetector | None:
        return self._detector

    @property
    def society(self) -> AgentSociety | None:
        return self._society

    @property
    def config(self) -> dict:
        return self._config
