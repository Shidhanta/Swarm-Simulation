"""Event-keyed hashing for causally valid counterfactual replay.

Replaces sequential PRNG draws with deterministic hash-based randomness.
Each random decision is keyed on (seed, tick, event_type, entity_id),
ensuring that removing or adding agents does not shift randomness
for other agents.

Reference: Buffalo et al. (2026), "Realizing Common Random Numbers:
Event-Keyed Hashing for Causally Valid Stochastic Models"
"""

import hashlib


def event_random(seed: int, tick: int, event: str, entity_id: str) -> float:
    """Deterministic random float in [0, 1) for a specific simulation event."""
    key = f"{seed}:{tick}:{event}:{entity_id}"
    h = hashlib.sha256(key.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def event_random_pair(seed: int, tick: int, event: str, id_a: str, id_b: str) -> float:
    """Deterministic random float for an event involving two entities."""
    pair_key = f"{min(id_a, id_b)}:{max(id_a, id_b)}"
    key = f"{seed}:{tick}:{event}:{pair_key}"
    h = hashlib.sha256(key.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF
