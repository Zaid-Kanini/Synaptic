"""OpenAI LLM integration with system prompt management.

Handles the reasoning layer of the GraphRAG pipeline — takes the
assembled context bundle from the retriever and synthesizes a
structured Markdown answer using GPT-4o / GPT-4o-mini.

Includes:
- A carefully designed system prompt that instructs the LLM to act
  as a Senior Technical Lead.
- Hallucination guardrails (explicit "not found" responses).
- Context-window budgeting via character limits.
"""

from __future__ import annotations

from typing import Any

import structlog
from openai import AzureOpenAI

from synaptic.rag.retriever import ContextBundle, RetrievedNode

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Senior Technical Lead analyzing a codebase. You have been given \
a set of code entities (functions, classes, files) retrieved from a knowledge graph, along with \
their source code and the relationships between them.

Your job is to answer the developer's question using ONLY the provided context. Follow these rules:

1. **Cite your sources**: Always reference the exact file path and line numbers when discussing code.
   Use the format `filepath:start_line-end_line`.

2. **Explain the logic flow**: When multiple functions/classes are involved, explain how they \
   connect — which function calls which, what classes define what methods, and how imports link \
   modules together.

3. **Use the relationship metadata**: The context includes graph relationships like CALLS, DEFINES, \
   and IMPORTS. Use these to explain the architecture and data flow.

4. **Be precise**: Quote relevant code snippets from the provided source when it helps clarify \
   your explanation. Use fenced code blocks with the appropriate language tag.

5. **Structured output**: Organize your answer with Markdown headings, bullet points, and code \
   blocks for readability.

6. **Honesty guardrail**: If the provided context does not contain enough information to answer \
   the question, clearly state: "I could not find sufficient information in the current codebase \
   context to answer this question." Do NOT invent or hallucinate code that is not in the context.

7. **Scope**: Only discuss code that appears in the provided context. Do not speculate about \
   code that might exist elsewhere in the repository.
"""

NO_CONTEXT_RESPONSE = """## No Relevant Code Found

I searched the knowledge graph but could not find any code entities that are \
semantically relevant to your question. This could mean:

- The relevant code has not been ingested into the graph yet.
- The question may need to be rephrased to match the codebase terminology.
- The functionality you're asking about may not exist in the indexed repository.

**Suggestion**: Try rephrasing your question or ensure the repository has been \
fully ingested via the `/graph/ingest` endpoint.
"""


# ------------------------------------------------------------------
# LLM Service
# ------------------------------------------------------------------


class LLMService:
    """Synchronous Azure OpenAI chat-completion wrapper for the RAG pipeline.

    Args:
        api_key: Azure OpenAI API key.
        azure_endpoint: Azure OpenAI endpoint URL.
        deployment: Azure deployment name (e.g. ``gpt-5-mini``).
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens in the completion response.
        api_version: Azure OpenAI API version.
    """

    def __init__(
        self,
        api_key: str,
        azure_endpoint: str,
        deployment: str = "gpt-5-mini",
        temperature: float = 0.2,
        max_tokens: int = 2048,
        api_version: str = "2024-12-01-preview",
    ) -> None:
        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
        self.deployment = deployment
        self.temperature = temperature
        self.max_tokens = max_tokens

    def synthesize(
        self,
        question: str,
        context: ContextBundle,
    ) -> str:
        """Generate an LLM answer from the retrieved context.

        If the context is empty (no vector matches), returns a canned
        "no results" message without calling the API.

        Args:
            question: The developer's natural-language question.
            context: The assembled :class:`ContextBundle` from the retriever.

        Returns:
            A Markdown-formatted answer string.
        """
        if context.is_empty:
            logger.info("llm_skip_empty_context")
            return NO_CONTEXT_RESPONSE

        user_message = self._build_user_message(question, context)

        logger.info(
            "llm_request",
            deployment=self.deployment,
            user_msg_chars=len(user_message),
        )

        response = self._client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=self.max_tokens,
        )

        answer = response.choices[0].message.content or ""

        logger.info(
            "llm_response",
            deployment=self.deployment,
            tokens_prompt=response.usage.prompt_tokens if response.usage else 0,
            tokens_completion=response.usage.completion_tokens if response.usage else 0,
        )

        return answer

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_message(question: str, context: ContextBundle) -> str:
        """Format the user message with question + structured context."""
        parts: list[str] = []

        parts.append(f"## Developer Question\n\n{question}\n")

        # Entry points (primary matches)
        if context.entry_points:
            parts.append("## Primary Matches (Vector Search)\n")
            for node in context.entry_points:
                parts.append(_format_node(node, show_score=True))

        # Graph relationships
        if context.relationships:
            parts.append("## Graph Relationships\n")
            # Deduplicate while preserving order
            seen: set[str] = set()
            for rel in context.relationships:
                if rel not in seen:
                    seen.add(rel)
                    parts.append(f"- {rel}")
            parts.append("")

        # Neighbour nodes (expanded context)
        if context.neighbours:
            parts.append("## Expanded Context (Graph Neighbours)\n")
            for node in context.neighbours:
                parts.append(_format_node(node, show_score=False))

        return "\n".join(parts)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _format_node(node: RetrievedNode, *, show_score: bool) -> str:
    """Format a single node as a Markdown block for the LLM prompt."""
    header = f"### {node.type or 'Entity'}: `{node.name}`"
    if show_score and node.score is not None:
        header += f"  (similarity: {node.score:.3f})"

    lines = [header]

    if node.filepath:
        loc = f"**Location**: `{node.filepath}"
        if node.start_line and node.end_line:
            loc += f":{node.start_line}-{node.end_line}"
        loc += "`"
        lines.append(loc)

    if node.relationship:
        lines.append(f"**Relationship**: {node.relationship}")

    if node.docstring:
        lines.append(f"**Docstring**: {node.docstring}")

    if node.source_code:
        lang = "python"
        if node.filepath:
            if node.filepath.endswith((".js", ".jsx", ".mjs")):
                lang = "javascript"
            elif node.filepath.endswith((".ts", ".tsx")):
                lang = "typescript"
        lines.append(f"\n```{lang}\n{node.source_code}\n```")

    lines.append("")
    return "\n".join(lines)
