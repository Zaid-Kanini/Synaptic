"""Quick verification that Module 2 imports and app loads correctly."""

import sys
import inspect

# Verify core imports first (no heavy ML model loading)
print("Checking imports...")
from synaptic.graph.database import GraphService
print(f"  [OK] database.py (sync={not inspect.iscoroutinefunction(GraphService.connect)})")
from synaptic.graph.ingestor import ingest_to_neo4j
print(f"  [OK] ingestor.py (sync={not inspect.iscoroutinefunction(ingest_to_neo4j)})")
from synaptic.graph.search import similarity_search, hybrid_search
print(f"  [OK] search.py (sync={not inspect.iscoroutinefunction(similarity_search)})")
from synaptic.graph.setup_index import create_vector_index
print(f"  [OK] setup_index.py (sync={not inspect.iscoroutinefunction(create_vector_index)})")

# Verify embedder import (loads sentence_transformers but NOT the model)
from synaptic.graph.embedder import Embedder, EMBEDDING_DIM
print(f"  [OK] embedder.py (dim={EMBEDDING_DIM})")

# Verify FastAPI app with all routes
from synaptic.api.app import app
print("\nApp loaded OK")
print("Routes:")
for r in app.routes:
    if hasattr(r, "methods"):
        print(f"  {r.methods}  {r.path}")

print("\n[PASS] Module 2 verification complete.")
