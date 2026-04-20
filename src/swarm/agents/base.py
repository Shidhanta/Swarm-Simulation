from abc import ABC, abstractmethod                                           
from typing import Callable
                                                                                
from pydantic import BaseModel, Field                                         
                                                                                
from swarm.graph.base import GraphBackend


class AgentPersona(BaseModel):
    """Structured persona derived from a graph entity."""
    entity_id: str
    name: str                                                                 
    role: str
    traits: list[str] = Field(default_factory=list)                           
    goals: list[str] = Field(default_factory=list)
    backstory: str = ""
    communication_style: str = ""

class PersonaGenerator(ABC):                                                  
    """Port: generates agent personas from graph entities."""
                                                                                
    @abstractmethod
    def generate(                                                             
        self,                                                                 
        entity_id: str,                                                       
        graph: GraphBackend,                                                  
        llm_fn: Callable[[str], str],                                         
    ) -> AgentPersona:                                                        
        pass

def persona_to_system_message(persona: AgentPersona) -> str:                  
    """Format an AgentPersona into a CAMEL-ready system message."""           
    parts = [                                                                 
        f"You are {persona.name}, a {persona.role}.",                         
    ]                                                                         
    if persona.backstory:                                                     
        parts.append(f"\nBackground: {persona.backstory}")                    
    if persona.traits:                                                        
        parts.append(f"\nPersonality traits: {', '.join(persona.traits)}")    
    if persona.goals:                                                         
        parts.append(f"\nYour goals: {'; '.join(persona.goals)}")
    if persona.communication_style:
        parts.append(f"\nCommunication style: {persona.communication_style}")
    return "\n".join(parts)    

