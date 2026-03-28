"""
digest.py — CEO digest generator
Pulls recent signals from Senso and generates a structured CEO summary via GPT-4o.
Exposed as GET /digest by main.py.
"""

import os
import json
import subprocess
from datetime import datetime
from openai import OpenAI

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _run_senso(args: list[str]) -> dict:
    env = {**os.environ, "SENSO_API_KEY": os.environ["SENSO_API_KEY"]}
    result = subprocess.run(
        ["senso"] + args + ["--output", "json", "--quiet"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"senso CLI error: {result.stderr or result.stdout}")
    stdout = result.stdout
    json_start = stdout.find("{")
    if json_start == -1:
        json_start = stdout.find("[")
    if json_start == -1:
        raise RuntimeError(f"No JSON in senso output: {stdout[:200]}")
    return json.loads(stdout[json_start:])


DIGEST_SYSTEM_PROMPT = """You are an AI chief of staff generating a daily CEO digest.

Given a set of recent customer signals, produce a structured digest in this exact format:

---
## Signal Agent — CEO Digest
**{date}**

### Summary
2-3 sentence executive summary of the overall customer sentiment and key themes.

### 🔴 Churn Risks ({n})
For each churn risk: "**{customer}** at **{company}** — {one-line reason}"

### 🐛 Top Bugs ({n})
For each bug: "**{summary}** — {n} customer(s), urgency {urgency}/10"

### 💡 Feature Requests ({n})
For each feature: "**{feature}** — {n} customer(s) requesting this"

### 📊 By the Numbers
- Total signals processed: {n}
- Average urgency: {x}/10
- Most affected company: {company}

### ⚡ Recommended Actions
3 bullet points — the most important things engineering/CS should do today.
---

Be concise. No fluff. CEOs read this in 60 seconds."""


def generate_digest() -> dict:
    """
    Pull recent signals from Senso and generate a CEO digest.
    Returns dict with 'markdown' and 'generated_at' keys.
    Called by GET /digest in main.py.
    """
    # Pull signals from Senso — search for all signal types
    chunks = []
    for query in ["BUG customer signal urgency", "CHURN_RISK cancel leaving",
                  "FEATURE_REQUEST wish need integration"]:
        try:
            result = _run_senso(["search", "context", query, "--max-results", "10"])
            chunks.extend(result.get("results", []))
        except Exception as e:
            print(f"[digest] Senso search failed for '{query}': {e}")

    if not chunks:
        return {
            "markdown": "No signals found in memory yet. Process some customer signals first.",
            "generated_at": datetime.utcnow().isoformat(),
        }

    # Deduplicate by chunk text
    seen = set()
    unique_chunks = []
    for c in chunks:
        text = c.get("chunk_text", "")[:300]
        if text not in seen:
            seen.add(text)
            unique_chunks.append(text)

    signals_text = "\n\n---\n\n".join(unique_chunks[:20])

    # Generate digest with GPT-4o
    today = datetime.utcnow().strftime("%B %d, %Y")
    client = _get_client()

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": DIGEST_SYSTEM_PROMPT.replace("{date}", today)},
            {"role": "user", "content": f"Here are the recent customer signals:\n\n{signals_text}"},
        ],
        temperature=0.3,
    )

    markdown = response.choices[0].message.content

    return {
        "markdown": markdown,
        "generated_at": datetime.utcnow().isoformat(),
        "signal_count": len(unique_chunks),
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from dotenv import load_dotenv
    load_dotenv("../.env")

    print("Generating CEO digest...\n")
    result = generate_digest()
    print(result["markdown"])
    print(f"\n[Generated at {result['generated_at']} from {result['signal_count']} signals]")
