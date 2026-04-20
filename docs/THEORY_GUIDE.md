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

### Detection Algorithms

*(To be detailed as implemented)*

The emergent behavior detection layer monitors graph-level metrics over time:
- **Belief variance** across agents (low = consensus, bimodal = polarization)
- **Information propagation speed** (sudden spikes = cascade)
- **Community detection** (modularity changes = clustering shifts)
- **Centrality shifts** (new influential nodes emerging)

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

### Agent-Graph Coupling

This is a key design decision: **agent behavior is a function of graph structure**. A well-connected agent with many information sources behaves differently from an isolated one. As the graph evolves (new relationships form, old ones expire), agent behavior naturally adapts.

This means emergent behavior is truly emergent — it arises from the interaction between agent reasoning and graph topology, not from scripted scenarios.

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

- Agent personas are generated from knowledge graph data and fed into CAMEL role definitions
- CAMEL handles the conversation protocol between agents
- Agent actions (graph updates, information sharing) are implemented as CAMEL tools
- The simulation engine orchestrates which agents interact each tick

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
Seeded randomness (`simulation.seed` in config) controls agent scheduling and interaction selection. With the same seed, same config, and deterministic LLM responses (temperature=0), simulations produce identical results.

**Q: What would you do differently if starting over?**
*(To be updated as the project matures)*
