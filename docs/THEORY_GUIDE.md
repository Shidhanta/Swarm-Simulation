# Swarm Simulation — Technical Reference

A living document covering the theory, algorithms, architecture, and implementation details of this project. Updated with each commit.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Knowledge Graphs](#knowledge-graphs)
4. [Temporal Knowledge Graphs](#temporal-knowledge-graphs)
5. [Swarm Intelligence and Emergent Behavior](#swarm-intelligence-and-emergent-behavior)
6. [Multi-Agent Systems](#multi-agent-systems)
7. [CAMEL-AI Framework](#camel-ai-framework)
8. [Graph Algorithms Used](#graph-algorithms-used)
9. [Similarity and Proximity](#similarity-and-proximity)
10. [LLM Integration Patterns](#llm-integration-patterns)
11. [Build Log](#build-log)
12. [Interview Q&A](#interview-qa)

---

## Project Overview

A generalized swarm intelligence simulation engine that models emergent behavior by combining temporal knowledge graphs with autonomous multi-agent systems.

The engine is domain-agnostic — it provides the simulation infrastructure, and domain-specific behavior (stock trading, opinion dynamics, etc.) is plugged in as configuration and agent personas.

**Core loop:**
1. Seed the knowledge graph with domain entities and relationships
2. Generate agent personas from graph structure
3. Run time-stepped simulation where agents interact, reason, and update shared knowledge
4. Detect emergent patterns (consensus, polarization, cascades)
5. Support intervention injection and counterfactual replay

---

## Architecture

### Ports and Adapters (Hexagonal Architecture)

The system separates domain logic from infrastructure through abstract interfaces. Each infrastructure concern (graph storage, LLM provider, UI) is an "adapter" that implements a "port" (abstract interface).

```
src/swarm/
├── graph/          # Port: GraphBackend ABC
│                   # Adapters: NetworkX (default), Neo4j (optional)
├── llm/            # Port: LLMProvider ABC
│                   # Adapters: Ollama (default), Gemini (optional)
├── agents/         # Agent personas, communication, society management
├── simulation/     # Time-stepped execution engine, event system
└── examples/       # Domain-specific simulations (stock market, opinion dynamics)
```

**Why this pattern:** The simulation engine should not care whether entities live in an in-memory graph or a database. Swapping backends is a configuration change, not a code change. This also means each adapter can be tested in isolation.

### Dependency Flow

```
configs/default.yaml
        │
        ▼
   LLM Provider ◄──── Agent Layer ────► Knowledge Graph
        │                  │                    │
        ▼                  ▼                    ▼
   Ollama/Gemini    CAMEL-AI Society     NetworkX/Neo4j
                           │
                           ▼
                   Simulation Engine
                           │
                           ▼
                  Emergent Behavior Detection
```

### Configuration

All runtime parameters are externalized in `configs/default.yaml`. The engine reads config at startup and passes relevant sections to each subsystem. No hardcoded values in business logic.

---

## Knowledge Graphs

### What They Are

A knowledge graph represents information as a directed network of **entities** (nodes) and **relationships** (edges). Each entity has a type (person, stock, topic, organization) and a property bag. Each relationship has a type (influences, trades, follows, reports_to) and its own properties.

### Why Graphs Over Relational Databases

| Concern | Relational DB | Knowledge Graph |
|---------|--------------|-----------------|
| Relationships | Foreign keys + JOIN tables | First-class edges with properties |
| Traversal (N hops) | N recursive JOINs (expensive) | Native graph traversal (O(neighbors)) |
| Schema flexibility | Fixed schema, migrations | Property bags, schema-on-read |
| Modeling social/market networks | Unnatural fit | Direct 1:1 mapping |

Graphs are the natural data structure when the core problem is about **how entities influence each other**. Social networks, market relationships, influence chains, and information flow are all inherently graph problems.

### Representation in This Project

- **Entities** are stored as graph nodes with: `id` (UUID), `type`, `properties` (dict), `created_at`, `updated_at`
- **Relationships** are stored as directed edges with: `source_id`, `target_id`, `type`, `properties`, `created_at`, `valid_from`, `valid_to`
- The `GraphBackend` ABC defines the interface; NetworkX is the default implementation

### NetworkX vs Neo4j

**NetworkX** — Pure Python, in-memory. Zero infrastructure. Fast for small-to-medium graphs (up to ~100K nodes). Ideal for development, testing, and single-machine simulations.

**Neo4j** — Dedicated graph database with its own query language (Cypher). Persistent storage, ACID transactions, scales to billions of nodes. Required for production-scale simulations or when the graph must survive process restarts.

The codebase uses NetworkX by default. Neo4j is an optional install (`pip install -e ".[neo4j]"`) that implements the same `GraphBackend` interface.

---

## Temporal Knowledge Graphs

### The Problem with Static Graphs

Standard knowledge graphs represent **current state only**. If agent A stops influencing agent B, the edge is deleted — and with it, any record that the influence ever existed.

For simulation, this is unacceptable. Understanding **how** the system evolved is as important as understanding its current state.

### How Temporal KGs Work

Every relationship carries time metadata:
- `valid_from` — when this relationship became active
- `valid_to` — when this relationship ended (None if still active)
- `created_at` — when the system first learned about this relationship

This enables three types of temporal queries:

1. **Current state** — all relationships where `valid_to is None`
2. **Point-in-time snapshot** — all relationships where `valid_from <= T` and (`valid_to is None` or `valid_to > T`)
3. **History** — all relationships for a given entity, ordered by time, showing the full evolution

### Causal Reasoning

With temporal data, you can answer: *"Why did agent B change behavior at step 50?"*

Trace backward: find all relationships that changed near step 50 → follow edges to find what influenced those changes → reconstruct the causal chain.

This is the foundation for the intervention replay feature — compare causal chains with and without a specific event.

### Implementation Notes

In NetworkX, temporal data is stored as edge attributes. The `get_snapshot(timestamp)` method filters the graph by time range. For Neo4j, this translates to Cypher queries with temporal predicates.

---

## Swarm Intelligence and Emergent Behavior

### Swarm Intelligence

Swarm intelligence is collective intelligent behavior arising from simple individual rules with no central coordination. Classic examples:

- **Ant colony optimization** — individual ants follow pheromone trails; the colony finds shortest paths
- **Flocking (Boids algorithm)** — three simple rules (separation, alignment, cohesion) produce realistic flocking
- **Market price discovery** — individual traders acting on local information collectively determine market prices

The key insight: **complex global behavior emerges from simple local interactions**. No single agent is "in charge" or has a global view.

### Emergent Behavior in This Project

Agents interact through the knowledge graph — reading from it, writing to it, and reacting to changes. Over many time steps, collective patterns form:

- **Consensus** — agents converge toward similar beliefs or actions
- **Polarization** — agents diverge into distinct camps with opposing positions
- **Information cascades** — a piece of information spreads rapidly through the network, potentially causing coordinated behavior changes
- **Clustering** — agents form subgroups based on shared properties or mutual interactions

### Detection Algorithms (Implemented)

The `EmergenceDetector` monitors 26 metrics across 6 categories at tiered intervals:

**A. Opinion Dynamics (every tick):**
- **Consensus** — mean pairwise distance normalized to [0,1]. Score > 0.9 = consensus reached.
- **Polarization** — bimodality coefficient on PCA-projected opinion distribution. BC > 5/9 = bimodal.
- **Fragmentation** — hierarchical clustering with Ward linkage. Effective Number of Parties (ENP) > 2.5 = fragmented.
- **Extremization** — mean distance from opinion-space center. Detects group-level drift toward extremes.
- **Convergence rate** — exponential decay fit on variance time series. Positive = settling, negative = diverging.

**B. Network Structure (every 5-10 ticks):**
- **Echo chambers** — modularity (Newman's Q) > 0.3 AND echo chamber index > 0.5 (opinion-community alignment).
- **Fragmentation** — connected component analysis. Herfindahl-based fragmentation index.
- **Hub emergence** — Freeman's degree centralization + Gini coefficient of degree distribution.
- **Small-world** — Humphries-Gurney sigma coefficient. Tracks if high-clustering + short-paths persists.
- **Algebraic connectivity** — Fiedler value (second eigenvalue of Laplacian). Approaching 0 = near disconnection.
- **Core-periphery** — iterative coreness assignment. Density gap between core and periphery subgraphs.

**C. Phase Transitions (every tick):**
- **Critical slowing down** — AR(1) autocorrelation of variance time series. > 0.85 and trending up = near tipping point.
- **Susceptibility peaks** — N × trace(covariance). Sharp peaks indicate phase transitions.
- **Flickering** — sign-change rate in projected mean opinion. High rate = system oscillating between attractors.
- **Skewness shifts** — Kendall tau trend test on rolling skewness. Non-zero trend = asymmetric transition approaching.
- **Rolling variance increase** — variance-of-variance over window. Increases before critical transitions (Scheffer et al., 2009).

**D. Temporal Patterns (every tick / every 10 ticks):**
- **Burst detection** — z-score of activity rate (mean belief shift magnitude). z > 2.5 = activity burst.
- **Periodicity** — autocorrelation peak detection on variance time series. Detects oscillatory regimes.
- **Trend detection** — Mann-Kendall test for monotonic drift. |tau| > 0.3 with p < 0.05 = significant trend.

**E. Collective Behavior (every 5-10 ticks):**
- **Herding** — cross-correlation of belief-change magnitudes at lag 1-3 between connected pairs. Detects leader-follower dynamics.
- **Contrarianism** — agents whose belief shifts systematically anti-correlate with population mean shift.
- **Free riding** — agents that interact but don't update (low shift magnitude despite interactions).
- **Groupthink** — intra-community opinion diversity collapse relative to full population diversity.

**Research grounding for detection thresholds:**
- Bimodality coefficient > 5/9: Pfister et al. (2013), standard threshold from the statistical literature
- Modularity > 0.3: Newman (2004), empirical threshold for meaningful community structure
- AR(1) > 0.85 as early warning: Scheffer et al. (2009), "Early-warning signals for critical transitions"
- Susceptibility peaks at phase transitions: from statistical physics (magnetic susceptibility analogy)
- Kendall tau for trend detection: Mann (1945), non-parametric trend test robust to non-normality

---

## Multi-Agent Systems

### Theory

A multi-agent system (MAS) consists of multiple autonomous agents that:
1. **Perceive** their environment (in this case, their knowledge graph neighborhood)
2. **Reason** about what to do (using LLM-based reasoning)
3. **Act** on the environment (update the knowledge graph, communicate with other agents)

### Agent Properties in This Project

Each agent has:
- **Persona** — personality, role, expertise, biases (generated from graph position)
- **Memory** — what the agent has observed and done (stored as graph relationships)
- **Neighborhood** — the agent's local view of the knowledge graph (entities within N hops)
- **Behavioral rules** — how the agent decides what to do each tick

### Persona Generation Pipeline

Agent personas are not hand-authored — they are derived from graph structure. The pipeline:

1. **Select entity** — pick a graph node to become an agent
2. **Extract context** — pull its 1-2 hop neighborhood, all relationships, entity properties
3. **Format for LLM** — relationships rendered as `source --[TYPE]--> target`, neighbors listed with types
4. **LLM generates persona** — structured JSON output: name, role, traits, goals, backstory, communication_style
5. **Parse into model** — `AgentPersona` (Pydantic) holds the structured result
6. **Bridge to CAMEL** — `persona_to_system_message()` converts the model into a system prompt string

This means personas are:
- **Graph-grounded** — traits and goals reflect actual entity position and connections
- **Regenerable** — as the graph evolves, personas can be regenerated to reflect changed circumstances
- **Traceable** — every persona links back to its source entity via `entity_id`

### Agent-Graph Coupling

This is a key design decision: **agent behavior is a function of graph structure**. A well-connected agent with many information sources behaves differently from an isolated one. As the graph evolves (new relationships form, old ones expire), agent behavior naturally adapts.

This means emergent behavior is truly emergent — it arises from the interaction between agent reasoning and graph topology, not from scripted scenarios.

### Communication Model

Agents interact through a turn-based conversation protocol:

1. **Topic selection** — the simulation engine selects a topic for two agents to discuss (based on similarity, shared context, or simulation events)
2. **Alternating turns** — Agent A speaks, Agent B responds, alternating for N turns (default 6)
3. **Tool access** — during conversation, agents can query the knowledge graph via `KnowledgeGraphToolkit` (search entities, get neighbors, get relationships)
4. **Result capture** — the full conversation is stored as a `ConversationResult` for later analysis by the emergence detector
5. **Memory reset** — after each conversation, the agent's chat history is cleared. Persistent memory lives in the graph, not in CAMEL's context window.

The `SwarmAgent` wrapper hides CAMEL internals from the rest of the system. The simulation engine interacts only with `SwarmAgent.step()` and `run_conversation()` — it never touches CAMEL classes directly.

---

## CAMEL-AI Framework

### What It Is

CAMEL (Communicative Agents for "Mind" Exploration of Large Language Model Society) is a framework for building multi-agent systems. Its core abstraction is **role-playing**: assign distinct roles to LLM-powered agents and let them converse autonomously.

### Key Concepts

- **Role-playing** — Two agents with different system prompts (roles) converse to accomplish a task
- **Society** — Multiple agents forming a network with configurable interaction patterns
- **Tool use** — Agents can invoke external tools (APIs, code execution, graph queries)
- **Task management** — Orchestrating multi-agent workflows

### How This Project Uses CAMEL

CAMEL provides the LLM-agent primitives; this project provides the orchestration, graph coupling, and emergence detection.

**What CAMEL handles:**
- `ChatAgent` — stateful conversation with system message, memory, and tool calling
- `ModelFactory` — connecting to Ollama/Gemini via OpenAI-compatible API
- `FunctionTool` — auto-generating tool schemas from Python docstrings
- Message passing protocol between agents

**What this project handles (not built into CAMEL):**
- Network topology — who talks to whom (driven by similarity scores)
- Persona generation — deriving system messages from graph structure
- Graph-as-tool — `KnowledgeGraphToolkit` wraps `GraphBackend` methods as CAMEL tools
- Simulation orchestration — tick-based scheduling, conversation routing
- Emergence detection — observing patterns across conversation histories

**Integration flow:**
```
GraphBackend → GraphPersonaGenerator → AgentPersona
    → persona_to_system_message() → CAMEL ChatAgent(system_message=...)
    + KnowledgeGraphToolkit → CAMEL FunctionTool(...)
    = SwarmAgent (our wrapper)
```

**Key design choice:** `SwarmAgent` wraps `ChatAgent` rather than extending it. This means we control the interface — if CAMEL's API changes, only `communication.py` needs updating. The rest of the system only knows about `SwarmAgent.step()` and `run_conversation()`.

### CAMEL vs Other Frameworks

| Framework | Focus | How It Differs |
|-----------|-------|----------------|
| CAMEL-AI | Autonomous role-playing, agent societies | Research-oriented, deep multi-agent communication |
| AutoGen | Conversable agents with human-in-loop | More human intervention, less autonomy |
| CrewAI | Task pipelines with crew roles | Pipeline-oriented, less emergent interaction |
| LangChain | Single-agent RAG and tool orchestration | Not designed for multi-agent simulation |

---

## Graph Algorithms Used

### Implemented

- **BFS traversal** (`get_neighbours` with depth parameter) — discovers all entities reachable within N hops from a starting node. Uses a deque-based iterative BFS (not recursive) to avoid stack overflow on deep graphs. Respects temporal validity — expired relationships are not traversed.

- **Personalized PageRank** (`PPRScorer` in similarity.py) — power iteration over time-weighted adjacency. Computes reachability probability from a source node to all other nodes. Used for global structural similarity.

- **Adamic-Adar Index** (`AdamicAdarScorer` in similarity.py) — shared-neighbor similarity weighted by inverse log-degree. Rare shared connections score higher than shared hubs. Used for local structural similarity.

- **Causal Anonymous Walks** (`CausalWalkScorer` in similarity.py) — random walks with temporal ordering constraint. Walks only follow edges in decreasing weight order (forward in time). Used for temporal co-occurrence similarity.

### Planned

- **Community detection (Louvain/Girvan-Newman)** — identifying agent clusters
- **Graph embeddings (Node2Vec or spectral)** — encoding agent position as feature vectors for adaptive behavior
- **Temporal motif detection** — finding recurring patterns in graph evolution
- **Spectral gap tracking** — eigenvalue analysis of the Laplacian for fragmentation early warning
- **Transfer entropy** — directed information flow measurement between agent pairs

---

## Similarity and Proximity

### The Problem: Why a Single Similarity Score Fails

Between any two agents in a swarm simulation, there are multiple independent reasons they might be "similar" — shared connections, structural proximity, temporal co-occurrence. Collapsing these into a single number loses the texture that emergence detection needs.

A consensus event looks different in each dimension: PPR scores converge (structural homogenization) while Adamic-Adar stays stable (no new shared connections formed — the convergence happened through multi-hop influence). A single scalar would show "similarity went up" but hide the mechanism.

### Research Grounding

The hybrid multi-score approach is grounded in several lines of published research:

**Foundational:**
- Liben-Nowell & Kleinberg (2007) — "The Link Prediction Problem for Social Networks" — demonstrated that combining local (Adamic-Adar) and global (PageRank/Katz) measures outperforms either alone
- Lü & Zhou (2011) — "Link prediction in complex networks: A survey" — formalized linear combination of local + global indices and showed they capture complementary information

**Multi-Scale Learned Combination (Neo-GNN approach):**
- Yun et al. (NeurIPS 2021) — "Neo-GNN: A New Graph Neural Network for Link Prediction" — learns weights for adjacency matrix powers A, A², A³... where A¹ captures local (common neighbors), Aᵏ converges to PPR-like global behavior. Demonstrates that optimal weighting is dataset-dependent, not universal.

**Temporal and Causal:**
- Wang et al. (ICLR 2021) — "Inductive Representation Learning in Temporal Networks via Causal Anonymous Walks" (CAWN) — temporal random walks respecting time ordering, combining local (short walks) and global (long walks) temporal structure
- Liu et al. (AAAI 2022) — "TLogic: Temporal Logical Rules for Explainable Link Prediction" — purely symbolic temporal rule mining via time-respecting walks. CPU-only, no neural networks required.
- Trivedi et al. (2017) — "Know-Evolve: Deep Temporal Reasoning for Dynamic Knowledge Graphs" — exponential time decay on edge weights: `w(edge) = exp(-λ · Δt)`

**Scalable Subgraph Methods:**
- Chamberlain et al. (ICLR 2023) — "BUDDY/ELPH" — sketch-based approximation of subgraph features capturing both local overlap and multi-hop structure without expensive extraction
- Yin et al. (NeurIPS 2022) — "SUREL: Scalable Subgraph-Based Link Prediction" — pre-computed walk structures at multiple scales

### Design: Similarity Vector, Not Scalar

The system computes a **SimilarityProfile** — a named vector of scores — for each entity pair:

```
SimilarityProfile(u, v, t) = {
    "ppr": 0.72,            # global structural proximity
    "adamic_adar": 0.45,    # local shared-neighbor signal
    "causal_walk": 0.61,    # temporal co-occurrence via time-respecting paths
    ...domain_scores...     # extensible per simulation domain
}
```

Two consumers use this differently:

1. **Agent interaction layer** — a domain-specific `DomainWeighting` collapses the vector to a scalar that drives who talks to whom and influence strength. Stock market might weight temporal co-occurrence highest (herding from recent shared news), social media might weight structural proximity (echo chambers from topology).

2. **Emergence detection layer** — watches the full vector distribution over time. Never sees the collapsed scalar. Patterns in the raw dimensions reveal emergence:
   - Consensus: PPR scores converging across agent pairs
   - Polarization: Adamic-Adar scores clustering bimodally
   - Cascade: Causal walk scores spiking in wave patterns

Both the full vector and the collapsed scalar are maintained per tick — the scalar explains agent behavior, the vector explains system-level phenomena.

### Core Scorers

#### Adamic-Adar (Temporal)

Based on Adamic & Adar (2003), extended with temporal decay from the weighted snapshot.

For entities u and v, the score is:

```
AA(u, v) = Σ_{z ∈ N(u) ∩ N(v)} 1 / log(|N(z)|)
```

Where N(x) is the set of neighbors of x in the time-decayed adjacency. Rare shared connections (low-degree z) contribute more than shared hubs. Normalized to [0, 1] by dividing by the maximum possible score (all neighbors shared).

**What it captures:** Local, concrete shared context. Two agents connected to the same niche analyst are more meaningfully similar than two agents both connected to a major news source.

#### Personalized PageRank (Temporal)

Power iteration implementation of PPR with teleport probability α (default 0.85). Edge transition probabilities are weighted by temporal decay.

```
PPR_u(v) = α · 1(v=u) + (1-α) · Σ_{w→v} PPR_u(w) · weight(w→v) / Σ_{w→*} weight(w→*)
```

Iterates until convergence (default 20 iterations, sufficient for graphs under 100K nodes).

**What it captures:** Global structural reachability. How easily information flows from u to v through the entire network, weighted by edge recency. Two agents may have no shared neighbors but still be strongly connected through the broader graph topology.

#### Causal Walk

Inspired by CAWN (Wang et al., 2021). Samples random walks from u that respect temporal ordering — each step follows an edge with weight ≤ the previous edge's weight (since `weight = exp(-λΔt)`, lower weight = older edge, so walks move from recent edges toward older ones).

```
CausalWalk(u, v) = (walks from u reaching v) / (total walks sampled)
```

The causal constraint means walks simulate realistic information propagation paths — information enters through recent connections and flows through established older channels.

**What it captures:** Temporal co-occurrence and information propagation potential. High score means there exist plausible time-respecting paths through which information could have flowed from u to v.

### Extensibility

The `SimilarityScorer` ABC is a port — domain-specific scorers plug in as adapters:

- Stock domain: `SectorAffinityScorer`, `PortfolioOverlapScorer`
- Social domain: `OpinionDistanceScorer`, `EchoChamberScorer`

These register with the `SimilarityEngine` alongside the core three. The `DomainWeighting` ABC defines how to collapse the full vector for driving agent interactions — each domain provides its own weighting strategy.

The adjacency structure is passed to all scorers as a generic `dict[str, list[tuple[str, str, float]]]` — no backend coupling. Any future scorer (spectral, embedding-based, etc.) operates on the same structure.

---

## LLM Integration Patterns

### Provider Abstraction

The `LLMProvider` ABC defines a unified interface. Implementations handle provider-specific details (API format, auth, streaming).

### Cost Management Strategies

Running N agents × T time steps can mean thousands of LLM calls. Strategies to manage this:

1. **Local models via Ollama** — zero marginal cost, runs on consumer hardware
2. **Batched interactions** — not every agent acts every tick; agents take turns based on priority or randomization
3. **Rule-based fallback** — routine decisions (no new information, low importance interactions) use deterministic rules instead of LLM calls
4. **Response caching** — identical prompts in similar graph states can reuse prior responses
5. **Tiered models** — use smaller/faster models for routine interactions, larger models for critical decisions

### Prompt Design

Agent prompts are assembled from:
1. Base persona (from graph data)
2. Current knowledge (relevant graph neighborhood, serialized)
3. Recent memory (last N interactions)
4. Task context (what the agent is supposed to do this tick)

This means prompts are dynamic and reflect the current simulation state, not static templates.

---

## Build Log

A record of what was built in each commit and the reasoning behind key decisions.

### Commit 1: `init: project scaffolding with src layout and config`

**What was built:**
- Python package structure using `src/` layout
- `pyproject.toml` with core dependencies and optional extras (`neo4j`, `gemini`, `ui`, `dev`)
- `configs/default.yaml` for externalized configuration
- Subpackage stubs: `graph/`, `agents/`, `simulation/`, `llm/`, `examples/`

**Key decisions and reasoning:**
- **`src/` layout** — prevents accidental import of the local package during testing. This is the recommended Python packaging approach per PEP 517/518.
- **Optional dependencies as extras** — Neo4j driver, Gemini SDK, and UI framework are not required for the core engine. Installing them is opt-in: `pip install -e ".[neo4j]"`. Keeps the default install lightweight.
- **YAML config over .env or Python config** — YAML supports nested structures (LLM settings, graph settings, simulation parameters) more naturally than flat key-value formats.

### Commit 2: `feat: core knowledge graph with temporal relationships`

**What was built:**
- `src/swarm/graph/base.py` — Pydantic data models (`Entity`, `Relationship`) and `GraphBackend` ABC
- `src/swarm/graph/networkx_backend.py` — Full NetworkX implementation of the graph backend
- `src/swarm/graph/__init__.py` — Public API re-exports

**Key decisions and reasoning:**

- **Pydantic models over dataclasses** — Pydantic gives us runtime validation, serialization to/from JSON (useful for API layer later), and immutability control. If an entity is created with invalid data, it fails immediately at construction rather than causing subtle bugs downstream.

- **`MultiDiGraph` over `DiGraph`** — Two entities can have multiple relationship types between them (e.g., agent A both "follows" and "trades_with" agent B). `MultiDiGraph` supports this via the `key` parameter on edges. A regular `DiGraph` only allows one edge per node pair.

- **UUID4 for entity IDs** — Universally unique, no coordination needed. Callers never manage IDs — they're generated internally by `add_entity`. This prevents collisions when merging graphs or running distributed simulations.

- **`valid_from` / `valid_to` temporal model** — Relationships are never deleted, only expired (by setting `valid_to`). This is the "bitemporal" pattern from database theory: every fact has a validity period. The advantages:
  - Full audit trail — you can always see what the graph looked like at any point in history
  - Causal reasoning — trace back through time to understand why something changed
  - Counterfactual analysis — replay simulations from a snapshot without losing future data

- **`_is_active()` helper** — Centralizes the temporal filtering logic (`valid_from <= ts` and `valid_to is None or valid_to > ts`). Used by `get_neighbours`, `get_snapshot`, and will be reused everywhere. Single source of truth for "is this relationship currently valid?"

- **BFS for `get_neighbours`** — Manual BFS with a `deque` instead of using `nx.bfs_tree` because:
  1. We need to filter by temporal validity at each hop
  2. `nx.bfs_tree` doesn't support custom edge predicates
  3. We traverse both in-edges and out-edges (undirected neighbor discovery on a directed graph)
  
  The algorithm:
  ```
  visited = {start_node}
  queue = [(start_node, depth=0)]
  while queue not empty:
      node, d = queue.popleft()
      if d >= max_depth: skip
      for each neighbor via active edges:
          if not visited:
              add to results, mark visited, enqueue at d+1
  ```
  Time complexity: O(V + E) where V and E are vertices and edges within the depth limit.

- **Double underscore (`__graph`) for the internal graph** — Name mangling prevents subclasses or external code from accidentally accessing the raw NetworkX graph, enforcing that all access goes through the abstract interface methods.

- **`get_entity_history` returns sorted by `created_at`** — Chronological ordering makes it natural to read as a timeline. Includes both active and expired relationships — this is the full history, not the current state.

**Design patterns used:**
- **Strategy pattern** — `GraphBackend` ABC defines the interface; `NetworkXBackend` is one strategy. Adding `Neo4jBackend` later is just another strategy implementing the same interface.
- **Repository pattern** — The graph backend acts as a repository for entities and relationships, abstracting away storage details.
- **Temporal pattern (bitemporal)** — Facts carry validity periods, enabling point-in-time queries and full history reconstruction.

### Commit 3: `feat: graph ingestion pipeline with episodic lineage`

**What was built:**
- `src/swarm/graph/ontology.py` — `EntityType`, `RelationshipType`, `Ontology` models with prompt formatting
- `src/swarm/graph/prompts.py` — 5 structured prompt templates (ontology generation, entity extraction/resolution, relationship extraction/resolution)
- `src/swarm/graph/ingestion.py` — Full ingestion pipeline: episode creation, entity/relationship extraction and resolution, lineage tracking
- Updated `base.py` with `search_entities()` method on the ABC
- Updated `networkx_backend.py` with `search_entities()` implementation

**Key decisions and reasoning:**

- **Episode-centric ingestion (inspired by Graphiti/Zep)** — Every piece of ingested text is stored as an Episode entity in the graph. All facts extracted from that text get `SOURCED_FROM` edges pointing back to the episode. This enables lineage tracking ("where did this fact come from?"), counterfactual analysis ("what if this episode never happened?"), and audit trails.

- **Ontology-constrained extraction (inspired by MiroFish)** — Extraction is constrained by a declared ontology (allowed entity types and relationship types). This guarantees consistent graph structure across multiple ingestion episodes. Without it, an LLM might output "Company" in one call and "Corporation" in the next for the same concept.

- **Two-mode ontology input** — Users can provide their own ontology (full control) or let the LLM generate one from the seed text + domain. There is no unconstrained mode — ingestion always operates against an ontology. This eliminates a code path and ensures agents can always rely on predictable graph schema.

- **Ontology stored in graph as nodes** — Ontology definitions are stored as `OntologyEntity` and `OntologyRelationship` nodes linked to the episode that introduced them. This means agents can introspect the schema ("what types of entities exist?") and ontology changes across simulation runs are tracked with lineage.

- **`Callable[[str], str]` for LLM calls** — The ingestion pipeline takes any function that maps prompt → response string. This is provider-agnostic by design — works with Ollama, Gemini, OpenAI, or a mock function for testing. No dependency on the LLM abstraction layer (which is built separately).

- **4 LLM calls per episode (batched resolution)** — Entity resolution and relationship resolution are batched (all entities resolved in one call, all relationships in one call). Per-entity resolution would require N+M calls for N entities and M relationships. Batching keeps it fixed at 4 calls regardless of how many entities/relationships are extracted.

- **Entity resolution via LLM** — Rather than fuzzy string matching, we ask the LLM to determine if extracted entities match existing graph entities. The LLM can handle abbreviations ("Tesla" vs "Tesla Inc"), contextual equivalence ("the EV maker" → Tesla), and subtle distinctions that rule-based matching misses.

- **Relationship contradiction detection** — New relationships don't just get inserted blindly. They're checked against existing edges between the same entity pair. If a contradiction is found (e.g., "X is CEO of Y" replaced by "X is former CEO of Y"), the old edge is expired and the new one inserted. Facts are never deleted, only expired — preserving full history.

- **Structured prompts with JSON output schemas** — Prompts follow the MiroFish pattern: role description at top, explicit constraints (naming conventions, formatting rules), and a JSON schema showing the exact expected output format. The "no markdown fences, raw JSON only" instruction plus a cleanup regex (`_parse_json`) handles the common case where LLMs add code fences anyway.

- **`search_entities()` on the ABC** — Needed for entity resolution to retrieve candidate matches from the graph. Filters by entity type and does case-insensitive substring matching on the `name` property. Added to the ABC (not just NetworkX) because any backend will need this for ingestion to work.

**Design patterns used:**
- **Pipeline pattern** — Ingestion is a linear pipeline of discrete stages (episode → extract → resolve → insert), each stage consuming the output of the previous one.
- **Strategy pattern (again)** — `extract_fn: Callable[[str], str]` is a strategy for LLM interaction, injected at call time.
- **Event sourcing (inspiration)** — Episodes function like events in event sourcing. The graph state at any point can theoretically be reconstructed by replaying episodes in order. Each fact is traceable to the event that produced it.

**Algorithms:**
- **Entity resolution** — candidate retrieval via `search_entities()` (type + name substring filter), then LLM-based semantic matching. This is a two-stage approach: cheap filter first (reduce candidates), expensive LLM second (semantic judgment).
- **Contradiction detection** — for each entity pair with new relationships, retrieve all active (non-expired) existing relationships. LLM determines if any new fact invalidates an old one.

### Commit 4: `feat: LLM provider abstraction with fallback chain`

**What was built:**
- `src/swarm/llm/base.py` — `LLMProvider` ABC with `complete(prompt) -> str` and `as_callable()` helper
- `src/swarm/llm/ollama_provider.py` — Ollama adapter using the `ollama` Python SDK
- `src/swarm/llm/gemini_provider.py` — Google Gemini adapter (optional dependency, guarded import)
- `src/swarm/llm/fallback.py` — `FallbackProvider` wrapper for transparent failover
- `src/swarm/llm/factory.py` — `create_provider(config)` factory that builds provider chain from YAML config
- `src/swarm/llm/__init__.py` — Public API re-exports
- Updated `configs/default.yaml` with fallback and gemini config sections

**Key decisions and reasoning:**

- **`complete(prompt: str) -> str` as the sole interface** — The simplest possible contract. Takes a string prompt, returns a string response. No system prompt parameter, no message history, no streaming. The prompt templates already contain all instructions (role, constraints, schema), so a separate system prompt is unnecessary complexity. If streaming or multi-turn is needed later, those become separate methods on the ABC — they don't complicate the base contract.

- **`as_callable()` bridge method** — Returns `self.complete` as a `Callable[[str], str]`. This is the integration point with the ingestion pipeline, which was designed to accept any callable. The bridge makes the connection explicit without coupling `ingestion.py` to `LLMProvider`.

- **Fallback as a wrapper (decorator pattern)** — `FallbackProvider` wraps any two providers. If the primary raises `RuntimeError` or `ConnectionError`, it transparently retries with the fallback. This is composable — you could chain `FallbackProvider(primary, FallbackProvider(secondary, tertiary))` for three levels. The wrapper doesn't know or care what providers it wraps.

- **Factory function from config dict** — `create_provider(config)` reads the `llm` section of `default.yaml` and constructs the appropriate provider (or chain). This keeps provider construction out of business logic. The caller just passes the config and gets back an `LLMProvider` ready to use.

- **Ollama as default + fallback** — Ollama is local, free, and keyless. The default config uses `llama3` as primary and `llama3.2` as fallback (a smaller model that's more likely to be downloaded). If Ollama isn't running at all, a clear `ConnectionError` is raised with installation instructions.

- **Gemini as optional dependency with guarded import** — `google-generativeai` is only imported if the user selects the Gemini provider. The import is guarded with a try/except at module level, and `GeminiProvider.__init__` raises `ImportError` if the package isn't installed. This means the core engine has zero dependency on Google's SDK.

- **Deferred Gemini import in factory** — `factory.py` only imports `GeminiProvider` inside the `elif provider_type == "gemini"` branch. Users who never use Gemini never pay the import cost or need the package installed.

- **Error classification** — `OllamaProvider` raises `RuntimeError` for API-level errors (bad model name, generation failure) and `ConnectionError` for network-level errors (Ollama not running). `FallbackProvider` catches both — any failure triggers fallback, regardless of whether it's "model not found" or "server unreachable."

**Design patterns used:**
- **Strategy pattern** — `LLMProvider` ABC is the strategy interface; Ollama and Gemini are concrete strategies.
- **Decorator pattern** — `FallbackProvider` wraps another provider, adding failover behavior without modifying the wrapped provider.
- **Factory pattern** — `create_provider()` encapsulates construction logic, returning the right provider based on config.
- **Adapter pattern** — Each provider adapts a vendor-specific SDK (ollama, google-generativeai) into the uniform `LLMProvider` interface.

### Commit 5: `feat: hybrid similarity scoring with temporal proximity`

**What was built:**
- `src/swarm/graph/similarity.py` — `SimilarityScorer` ABC, `SimilarityProfile` model, `DomainWeighting` ABC, `SimilarityEngine`, and three core scorers (AdamicAdar, PPR, CausalWalk)
- Updated `base.py` with `get_weighted_snapshot()` method on the `GraphBackend` ABC
- Updated `networkx_backend.py` with `get_weighted_snapshot()` implementation
- Updated `__init__.py` with re-exports for all similarity classes

**Key decisions and reasoning:**

- **Similarity vector, not scalar** — Between any two entities, the system computes a multi-dimensional profile rather than a single number. This preserves the *mechanism* of similarity, which the emergence detection layer needs. A scalar of 0.65 hides whether similarity comes from shared connections (local), structural position (global), or temporal co-occurrence (causal). The full vector lets the observer distinguish between convergence mechanisms.

- **Two consumers, different views** — The agent interaction layer collapses the vector to a scalar via `DomainWeighting` (domain decides what matters for driving behavior). The emergence detection layer watches the raw vector distribution over time (no information loss). Both the collapsed scalar and the full vector are stored per tick.

- **Generic adjacency structure (`dict[str, list[tuple[str, str, float]]]`)** — Scorers receive topology as a plain dict, not a NetworkX graph or any backend-specific object. This means: (1) any future backend implements `get_weighted_snapshot` once, (2) scorers are pure functions over topology, testable without a graph backend, (3) new algorithms (spectral, embedding-based) plug in without ABC changes.

- **Temporal decay in the snapshot, not in scorers** — Edge weights already encode recency via `exp(-λΔt)` before scorers see them. This keeps scorer logic simple and ensures consistent temporal treatment across all scoring dimensions. The `decay_lambda` parameter is configurable per call.

- **Bidirectional unpacking** — Each directed edge A→B produces two adjacency entries (A sees B, B sees A). Similarity is about proximity, not direction. If both A→B and B→A exist as real edges, the pair appears multiple times — naturally amplifying genuinely bidirectional connections without special-case code.

- **Scorers operate on the same snapshot** — `SimilarityEngine.compute()` calls `get_weighted_snapshot()` once and passes the result to all scorers. No redundant graph traversals. O(E) to build the snapshot, then each scorer operates on the pre-built adjacency.

- **`SimilarityScorer` ABC as port** — Domain-specific scorers (e.g., `SectorAffinityScorer` for stocks, `OpinionDistanceScorer` for social media) implement the same interface and register with the engine. Core graph-structural scorers coexist with domain-semantic scorers in the same profile.

- **PPR via manual power iteration** — Implemented directly rather than calling `nx.pagerank`. The iteration operates on the generic adjacency dict, making it backend-agnostic. 20 iterations suffice for convergence on graphs under 100K nodes (the simulation caps at 50 agents, so this is vastly over-provisioned for safety).

- **Causal walk constraint** — Walks only follow edges where `weight <= last_weight` (weight decreases with age, so this enforces time-forward traversal). This is directly inspired by CAWN (Wang et al., 2021) — walks simulate realistic information propagation paths. Seeded RNG ensures reproducibility.

- **Normalization to [0, 1]** — All scorers return values in [0, 1]. Adamic-Adar normalizes by max possible score. PPR is naturally bounded. Causal walk is a fraction. This makes the profile dimensions comparable without post-hoc normalization in the engine.

**Research grounding:**
- Hybrid scoring: Lü & Zhou (2011), Liben-Nowell & Kleinberg (2007)
- Learned multi-scale combination: Neo-GNN (Yun et al., NeurIPS 2021)
- Causal temporal walks: CAWN (Wang et al., ICLR 2021)
- Temporal edge decay: Know-Evolve (Trivedi et al., 2017)
- Symbolic temporal rules: TLogic (Liu et al., AAAI 2022)

**Design patterns used:**
- **Strategy pattern** — `SimilarityScorer` ABC is the interface; each scorer (AA, PPR, CausalWalk) is a concrete strategy. Domain-specific scorers are additional strategies.
- **Composite pattern** — `SimilarityEngine` composes multiple scorers into a unified computation. Adding a scorer doesn't change existing code.
- **Adapter pattern** — `DomainWeighting` adapts the generic similarity vector to domain-specific agent interaction logic.
- **Template method (variation)** — `SimilarityEngine.compute()` defines the algorithm skeleton (get snapshot → score all → optionally collapse). Scorers fill in the variable step.

**Algorithms:**
- **Adamic-Adar** — O(|N(u)| + |N(v)|) to compute neighbor sets, O(|N(u) ∩ N(v)|) to sum contributions. Overall O(d²) where d is max degree.
- **Personalized PageRank** — O(iterations × E) where E is edge count in the snapshot. 20 iterations × 50 nodes = trivial.
- **Causal Walk** — O(num_walks × max_steps × avg_degree). With defaults (100 walks, 5 steps, ~10 avg degree) = ~5000 operations. Constant time regardless of graph size since walks are local.

### Commit 6: `feat: agent persona generation from graph nodes`

**What was built:**
- `src/swarm/agents/base.py` — `AgentPersona` Pydantic model, `PersonaGenerator` ABC, `persona_to_system_message()` bridge function
- `src/swarm/agents/prompts.py` — Persona generation prompt template
- `src/swarm/agents/persona.py` — `GraphPersonaGenerator` implementation
- `src/swarm/agents/__init__.py` — Public API re-exports

**Key decisions and reasoning:**

- **`AgentPersona` as structured Pydantic model (not raw string)** — Fields (name, role, traits, goals, backstory, communication_style) are individually addressable. The emergence detector can compare traits across agents without parsing strings. The simulation engine can filter agents by role. Serialization to JSON is free via Pydantic.

- **`persona_to_system_message()` as a separate function** — Decouples the data model from the CAMEL integration. If CAMEL changes its API or we switch frameworks, only this function changes. The `AgentPersona` model remains stable.

- **`Callable[[str], str]` for LLM (same pattern as ingestion)** — `PersonaGenerator.generate()` takes an `llm_fn` callable, not an `LLMProvider`. This means persona generation works with any LLM backend, mocks, or test fixtures. The same `provider.as_callable()` bridge works here.

- **Configurable `neighbor_depth` (default 2)** — Depth 1 gives only direct connections (shallow persona). Depth 2 captures connections-of-connections, which provides richer context about the entity's structural position. Deeper than 2 produces diminishing returns for most graph sizes.

- **Relationship formatting as `source --[TYPE]--> target`** — Human-readable for the LLM. Both source and target are resolved to names (not UUIDs) for better LLM comprehension. Falls back to UUID if entity lookup fails.

- **Markdown fence stripping in `_parse_response()`** — LLMs frequently add code fences despite explicit instructions not to. Same pattern used in `graph/ingestion.py`. Defensive parsing rather than relying on model compliance.

- **`entity_id` stored in persona** — Links the persona back to its graph source. Enables persona regeneration when the entity's neighborhood changes, and allows the simulation engine to look up an agent's graph position.

**Design patterns used:**
- **Strategy pattern** — `PersonaGenerator` ABC is the interface; `GraphPersonaGenerator` is the default strategy. Alternative strategies could generate personas from templates, config files, or external APIs.
- **Bridge pattern** — `persona_to_system_message()` bridges our domain model to CAMEL's expected input format.
- **Builder (implicit)** — `GraphPersonaGenerator.generate()` assembles a persona step-by-step: fetch entity → get relationships → get neighbors → format prompt → call LLM → parse result.

### Commit 7: `feat: agent communication via CAMEL role-playing`

**What was built:**
- `src/swarm/agents/toolkit.py` — `KnowledgeGraphToolkit` wrapping graph methods as CAMEL-compatible tools
- `src/swarm/agents/communication.py` — `SwarmAgent` wrapper, `ConversationResult`/`ConversationTurn` models, `run_conversation()` orchestrator
- Updated `__init__.py` with all new exports
- Codebase-wide cleanup: fixed indentation (6-space → 4-space PEP 8), removed unused imports

**Key decisions and reasoning:**

- **`SwarmAgent` wraps `ChatAgent` (composition, not inheritance)** — We control the interface. CAMEL's internal API changes don't propagate beyond `communication.py`. The rest of the system interacts only with `SwarmAgent.step(message) -> str` and `SwarmAgent.reset()`. This is the Adapter pattern — adapting CAMEL's API into our system's expectations.

- **Config-driven model selection via `llm_config` dict** — `SwarmAgent` receives the `llm` section of `default.yaml` directly. Provider and model are runtime configuration, not code. `PLATFORM_MAP` translates our config strings ("ollama", "gemini") to CAMEL's `ModelPlatformType` enum.

- **`KnowledgeGraphToolkit` with Google-style docstrings** — CAMEL's `FunctionTool` auto-generates OpenAI-compatible tool schemas from function signatures and docstrings. Google-style Args/Returns sections map directly to parameter descriptions in the schema. This means agents see well-described tools without manual schema authoring.

- **Result caps (10 entities, 20 neighbors/relationships)** — LLM context windows are finite. Returning the entire graph would overwhelm the model. Caps ensure tool responses are digestible while still providing useful information.

- **`run_conversation()` as free function (not a method)** — Takes two `SwarmAgent` instances and orchestrates. The simulation engine calls this function — agents don't initiate conversations themselves. This keeps the control flow explicit and observable.

- **Alternating turns with shared `message` variable** — Agent A's response becomes Agent B's input. Simple ping-pong protocol. More complex protocols (multi-party, interrupt-based) can be built later as alternative conversation functions.

- **`reset()` after each conversation** — CAMEL's `ChatAgent` accumulates message history. Without reset, context grows unboundedly across conversations. By resetting, each conversation starts fresh — persistent memory belongs in the knowledge graph, not in the LLM's context window.

- **`ConversationResult` stores full exchange** — Every turn (speaker + content) is captured. The emergence detector can analyze conversation patterns across all agent pairs. The simulation engine can decide graph updates based on what was said.

**Design patterns used:**
- **Adapter pattern** — `SwarmAgent` adapts CAMEL's `ChatAgent` API to our system's interface. `KnowledgeGraphToolkit` adapts `GraphBackend` to CAMEL's tool format.
- **Facade pattern** — `SwarmAgent` provides a simplified interface (just `step` and `reset`) hiding CAMEL's complexity (model creation, tool registration, message wrapping).
- **Mediator pattern** — `run_conversation()` mediates the interaction between two agents without either agent knowing about the other's internals.

### Commit 8: `feat: multi-agent society with adaptive topology`

**What was built:**
- `src/swarm/agents/state.py` — `AgentState` with domain-agnostic belief vector, Friedkin-Johnsen anchoring, distance computation
- `src/swarm/agents/domain.py` — `DomainSpec` ABC defining state shape, initialization, and update rules per domain
- `src/swarm/agents/topology.py` — `TopologyManager` with Watts-Strogatz initialization and adaptive homophily rewiring
- `src/swarm/agents/scheduler.py` — `InteractionScheduler` with activity-driven + event-driven scheduling
- `src/swarm/agents/society.py` — `AgentSociety` orchestrator and `TickResult` model
- Updated `pyproject.toml` with numpy dependency
- Updated `__init__.py` with all new exports

**Key decisions and reasoning:**

- **Generic belief vector (not opinion-specific)** — `AgentState.vector` is a `list[float]` with no hardcoded semantics. Dimensions are defined by `DomainSpec.vector_dimensions()`. Stock domain might use [tech_sentiment, risk_appetite, market_confidence]; social domain might use [opinion_axis_1, trust_in_media]. The Deffuant distance, Friedkin-Johnsen anchoring, and rewiring logic all operate on the generic vector — they don't know what it represents. This prevents the society layer from being locked to any single simulation type.

- **`DomainSpec` ABC as the domain contract** — Every domain provides: what dimensions the vector has, how to initialize from graph position, the confidence bound (epsilon), how conversations update state, and the similarity weighting strategy. The society layer calls these generically. Adding a new domain means implementing one class, not changing the engine.

- **Friedkin-Johnsen anchoring built into `AgentState`** — `apply_anchoring(influence) = (1-λ)*influence + λ*initial_vector`. The stubbornness parameter λ prevents unrealistic full consensus — agents resist drifting too far from their initial position. This is grounded in Friedkin & Johnsen (1990) and produces more realistic dynamics than unbounded opinion averaging.

- **Watts-Strogatz small-world initialization** — Real social networks have high clustering (my friends know each other) and short path lengths (small world). Random graphs lack clustering; lattices lack short paths. Watts-Strogatz gives both. The topology then evolves via adaptive rewiring — this is the starting point, not the fixed structure.

- **Adaptive homophily rewiring** — After each interaction, if agents are too dissimilar (beyond confidence bound), the edge is probabilistically expired and a new edge forms toward a more similar agent. This creates a feedback loop: similar agents cluster → reinforced agreement → further clustering. This coevolution of topology and state is what produces phase transitions (fragmentation, echo chambers). Grounded in Gross & Blasius (2008) adaptive network models.

- **All rewiring through temporal KG** — `expire_relationship()` + `add_relationship()` with `formed_reason` property. The full rewiring history is preserved in the graph. No edge is ever deleted — the emergence detector can trace exactly when and why the topology changed.

- **Activity-driven scheduling with power-law rates** — Not all agents act every tick. Each agent has an `activity_rate` (set by the domain at initialization, potentially from graph centrality). Activation is probabilistic: `P(active) = rate * dt`. This produces bursty, heterogeneous activity patterns matching real social systems (Perra et al., 2012; Barabási, 2005).

- **Event-driven overlay** — When an agent's state changes, its neighbors are pushed onto a priority queue. This means agents wake up when something relevant happens nearby, not just by random chance. Combines the realism of burstiness with the responsiveness of event-driven systems.

- **Bounded confidence pre-filter in pair selection** — `scheduler.select_pairs()` skips pairs where `distance > confidence_bound`. This is the Deffuant bounded confidence mechanism — agents too far apart in belief space don't interact. Critical for CPU efficiency: avoids expensive Ollama calls for interactions that would produce no influence anyway.

- **Weighted partner selection** — Among valid partners, selection is weighted by inverse distance (closer agents more likely to be picked). This produces preferential interaction with similar agents without completely excluding dissimilar ones within the bound.

- **Topic generation from shared graph context** — `_generate_topic()` finds entities in the intersection of both agents' neighborhoods. Conversations are about shared context, not arbitrary topics. This grounds interactions in the knowledge graph state.

- **`TickResult` captures full tick outcomes** — Active agents, pairs formed, conversations, and rewiring events. The emergence detection layer (next step) consumes these to track system evolution over time.

**Research grounding:**
- Adaptive coevolutionary networks: Gross & Blasius (2008), extended 2020+
- Bounded confidence: Deffuant-Weisbuch model; Chuang et al. (2023) showing LLMs exhibit implicit bounded confidence
- Friedkin-Johnsen anchoring: Friedkin & Johnsen (1990) — prevents unrealistic full consensus
- Activity-driven temporal networks: Perra et al. (2012)
- Small-world initialization: Watts & Strogatz (1998)
- LLM multi-agent societies: Park et al. (2023) Generative Agents — proves 25-50 agents suffice for emergence
- Opinion dynamics + LLM: Papachristou & Yuan (2024) on network formation among LLM agents

**Design patterns used:**
- **Strategy pattern** — `DomainSpec` ABC is the interface; each domain (stock, social) is a concrete strategy. The society layer operates identically regardless of domain.
- **Observer pattern (implicit)** — `InteractionScheduler.notify_change()` propagates state changes to neighbors. Agents reactively wake when their context changes.
- **Mediator pattern** — `AgentSociety` mediates all agent interactions. No agent directly references another — the society decides who communicates.
- **Template method** — `AgentSociety.tick()` defines the algorithm skeleton (schedule → pair → converse → update → rewire → notify). Domain-specific behavior fills in via `DomainSpec` methods.
- **Composition over inheritance** — `AgentSociety` composes `TopologyManager`, `InteractionScheduler`, `SimilarityEngine`, and `DomainSpec` rather than inheriting from any of them.

**Algorithms:**
- **Watts-Strogatz** — O(N*k) to create ring lattice, O(N*k*p) rewiring passes. For N=50, k=4: trivial.
- **Adaptive rewiring** — O(N) to find candidates per rewire event. At most one rewire per interaction.
- **Activity-driven scheduling** — O(N) per tick to sample activations. O(A*P) for pair selection where A = active agents, P = avg partners.
- **Friedkin-Johnsen update** — O(d) where d = vector dimensionality. Constant time per agent.

### Commit 9: `feat: time-stepped simulation engine`

**What was built:**
- `src/swarm/simulation/engine.py` — `SimulationEngine`, `SimulationConfig`, `SimulationResult`, `SimulationSnapshot`
- Updated `src/swarm/simulation/__init__.py` with public API re-exports

**Key decisions and reasoning:**

- **Thin orchestration layer** — The engine is deliberately simple. `AgentSociety.tick()` already handles scheduling, pair selection, conversation, state updates, and rewiring. The engine just loops ticks, records history, and checks stopping conditions. This avoids duplicating logic.

- **Callback-based extensibility** — `add_tick_callback(fn)` allows external observers (emergence detector, logger, metrics dashboard) to hook into the simulation without the engine knowing about them. The engine doesn't compute metrics — it just provides hook points.

- **Pluggable stop conditions** — `add_stop_condition(fn)` accepts any `(tick, TickResult) -> bool` predicate. The emergence detector (step 10) will register conditions like "stop when consensus detected" or "stop when polarization exceeds threshold". The engine doesn't define what emergence means — it just stops when told to.

- **Snapshots at configurable intervals** — `SimulationSnapshot` captures all agent belief vectors at a point in time. Stored every N ticks (configurable via `snapshot_every`). This is the time-series data the emergence detector analyzes. Storing every tick is the default — disk is cheap, information loss is expensive.

- **`datetime` for timestamps (consistent with the codebase)** — All other timestamps (`Relationship.valid_from`, `TickResult.timestamp`, `ConversationResult.timestamp`) use `datetime`. Keeping `SimulationSnapshot.timestamp` as `datetime` avoids conversion errors at boundaries.

- **`SimulationResult` as complete output** — Contains tick count, stop reason, all snapshots, and all tick results. Everything needed for post-hoc analysis is in one object. Can be serialized to JSON via Pydantic for storage/sharing.

- **No wall-clock timing** — The simulation operates in logical ticks, not real time. Each tick is one step of the society loop. Wall-clock pacing (for real-time visualization) would be a separate concern layered on top later.

**Design patterns used:**
- **Template method** — `run()` defines the loop skeleton: tick → snapshot → callbacks → stop check. Concrete behavior is injected via callbacks and stop conditions.
- **Observer pattern** — Tick callbacks are observers notified after each tick. They don't affect the simulation — they only observe.
- **Strategy pattern** — Stop conditions are strategies for deciding when to halt. Multiple can be composed (first one that fires wins).

**Algorithms:**
- **Main loop** — O(max_ticks × tick_cost). Tick cost dominated by LLM calls in the society layer, not by the engine itself.
- **Snapshot** — O(N) where N = agent count. Copies all belief vectors.
- **Stop condition check** — O(C) per tick where C = number of registered conditions. Typically 1-3.

### Commit 10: `feat: emergent behavior detection with 26 metrics`

**What was built:**
- `src/swarm/simulation/emergence.py` — `EmergenceDetector` orchestrator, `EmergenceEvent` model, `TimeSeriesStore`, and 5 metric classes (`OpinionMetrics`, `NetworkMetrics`, `PhaseTransitionMetrics`, `TemporalMetrics`, `CollectiveMetrics`)
- Updated `src/swarm/simulation/__init__.py` with all exports
- Added scipy to `pyproject.toml` and `requirements.txt`

**Key decisions and reasoning:**

- **Tiered computation schedule** — Not all metrics need to run every tick. Cheap metrics (O(N*D) or O(N)) run every tick. Moderate ones (O(N²)) run every 5 ticks. Expensive ones (O(N²+) or requiring history) run every 10 ticks. This keeps per-tick overhead dominated by LLM calls, not metric computation.

- **Six metric classes (separation of concerns)** — Each class groups related computations: opinion dynamics, network structure, phase transitions, temporal patterns, collective behavior. They're stateless — they take data in, return metrics out. The `EmergenceDetector` orchestrates them and manages state (time series, event history).

- **`TimeSeriesStore` for rolling computations** — Windowed metrics (AR(1), rolling variance, Kendall tau, periodicity) need history. The store accumulates up to 500 ticks of metric values and raw belief vectors. Capped to bound memory. All windowed computations pull from here rather than maintaining separate histories.

- **Event deduplication** — `_emit()` suppresses repeated events of the same type within 2 ticks. This prevents flooding: if consensus holds for 50 ticks, you get one "consensus" event, not 50.

- **Configurable thresholds** — All detection thresholds come from a config dict, with research-backed defaults (BC > 5/9 for polarization, modularity > 0.3 for communities, AR(1) > 0.85 for critical slowing down). Domains can override these.

- **Observer pattern (callback registration)** — `EmergenceDetector.on_tick` is registered via `SimulationEngine.add_tick_callback()`. The detector doesn't control the simulation — it observes. This means multiple detectors could run simultaneously (e.g., one focused on opinion dynamics, another on network structure).

- **`_build_communication_graph()` reconstructs undirected topology** — Network metrics need an `nx.Graph`. This method reads active `COMMUNICATES_WITH` edges from the temporal KG and builds a fresh undirected graph. Not cached — topology can change between calls due to adaptive rewiring.

- **PCA projection for multivariate opinions** — Several metrics (polarization, flickering, skewness) need 1D projections of the D-dimensional belief vector. SVD on the centered vectors gives the first principal component — the axis of maximum variance. This is the dimension where polarization is most visible.

- **Scipy for statistical rigor** — `pearsonr` for AR(1), `kendalltau` for trend detection, `find_peaks` for periodicity/susceptibility peaks, `pdist` for efficient pairwise distances, `linkage`/`fcluster` for hierarchical clustering. These are standard, well-tested implementations.

**Research grounding:**
- Early warning signals: Scheffer et al. (2009, 2012) — "Early-warning signals for critical transitions"
- Bimodality coefficient: Pfister et al. (2013) — standard statistical threshold BC > 5/9
- Modularity: Newman (2004) — empirical threshold Q > 0.3
- Susceptibility as phase transition indicator: from statistical physics (Ising model analogy)
- Small-world coefficient: Humphries & Gurney (2008) — sigma > 1
- Echo chamber index: Cinelli et al. (2021) — opinion-network alignment
- Herding via cross-correlation: Cont & Bouchaud (2000) — herding in financial markets
- Bounded confidence implicit in LLMs: Chuang et al. (2023) — LLM agents exhibit BC-like behavior
- Friedkin-Johnsen anchoring: Friedkin & Johnsen (1990) — stubbornness prevents full consensus
- Activity-driven bursts: Perra et al. (2012), Barabási (2005) — heavy-tailed inter-event times

**Design patterns used:**
- **Observer pattern** — `EmergenceDetector` observes the simulation via tick callbacks without affecting it.
- **Strategy pattern** — Each metric class is a strategy for computing one category of metrics. The detector composes them.
- **Time Series pattern** — `TimeSeriesStore` acts as a ring buffer for rolling window computations.
- **Event Sourcing (output)** — `EmergenceEvent` list is an append-only log of detected phenomena. Never modified after emission.

**Algorithms (26 total across 6 categories):**
- **Opinion (5):** Consensus (pdist O(N²D)), Polarization (PCA + skew/kurtosis O(ND)), Fragmentation (Ward linkage O(N²D)), Extremization (norm O(ND)), Convergence rate (polyfit O(W))
- **Network (6):** Communities (greedy modularity O(N log²N)), Fragmentation (connected_components O(N+E)), Hub emergence (degree stats O(N)), Small-world (BFS all-pairs O(NE)), Algebraic connectivity (eigenvalue O(N²)), Core-periphery (iterative O(N²))
- **Phase transitions (5):** AR(1) (pearsonr O(W)), Rolling variance (numpy O(W)), Susceptibility (covariance O(ND)), Flickering (sign changes O(W)), Skewness trend (kendalltau O(W²))
- **Temporal (3):** Burst detection (z-score O(ND)), Periodicity (autocorrelation O(T²)), Trend (Mann-Kendall O(W²))
- **Collective (4):** Herding (cross-correlation O(N²W)), Contrarianism (alignment O(NWD)), Free riding (activity check O(NWD)), Groupthink (community diversity O(N²D))
- **Information (3):** Cascade detection, bottlenecks, influence asymmetry — detected indirectly via burst + herding + centralization metrics.

### Commit 11: `feat: config-driven experiment runner with CLI`

**What was built:**
- `src/swarm/agents/default_domain.py` — `DefaultDomainSpec` (config-parameterized) + `DefaultWeighting`
- `src/swarm/simulation/runner.py` — `ExperimentRunner` (reads one YAML, executes full pipeline)
- `src/swarm/__main__.py` — CLI entrypoint (`python -m swarm run config.yaml`)
- `configs/experiments/wisdom_of_crowds.yaml` — first experiment config (Lorenz 2011 replication)
- Updated `simulation/__init__.py` with `ExperimentRunner` export

**Key decisions and reasoning:**

- **Config-driven over code-driven** — Users should not write Python to run standard experiments. A YAML file specifying belief dimensions, interaction mode, confidence bound, and agent count is sufficient. The engine reads the config and does everything: graph creation, seeding, persona generation, society initialization, simulation loop, emergence detection.

- **Three modes of operation:**
  - **Config-only** — `DefaultDomainSpec` handles standard bounded confidence experiments. Built-in interaction modes (deffuant, mean_field, degroot, repulsive). No Python needed.
  - **Config + LLM tools** — agent capabilities described in YAML, tool functions generated at runtime (architecture in place, implementation next).
  - **Plugin** — custom `DomainSpec` subclass referenced by import path in config. For experiments that need domain logic beyond the built-in modes.

- **`DefaultDomainSpec` with 4 interaction modes:**
  - `deffuant` — standard bounded confidence (move toward other by mu if within epsilon)
  - `mean_field` — move toward other regardless of distance
  - `degroot` — weighted average (equal weight)
  - `repulsive` — Deffuant within bound, PUSH AWAY if beyond (models backfire effect from Bail et al. 2018)

- **Configurable initial belief distributions** — `uniform`, `normal`, `bimodal`. Covers the common experimental setups. Bimodal is needed for pre-polarized populations (Bail replication). Normal with tunable mean/std for experiments with initial consensus that may fragment.

- **Three persona sources** — `minimal` (no LLM, fast testing), `generate` (LLM creates from graph neighborhood), `manual` (hand-defined in YAML). Minimal mode allows running the full pipeline without Ollama for development/testing — only the conversation step needs LLM.

- **Dynamic plugin import** — `domain.plugin: "mymodule.ClassName"` uses `importlib.import_module` + `getattr` to load custom domain classes. No registry needed. Any Python class on the path that implements `DomainSpec` works.

- **Full mesh topology option** — For Lorenz-style experiments where all agents can see/interact with all others. `topology.type: "full_mesh"` creates all N*(N-1)/2 edges. Alongside existing `small_world` initialization.

- **CLI as `python -m swarm run`** — Standard Python module execution. No separate CLI framework needed (no click/argparse dependency). Just reads sys.argv[2] as config path.

**Design patterns used:**
- **Factory pattern** — `ExperimentRunner` is a factory that builds the entire simulation object graph from config.
- **Strategy pattern** — interaction modes are strategies selected by config string. Persona sources are strategies. Topology types are strategies. All without subclassing.
- **Configuration object pattern** — YAML → dict → passed to constructors. Single source of truth for all parameters.
- **Plugin architecture** — dynamic import enables extension without modifying core code.

### Commit 12: `feat: simulation logger, group initialization, separated rewire threshold`

**What was built:**
- `src/swarm/simulation/logger.py` — `SimulationLogger` with three verbosity levels (verbose/summary/silent) and optional structured JSON file output
- Updated `DefaultDomainSpec` with group-based initialization — per-group belief ranges, stubbornness, activity rates
- Updated `TopologyManager` with separate `rewire_threshold` decoupled from `confidence_bound`
- Updated `ExperimentRunner` to automatically create and register the logger from config
- `run_experiment.py` — simplified experiment runner script
- `configs/experiments/three_group_schelling.yaml` — three-group conversational Schelling experiment
- Fixed `EmergenceDetector.susceptibility()` for 1D belief vectors
- Updated experiment configs to support llama.cpp backend via `base_url`

**Key decisions and reasoning:**

- **`SimulationLogger` as first-class tick callback** — same pattern as `EmergenceDetector`. Registers via `add_tick_callback()`, doesn't affect simulation logic. Created automatically by `ExperimentRunner` from the `logging` config section. No per-experiment logging code needed.

- **Three verbosity levels:**
  - `verbose` — per-tick: active agents, pairs, conversations with snippets, rewires, belief mean/variance. For interactive debugging and experiment monitoring.
  - `summary` — per-tick one-liner: pairs, rewires, variance. For batch runs.
  - `silent` — no stdout. For programmatic use.

- **Structured JSON logs (`file: "path.jsonl"`)** — one JSON object per tick: full belief vectors, pair counts, rewire details. Written with `flush()` after each tick so logs survive crashes. JSONL format enables post-hoc analysis with pandas/numpy without custom parsing.

- **`on_start()` / `on_complete()` lifecycle hooks** — print experiment banner (name, agent count, max ticks) at start and summary (ticks completed, elapsed time, stop reason) at end. Called by `ExperimentRunner.run()` before and after the engine loop.

- **Group-based initialization (backwards-compatible)** — when config has `groups` key, each group specifies count, belief range, stubbornness, and activity rate. Agents are assigned to groups in shuffled order. When `groups` is absent, existing distribution-based logic runs unchanged. Group name stored in `AgentState.properties["group"]` for analysis.

- **Separated `rewire_threshold` from `confidence_bound`** — these control different decisions: `confidence_bound` determines "can these agents talk?" (pair selection), `rewire_threshold` determines "should these agents disconnect?" (post-interaction topology). Decoupling them enables experiments where dissimilar agents CAN converse but MAY choose to disconnect afterward (the conversational Schelling design). When `rewire_threshold` is absent, falls back to `confidence_bound` (no change to existing experiments).

**Experiment: Three-Group Conversational Schelling**

Design: 4 hardline-left (beliefs [0.0-0.2], stubbornness 0.85), 4 hardline-right (beliefs [0.8-1.0], stubbornness 0.85), 4 moderates (beliefs [0.35-0.65], stubbornness 0.2). Small-world topology, confidence_bound 1.5 (everyone can talk), rewire_threshold 0.4 (disconnect if very dissimilar after talking).

Results after 8 ticks:
- Hardliners held position — left mean stayed at ~0.07, right at ~0.94. High stubbornness prevented drift.
- Moderates drifted slightly rightward — ideology 0.500 → 0.550. Suggests asymmetric interaction patterns in this topology instance.
- 5 rewiring events total — rare but present. Cross-group connections occasionally broke.
- 7 of 12 agents showed measurable belief change — all moderates + some hardliners who happened to pair with moderates.
- No emergence events triggered — 8 ticks insufficient for dramatic structural change. Would need 20-30 ticks for echo chamber formation.
- One moderate briefly crossed into "right" zone at tick 2-3, then returned — the "bridge wobble" effect.

**Research grounding:**
- Schelling (1971) — "Dynamic models of segregation" — original model showing mild preferences produce dramatic segregation
- The conversational variant tests: does dialogue between groups slow segregation? Result: moderates act as partial bridges but are gradually pulled toward one pole.

**Design patterns used:**
- **Observer pattern** — `SimulationLogger` observes without affecting. Multiple observers (logger + detector) coexist on the same engine.
- **Null object pattern** — when `rewire_threshold` is `None`, falls back to confidence_bound. No special-casing needed in calling code.
- **Builder pattern** — group queue built once at first call to `_group_initial_state()`, then consumed sequentially. Shuffle ensures group assignment isn't order-dependent.

### Commit 13: `feat: intervention + counterfactual replay with event-keyed hashing`

**What was built:**
- `src/swarm/simulation/hashing.py` — `event_random()` and `event_random_pair()` for causally valid counterfactual replay
- `src/swarm/simulation/intervention.py` — `Intervention`, `Scenario`, `CounterfactualRunner`, `TrajectoryResult`, `ComparisonResult`, `DivergencePoint`
- Refactored `src/swarm/agents/scheduler.py` — replaced sequential PRNG with event-keyed hashing
- Refactored `src/swarm/agents/topology.py` — replaced sequential PRNG with event-keyed hashing
- Updated `src/swarm/agents/society.py` — passes tick number to scheduler and topology
- Updated `src/swarm/simulation/engine.py` — passes tick number to society
- Updated `run_experiment.py` — detects `counterfactual` config section and delegates to `CounterfactualRunner`
- `configs/experiments/propaganda_counterfactual.yaml` — example counterfactual config with 3 scenarios
- Updated `simulation/__init__.py` with all new exports

**Key decisions and reasoning:**

- **Event-keyed hashing (Buffalo et al., 2026)** — The single most important architectural change. Standard `random.Random(seed)` produces causally invalid counterfactuals: removing one agent shifts the PRNG sequence for all subsequent events, so observed divergence reflects PRNG artifacts, not causal effects. Event-keyed hashing uses `hash(seed, tick, event_type, entity_id)` per random decision, making each agent's randomness independent. Removing Agent_2 has zero effect on Agent_3's random values. This is the foundation for valid causal comparison.

- **Multi-trajectory comparison (not just pairwise)** — Most ABM literature compares baseline vs one intervention. Our system supports N scenarios compared simultaneously against one baseline. This enables comparative attribution: "removing the defender mattered more than weakening propaganda." Forward-looking design — multi-trajectory ABM comparison is an emerging methodology (Triantafyllou et al., 2024).

- **Config-driven scenarios** — Users write YAML specifying rewind tick + interventions per scenario. No Python needed. The `run_experiment.py` entrypoint auto-detects counterfactual configs and delegates to `CounterfactualRunner`.

- **Five intervention types:**
  - `remove_agent` — structural (removes node + all edges)
  - `modify_belief` — parametric (sets belief vector)
  - `modify_property` — parametric (sets stubbornness, activity_rate, or custom properties)
  - `add_relationship` — structural (creates new edge)
  - `remove_relationship` — structural (expires existing edge)

- **Fast-forward + replay architecture** — For a scenario rewinding to tick 5: the system re-runs ticks 0-4 with the same event-keyed randomness (producing identical results to baseline), applies interventions at tick 5, then replays ticks 5-N. The fast-forward phase is necessary because we don't serialize full state (graph + all agent objects) — we reconstruct by replaying. LLM calls happen during both phases.

- **Per-tick logging during counterfactual** — Both fast-forward and replay phases print live progress: tick number, pairs formed, rewires, mean belief, variance. Essential for monitoring long-running counterfactual analysis.

- **Divergence detection via threshold** — For each metric, the system walks the baseline and scenario trajectories in parallel. The first tick where `|baseline - scenario| > threshold` is the divergence point. Simple and interpretable. More sophisticated methods (PELT change-point detection, BOCPD) can be added later.

- **Agent name resolution** — Interventions reference agents by name ("Agent_3"), not UUID. The runner resolves names to entity IDs via the persona registry. This keeps configs human-readable.

**Research grounding:**
- Event-keyed hashing: Buffalo et al. (2026) — "Realizing Common Random Numbers: Event-Keyed Hashing for Causally Valid Stochastic Models"
- Counterfactual effect decomposition: Triantafyllou et al. (2024) — Shapley-based attribution in multi-agent sequential decision-making
- LLM non-determinism: Atil et al. (2024) — justifies why opinion dynamics (deterministic Deffuant) should drive state updates, not LLM conversation content
- Counterfactual probing in LLM simulations: Yu et al. (2026), CAMO — micro-to-macro causal chains
- Pearl's do-calculus: `remove_agent` = `do(agent_exists := false)`, `modify_belief` = `do(belief := value)`

**Design patterns used:**
- **Command pattern** — each `Intervention` is a command object. The runner applies them polymorphically based on `type`.
- **Memento pattern (variation)** — the source log JSONL serves as the memento. Baseline state at any tick is reconstructable from the log without re-running.
- **Strategy pattern** — `CounterfactualRunner` vs `ExperimentRunner` are selected by config content (presence of `counterfactual` key). Same entrypoint, different execution path.
- **Template method** — `_run_scenario()` defines the skeleton: fast-forward → apply interventions → replay → collect metrics. Intervention types fill in the variable step.

### Commit 14: `feat: report generation and FastAPI dashboard`

**What was built:**
- `src/swarm/simulation/report.py` — `ReportGenerator` producing text summaries + 7 publication-quality matplotlib plots (opinion trajectories, density heatmap, final distribution, metric timeseries, network snapshots, interaction heatmap, early warnings)
- `src/swarm/dashboard/` — full FastAPI web dashboard:
  - `app.py` — FastAPI application with 11 API endpoints serving experiment data
  - `data_loader.py` — `ExperimentData` (JSONL parser) + `ExperimentIndex` (experiment discovery)
  - `static/index.html` — single-page dashboard with 6 tabs
  - `static/style.css` — dark theme layout with CSS grid
  - `static/dashboard.js` — Plotly.js charts, vis.js network graph, tick slider, tab switching
- Enhanced `src/swarm/simulation/logger.py` — enriched JSONL format with conversation text, network edges, metrics, agent map (header/footer records)
- Updated `src/swarm/__main__.py` — added `dashboard` CLI command
- Fixed `topology.py` — bidirectional edge expiry in `maybe_rewire()`
- Fixed `intervention.py` — counterfactual runner no longer overwrites source log
- Added matplotlib to `pyproject.toml` and `requirements.txt`

**Key decisions and reasoning:**

- **Enriched JSONL as single data source** — the logger now writes per-tick: full conversation text (speaker + content per turn), network edge list, all emergence metrics, pairs detail, and rewire details. Header record stores agent map + config, footer stores events + summary. The dashboard reads only from this file — no re-computation needed. Trade-off: larger log files (~100KB-1MB per experiment), but avoids any dependency on the simulation runtime for post-hoc analysis.

- **Header/footer records in JSONL** — metadata bookends around tick records. Header stores `agent_map` (UUID → name mapping) and `dimensions` (belief vector meaning). Footer stores all emergence events and final summary. Records distinguished by `"type": "header"/"tick"/"footer"`. Backward-compatible: old logs without `type` field are treated as tick records.

- **FastAPI + vanilla JS (no React/Vue/npm)** — the dashboard is a single HTML page with Plotly.js and vis.js loaded from CDN. No build step, no node_modules. FastAPI serves both the API and static files. This keeps the dependency surface minimal and the project easy to clone and run.

- **Plotly.js for charts** — interactive (zoom, hover, pan) out of the box. Dark theme via layout configuration. Used for: opinion trajectories, belief histograms, metric time series, sparklines, interaction heatmaps, metric small multiples.

- **vis.js for network graph** — superior network interactivity over Plotly: drag nodes, physics-based layout, hover labels. Nodes colored by belief (red = high, blue = low). Updates when tick slider moves.

- **Tick slider governs all panels** — moving the slider updates: belief histogram, network graph, conversation panel, metric current-value indicators. Summary and trajectory panels show all ticks at once. This unifies the temporal exploration experience.

- **6 dashboard tabs** — Summary (config + events + sparklines), Beliefs (trajectories + histogram), Network (graph + stats), Metrics (selectable time series + small multiples), Interactions (heatmap + rewire log), Conversations (full dialogue text per tick).

- **Counterfactual runner silent logging** — scenario replays set `logging: {level: "silent"}` to prevent overwriting the source log file. This was a bug discovered during testing: the runner's `ExperimentRunner` re-opened the log in write mode, truncating the baseline data.

- **Report generator with matplotlib** — produces 7 publication-quality plots (300 DPI, serif font, proper axis labels). Auto-generated after each experiment run when `report.enabled: true` in config. Saves to `reports/{experiment_name}/`. Uses `Agg` backend (no display needed).

**Dashboard API endpoints:**
- `GET /api/experiments` — list all experiments with log files
- `GET /api/experiment/{name}/config` — YAML config as JSON
- `GET /api/experiment/{name}/ticks` — lightweight tick summaries
- `GET /api/experiment/{name}/tick/{n}` — full tick data
- `GET /api/experiment/{name}/metrics` — all metric time series
- `GET /api/experiment/{name}/events` — emergence events
- `GET /api/experiment/{name}/network/{tick}` — nodes + edges at tick
- `GET /api/experiment/{name}/conversations/{tick}` — full conversation text
- `GET /api/experiment/{name}/beliefs` — per-agent belief trajectories
- `GET /api/experiment/{name}/reports` — list report images
- `GET /api/experiment/{name}/reports/{file}` — serve report image

**Design patterns used:**
- **Backend for Frontend (BFF)** — the API is shaped for the dashboard's specific data needs, not a generic REST API. Each endpoint returns exactly what one panel needs.
- **Lazy loading with caching** — `ExperimentData` loads the JSONL once on first access, caches in memory. Per-tick network/conversation data fetched on demand from the frontend.
- **Observer pattern (continued)** — `SimulationLogger` and `EmergenceDetector` both observe the simulation via tick callbacks. The logger now reads the detector's metrics via `set_detector()` coupling.

---

## Interview Q&A

Common questions about this project and concise answers.

**Q: Why did you choose NetworkX over Neo4j?**
NetworkX is pure Python with zero infrastructure — no database to install or manage. For development and simulations under ~100K nodes, it's faster than a network round-trip to Neo4j. But the `GraphBackend` ABC means swapping in Neo4j is just a new adapter implementing the same interface. It's an optional dependency: `pip install -e ".[neo4j]"`.

**Q: How does this differ from just using LangChain with a graph database?**
LangChain is an orchestration layer for single-agent RAG pipelines. This is a multi-agent simulation where agents autonomously interact and the knowledge graph evolves over time. The temporal dimension, emergent behavior detection, and counterfactual replay don't exist in LangChain's paradigm.

**Q: How do you handle the cost of running many LLM calls?**
Three strategies: (1) Ollama with local models for zero-cost development, (2) not every agent acts every tick — they're scheduled based on priority, (3) rule-based fallback for routine decisions, reserving LLM calls for novel situations.

**Q: What's the hardest technical challenge you faced?**
*(To be updated with genuine experience as the project develops)*

**Q: Why CAMEL-AI over AutoGen or CrewAI?**
CAMEL's autonomous role-playing model maps directly to what a swarm simulation needs — agents that converse and act without human intervention. AutoGen assumes a human-in-the-loop pattern. CrewAI is pipeline-oriented, which doesn't fit emergent interaction. CAMEL also has native support for agent societies and knowledge graph integration.

**Q: How do you ensure simulation results are reproducible?**
Event-keyed hashing (not sequential PRNG) ensures that each random decision is deterministic based on `hash(seed, tick, event_type, agent_id)`. This means removing or adding agents doesn't shift randomness for other agents — critical for valid counterfactual comparison. The opinion dynamics (Deffuant update) are deterministic given the same belief vectors, regardless of LLM conversation content.

**Q: Why event-keyed hashing instead of standard seeded randomness?**
Standard `random.Random(seed)` draws from a sequential stream. Removing one agent shifts every subsequent draw — Agent_3 gets Agent_2's random number, Agent_4 gets Agent_3's, etc. Counterfactual comparisons then measure PRNG artifacts, not causal effects. Event-keyed hashing makes each decision independent: `hash(seed, tick, "activation", "Agent_3")` returns the same value regardless of whether Agent_2 exists. This is based on Buffalo et al. (2026).

**Q: How does the society layer handle domain extensibility?**
The `DomainSpec` ABC defines the contract: vector dimensions, initial state, confidence bound, post-interaction update, and similarity weighting. Adding a new simulation domain (e.g., supply chain, epidemiology) means implementing one class — no engine changes. The society layer operates on generic belief vectors and never knows whether it's simulating stock traders or social media users. The Deffuant bounded confidence, Friedkin-Johnsen anchoring, and adaptive rewiring all work on the generic vector.

**Q: Why not use CAMEL's built-in Society/Workforce for multi-agent orchestration?**
CAMEL's Workforce is hub-and-spoke (coordinator routes tasks to workers). It doesn't support configurable topology, adaptive rewiring, or bounded confidence dynamics. We need agents that form, break, and reform connections based on opinion similarity — this is coevolutionary dynamics, not task routing. We use CAMEL for what it's good at (individual agent conversation with tools) and build our own orchestration for the topology and dynamics layer.

**Q: How does the emergence detector avoid false positives?**
Three mechanisms: (1) Event deduplication — the same event type is suppressed if it fired within the last 2 ticks, preventing floods when a state persists. (2) Research-backed thresholds — defaults come from published literature (BC > 5/9, Q > 0.3, AR(1) > 0.85), not arbitrary values. (3) Windowed computation — metrics like AR(1) and Kendall tau require sustained patterns over 20+ ticks, not single-tick spikes. These can still be tuned per domain via the config dict.

**Q: Why 26 metrics? Isn't that excessive for 50 agents?**
The point isn't that every metric fires every run. Different simulation domains produce different emergent phenomena — stock markets produce cascades and herding, social simulations produce echo chambers and polarization. Having a comprehensive metric suite means the system can detect whatever emerges without domain-specific tuning. The tiered scheduling (every tick / every 5 / every 10) ensures the computational cost is bounded: ~O(N²D) per tick worst case, which for N=50 is sub-millisecond — the LLM calls are 10,000x more expensive.

**Q: Can you run the simulation with different LLM backends?**
Yes — any OpenAI-compatible endpoint works. The config just needs `base_url` pointing to the server. We've tested with Ollama (llama3, llama3.2:1b) and llama.cpp (Qwen2.5-3B). Switching backends is a one-line config change. The `provider: "ollama"` setting works for any OpenAI-compatible API, not just Ollama specifically.

**Q: What kinds of simulations can you run without writing code?**
Anything expressible as: agents with N-dimensional beliefs, pairwise conversations, Deffuant/DeGroot/mean-field/repulsive interaction, adaptive topology. This covers: opinion polarization, echo chamber formation, wisdom-of-crowds degradation, backfire effects, multi-group segregation dynamics, and parameter sweep phase transition studies. Custom domains with external tools or non-standard state machines require plugin mode (a Python class implementing `DomainSpec`).

**Q: What would you do differently if starting over?**
*(To be updated as the project matures)*
