"""Quick script to list what's in the Neo4j graph."""
from dotenv import load_dotenv
load_dotenv()

from synaptic.config import settings
from synaptic.graph.database import GraphService

svc = GraphService(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
svc.connect()
results = svc.run_cypher(
    "MATCH (n:CodeEntity) RETURN n.name AS name, n.type AS type, n.filepath AS filepath LIMIT 25"
)
svc.close()

print(f"Found {len(results)} nodes:\n")
for r in results:
    print(f"  [{r['type']}] {r['name']} @ {r['filepath']}")
