"""Knowledge graph layer — temporal entity and relationship management."""

from swarm.graph.base import Entity, GraphBackend, Relationship
from swarm.graph.ingestion import Episode, IngestionResult, ingest
from swarm.graph.networkx_backend import NetworkXBackend
from swarm.graph.ontology import EntityType, Ontology, RelationshipType

__all__ = [
    "Entity",
    "EntityType",
    "Episode",
    "GraphBackend",
    "IngestionResult",
    "NetworkXBackend",
    "Ontology",
    "Relationship",
    "RelationshipType",
    "ingest",
]