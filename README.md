# Synaptic

A GraphRAG-powered codebase intelligence engine. Synaptic scans a repository, extracts its structural DNA into a Neo4j knowledge graph, and answers natural-language questions about the architecture using hybrid vector + graph retrieval and LLM synthesis.

## Modules

| Module | Description | Status |
|--------|-------------|--------|
| **Module 1** — Ingestion & Parsing | Tree-sitter AST extraction → nodes & edges | Complete |
| **Module 2** — Knowledge Graph | Neo4j Aura population, HuggingFace embeddings, vector index | Complete |
| **Module 3** — GraphRAG Pipeline | Hybrid retrieval + Azure OpenAI synthesis | Complete |
| **Module 4** — Frontend | React + 3D force graph + chat UI | Complete |

## Architecture

```
Synapse/
├── main.py                              # Uvicorn entry point
├── requirements.txt                     # Python dependencies
├── .env                                 # Environment variables
├── README.md
├── synaptic/
│   ├── __init__.py                      # Package version
│   ├── config.py                        # Pydantic-settings (all modules)
│   ├── logging.py                       # Structured logging (structlog)
│   ├── api/
│   │   ├── app.py                       # FastAPI app factory + CORS
│   │   ├── routes.py                    # /ingest, /node/{id}/content
│   │   ├── graph_routes.py              # /graph/ingest, /graph/search, /graph/setup, /graph/clear
│   │   └── query_routes.py             # /rag/query (GraphRAG endpoint)
│   ├── core/
│   │   ├── crawler.py                   # Recursive file walker with blacklist
│   │   ├── content_reader.py            # On-demand source code reader
│   │   └── ingestion.py                 # Orchestrator service
│   ├── models/
│   │   └── graph.py                     # Pydantic v2 node/edge/graph models
│   ├── parsers/
│   │   ├── base.py                      # Abstract base parser
│   │   ├── factory.py                   # Parser factory (registry pattern)
│   │   ├── python_parser.py             # Tree-sitter Python grammar
│   │   └── javascript_parser.py         # Tree-sitter JavaScript grammar
│   ├── graph/
│   │   ├── database.py                  # Sync Neo4j GraphService (execute_query)
│   │   ├── embedder.py                  # HuggingFace all-MiniLM-L6-v2 (384-dim)
│   │   ├── ingestor.py                  # 3-phase: nodes → edges → embeddings
│   │   ├── search.py                    # Vector similarity + hybrid search
│   │   └── setup_index.py              # One-time vector index + constraints
│   └── rag/
│       ├── retriever.py                 # Hybrid vector search + graph expansion
│       ├── llm_service.py               # Azure OpenAI integration + system prompt
│       └── pipeline.py                  # Orchestrator: question → retrieval → LLM → answer
└── frontend/
    ├── vite.config.js                   # Vite + Tailwind + API proxy
    └── src/
        ├── App.jsx                      # Dual-pane layout root
        ├── index.css                    # Tailwind + dark theme + animations
        ├── components/
        │   ├── ChatPane.jsx             # Chat UI: input, messages, settings
        │   ├── ChatMessage.jsx          # Markdown rendering + clickable file refs
        │   ├── GraphPane.jsx            # 3D force graph + tooltips + legend
        │   └── ScanLoader.jsx           # High-tech skeleton loader
        ├── hooks/
        │   └── useSynaptic.js           # State management + API orchestration
        └── lib/
            ├── api.js                   # Fetch wrapper for /rag/query
            └── graphUtils.js            # Graph data builder + node lookup
```
![alt text](<Screenshot 2026-02-12 230852.png>)

## Quick Start

### Backend

```bash
# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Neo4j Aura and Azure OpenAI credentials

# Run the API server
python main.py
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:3000`.

### First-Time Setup

```bash
# 1. Create the Neo4j vector index (one-time)
#    POST http://localhost:8000/graph/setup

# 2. Ingest a repository
#    POST http://localhost:8000/graph/ingest
#    Body: { "path": "D:/your/repo", "embed": true }

# 3. Ask questions via the UI at http://localhost:3000
#    or via the API:
#    POST http://localhost:8000/rag/query
#    Body: { "question": "How is user data validated?", "repo_path": "D:/your/repo" }
```

## API Endpoints

### Module 1 — Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ingest` | Parse a repo and return the code graph (streaming NDJSON) |
| GET | `/node/{node_id}/content` | Lazy-load source code for a node |

