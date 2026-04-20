import json

from swarm.graph.base import GraphBackend


class KnowledgeGraphToolkit:
    """Wraps GraphBackend methods as callables for CAMEL FunctionTool."""

    def __init__(self, graph: GraphBackend):
        self._graph = graph

    def search_entities(self, query: str, entity_type: str = "") -> str:
        """Search the knowledge graph for entities matching a query.

        Args:
            query: Name or partial name to search for.
            entity_type: Optional type filter (e.g. "Person", "Company").

        Returns:
            JSON string of matching entities with their properties.
        """
        results = self._graph.search_entities(
            entity_type=entity_type or None,
            name_hint=query,
        )
        return json.dumps([
            {"id": e.id, "type": e.type, "name": e.properties.get("name", ""), "properties": e.properties}
            for e in results[:10]
        ])

    def get_neighbors(self, entity_id: str, depth: int = 1) -> str:
        """Get entities connected to a given entity in the knowledge graph.

        Args:
            entity_id: The UUID of the entity to explore from.
            depth: How many hops to traverse (1 or 2).

        Returns:
            JSON string of neighboring entities.
        """
        neighbors = self._graph.get_neighbours(entity_id, depth=min(depth, 2))
        return json.dumps([
            {"id": e.id, "type": e.type, "name": e.properties.get("name", "")}
            for e in neighbors[:20]
        ])

    def get_relationships(self, entity_id: str) -> str:
        """Get all active relationships for an entity.

        Args:
            entity_id: The UUID of the entity.

        Returns:
            JSON string of relationships with source, target, and type.
        """
        rels = self._graph.get_relationships(entity_id)
        active = [r for r in rels if r.valid_to is None]
        return json.dumps([
            {"source": r.source_id, "target": r.target_id, "type": r.type, "properties": r.properties}
            for r in active[:20]
        ])

    def get_tools(self) -> list:
        """Return the toolkit methods as a list for CAMEL FunctionTool wrapping."""
        return [self.search_entities, self.get_neighbors, self.get_relationships]
