ONTOLOGY_GENERATION = """You are a knowledge graph ontology designer.

DOMAIN: {domain}

SEED TEXT:
{text}

TASK: Generate an ontology of entity types and relationship types suitable for
building a temporal knowledge graph about this domain.

OUTPUT CONSTRAINTS:
- Entity type names: PascalCase (e.g., Company, Person, MarketEvent)
- Relationship type names: UPPER_SNAKE_CASE (e.g., COMPETES_WITH, FOUNDED_BY)
- Descriptions: max 100 characters
- Minimum 3 entity types, maximum 10
- Minimum 3 relationship types, maximum 15
- Each relationship must specify valid source and target entity types
- No markdown fences, raw JSON only
- No newlines inside string values

OUTPUT SCHEMA:
{{
  "entity_types": [
    {{"name": "PascalCase", "description": "string", "attributes": ["string"]}}
  ],
  "relationship_types": [
    {{"name": "UPPER_SNAKE_CASE", "description": "string", "source_types": ["PascalCase"], "target_types": ["PascalCase"], "attributes": ["string"]}}
  ]
}}"""

ENTITY_EXTRACTION = """You are a knowledge graph extraction system.

INPUT TEXT:
{text}

{ontology_block}

TASK: Extract all entities from the text that match the allowed types.

OUTPUT CONSTRAINTS:
- Entity names: normalized, canonical form (e.g., "Tesla Inc" not "the EV company")
- Only use entity types from the allowed list
- Properties should include the attributes specified for each type where available
- Include a "name" key in properties for every entity
- No markdown fences, raw JSON only
- No newlines inside string values

OUTPUT SCHEMA:
{{
  "entities": [
    {{"name": "string", "type": "PascalCase", "properties": {{"name": "string", "key": "value"}}}}
  ]
}}"""

ENTITY_RESOLUTION = """You are an entity resolution system for a knowledge graph.

EXTRACTED ENTITIES:
{extracted_entities}

EXISTING GRAPH ENTITIES (candidates):
{candidate_entities}

TASK: For each extracted entity, determine if it refers to the same real-world
thing as any existing entity in the graph. Consider name variations, abbreviations,
and contextual equivalence.

OUTPUT CONSTRAINTS:
- Set matched_existing_id to the ID of the matching entity, or null if it is new
- Every extracted entity must appear exactly once in the output
- No markdown fences, raw JSON only

OUTPUT SCHEMA:
{{
  "resolutions": [
    {{"name": "string", "type": "string", "matched_existing_id": "uuid_string_or_null"}}
  ]
}}"""

RELATIONSHIP_EXTRACTION = """You are a knowledge graph extraction system.

INPUT TEXT:
{text}

RESOLVED ENTITIES:
{resolved_entities}

{ontology_block}

TASK: Extract all relationships between the resolved entities that are present
in the text. Only use entities from the resolved list as source and target.

OUTPUT CONSTRAINTS:
- Only use relationship types from the allowed list
- Source and target must be entity names from the resolved entities list
- Respect source_types and target_types constraints from the ontology
- Properties should include attributes specified for each relationship type where available
- No markdown fences, raw JSON only
- No newlines inside string values

OUTPUT SCHEMA:
{{
  "relationships": [
    {{"source": "entity_name", "target": "entity_name", "type": "UPPER_SNAKE_CASE", "properties": {{"key": "value"}}}}
  ]
}}"""

RELATIONSHIP_RESOLUTION = """You are a knowledge graph consistency system.

NEW RELATIONSHIPS:
{new_relationships}

EXISTING RELATIONSHIPS (between the same entity pairs):
{existing_relationships}

TASK: For each new relationship, determine if it contradicts any existing
relationship between the same entities. A contradiction means the new fact
invalidates or replaces the old fact (e.g., "CEO of X" replaced by "former CEO of X").

OUTPUT CONSTRAINTS:
- Set contradicts_existing to the type of the contradicted relationship, or null
- Relationships that add new information without contradicting are not contradictions
- No markdown fences, raw JSON only

OUTPUT SCHEMA:
{{
  "resolutions": [
    {{"source": "entity_name", "target": "entity_name", "type": "UPPER_SNAKE_CASE", "contradicts_existing": "UPPER_SNAKE_CASE_or_null"}}
  ]
}}"""
