# Swarm Simulation

A generalized swarm intelligence simulation engine that combines temporal knowledge graphs with multi-agent systems to model emergent behavior.

Built with [CAMEL-AI](https://github.com/camel-ai/camel) for agent orchestration and [NetworkX](https://networkx.org/) (with optional Neo4j) for knowledge graph management.

## Features (Planned)

- Temporal knowledge graph with causal reasoning
- Adaptive agent personas driven by graph embeddings
- Emergent behavior detection (consensus, polarization, cascades)
- Intervention replay and counterfactual analysis
- Provider-agnostic LLM integration (Ollama, Gemini)
- Example simulations: stock market trading, social media opinion dynamics

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Optional extras

```bash
pip install -e ".[neo4j]"    # Neo4j graph backend
pip install -e ".[gemini]"   # Google Gemini LLM
pip install -e ".[ui]"       # Web UI
pip install -e ".[all]"      # Everything
```

## Status

Work in progress.