### Module 2 — Knowledge Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/graph/setup` | Create Neo4j vector index + constraints (one-time) |
| POST | `/graph/ingest` | Populate Neo4j with nodes, edges, and embeddings |
| POST | `/graph/search` | Vector similarity search over the graph |
| DELETE | `/graph/clear` | Clear all graph data |

### Module 3 — GraphRAG

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/rag/query` | Ask a question → hybrid retrieval → LLM answer |

**Request:**
```json
{
  "question": "What does utils.py do?",
  "repo_path": "D:\\Practice\\python\\Synapse\\test_repo",
  "top_k": 5,
  "expand_depth": 2
}
```

**Response:**
```json
{
  "answer": "## Summary\n`utils.py` provides data processing and validation utilities...",
  "source_nodes": [
    {
      "node_id": "utils.py::validate_input",
      "name": "validate_input",
      "type": "function",
      "filepath": "utils.py",
      "start_line": 23,
      "end_line": 32,
      "score": 0.675
    }
  ],
  "relationships": [
    "validate_input --[DEFINES]--> utils.py",
    "DataProcessor.process_batch --[CALLS]--> validate_input"
  ],
  "metadata": {
    "retrieval_time_ms": 5109,
    "synthesis_time_ms": 20083,
    "total_time_ms": 25192,
    "entry_points": 5,
    "neighbours": 10,
    "model": "gpt-5-mini"
  }
}
```
## Sample Output
![alt text](<Screenshot 2026-02-13 155052-1.png>) 
![alt text](<Screenshot 2026-02-13 155022-1.png>)

## Supported Languages

| Language   | Extensions            | Parser                    |
|------------|-----------------------|---------------------------|
| Python     | `.py`                 | `tree-sitter-python`      |
| JavaScript | `.js`, `.jsx`, `.mjs` | `tree-sitter-javascript`  |

## Adding a New Language

1. Install the tree-sitter grammar package (e.g. `tree-sitter-go`).
2. Create `synaptic/parsers/go_parser.py` subclassing `BaseLanguageParser`.
3. Register it in `synaptic/core/ingestion.py::_build_factory()`.
4. Add the file extension mapping in `synaptic/core/crawler.py::EXTENSION_LANGUAGE_MAP`.

## Configuration

All environment variables use the `SYNAPTIC_` prefix and are loaded from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPTIC_LOG_LEVEL` | `INFO` | Logging level |
| `SYNAPTIC_MAX_FILE_SIZE_BYTES` | `1048576` | Skip files larger than this |
| `SYNAPTIC_NEO4J_URI` | — | Neo4j Aura connection URI (`neo4j+ssc://...`) |
| `SYNAPTIC_NEO4J_USER` | `neo4j` | Neo4j username |
| `SYNAPTIC_NEO4J_PASSWORD` | — | Neo4j password |
| `SYNAPTIC_NEO4J_DATABASE` | `neo4j` | Neo4j database name |
| `SYNAPTIC_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | HuggingFace embedding model |
| `SYNAPTIC_EMBEDDING_BATCH_SIZE` | `200` | Embedding batch size |
| `SYNAPTIC_OPENAI_API_KEY` | — | Azure OpenAI API key |
| `SYNAPTIC_OPENAI_MODEL` | `gpt-4o-mini` | Azure OpenAI deployment name |
| `SYNAPTIC_AZURE_ENDPOINT` | — | Azure OpenAI endpoint URL |
| `SYNAPTIC_RAG_TOP_K` | `5` | Vector search result count |
| `SYNAPTIC_RAG_EXPAND_DEPTH` | `2` | Graph traversal depth (hops) |
| `SYNAPTIC_RAG_MAX_NODES` | `15` | Max context nodes for LLM |
| `SYNAPTIC_RAG_MAX_CONTEXT_CHARS` | `12000` | Max source code chars for LLM |

## Tech Stack

### Backend
- **Python 3.11+** — Runtime
- **FastAPI** — API framework
- **tree-sitter** — AST parsing engine
- **Neo4j Aura** — Cloud graph database
- **sentence-transformers** — Local HuggingFace embeddings (all-MiniLM-L6-v2, 384-dim)
- **Azure OpenAI** — LLM synthesis (gpt-5-mini)
- **Pydantic v2** — Data validation & settings
- **structlog** — Structured logging

### Frontend
- **React 19** + **Vite** — Build toolchain
- **Tailwind CSS** — Utility-first styling (dark mode)
- **react-force-graph-3d** + **Three.js** — 3D knowledge graph visualization
- **react-markdown** — AI answer rendering with syntax highlighting
- **lucide-react** — Icons
