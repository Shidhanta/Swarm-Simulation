import json
from typing import Callable

from swarm.agents.base import AgentPersona, PersonaGenerator
from swarm.agents.prompts import PERSONA_GENERATION
from swarm.graph.base import GraphBackend


class GraphPersonaGenerator(PersonaGenerator):

    def __init__(self, neighbor_depth: int = 2):
        self._depth = neighbor_depth

    def generate(
        self,
        entity_id: str,
        graph: GraphBackend,
        llm_fn: Callable[[str], str],
    ) -> AgentPersona:
        entity = graph.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"Entity {entity_id} not found")

        relationships = graph.get_relationships(entity_id)
        neighbors = graph.get_neighbours(entity_id, depth=self._depth)

        rel_text = self._format_relationships(relationships, graph)
        neighbor_text = self._format_neighbors(neighbors)

        prompt = PERSONA_GENERATION.format(
            entity_name=entity.properties.get("name", entity.type),
            entity_type=entity.type,
            entity_properties=json.dumps(entity.properties),
            relationships=rel_text,
            neighbors=neighbor_text,
        )

        raw = llm_fn(prompt)
        return self._parse_response(raw, entity_id)

    def _format_relationships(self, relationships, graph: GraphBackend) -> str:
        if not relationships:
            return "No relationships found."
        lines = []
        for rel in relationships:
            target = graph.get_entity(rel.target_id)
            source = graph.get_entity(rel.source_id)
            target_name = (
                target.properties.get("name", rel.target_id) if target else rel.target_id
            )
            source_name = (
                source.properties.get("name", rel.source_id) if source else rel.source_id
            )
            lines.append(f"- {source_name} --[{rel.type}]--> {target_name}")
        return "\n".join(lines)

    def _format_neighbors(self, neighbors) -> str:
        if not neighbors:
            return "No connected entities."
        lines = []
        for entity in neighbors:
            name = entity.properties.get("name", entity.id)
            lines.append(f"- {name} (type: {entity.type})")
        return "\n".join(lines)

    def _parse_response(self, raw: str, entity_id: str) -> AgentPersona:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        data = json.loads(cleaned)
        return AgentPersona(
            entity_id=entity_id,
            name=data["name"],
            role=data["role"],
            traits=data.get("traits", []),
            goals=data.get("goals", []),
            backstory=data.get("backstory", ""),
            communication_style=data.get("communication_style", ""),
        )
