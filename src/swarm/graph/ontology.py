from pydantic import BaseModel, Field


class EntityType(BaseModel):
    name: str
    description: str
    attributes: list[str] = Field(default_factory=list)


class RelationshipType(BaseModel):
    name: str
    description: str
    source_types: list[str]
    target_types: list[str]
    attributes: list[str] = Field(default_factory=list)


class Ontology(BaseModel):
    entity_types: list[EntityType]
    relationship_types: list[RelationshipType]

    def entity_type_names(self) -> list[str]:
        return [et.name for et in self.entity_types]

    def relationship_type_names(self) -> list[str]:
        return [rt.name for rt in self.relationship_types]

    def format_for_prompt(self) -> str:
        lines = ["ALLOWED ENTITY TYPES:"]
        for et in self.entity_types:
            attrs = ", ".join(et.attributes) if et.attributes else "none"
            lines.append(f"- {et.name}: {et.description}. Attributes: [{attrs}]")

        lines.append("")
        lines.append("ALLOWED RELATIONSHIP TYPES:")
        for rt in self.relationship_types:
            sources = ", ".join(rt.source_types)
            targets = ", ".join(rt.target_types)
            lines.append(f"- {rt.name}: {rt.description} ({sources} -> {targets})")

        lines.append("")
        lines.append("CONSTRAINT: Only use types from the above lists.")
        return "\n".join(lines)
