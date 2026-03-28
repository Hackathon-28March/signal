"""
gemini_processor.py — Gemini multimodal transcribe + classify in one call.
Replaces the two-step Whisper → GPT-4o flow for audio signals.
For email signals, falls back to GPT-4o classifier directly.

Requires: pip install google-genai
Env var:  GEMINI_API_KEY
"""

import os
import json
import tempfile
import base64
from typing import List
from pydantic import BaseModel
import railtracks as rt

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


SYSTEM_PROMPT = """You are a customer signal classifier for a B2B SaaS company.

Analyze the audio recording or text and return a JSON object with exactly these fields:

{
  "text": "<full transcript or email body>",
  "classification": "<one of: BUG | FEATURE_REQUEST | CHURN_RISK | PRAISE | QUESTION>",
  "urgency": <integer 1-10>,
  "customer": "<customer name if mentioned, else 'Unknown'>",
  "company": "<company name if mentioned, else 'Unknown'>",
  "key_phrases": ["<phrase1>", "<phrase2>", "<phrase3>"],
  "sentiment": "<one of: positive | negative | neutral>"
}

Classification rules:
- BUG: customer reports something broken or not working as expected
- FEATURE_REQUEST: customer asks for something new or different
- CHURN_RISK: customer expresses frustration or mentions cancelling/leaving/switching
- PRAISE: customer expresses satisfaction or positive feedback
- QUESTION: customer needs information or clarification

Urgency rules:
- CHURN_RISK: always 8-10
- BUG crash/blocking/data loss: 8-10
- BUG minor/intermittent: 4-7
- FEATURE_REQUEST: 3-6
- PRAISE/QUESTION: 1-3

Return ONLY valid JSON. No markdown, no explanation."""


class GeminiInput(BaseModel):
    signal_type: str   # "audio" | "email"
    content: str       # base64-encoded audio OR raw email text


class GeminiOutput(BaseModel):
    text: str
    classification: str
    urgency: int
    customer: str
    company: str
    key_phrases: List[str]
    sentiment: str


@rt.function_node
async def gemini_process(input: GeminiInput) -> GeminiOutput:
    """
    Process a customer signal using Gemini multimodal.
    For audio: transcribes AND classifies in a single API call.
    For email: classifies text directly.
    Returns same shape as classifier.py ClassifyOutput.
    """
    from google import genai
    from google.genai import types

    client = _get_client()

    if input.signal_type == "audio":
        # Write audio to temp file and upload to Gemini Files API
        audio_bytes = base64.b64decode(input.content)

        # Detect format from magic bytes
        magic = audio_bytes[:12]
        if magic[:4] == b'RIFF' and magic[8:12] == b'WAVE':
            suffix, mime_type = ".wav", "audio/wav"
        elif magic[:3] == b'ID3' or magic[:2] == b'\xff\xfb':
            suffix, mime_type = ".mp3", "audio/mp3"
        elif magic[4:8] in (b'ftyp', b'moov') or magic[:4] in (b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c'):
            suffix, mime_type = ".m4a", "audio/mp4"
        elif magic[:4] == b'OggS':
            suffix, mime_type = ".ogg", "audio/ogg"
        elif magic[:4] == b'fLaC':
            suffix, mime_type = ".flac", "audio/flac"
        else:
            suffix, mime_type = ".mp3", "audio/mp3"  # fallback

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            uploaded = client.files.upload(
                file=tmp_path,
                config=types.UploadFileConfig(mime_type=mime_type),
            )
            # Wait for file to become ACTIVE
            import time
            for _ in range(20):
                file_info = client.files.get(name=uploaded.name)
                if file_info.state.name == "ACTIVE":
                    break
                time.sleep(1)
            contents = [
                types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime_type),
                types.Part.from_text(text=
                    "Transcribe this customer call recording and classify the signal. " + SYSTEM_PROMPT
                ),
            ]
        finally:
            os.unlink(tmp_path)
    else:
        contents = [
            types.Part.from_text(text=
                f"Classify this customer signal:\n\n{input.content}\n\n{SYSTEM_PROMPT}"
            )
        ]

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )

    raw = response.text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())

    return GeminiOutput(
        text=result.get("text", input.content[:500]),
        classification=result["classification"],
        urgency=int(result["urgency"]),
        customer=result.get("customer", "Unknown"),
        company=result.get("company", "Unknown"),
        key_phrases=result.get("key_phrases", []),
        sentiment=result["sentiment"],
    )


async def process(signal_type: str, content: str) -> GeminiOutput:
    """Convenience wrapper."""
    return await gemini_process(GeminiInput(signal_type=signal_type, content=content))
