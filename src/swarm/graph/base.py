from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

def utc_now()-> datetime:
    return datetime.now(timezone.utc)

class Entity(BaseModel):
    id: str = Field(default_factory= lambda: str(uuid4()))
    type: str
    properties: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class Relationship(BaseModel):
    source_id: str
    target_id: str
    type: str
    properties: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: Optional[datetime]=None

class GraphBackend(ABC):
    @abstractmethod
    def add_entity(self, entity_type: str, properties: dict| None= None) -> Entity:
        pass
    
    @abstractmethod
    def get_entity(self,entity_id: str) -> Entity | None:
        pass

    @abstractmethod
    def update_entity(self, entity_id: str,properties: dict) -> Entity:
        pass
    
    @abstractmethod
    def remove_entity(self, entity_id: str) -> None:
        pass
    
    @abstractmethod
    def add_relationship(
        self, 
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict| None = None,
        valid_from: datetime | None=None
    ) -> Relationship:
        pass
    
    @abstractmethod
    def get_relationships(
        self,
        entity_id: str,
        direction: str = "both",
        rel_type: str|None = None
    ) -> list[Relationship]:
        pass
    
    @abstractmethod
    def expire_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        valid_to: datetime | None = None
    ) -> None:
        pass
    
    @abstractmethod
    def get_neighbours(
        self,
        entity_id: str,
        depth: int = 1,
        timestamp: datetime|None=None
    ) -> list[Entity]:
        pass

    @abstractmethod
    def get_snapshot(
        self,
        timestamp: datetime
    ) -> tuple[list[Entity], list[Relationship]]:
        pass
    
    @abstractmethod
    def get_entity_history(self, entity_id: str) -> list[Relationship]:
        pass
     