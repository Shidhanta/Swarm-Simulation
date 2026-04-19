from collections import deque
from datetime import datetime, timezone

import networkx as nx

from swarm.graph.base import Entity, GraphBackend, Relationship, utc_now

class NetworkXBackend(GraphBackend):
    def __init__(self) -> None:
        self.__graph = nx.MultiDiGraph()

    def add_entity(self, entity_type: str, properties: dict|None= None) -> Entity:
        entity = Entity(type=entity_type, properties=properties or {})
        self.__graph.add_node(
            entity.id,
            entity=entity
        )
        return entity
    
    def get_entity(self, entity_id: str) -> Entity|None:
        if entity_id not in self.__graph:
            return None
        return self.__graph.nodes[entity_id]["entity"]
    
    def update_entity(self, entity_id:str, properties: dict) -> Entity:
        entity = self.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"Entity {entity_id} not found")
        entity.properties.update(properties)
        entity.updated_at = utc_now()
        return entity
    
    def remove_entity(self,entity_id: str) -> None:
        if entity_id not in self.__graph:
            raise ValueError(f"Entity {entity_id} not found")
        self.__graph.remove_node(entity_id)
    
    def add_relationship(self, source_id: str, target_id: str, rel_type: str, properties: dict|None=None, valid_from: datetime|None=None) -> Relationship:
        if source_id not in self.__graph or target_id not in self.__graph:
            raise ValueError("Both source and target entities must exist")
        rel =  Relationship(
            source_id=source_id,
            target_id = target_id,
            type = rel_type,
            properties=properties or {},
            valid_from = valid_from or utc_now()
        )

        self.__graph.add_edge(
            source_id,
            target_id,
            key = rel_type,
            relationship = rel
        )
        return rel
    
    def get_relationships(self, entity_id: str, direction: str = "both", rel_type: str | None=None)-> list[Relationship]:
        results = []
        if direction in ("out" , "both"):
            for _, _, data in self.__graph.out_edges(entity_id, data=True):
                rel = data["relationship"]
                if rel_type is None or rel.type == rel_type:
                    results.append(rel)
        if direction in ("in","both"):
            for _,_,data in self.__graph.in_edges(entity_id, data=True):
                rel = data["relationship"]
                if rel_type is None or rel.type== rel_type:
                    results.append(rel)
        return results
    
    def expire_relationship(self, source_id: str, target_id: str, rel_type: str, valid_to: datetime|None=None) -> None:
        if not self.__graph.has_edge(source_id,target_id,key=rel_type):
            raise ValueError(f"Relationship {rel_type} not found between {source_id} and {target_id}")

        edge_data = self.__graph.edges[source_id, target_id, rel_type]
        edge_data["relationship"].valid_to = valid_to or utc_now()

    def _is_active(self, rel: Relationship, timestamp: datetime| None = None) -> bool:
        ts =  timestamp or utc_now()
        if rel.valid_from > ts:
            return False
        if rel.valid_to is not None and rel.valid_to <= ts:
            return False
        return True
    
    def get_neighbours(self, entity_id: str, depth: int = 1, timestamp: datetime|None=None) -> list[Entity]:
        if entity_id not in self.__graph:
            raise ValueError(f"Entity {entity_id} not found")
        visited: set[str]={entity_id}
        queue: deque[tuple[str, int]] = deque([(entity_id,0)])
        result: list[Entity]= []

        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for _, neighbour_id, data in self.__graph.out_edges(current_id,data=True):
                rel = data["relationship"]
                if not self._is_active(rel,timestamp):
                    continue
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    result.append(self.__graph.nodes[neighbour_id]["entity"])
                    queue.append((neighbour_id,current_depth+1))
            for neighbour_id,_,data in self.__graph.in_edges(current_id, data=True):
                rel = data["relationship"]
                if not self._is_active(rel, timestamp):
                    continue
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    result.append(self.__graph.nodes[neighbour_id]["entity"])
                    queue.append((neighbour_id,current_depth+1))
        return result

    def get_snapshot(self, timestamp:datetime) -> tuple[list[Entity],list[Relationship]]:
        entities = [data["entity"] for _, data in self.__graph.nodes(data=True)]
        relationships = [data["relationship"] for _,_, data in self.__graph.edges(data=True) if self._is_active(data["relationship"],timestamp)]
        return entities,relationships

    def get_entity_history(self, entity_id: str) -> list["Relationship"]:
        if entity_id not in self.__graph:
            raise ValueError(f"Entity {entity_id} not found")
        rels = []
        for _,_,data in self.__graph.out_edges(entity_id, data=True):
            rels.append(data["relationship"])
        for _,_, data in self.__graph.in_edges(entity_id, data=True):
            rels.append(data["relationship"])
        rels.sort(key = lambda r: r.created_at)
        return rels

    def search_entities(self, entity_type: str | None = None, name_hint: str | None = None) -> list[Entity]:
        results = []
        hint_lower = name_hint.lower() if name_hint else None
        for _, data in self.__graph.nodes(data=True):
            entity = data["entity"]
            if entity_type and entity.type != entity_type:
                continue
            if hint_lower:
                name = entity.properties.get("name", "").lower()
                if hint_lower not in name:
                    continue
            results.append(entity)
        return results
        

