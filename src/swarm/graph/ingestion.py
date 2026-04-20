import json
import re
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field

from swarm.graph.base import GraphBackend, utc_now
from swarm.graph.ontology import Ontology
from swarm.graph.prompts import (
    ENTITY_EXTRACTION,
    ENTITY_RESOLUTION,
    ONTOLOGY_GENERATION,
    RELATIONSHIP_EXTRACTION,
    RELATIONSHIP_RESOLUTION,
)


class Episode(BaseModel):
    id: str = ""
    content: str
    source: str
    domain: str
    timestamp: datetime = Field(default_factory=utc_now)


class ExtractedEntity(BaseModel):
    name: str
    type: str
    properties: dict = Field(default_factory=dict)


class ExtractedRelationship(BaseModel):
    source: str
    target: str
    type: str
    properties: dict = Field(default_factory=dict)


class ResolvedEntity(BaseModel):
    name: str
    type: str
    properties: dict = Field(default_factory=dict)
    entity_id: str = ""
    is_new: bool = True


class IngestionResult(BaseModel):
    episode_id: str
    entities_created: int = 0
    entities_resolved: int = 0
    relationships_created: int = 0
    relationships_expired: int = 0


def _parse_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def generate_ontology(
    seed_text: str,
    domain: str,
    extract_fn: Callable[[str], str],
) -> Ontology:
    prompt = ONTOLOGY_GENERATION.format(domain=domain, text=seed_text)
    raw = extract_fn(prompt)
    data = _parse_json(raw)
    return Ontology.model_validate(data)


def _store_ontology(ontology: Ontology, graph: GraphBackend, episode_id: str) -> None:
    for et in ontology.entity_types:
        entity = graph.add_entity(
            "OntologyEntity",
            {"name": et.name, "description": et.description, "attributes": et.attributes},
        )
        graph.add_relationship(entity.id, episode_id, "SOURCED_FROM")

    for rt in ontology.relationship_types:
        entity = graph.add_entity(
            "OntologyRelationship",
            {
                "name": rt.name,
                "description": rt.description,
                "source_types": rt.source_types,
                "target_types": rt.target_types,
                "attributes": rt.attributes,
            },
        )
        graph.add_relationship(entity.id, episode_id, "SOURCED_FROM")


def _extract_entities(
    text: str,
    ontology: Ontology,
    extract_fn: Callable[[str], str],
) -> list[ExtractedEntity]:
    prompt = ENTITY_EXTRACTION.format(
        text=text,
        ontology_block=ontology.format_for_prompt(),
    )
    raw = extract_fn(prompt)
    data = _parse_json(raw)
    return [ExtractedEntity.model_validate(e) for e in data["entities"]]


def _resolve_entities(
    extracted: list[ExtractedEntity],
    graph: GraphBackend,
    extract_fn: Callable[[str], str],
) -> list[ResolvedEntity]:
    candidates = []
    for ent in extracted:
        found = graph.search_entities(entity_type=ent.type, name_hint=ent.name)
        candidates.extend(found)

    candidate_data = [
        {"id": c.id, "type": c.type, "properties": c.properties}
        for c in candidates
    ]

    extracted_data = [
        {"name": e.name, "type": e.type, "properties": e.properties}
        for e in extracted
    ]

    if not candidate_data:
        return [
            ResolvedEntity(
                name=e.name, type=e.type, properties=e.properties, is_new=True
            )
            for e in extracted
        ]

    prompt = ENTITY_RESOLUTION.format(
        extracted_entities=json.dumps(extracted_data, indent=2),
        candidate_entities=json.dumps(candidate_data, indent=2),
    )
    raw = extract_fn(prompt)
    data = _parse_json(raw)

    resolved = []
    for r in data["resolutions"]:
        matched_id = r.get("matched_existing_id")
        source_ent = next((e for e in extracted if e.name == r["name"]), None)
        if source_ent is None:
            continue
        resolved.append(
            ResolvedEntity(
                name=source_ent.name,
                type=source_ent.type,
                properties=source_ent.properties,
                entity_id=matched_id or "",
                is_new=matched_id is None,
            )
        )
    return resolved


def _insert_entities(
    resolved: list[ResolvedEntity],
    graph: GraphBackend,
    episode_id: str,
) -> dict[str, str]:
    name_to_id: dict[str, str] = {}

    for ent in resolved:
        if ent.is_new:
            props = {**ent.properties, "name": ent.name}
            entity = graph.add_entity(ent.type, props)
            ent.entity_id = entity.id
        else:
            graph.update_entity(ent.entity_id, ent.properties)

        name_to_id[ent.name] = ent.entity_id
        graph.add_relationship(ent.entity_id, episode_id, "SOURCED_FROM")

    return name_to_id


