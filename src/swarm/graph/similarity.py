from abc import ABC, abstractmethod                                           
from datetime import datetime                                                 
                                                                            
from pydantic import BaseModel                                         
                                                                            
from swarm.graph.base import GraphBackend, utc_now                            

import math 
import random
                                                                                
class SimilarityScorer(ABC):
    """One dimension of similarity between two entities."""                   
                                                                            
    @property                                                                 
    @abstractmethod                                                           
    def name(self) -> str:                                                    
        pass                                                                  

    @abstractmethod                                                           
    def score(  
        self,                                                                 
        u: str, 
        v: str,                                                               
        adjacency: dict[str, list[tuple[str, str, float]]],                   
    ) -> float:                                                               
        """Return similarity in [0, 1] between two entity IDs."""             
        pass                                                                  
                                                                            
                                                                            
class SimilarityProfile(BaseModel):                                           
    entity_a: str                                                             
    entity_b: str                                                             
    timestamp: datetime                                                       
    scores: dict[str, float]                                                  
    collapsed: float | None = None                                            
    weights_used: dict[str, float] | None = None                              
                                                                            
                                                                            
class DomainWeighting(ABC):                                                   
    """Domain-specific collapse rule: vector -> scalar."""                    
                                                                            
    @abstractmethod
    def collapse(self, scores: dict[str, float]) -> tuple[float, dict[str,    
float]]:                                                                      
        """Return (scalar, weights_used)."""
        pass                                                                  
                
                                                                            
class SimilarityEngine:
    """Holds registered scorers, produces SimilarityProfiles."""              
                                                                            
    def __init__(                                                             
        self,                                                                 
        graph: GraphBackend,                                                  
        scorers: list[SimilarityScorer],                                      
        weighting: DomainWeighting | None = None,                             
    ):                                                                        
        self._graph = graph                                                   
        self._scorers = scorers                                               
        self._weighting = weighting                                           
                                                                            
    def compute(                                                              
        self, u: str, v: str, timestamp: datetime | None = None               
    ) -> SimilarityProfile:                                                   
        ts = timestamp or utc_now()                                           
        adjacency = self._graph.get_weighted_snapshot(ts)                     
        scores = {s.name: s.score(u, v, adjacency) for s in self._scorers}    
        collapsed = None                                                      
        weights_used = None                                                   
        if self._weighting:                                                   
            collapsed, weights_used = self._weighting.collapse(scores)        
        return SimilarityProfile(                                             
            entity_a=u,                                                       
            entity_b=v,
            timestamp=ts,                                                     
            scores=scores,
            collapsed=collapsed,                                              
            weights_used=weights_used,
        )

class AdamicAdarScorer(SimilarityScorer):

    @property
    def name(self) -> str:
        return "adamic_adar"

    def score(self, u: str, v: str, adjacency: dict[str, list[tuple[str, str, float]]]) -> float:
        neighbors_u = {target for target, _, _ in adjacency.get(u, [])}
        neighbors_v = {target for target, _, _ in adjacency.get(v, [])}
        common = neighbors_u & neighbors_v
        if not common:
            return 0.0
        total = 0.0
        for z in common:
            degree_z = len(adjacency.get(z, []))
            if degree_z > 1:
                total += 1.0 / math.log(degree_z)
        if total == 0.0:
            return 0.0
        max_possible = sum(
            1.0 / math.log(len(adjacency.get(z, [])))
            for z in (neighbors_u | neighbors_v)
            if len(adjacency.get(z, [])) > 1
        )
        return total / max_possible if max_possible > 0 else 0.0


class PPRScorer(SimilarityScorer):

    def __init__(self, alpha: float = 0.85, iterations: int = 20):
        self._alpha = alpha
        self._iterations = iterations

    @property
    def name(self) -> str:
        return "ppr"

    def score(self, u: str, v: str, adjacency: dict[str, list[tuple[str, str, float]]]) -> float:
        all_nodes = set(adjacency.keys())
        if u not in all_nodes or v not in all_nodes:
            return 0.0
        scores: dict[str, float] = {node: 0.0 for node in all_nodes}
        scores[u] = 1.0
        for _ in range(self._iterations):
            new_scores: dict[str, float] = {node: 0.0 for node in all_nodes}
            for node in all_nodes:
                neighbors = adjacency.get(node, [])
                total_weight = sum(w for _, _, w in neighbors)
                if total_weight == 0:
                    continue
                for target, _, w in neighbors:
                    new_scores[target] += (1 - self._alpha) * scores[node] * (w / total_weight)
            for node in all_nodes:
                new_scores[node] += self._alpha * (1.0 if node == u else 0.0)
            scores = new_scores
        return scores.get(v, 0.0)


class CausalWalkScorer(SimilarityScorer):

    def __init__(self, num_walks: int = 100, max_steps: int = 5, seed: int | None = None):
        self._num_walks = num_walks
        self._max_steps = max_steps
        self._rng = random.Random(seed)

    @property
    def name(self) -> str:
        return "causal_walk"

    def score(self, u: str, v: str, adjacency: dict[str, list[tuple[str, str, float]]]) -> float:
        if u not in adjacency:
            return 0.0
        hits = 0
        for _ in range(self._num_walks):
            current = u
            last_weight = 1.0
            for _ in range(self._max_steps):
                neighbors = adjacency.get(current, [])
                causal = [(t, w) for t, _, w in neighbors if w <= last_weight]
                if not causal:
                    break
                targets, weights = zip(*causal)
                total = sum(weights)
                pick = self._rng.random() * total
                cumulative = 0.0
                chosen_target = targets[0]
                chosen_weight = weights[0]
                for t, w in zip(targets, weights):
                    cumulative += w
                    if cumulative >= pick:
                        chosen_target = t
                        chosen_weight = w
                        break
                current = chosen_target
                last_weight = chosen_weight
                if current == v:
                    hits += 1
                    break
        return hits / self._num_walks