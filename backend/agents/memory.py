"""
memory.py — Senso.ai memory layer
Ingest customer signals into Senso KB, search for similar past signals.
Uses @senso-ai/cli — install with: npm install -g @senso-ai/cli
"""

import os
import json
import subprocess
import tempfile
from typing import List
from pydantic import BaseModel
import railtracks as rt


def _run_senso(args: list[str]) -> dict:
    """Run a senso CLI command and return parsed JSON output."""
    env = {**os.environ, "SENSO_API_KEY": os.environ["SENSO_API_KEY"]}
    result = subprocess.run(
        ["senso"] + args + ["--output", "json", "--quiet"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"senso CLI error: {result.stderr or result.stdout}")
    # CLI emits human-readable lines before the JSON — strip them
    stdout = result.stdout
    json_start = stdout.find("{")
    if json_start == -1:
        json_start = stdout.find("[")
    if json_start == -1:
        raise RuntimeError(f"No JSON in senso output: {stdout[:200]}")
    return json.loads(stdout[json_start:])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class IngestInput(BaseModel):
    text: str
    classification: str
    urgency: int
    customer: str
    company: str
    key_phrases: List[str]
    actions_summary: str = "none"


class IngestOutput(BaseModel):
    senso_id: str


class SearchInput(BaseModel):
    key_phrases: List[str]
    classification: str


class SearchOutput(BaseModel):
    frequency: int
    related_signals: List[str]


# ---------------------------------------------------------------------------
# Railtracks nodes
# ---------------------------------------------------------------------------

@rt.function_node
async def ingest_signal(signal: IngestInput) -> IngestOutput:
    """
    Ingest a processed customer signal into the Senso knowledge base.
    Returns the Senso document ID.
    """
    content = (
        f"Customer Signal\n\n"
        f"Customer: {signal.customer} at {signal.company}\n"
        f"Type: {signal.classification}\n"
        f"Urgency: {signal.urgency}/10\n"
        f"Key phrases: {', '.join(signal.key_phrases)}\n"
        f"Actions taken: {signal.actions_summary}\n\n"
        f"Transcript:\n{signal.text[:1000]}"
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="signal_"
        ) as f:
            f.write(content)
            tmp_path = f.name

        result = _run_senso(["ingest", "upload", tmp_path])
        os.unlink(tmp_path)

        results = result.get("results", [])
        senso_id = results[0].get("content_id", "unknown") if results else "unknown"
        return IngestOutput(senso_id=senso_id)
    except Exception as e:
        print(f"[memory] Senso ingest failed ({e}), skipping")
        return IngestOutput(senso_id="senso-unavailable")


@rt.function_node
async def search_memory(query: SearchInput) -> SearchOutput:
    """
    Search Senso KB for signals similar to the given classification and key phrases.
    Returns frequency count and summaries of related past signals.
    """
    search_query = f"{query.classification}: {' '.join(query.key_phrases[:3])}"

    try:
        result = _run_senso(["search", "context", search_query, "--max-results", "10"])
        results = result.get("results", [])
        summaries = [r.get("chunk_text", "")[:200] for r in results]
        return SearchOutput(frequency=len(results), related_signals=summaries)
    except Exception as e:
        print(f"[memory] Senso search failed ({e}), continuing with frequency=0")
        return SearchOutput(frequency=0, related_signals=[])
