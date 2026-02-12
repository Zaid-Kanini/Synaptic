"""Test script for Module 3: GraphRAG Pipeline.

Verifies the full pipeline: question → hybrid retrieval → LLM synthesis.

Usage::

    python test_rag.py

Requires:
    - Neo4j Aura populated (run /graph/ingest first).
    - SYNAPTIC_OPENAI_API_KEY set in .env.
    - Repository on disk at the path used during ingestion.
"""

from __future__ import annotations

import sys
import os

# Ensure project root is on path.
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from synaptic.rag.pipeline import GraphRAGPipeline


def main() -> None:
    repo_path = r"D:\Practice\python\Synapse\test_repo"

    if not os.path.isdir(repo_path):
        print(f"[ERROR] Repository not found: {repo_path}")
        sys.exit(1)

    pipeline = GraphRAGPipeline(repo_root=repo_path)

    questions = [
        "How is user data validated?",
        "What functions handle analytics tracking?",
        "Explain the main entry point of the application.",
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n{'='*70}")
        print(f"Question {i}: {question}")
        print("=" * 70)

        try:
            result = pipeline.query(question)
        except RuntimeError as exc:
            print(f"\n[ERROR] {exc}")
            print("Set SYNAPTIC_OPENAI_API_KEY in your .env file to test LLM synthesis.")
            sys.exit(1)
        except Exception as exc:
            print(f"\n[ERROR] Pipeline failed: {exc}")
            continue

        print(f"\n--- Answer ---\n{result.answer}")

        if result.source_nodes:
            print(f"\n--- Source Nodes ({len(result.source_nodes)}) ---")
            for sn in result.source_nodes:
                loc = f"{sn.filepath}:{sn.start_line}-{sn.end_line}" if sn.filepath else "n/a"
                score = f" (score={sn.score:.3f})" if sn.score else ""
                print(f"  [{sn.type}] {sn.name} @ {loc}{score}")

        if result.relationships:
            print(f"\n--- Relationships ({len(result.relationships)}) ---")
            for rel in result.relationships[:10]:
                print(f"  {rel}")
            if len(result.relationships) > 10:
                print(f"  ... and {len(result.relationships) - 10} more")

        if result.metadata:
            print(f"\n--- Metadata ---")
            for k, v in result.metadata.items():
                print(f"  {k}: {v}")

        # Only run first question to save API credits.
        print("\n[INFO] Stopping after first question to save API credits.")
        print("[INFO] Remove the break to test all questions.")
        break

    print("\n[DONE] GraphRAG pipeline test complete.")


if __name__ == "__main__":
    main()
