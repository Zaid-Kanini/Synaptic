# Synaptic — Module 1: Ingestion & Parsing Engine

A GraphRAG-based codebase onboarding engine that maps a repository's structural DNA by extracting functions, classes, call-sites, and imports into a Knowledge Graph.

## Architecture

```
Synapse/
├── main.py                          # Uvicorn entry point
├── requirements.txt                 # Pinned dependencies
├── README.md
└── synaptic/
    ├── __init__.py                  # Package version
    ├── config.py                    # Pydantic-settings configuration
    ├── logging.py                   # Structured logging (structlog)
    ├── api/
    │   ├── __init__.py
    │   ├── app.py                   # FastAPI application factory
    │   └── routes.py                # /ingest endpoint
    ├── core/
    │   ├── __init__.py
    │   ├── crawler.py               # Recursive file walker with blacklist
    │   └── ingestion.py             # Orchestrator service
    ├── models/
    │   ├── __init__.py
    │   └── graph.py                 # Pydantic v2 node/edge/graph models
    └── parsers/
        ├── __init__.py
        ├── base.py                  # Abstract base parser
        ├── factory.py               # Parser factory (registry pattern)
        ├── python_parser.py         # Tree-sitter Python grammar
        └── javascript_parser.py     # Tree-sitter JavaScript grammar
```

## Quick Start

```bash
# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## API Usage

### POST /ingest

Scan a local repository and return its knowledge graph.

**Request:**
```json
{
  "path": "C:/Users/you/projects/my-repo",
  "blacklist": [".git", "node_modules", "__pycache__"]
}
```

**Response:**
```json
{
  "status": "success",
  "total_nodes": 42,
  "total_edges": 87,
  "graph": {
    "nodes": [
      {
        "id": "src/utils.py",
        "type": "file",
        "name": "utils.py",
        "filepath": "src/utils.py",
        "start_line": 1,
        "end_line": 50,
        "docstring": "Utility helpers.",
        "content": "..."
      }
    ],
    "edges": [
      {
        "source_id": "src/utils.py::process",
        "target_id": "src/utils.py::validate",
        "type": "calls"
      }
    ]
  }
}
```

## Supported Languages

| Language   | Extensions          | Parser                    |
|------------|---------------------|---------------------------|
| Python     | `.py`               | `tree-sitter-python`      |
| JavaScript | `.js`, `.jsx`, `.mjs` | `tree-sitter-javascript` |

## Adding a New Language

1. Install the tree-sitter grammar package (e.g. `tree-sitter-go`).
2. Create `synaptic/parsers/go_parser.py` subclassing `BaseLanguageParser`.
3. Register it in `synaptic/core/ingestion.py::_build_factory()`.
4. Add the file extension mapping in `synaptic/core/crawler.py::EXTENSION_LANGUAGE_MAP`.

## Configuration

Environment variables (prefix `SYNAPTIC_`):

| Variable                      | Default   | Description                     |
|-------------------------------|-----------|---------------------------------|
| `SYNAPTIC_LOG_LEVEL`          | `INFO`    | Logging level                   |
| `SYNAPTIC_MAX_FILE_SIZE_BYTES`| `1048576` | Skip files larger than this     |

## Tech Stack

- **Python 3.11+** (async)
- **FastAPI** — API framework
- **tree-sitter** — AST parsing engine
- **Pydantic v2** — Data validation
- **structlog** — Structured logging
- **pathspec** — Gitignore-style pattern matching
