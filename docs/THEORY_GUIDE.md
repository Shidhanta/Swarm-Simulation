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
9. [LLM Integration Patterns](#llm-integration-patterns)
10. [Build Log](#build-log)
11. [Interview Q&A](#interview-qa)

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

### Planned

- **Community detection (Louvain/Girvan-Newman)** — identifying agent clusters
- **PageRank / Betweenness centrality** — finding influential agents
- **Graph embeddings (Node2Vec or spectral)** — encoding agent position as feature vectors for adaptive behavior
- **Temporal motif detection** — finding recurring patterns in graph evolution

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