def _extract_relationships(
    text: str,
    resolved_entities: list[ResolvedEntity],
    ontology: Ontology,
    extract_fn: Callable[[str], str],
) -> list[ExtractedRelationship]:
    resolved_data = [
        {"name": e.name, "type": e.type, "properties": e.properties}
        for e in resolved_entities
    ]
    prompt = RELATIONSHIP_EXTRACTION.format(
        text=text,
        resolved_entities=json.dumps(resolved_data, indent=2),
        ontology_block=ontology.format_for_prompt(),
    )
    raw = extract_fn(prompt)
    data = _parse_json(raw)
    return [ExtractedRelationship.model_validate(r) for r in data["relationships"]]


def _resolve_relationships(
    extracted: list[ExtractedRelationship],
    name_to_id: dict[str, str],
    graph: GraphBackend,
    extract_fn: Callable[[str], str],
) -> list[tuple[ExtractedRelationship, str | None]]:
    existing_by_pair: dict[str, list[dict]] = {}
    for rel in extracted:
        source_id = name_to_id.get(rel.source)
        target_id = name_to_id.get(rel.target)
        if not source_id or not target_id:
            continue
        pair_key = f"{source_id}:{target_id}"
        if pair_key not in existing_by_pair:
            existing_rels = graph.get_relationships(source_id, direction="out")
            existing_by_pair[pair_key] = [
                {
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "type": r.type,
                    "properties": r.properties,
                }
                for r in existing_rels
                if r.target_id == target_id and r.valid_to is None
            ]

    all_existing = []
    for rels in existing_by_pair.values():
        all_existing.extend(rels)

    if not all_existing:
        return [(rel, None) for rel in extracted]

    new_data = [
        {"source": r.source, "target": r.target, "type": r.type, "properties": r.properties}
        for r in extracted
    ]

    prompt = RELATIONSHIP_RESOLUTION.format(
        new_relationships=json.dumps(new_data, indent=2),
        existing_relationships=json.dumps(all_existing, indent=2),
    )
    raw = extract_fn(prompt)
    data = _parse_json(raw)

    contradiction_map: dict[str, str | None] = {}
    for r in data["resolutions"]:
        key = f"{r['source']}:{r['target']}:{r['type']}"
        contradiction_map[key] = r.get("contradicts_existing")

    results = []
    for rel in extracted:
        key = f"{rel.source}:{rel.target}:{rel.type}"
        contradicts = contradiction_map.get(key)
        results.append((rel, contradicts))

    return results


def _insert_relationships(
    resolved: list[tuple[ExtractedRelationship, str | None]],
    name_to_id: dict[str, str],
    graph: GraphBackend,
    episode_id: str,
) -> tuple[int, int]:
    created = 0
    expired = 0

    for rel, contradicts_type in resolved:
        source_id = name_to_id.get(rel.source)
        target_id = name_to_id.get(rel.target)
        if not source_id or not target_id:
            continue

        if contradicts_type:
            graph.expire_relationship(source_id, target_id, contradicts_type)
            expired += 1

        new_rel = graph.add_relationship(
            source_id, target_id, rel.type, rel.properties
        )
        graph.add_relationship(source_id, episode_id, "SOURCED_FROM")
        created += 1

    return created, expired


def ingest(
    text: str,
    domain: str,
    source: str,
    graph: GraphBackend,
    extract_fn: Callable[[str], str],
    ontology: Ontology | None = None,
) -> tuple[IngestionResult, Ontology]:
    episode = Episode(content=text, source=source, domain=domain)
    episode_entity = graph.add_entity(
        "Episode",
        {"content": episode.content, "source": episode.source, "domain": episode.domain},
    )
    episode.id = episode_entity.id

    if ontology is None:
        ontology = generate_ontology(text, domain, extract_fn)

    _store_ontology(ontology, graph, episode.id)

    extracted_entities = _extract_entities(text, ontology, extract_fn)

    resolved_entities = _resolve_entities(extracted_entities, graph, extract_fn)

    name_to_id = _insert_entities(resolved_entities, graph, episode.id)

    extracted_rels = _extract_relationships(
        text, resolved_entities, ontology, extract_fn
    )

    resolved_rels = _resolve_relationships(
        extracted_rels, name_to_id, graph, extract_fn
    )

    created, expired = _insert_relationships(
        resolved_rels, name_to_id, graph, episode.id
    )

    result = IngestionResult(
        episode_id=episode.id,
        entities_created=sum(1 for e in resolved_entities if e.is_new),
        entities_resolved=sum(1 for e in resolved_entities if not e.is_new),
        relationships_created=created,
        relationships_expired=expired,
    )

    return result, ontology
