"""Smoke test for the refactored Synaptic ingestion API.

Tests:
1. POST /ingest  (standard JSON — lean metadata, no content field)
2. POST /ingest  (NDJSON streaming mode)
3. GET  /node/{node_id}/content  (on-demand content reader)
"""

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"
REPO = "D:/Practice/python/Synapse/test_repo"


def post_json(url: str, body: dict) -> dict:
    """POST JSON and return parsed response."""
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        raise SystemExit(1)


def post_stream(url: str, body: dict) -> list[str]:
    """POST JSON and return raw NDJSON lines."""
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.read().decode().strip().splitlines()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        raise SystemExit(1)


def get_json(url: str) -> dict:
    """GET and return parsed response."""
    req = urllib.request.Request(url, method="GET")
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        raise SystemExit(1)


# ── Test 1: Standard JSON ingest (lean metadata) ────────────────────
print("=" * 60)
print("TEST 1: POST /ingest (standard JSON, lean metadata)")
print("=" * 60)

data = post_json(f"{BASE}/ingest", {"path": REPO})

print(f"Status : {data['status']}")
print(f"Nodes  : {data['total_nodes']}")
print(f"Edges  : {data['total_edges']}")
print()

# Verify no 'content' field in nodes
sample_node = data["graph"]["nodes"][0]
assert "content" not in sample_node, "ERROR: 'content' field still present!"
print("[PASS] No 'content' field in nodes — lean metadata confirmed.")
print()

print("--- Nodes ---")
for n in data["graph"]["nodes"]:
    print(f"  [{n['type']:8s}] {n['id']}  (L{n['start_line']}-{n['end_line']})")

print()
print("--- Edges (first 15) ---")
for e in data["graph"]["edges"][:15]:
    print(f"  [{e['type']:7s}] {e['source_id']}  ->  {e['target_id']}")


# ── Test 2: Streaming NDJSON ingest ─────────────────────────────────
print()
print("=" * 60)
print("TEST 2: POST /ingest (NDJSON streaming)")
print("=" * 60)

lines = post_stream(f"{BASE}/ingest", {"path": REPO, "stream": True})
print(f"Received {len(lines)} NDJSON lines")

nodes_streamed = [json.loads(l) for l in lines if json.loads(l)["_type"] == "node"]
edges_streamed = [json.loads(l) for l in lines if json.loads(l)["_type"] == "edge"]
print(f"  Nodes: {len(nodes_streamed)}, Edges: {len(edges_streamed)}")

assert "content" not in nodes_streamed[0], "ERROR: 'content' in streamed node!"
print("[PASS] Streaming mode works — no content in streamed nodes.")


# ── Test 3: On-demand content reader ────────────────────────────────
print()
print("=" * 60)
print("TEST 3: GET /node/{node_id}/content (on-demand reader)")
print("=" * 60)

# Pick a function node to read
func_nodes = [n for n in data["graph"]["nodes"] if n["type"] == "function"]
if func_nodes:
    target = func_nodes[0]
    node_id = target["id"]
    qs = urllib.parse.urlencode({"repo_root": REPO})
    content_data = get_json(f"{BASE}/node/{node_id}/content?{qs}")

    print(f"Node ID   : {content_data['node_id']}")
    print(f"File      : {content_data['filepath']}")
    print(f"Lines     : {content_data['start_line']}-{content_data['end_line']}")
    print(f"Content   :")
    for line in content_data["content"].splitlines():
        print(f"    {line}")
    print()
    print("[PASS] On-demand content reader works.")
else:
    print("[SKIP] No function nodes found to test content reader.")

print()
print("=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
